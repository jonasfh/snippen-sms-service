"""Unit tests for GatewayService lifecycle, configuration, and SMS provider integration."""

from __future__ import annotations

import asyncio

from snippen_sms import __version__
from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.models import MessageDirection, MessageStatus
from snippen_sms.providers import InMemorySmsProvider, SendResult, SmsProvider


def test_gateway_config_defaults():
    config = GatewayConfig()
    assert config.service_name == "snippen-sms-service"
    assert config.log_level == "INFO"
    assert config.poll_interval_seconds == 2.0
    assert config.database_path == "data/sms_gateway.db"


def test_gateway_config_from_env(monkeypatch):
    monkeypatch.setenv("SNIPPEN_SMS_SERVICE_NAME", "custom-gateway")
    monkeypatch.setenv("SNIPPEN_SMS_LOG_LEVEL", "debug")
    monkeypatch.setenv("SNIPPEN_SMS_POLL_INTERVAL", "5.5")
    monkeypatch.setenv("SNIPPEN_SMS_DATABASE_PATH", ":memory:")

    config = GatewayConfig.from_env()
    assert config.service_name == "custom-gateway"
    assert config.log_level == "DEBUG"
    assert config.poll_interval_seconds == 5.5
    assert config.database_path == ":memory:"


def test_gateway_start_and_stop():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05, database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        assert not service.is_running
        assert not provider.is_opened
        assert service.uptime_seconds == 0.0

        await service.start()
        assert service.is_running
        assert provider.is_opened
        assert service.uptime_seconds >= 0.0

        status = service.get_status()
        assert status["status"] == "running"
        assert status["service"] == "snippen-sms-service"
        assert status["version"] == __version__
        assert status["provider"] == "InMemorySmsProvider"
        assert status["database_path"] == ":memory:"
        assert status["total_messages"] == 0

        await service.stop()
        assert not service.is_running
        assert not provider.is_opened
        assert service.get_status()["status"] == "stopped"

    asyncio.run(_test())


def test_gateway_send_sms_success():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        message = await service.send_sms(
            recipient="+4791234567",
            body="Booking confirmation #101",
        )

        assert message.id is not None
        assert message.direction == MessageDirection.OUTBOUND
        assert message.recipient == "+4791234567"
        assert message.sender == "snippen-sms-service"
        assert message.body == "Booking confirmation #101"
        assert message.status == MessageStatus.SENT
        assert message.modem_message_id is not None
        assert message.modem_message_id.startswith("mem-")
        assert message.error_message is None

        # Verify DB storage
        stored = service.storage.get_message(message.id)
        assert stored is not None
        assert stored.status == MessageStatus.SENT
        assert stored.modem_message_id == message.modem_message_id

    asyncio.run(_test())


def test_gateway_send_sms_failure():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        provider.simulate_send_failure(True, error_message="Modem network registration rejected")
        service = GatewayService(config=config, provider=provider)

        message = await service.send_sms(
            recipient="+4791234567",
            body="Booking confirmation #102",
        )

        assert message.id is not None
        assert message.status == MessageStatus.FAILED
        assert message.error_message == "Modem network registration rejected"
        assert message.modem_message_id is None

        stored = service.storage.get_message(message.id)
        assert stored is not None
        assert stored.status == MessageStatus.FAILED
        assert stored.error_message == "Modem network registration rejected"

    asyncio.run(_test())


def test_gateway_send_sms_exception():
    async def _test():
        class CrashingProvider(SmsProvider):
            async def send_sms(self, recipient: str, body: str) -> SendResult:
                raise ConnectionResetError("Modem disconnected unexpectedly")

            async def receive_sms(self):
                return []

        config = GatewayConfig(database_path=":memory:")
        service = GatewayService(config=config, provider=CrashingProvider())

        message = await service.send_sms(
            recipient="+4791234567",
            body="Booking confirmation #103",
        )

        assert message.id is not None
        assert message.status == MessageStatus.FAILED
        assert "Modem disconnected unexpectedly" in (message.error_message or "")

        stored = service.storage.get_message(message.id)
        assert stored is not None
        assert stored.status == MessageStatus.FAILED

    asyncio.run(_test())


def test_gateway_poll_incoming_messages():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # Queue simulated inbound messages
        provider.simulate_inbound(
            sender="+4799001122",
            body="CONFIRM",
            provider_message_id="sim-in-1",
        )
        provider.simulate_inbound(
            sender="+4799001133",
            body="CANCEL",
            provider_message_id="sim-in-2",
        )

        ingested = await service.poll_incoming_messages()
        assert len(ingested) == 2

        assert ingested[0].id is not None
        assert ingested[0].direction == MessageDirection.INBOUND
        assert ingested[0].sender == "+4799001122"
        assert ingested[0].body == "CONFIRM"
        assert ingested[0].status == MessageStatus.RECEIVED
        assert ingested[0].modem_message_id == "sim-in-1"

        assert ingested[1].direction == MessageDirection.INBOUND
        assert ingested[1].sender == "+4799001133"
        assert ingested[1].body == "CANCEL"
        assert ingested[1].status == MessageStatus.RECEIVED
        assert ingested[1].modem_message_id == "sim-in-2"

        # Verify DB counts
        assert service.storage.count_messages(direction=MessageDirection.INBOUND) == 2

        # Subsequent poll should find no new messages
        second_poll = await service.poll_incoming_messages()
        assert second_poll == []

    asyncio.run(_test())


def test_gateway_poll_incoming_messages_exception():
    async def _test():
        class CrashingReceiveProvider(SmsProvider):
            async def send_sms(self, recipient: str, body: str) -> SendResult:
                return SendResult(success=True)

            async def receive_sms(self):
                raise OSError("Serial port read failure")

        config = GatewayConfig(database_path=":memory:")
        service = GatewayService(config=config, provider=CrashingReceiveProvider())

        ingested = await service.poll_incoming_messages()
        assert ingested == []

    asyncio.run(_test())


def test_gateway_run_loop_and_graceful_stop():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05, database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # Pre-queue an incoming message before starting loop
        provider.simulate_inbound(sender="+4799999999", body="TICK_TEST")

        task = asyncio.create_task(service.run())

        # Wait briefly for loop to tick and process incoming message
        await asyncio.sleep(0.08)
        assert service.is_running
        assert service.storage.count_messages(direction=MessageDirection.INBOUND) == 1

        # Signal stop
        await service.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert not service.is_running

    asyncio.run(_test())


def test_gateway_run_cancellation():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05, database_path=":memory:")
        service = GatewayService(config)

        task = asyncio.create_task(service.run())

        await asyncio.sleep(0.02)
        assert service.is_running

        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)
        assert not service.is_running

    asyncio.run(_test())
