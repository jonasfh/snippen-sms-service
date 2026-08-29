"""Unit and integration tests for MockSmsProvider and provider factory."""

from __future__ import annotations

import asyncio

import pytest

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.models import MessageDirection, MessageStatus
from snippen_sms.providers import (
    IncomingMessage,
    MockSMSProvider,
    MockSmsProvider,
    SendResult,
    SmsProvider,
    get_provider,
    register_provider,
)
from snippen_sms.storage import MessageStorage


def test_mock_sms_provider_lifecycle():
    async def _test():
        provider = MockSmsProvider()
        assert not provider.is_opened

        await provider.open()
        assert provider.is_opened

        await provider.close()
        assert not provider.is_opened

    asyncio.run(_test())


def test_mock_sms_provider_send_success():
    async def _test():
        provider = MockSmsProvider()
        await provider.open()

        result = await provider.send_sms(recipient="+4791112233", body="Booking #101 confirmed")
        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("mock-")
        assert result.error_message is None

        assert len(provider.sent_messages) == 1
        record = provider.sent_messages[0]
        assert record.recipient == "+4791112233"
        assert record.body == "Booking #101 confirmed"
        assert record.result == result
        assert record.timestamp.tzinfo is not None

    asyncio.run(_test())


def test_mock_sms_provider_send_failure_simulation():
    async def _test():
        provider = MockSmsProvider()
        provider.simulate_send_failure(True, error_message="Network unreachable")

        result = await provider.send_sms(recipient="+4791112233", body="Hello")
        assert result.success is False
        assert result.message_id is None
        assert result.error_message == "Network unreachable"

        assert len(provider.sent_messages) == 1
        assert provider.sent_messages[0].result.success is False

        # Reset failure simulation
        provider.simulate_send_failure(False)
        result_ok = await provider.send_sms(recipient="+4791112233", body="Retry message")
        assert result_ok.success is True
        assert len(provider.sent_messages) == 2

    asyncio.run(_test())


def test_mock_sms_provider_receive_failure_simulation():
    async def _test():
        provider = MockSmsProvider()
        provider.simulate_incoming(sender="+4790000000", body="Test message")
        provider.simulate_receive_failure(True, error_message="Modem busy")

        with pytest.raises(RuntimeError, match="Modem busy"):
            await provider.receive_sms()

        # Reset receive failure
        provider.simulate_receive_failure(False)
        msgs = await provider.receive_sms()
        assert len(msgs) == 1
        assert msgs[0].body == "Test message"

    asyncio.run(_test())


def test_mock_sms_provider_simulate_inbound_and_alias():
    async def _test():
        provider = MockSmsProvider()

        # simulate_inbound
        msg1 = provider.simulate_inbound(
            sender="+4790001111",
            body="First incoming",
            provider_message_id="in-1",
        )
        assert msg1.sender == "+4790001111"
        assert msg1.body == "First incoming"
        assert msg1.provider_message_id == "in-1"

        # simulate_incoming alias
        msg2 = provider.simulate_incoming(
            sender="+4790002222",
            body="Second incoming",
        )
        assert msg2.sender == "+4790002222"
        assert msg2.body == "Second incoming"
        assert msg2.provider_message_id is not None

        # Drain
        messages = await provider.receive_sms()
        assert len(messages) == 2
        assert messages[0] == msg1
        assert messages[1] == msg2

        # Subsequent receive is empty
        assert await provider.receive_sms() == []

    asyncio.run(_test())


def test_mock_sms_provider_auto_reply():
    async def _test():
        provider = MockSmsProvider()
        provider.add_auto_reply(trigger="CONFIRM", reply="Confirmed! Your code is 1234.")

        # Outbound send matching trigger
        result = await provider.send_sms(
            recipient="+4799887766", body="Please CONFIRM your booking"
        )
        assert result.success is True

        # Inbound inbox should now have the simulated auto-reply
        inbound = await provider.receive_sms()
        assert len(inbound) == 1
        assert inbound[0].sender == "+4799887766"
        assert inbound[0].body == "Confirmed! Your code is 1234."

    asyncio.run(_test())


def test_mock_sms_provider_clear():
    async def _test():
        provider = MockSmsProvider()
        await provider.send_sms("+4790000000", "Hello")
        provider.simulate_incoming("+4790000000", "Reply")
        provider.simulate_send_failure(True)
        provider.simulate_receive_failure(True)
        provider.add_auto_reply("HI", "HELLO")

        assert len(provider.sent_messages) == 1
        assert len(provider._inbox) == 1
        assert len(provider._auto_replies) == 1

        provider.clear()

        assert len(provider.sent_messages) == 0
        assert len(provider._inbox) == 0
        assert len(provider._auto_replies) == 0
        assert provider._fail_next_sends is False
        assert provider._fail_next_receives is False

        # Sending after clear should work
        res = await provider.send_sms("+4790000000", "Fresh send")
        assert res.success is True

    asyncio.run(_test())


def test_provider_factory_and_registry():
    # Retrieve built-in mock provider
    mock_p = get_provider("mock")
    assert isinstance(mock_p, MockSmsProvider)

    # Retrieve built-in memory provider
    mem_p = get_provider("memory")
    assert isinstance(mem_p, MockSmsProvider)

    # Retrieve case-insensitive
    mock_upper = get_provider("MOCK")
    assert isinstance(mock_upper, MockSmsProvider)

    # Unknown provider raises ValueError
    with pytest.raises(ValueError, match="Unknown SMS provider 'nonexistent'"):
        get_provider("nonexistent")

    # Custom provider registration
    class CustomProvider(SmsProvider):
        async def send_sms(self, recipient: str, body: str) -> SendResult:
            return SendResult(success=True, message_id="custom-1")

        async def receive_sms(self) -> list[IncomingMessage]:
            return []

    register_provider("custom", CustomProvider)
    custom_inst = get_provider("custom")
    assert isinstance(custom_inst, CustomProvider)


def test_gateway_end_to_end_with_mock_provider(tmp_path):
    async def _test():
        db_file = str(tmp_path / "test_gateway_mock.db")
        config = GatewayConfig(
            service_name="snippen-test-service",
            database_path=db_file,
            provider="mock",
        )
        storage = MessageStorage(db_file)
        mock_provider = MockSmsProvider()

        gateway = GatewayService(config=config, storage=storage, provider=mock_provider)
        await gateway.start()
        assert gateway.is_running
        assert gateway.get_status()["provider"] == "MockSmsProvider"

        # 1. Outbound message sending
        sent_msg = await gateway.send_sms(recipient="+4790000001", body="Welcome to Snippen!")
        assert sent_msg.status == MessageStatus.SENT
        assert sent_msg.direction == MessageDirection.OUTBOUND
        assert sent_msg.modem_message_id is not None
        assert len(mock_provider.sent_messages) == 1

        # 2. Inbound message simulation and ingestion
        mock_provider.simulate_incoming(sender="+4790000001", body="Thank you!")
        polled = await gateway.poll_incoming_messages()
        assert len(polled) == 1
        assert polled[0].sender == "+4790000001"
        assert polled[0].body == "Thank you!"
        assert polled[0].status == MessageStatus.RECEIVED
        assert polled[0].direction == MessageDirection.INBOUND

        # Verify storage count
        assert storage.count_messages() == 2

        await gateway.stop()
        assert not gateway.is_running

    asyncio.run(_test())


def test_mock_sms_provider_class_alias():
    assert MockSMSProvider is MockSmsProvider
