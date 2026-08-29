"""Unit tests for GatewayService lifecycle and configuration."""

import asyncio

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService


def test_gateway_config_defaults():
    config = GatewayConfig()
    assert config.service_name == "snippen-sms-service"
    assert config.log_level == "INFO"
    assert config.poll_interval_seconds == 2.0


def test_gateway_config_from_env(monkeypatch):
    monkeypatch.setenv("SNIPPEN_SMS_SERVICE_NAME", "custom-gateway")
    monkeypatch.setenv("SNIPPEN_SMS_LOG_LEVEL", "debug")
    monkeypatch.setenv("SNIPPEN_SMS_POLL_INTERVAL", "5.5")

    config = GatewayConfig.from_env()
    assert config.service_name == "custom-gateway"
    assert config.log_level == "DEBUG"
    assert config.poll_interval_seconds == 5.5


def test_gateway_start_and_stop():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05)
        service = GatewayService(config)

        assert not service.is_running
        assert service.uptime_seconds == 0.0

        await service.start()
        assert service.is_running
        assert service.uptime_seconds >= 0.0

        status = service.get_status()
        assert status["status"] == "running"
        assert status["service"] == "snippen-sms-service"
        assert status["version"] == "0.2.0"

        await service.stop()
        assert not service.is_running
        assert service.get_status()["status"] == "stopped"

    asyncio.run(_test())


def test_gateway_run_loop_and_graceful_stop():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05)
        service = GatewayService(config)

        task = asyncio.create_task(service.run())

        # Wait briefly for loop to start running
        await asyncio.sleep(0.02)
        assert service.is_running

        # Signal stop
        await service.stop()
        await asyncio.wait_for(task, timeout=1.0)
        assert not service.is_running

    asyncio.run(_test())


def test_gateway_run_cancellation():
    async def _test():
        config = GatewayConfig(poll_interval_seconds=0.05)
        service = GatewayService(config)

        task = asyncio.create_task(service.run())

        await asyncio.sleep(0.02)
        assert service.is_running

        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=1.0)
        assert not service.is_running

    asyncio.run(_test())
