"""Unit tests for main module."""

from snippen_sms import __version__
from snippen_sms.main import build_parser, get_status, setup_logging


def test_get_status():
    status = get_status()
    assert status["status"] in ("stopped", "running")
    assert status["service"] == "snippen-sms-service"
    assert status["version"] == __version__


def test_setup_logging():
    setup_logging("DEBUG")


def test_cli_parser_defaults():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.poll_interval == 2.0
    assert args.log_level == "INFO"
    assert args.database_path == "data/sms_gateway.db"
    assert args.provider is None


def test_cli_parser_custom_provider():
    parser = build_parser()
    args = parser.parse_args(["--provider", "mock", "--poll-interval", "1.0"])
    assert args.provider == "mock"
    assert args.poll_interval == 1.0

    args_run = parser.parse_args(["run", "--provider", "memory", "--database-path", ":memory:"])
    assert args_run.command == "run"
    assert args_run.provider == "memory"
    assert args_run.database_path == ":memory:"
