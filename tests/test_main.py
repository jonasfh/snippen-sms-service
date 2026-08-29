"""Unit tests for main module."""

from snippen_sms.main import get_status


def test_get_status():
    status = get_status()
    assert status["status"] == "ok"
    assert status["service"] == "snippen-sms-service"
    assert status["version"] == "0.1.0"
