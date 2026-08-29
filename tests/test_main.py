"""Unit tests for main module."""

from snippen_sms.main import get_status, setup_logging


def test_get_status():
    status = get_status()
    assert status["status"] in ("stopped", "running")
    assert status["service"] == "snippen-sms-service"
    assert status["version"] == "0.3.0"


def test_setup_logging():
    setup_logging("DEBUG")
