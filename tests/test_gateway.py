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
    assert config.provider == "mock"


def test_gateway_config_from_env(monkeypatch):
    monkeypatch.setenv("SNIPPEN_SMS_SERVICE_NAME", "custom-gateway")
    monkeypatch.setenv("SNIPPEN_SMS_LOG_LEVEL", "debug")
    monkeypatch.setenv("SNIPPEN_SMS_POLL_INTERVAL", "5.5")
    monkeypatch.setenv("SNIPPEN_SMS_DATABASE_PATH", ":memory:")
    monkeypatch.setenv("SNIPPEN_SMS_PROVIDER", "memory")

    config = GatewayConfig.from_env()
    assert config.service_name == "custom-gateway"
    assert config.log_level == "DEBUG"
    assert config.poll_interval_seconds == 5.5
    assert config.database_path == ":memory:"
    assert config.provider == "memory"


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


def test_gateway_default_provider_resolution():
    config = GatewayConfig(database_path=":memory:", provider="mock")
    service = GatewayService(config=config)
    assert service.provider.__class__.__name__ == "MockSmsProvider"

    config_mem = GatewayConfig(database_path=":memory:", provider="memory")
    service_mem = GatewayService(config=config_mem)
    assert service_mem.provider.__class__.__name__ == "InMemorySmsProvider"


def test_gateway_enqueue_and_process_outbox():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # Enqueue 2 messages in outbox without dispatching yet
        msg1 = service.enqueue_outbox(recipient="+4790000001", body="Outbox batch 1")
        msg2 = service.enqueue_outbox(recipient="+4790000002", body="Outbox batch 2")

        assert msg1.status == MessageStatus.PENDING
        assert msg2.status == MessageStatus.PENDING
        assert service.storage.count_outbox(status=MessageStatus.PENDING) == 2

        # Process outbox batch
        processed = await service.process_outbox(limit=10)
        assert len(processed) == 2
        assert processed[0].status == MessageStatus.SENT
        assert processed[0].modem_message_id is not None
        assert processed[1].status == MessageStatus.SENT
        assert processed[1].modem_message_id is not None

        # Verify no pending messages remain
        assert service.storage.count_outbox(status=MessageStatus.PENDING) == 0
        assert len(service.storage.get_pending_outbox()) == 0

    asyncio.run(_test())


def test_gateway_process_outbox_failure_retains_message():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        provider.simulate_send_failure(True, error_message="SIM card busy")
        service = GatewayService(config=config, provider=provider)

        msg = service.enqueue_outbox(recipient="+4790000003", body="Fail test")
        assert msg.id is not None

        processed = await service.process_outbox()
        assert len(processed) == 1
        assert processed[0].status == MessageStatus.FAILED
        assert processed[0].error_message == "SIM card busy"

        # Verify message is retained in storage and not deleted
        stored = service.storage.get_message(msg.id)
        assert stored is not None
        assert stored.status == MessageStatus.FAILED
        assert stored.error_message == "SIM card busy"
        assert service.storage.count_outbox() == 1

    asyncio.run(_test())


def test_gateway_process_outbox_exception_retains_message():
    async def _test():
        class CrashingSendProvider(SmsProvider):
            async def send_sms(self, recipient: str, body: str) -> SendResult:
                raise TimeoutError("AT command timeout")

            async def receive_sms(self):
                return []

        config = GatewayConfig(database_path=":memory:")
        service = GatewayService(config=config, provider=CrashingSendProvider())

        msg = service.enqueue_outbox(recipient="+4790000004", body="Exception test")
        assert msg.id is not None

        processed = await service.process_outbox()
        assert len(processed) == 1
        assert processed[0].status == MessageStatus.FAILED
        assert "AT command timeout" in (processed[0].error_message or "")

        # Verify message is retained in storage
        stored = service.storage.get_message(msg.id)
        assert stored is not None
        assert stored.status == MessageStatus.FAILED

    asyncio.run(_test())


def test_gateway_outbox_survives_restart_and_processes(tmp_path):
    async def _test():
        db_path = str(tmp_path / "restart_test.db")
        config = GatewayConfig(database_path=db_path)

        # Instance 1: Enqueue message to outbox while provider is offline/service not running
        service1 = GatewayService(config=config, provider=InMemorySmsProvider())
        msg = service1.enqueue_outbox(
            recipient="+4791000000",
            body="Message enqueued before restart",
        )
        assert msg.id is not None
        assert msg.status == MessageStatus.PENDING
        service1.storage.close()

        # Instance 2: Gateway service restart
        provider2 = InMemorySmsProvider()
        service2 = GatewayService(config=config, provider=provider2)

        status_before = service2.get_status()
        assert status_before["outbox_pending"] == 1
        assert status_before["outbox_total"] == 1

        # Process outbox on new service instance
        processed = await service2.process_outbox()
        assert len(processed) == 1
        assert processed[0].id == msg.id
        assert processed[0].status == MessageStatus.SENT

        status_after = service2.get_status()
        assert status_after["outbox_pending"] == 0
        assert status_after["outbox_total"] == 1

        service2.storage.close()

    asyncio.run(_test())


def test_gateway_process_inbox_alias():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        provider.simulate_inbound(sender="+4798765432", body="INBOX_TEST")
        service = GatewayService(config=config, provider=provider)

        ingested = await service.process_inbox()
        assert len(ingested) == 1
        assert ingested[0].direction == MessageDirection.INBOUND
        assert ingested[0].sender == "+4798765432"
        assert ingested[0].status == MessageStatus.RECEIVED

        status = service.get_status()
        assert status["inbox_total"] == 1
        assert status["total_messages"] == 1

    asyncio.run(_test())


def test_gateway_run_loop_processes_outbox_and_inbox():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05, database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # Enqueue outbound message and simulate inbound message
        service.enqueue_outbox(recipient="+4799009900", body="OUT_LOOP")
        provider.simulate_inbound(sender="+4799119911", body="IN_LOOP")

        task = asyncio.create_task(service.run())
        await asyncio.sleep(0.08)

        # Both should have been processed
        assert service.storage.count_outbox(status=MessageStatus.SENT) == 1
        assert service.storage.count_inbox() == 1

        await service.stop()
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(_test())


def test_gateway_updater_integration():
    from unittest.mock import patch

    from snippen_sms.updater import ReleaseInfo, UpdateCheckResult

    config = GatewayConfig(
        database_path=":memory:",
        github_repo="test-owner/test-repo",
        check_updates_on_startup=False,
    )
    service = GatewayService(config=config)

    # Initial status
    status = service.get_status()
    assert status["github_repo"] == "test-owner/test-repo"
    assert status["update_available"] is False
    assert status["latest_version"] is None

    mock_check = UpdateCheckResult(
        update_available=True,
        current_version="0.8.0",
        latest_version="0.9.0",
        release_info=ReleaseInfo(
            version="0.9.0",
            tag_name="v0.9.0",
            published_at="",
            wheel_url="https://example.com/wheel.whl",
            tarball_url=None,
            html_url="",
            release_notes="",
        ),
    )

    with patch.object(service.updater, "check_for_update", return_value=mock_check):
        res = service.check_for_updates()

    assert res.update_available is True
    assert res.latest_version == "0.9.0"

    status_updated = service.get_status()
    assert status_updated["update_available"] is True
    assert status_updated["latest_version"] == "0.9.0"


def test_gateway_startup_check_offline_graceful():
    async def _test():
        from unittest.mock import patch

        config = GatewayConfig(
            database_path=":memory:",
            check_updates_on_startup=True,
        )
        service = GatewayService(config=config)

        with patch.object(
            service.updater,
            "check_for_update",
            side_effect=TimeoutError("Network offline"),
        ):
            # start() should catch the error gracefully and not crash
            await service.start()
            assert service.is_running
            await service.stop()

    asyncio.run(_test())


def test_gateway_poll_incoming_deduplication():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # First delivery of message
        provider.simulate_inbound(
            sender="+4791112233",
            body="First delivery",
            provider_message_id="msg-dedup-100",
        )
        first_poll = await service.poll_incoming_messages()
        assert len(first_poll) == 1
        assert first_poll[0].modem_message_id == "msg-dedup-100"
        assert service.storage.count_inbox() == 1

        # Simulate provider re-delivering the exact same provider_message_id
        provider.simulate_inbound(
            sender="+4791112233",
            body="First delivery duplicate",
            provider_message_id="msg-dedup-100",
        )
        second_poll = await service.poll_incoming_messages()
        assert len(second_poll) == 0

        # Total stored inbox count remains 1
        assert service.storage.count_inbox() == 1

        # A new unique message is ingested normally
        provider.simulate_inbound(
            sender="+4791112233",
            body="Second unique message",
            provider_message_id="msg-dedup-200",
        )
        third_poll = await service.poll_incoming_messages()
        assert len(third_poll) == 1
        assert third_poll[0].modem_message_id == "msg-dedup-200"
        assert service.storage.count_inbox() == 2

    asyncio.run(_test())


def test_gateway_temporary_receive_failure_retains_messages():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        # Queue message in provider
        provider.simulate_inbound(
            sender="+4791119999",
            body="Resilience test message",
            provider_message_id="msg-resilient-1",
        )

        # Inject temporary receive failure
        provider.simulate_receive_failure(True, error_message="SIM busy reading buffer")
        failed_poll = await service.poll_incoming_messages()
        assert failed_poll == []
        assert service.storage.count_inbox() == 0

        # Clear temporary failure and retry
        provider.simulate_receive_failure(False)
        recovered_poll = await service.poll_incoming_messages()
        assert len(recovered_poll) == 1
        assert recovered_poll[0].body == "Resilience test message"
        assert recovered_poll[0].modem_message_id == "msg-resilient-1"
        assert service.storage.count_inbox() == 1

    asyncio.run(_test())


def test_gateway_partial_persistence_failure():
    async def _test():
        from snippen_sms.providers.base import IncomingMessage

        class BatchProvider(SmsProvider):
            async def send_sms(self, recipient: str, body: str) -> SendResult:
                return SendResult(success=True)

            async def receive_sms(self):
                return [
                    IncomingMessage(sender="+4791", body="Msg 1", provider_message_id="p-1"),
                    IncomingMessage(sender="+4792", body="Msg 2", provider_message_id="p-2"),
                    IncomingMessage(sender="+4793", body="Msg 3", provider_message_id="p-3"),
                ]

        config = GatewayConfig(database_path=":memory:")
        service = GatewayService(config=config, provider=BatchProvider())

        # Cause an exception on saving msg 2
        original_save = service.storage.save_message

        def mock_save(msg):
            if msg.modem_message_id == "p-2":
                raise sqlite3.OperationalError("Simulated disk error on message 2")
            return original_save(msg)

        import sqlite3

        service.storage.save_message = mock_save

        ingested = await service.poll_incoming_messages()
        # msg 1 and msg 3 should be successfully saved despite msg 2 failure
        assert len(ingested) == 2
        assert ingested[0].modem_message_id == "p-1"
        assert ingested[1].modem_message_id == "p-3"
        assert service.storage.count_inbox() == 2

    asyncio.run(_test())


def test_gateway_unprocessed_inbox_and_mark_processed_helpers():
    async def _test():
        config = GatewayConfig(database_path=":memory:")
        provider = InMemorySmsProvider()
        service = GatewayService(config=config, provider=provider)

        provider.simulate_inbound(sender="+4790001111", body="HELP 1")
        provider.simulate_inbound(sender="+4790002222", body="HELP 2")

        await service.poll_incoming_messages()

        status = service.get_status()
        assert status["inbox_unprocessed"] == 2
        assert status["inbox_total"] == 2

        unprocessed = service.get_unprocessed_inbox()
        assert len(unprocessed) == 2
        assert unprocessed[0].body == "HELP 1"
        assert unprocessed[1].body == "HELP 2"

        # Mark first message as processed
        assert unprocessed[0].id is not None
        updated = service.mark_inbox_processed(unprocessed[0].id)
        assert updated is not None
        assert updated.status == MessageStatus.PROCESSED

        # Check status and remaining unprocessed
        status_after = service.get_status()
        assert status_after["inbox_unprocessed"] == 1
        assert status_after["inbox_total"] == 2

        remaining = service.get_unprocessed_inbox()
        assert len(remaining) == 1
        assert remaining[0].body == "HELP 2"

    asyncio.run(_test())


def test_gateway_mock_provider_auto_reply_flow():
    async def _test():
        from snippen_sms.providers.mock import MockSmsProvider

        config = GatewayConfig(database_path=":memory:")
        mock_provider = MockSmsProvider()
        mock_provider.add_auto_reply(trigger="BOOK", reply="CONFIRMED 456")
        service = GatewayService(config=config, provider=mock_provider)

        # Send outbound SMS that matches auto reply trigger
        sent = await service.send_sms(recipient="+4793334444", body="Please confirm BOOK #123")
        assert sent.status == MessageStatus.SENT

        # Inbound auto-reply should be ready in mock provider
        ingested = await service.poll_incoming_messages()
        assert len(ingested) == 1
        assert ingested[0].sender == "+4793334444"
        assert ingested[0].body == "CONFIRMED 456"
        assert ingested[0].status == MessageStatus.RECEIVED

        unprocessed = service.get_unprocessed_inbox()
        assert len(unprocessed) == 1
        assert unprocessed[0].body == "CONFIRMED 456"

    asyncio.run(_test())
