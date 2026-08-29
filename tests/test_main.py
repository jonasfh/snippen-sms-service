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


def test_cli_parser_updater_commands():
    parser = build_parser()

    args_check = parser.parse_args(["check-update", "--repo", "custom/repo"])
    assert args_check.command == "check-update"
    assert args_check.repo == "custom/repo"

    args_update = parser.parse_args(["update", "--force", "--database-path", ":memory:"])
    assert args_update.command == "update"
    assert args_update.force is True
    assert args_update.database_path == ":memory:"


def test_handle_check_update_and_update_cli():
    from unittest.mock import patch

    from snippen_sms.main import handle_check_update, handle_update
    from snippen_sms.updater import UpdateCheckResult

    mock_check_ok = UpdateCheckResult(
        update_available=False,
        current_version="0.8.0",
        latest_version="0.8.0",
    )
    with patch("snippen_sms.updater.SoftwareUpdater.check_for_update", return_value=mock_check_ok):
        exit_code = handle_check_update()
        assert exit_code == 0

    with patch(
        "snippen_sms.updater.SoftwareUpdater.perform_upgrade",
        return_value=(True, "Upgraded successfully"),
    ):
        exit_code = handle_update()
        assert exit_code == 0

    with patch(
        "snippen_sms.updater.SoftwareUpdater.perform_upgrade",
        return_value=(False, "Failed to download"),
    ):
        exit_code = handle_update()
        assert exit_code == 1
