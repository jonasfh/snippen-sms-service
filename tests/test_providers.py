"""Unit tests for SMS provider abstraction and InMemorySmsProvider."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from snippen_sms.providers import IncomingMessage, InMemorySmsProvider, SendResult, SmsProvider


def test_send_result_structure():
    res_success = SendResult(success=True, message_id="modem-123")
    assert res_success.success is True
    assert res_success.message_id == "modem-123"
    assert res_success.error_message is None

    res_fail = SendResult(success=False, error_message="Network error")
    assert res_fail.success is False
    assert res_fail.message_id is None
    assert res_fail.error_message == "Network error"


def test_incoming_message_structure():
    msg = IncomingMessage(
        sender="+4790000000",
        body="Hello world",
    )
    assert msg.sender == "+4790000000"
    assert msg.body == "Hello world"
    assert msg.received_at.tzinfo is not None
    assert msg.provider_message_id is None

    # Test timezone normalization with naive datetime
    naive_dt = datetime(2026, 8, 29, 12, 0, 0, tzinfo=None)  # noqa: DTZ001
    msg_naive = IncomingMessage(
        sender="+4790000000",
        body="Test",
        received_at=naive_dt,
        provider_message_id="prov-1",
    )
    assert msg_naive.received_at.tzinfo == UTC
    assert msg_naive.provider_message_id == "prov-1"


def test_sms_provider_abstract_instantiation():
    class IncompleteProvider(SmsProvider):
        pass

    with pytest.raises(TypeError):
        IncompleteProvider()  # type: ignore[abstract]


def test_in_memory_provider_lifecycle():
    async def _test():
        provider = InMemorySmsProvider()
        assert not provider.is_opened

        await provider.open()
        assert provider.is_opened

        await provider.close()
        assert not provider.is_opened

    asyncio.run(_test())


def test_in_memory_provider_send_success():
    async def _test():
        provider = InMemorySmsProvider()
        await provider.open()

        result = await provider.send_sms(recipient="+4791112233", body="Order confirmed")
        assert result.success is True
        assert result.message_id is not None
        assert result.message_id.startswith("mem-")
        assert result.error_message is None

        assert len(provider.sent_messages) == 1
        record = provider.sent_messages[0]
        assert record.recipient == "+4791112233"
        assert record.body == "Order confirmed"
        assert record.result == result

    asyncio.run(_test())


def test_in_memory_provider_send_failure_simulation():
    async def _test():
        provider = InMemorySmsProvider()
        provider.simulate_send_failure(True, error_message="SIM card busy")

        result = await provider.send_sms(recipient="+4791112233", body="Test message")
        assert result.success is False
        assert result.message_id is None
        assert result.error_message == "SIM card busy"

        assert len(provider.sent_messages) == 1
        assert provider.sent_messages[0].result.success is False

        # Reset failure simulation
        provider.simulate_send_failure(False)
        result_ok = await provider.send_sms(recipient="+4791112233", body="Test message 2")
        assert result_ok.success is True
        assert len(provider.sent_messages) == 2

    asyncio.run(_test())


def test_in_memory_provider_inbound_simulation_and_drain():
    async def _test():
        provider = InMemorySmsProvider()

        # Initially empty
        received = await provider.receive_sms()
        assert received == []

        # Simulate inbound messages
        inbound1 = provider.simulate_inbound(sender="+4799887766", body="YES")
        inbound2 = provider.simulate_inbound(
            sender="+4799887767",
            body="NO",
            provider_message_id="custom-inbound-id",
        )

        assert inbound1.sender == "+4799887766"
        assert inbound1.body == "YES"
        assert inbound2.provider_message_id == "custom-inbound-id"

        # Drain messages
        drained = await provider.receive_sms()
        assert len(drained) == 2
        assert drained[0].sender == "+4799887766"
        assert drained[0].body == "YES"
        assert drained[1].sender == "+4799887767"
        assert drained[1].body == "NO"

        # Subsequent receive call should be empty
        drained_again = await provider.receive_sms()
        assert drained_again == []

    asyncio.run(_test())


def test_in_memory_provider_clear():
    async def _test():
        provider = InMemorySmsProvider()
        await provider.send_sms("+4790000000", "Msg 1")
        provider.simulate_inbound("+4790000000", "Inbound 1")
        provider.simulate_send_failure(True)

        assert len(provider.sent_messages) == 1
        assert len(provider._inbox) == 1
        assert provider._fail_next_sends is True

        provider.clear()

        assert len(provider.sent_messages) == 0
        assert len(provider._inbox) == 0
        assert provider._fail_next_sends is False

        # Sending after clear should succeed
        res = await provider.send_sms("+4790000000", "Msg 2")
        assert res.success is True

    asyncio.run(_test())


def test_provider_registry_http_and_fake():
    from snippen_sms.providers import HttpSmsProvider, get_provider

    prov_http = get_provider("http", base_url="http://localhost:3000")
    assert isinstance(prov_http, HttpSmsProvider)
    assert prov_http.base_url == "http://localhost:3000"

    prov_fake = get_provider("fake", base_url="http://fake-host:8080")
    assert isinstance(prov_fake, HttpSmsProvider)
    assert prov_fake.base_url == "http://fake-host:8080"

    prov_testing = get_provider("snippen-testing")
    assert isinstance(prov_testing, HttpSmsProvider)
    assert prov_testing.base_url == "http://127.0.0.1:3000"

    with pytest.raises(ValueError, match="Unknown SMS provider 'unknown_provider'"):
        get_provider("unknown_provider")
