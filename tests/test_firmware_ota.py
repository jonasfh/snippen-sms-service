"""Unit tests for firmware/ota.py and OTA boot recovery mechanisms (Issue #129)."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockResponse


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    Path("ota_failed.json").unlink(missing_ok=True)
    Path("ota_pending.json").unlink(missing_ok=True)
    sys.modules.pop("ota", None)
    sys.modules.pop("boot", None)
    sys.modules.pop("main", None)
    yield env
    Path("ota_failed.json").unlink(missing_ok=True)
    Path("ota_pending.json").unlink(missing_ok=True)
    env.uninstall()
    sys.modules.pop("ota", None)
    sys.modules.pop("boot", None)
    sys.modules.pop("main", None)


def create_sample_bundle(
    version: str = "0.32.0",
    files_content: dict[str, str] | None = None,
) -> dict:
    """Helper to generate a valid firmware bundle dictionary with calculated SHA-256."""
    if files_content is None:
        files_content = {
            "main.py": "print('new main 0.32.0')\n",
            "version.py": f'FIRMWARE_VERSION = "{version}"\n',
        }

    files_dict = {}
    total_bytes = 0
    for name, content in files_content.items():
        content_bytes = content.encode("utf-8")
        sha = hashlib.sha256(content_bytes).hexdigest()
        size = len(content_bytes)
        total_bytes += size
        files_dict[name] = {
            "sha256": sha,
            "size": size,
            "content": content,
        }

    return {
        "version": version,
        "tag": f"v{version}",
        "created_at": "2026-10-11T08:00:00Z",
        "total_files": len(files_dict),
        "total_bytes": total_bytes,
        "files": files_dict,
    }


def test_calculate_sha256(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    content = "Hello, OTA update!"
    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert ota.calculate_sha256(content) == expected
    assert ota.calculate_sha256(content.encode("utf-8")) == expected


def test_parse_semver_and_is_newer_version(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    assert ota.parse_semver("0.31.20") == (0, 31, 20)
    assert ota.parse_semver("v1.2.3") == (1, 2, 3)
    assert ota.parse_semver("2.0") == (2, 0, 0)
    assert ota.parse_semver("invalid") == (0, 0, 0)

    assert ota.is_newer_version("0.31.21", "0.31.20") is True
    assert ota.is_newer_version("1.0.0", "0.99.99") is True
    assert ota.is_newer_version("0.31.20", "0.31.20") is False
    assert ota.is_newer_version("0.30.99", "0.31.0") is False


def test_validate_bundle_success(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    bundle = create_sample_bundle("0.32.0")
    valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
    assert valid is True
    assert msg == "Valid"


def test_validate_bundle_rejects_older_version(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    bundle = create_sample_bundle("0.30.0")
    valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
    assert valid is False
    assert "not newer" in msg

    # Allowed with force=True
    valid_forced, msg_forced = ota.validate_bundle(bundle, current_version="0.31.20", force=True)
    assert valid_forced is True
    assert msg_forced == "Valid"


def test_validate_bundle_checksum_mismatch(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    bundle = create_sample_bundle("0.32.0")
    bundle["files"]["main.py"]["sha256"] = (
        "0000000000000000000000000000000000000000000000000000000000000000"
    )

    valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
    assert valid is False
    assert "SHA-256 checksum mismatch" in msg


def test_validate_bundle_size_mismatch(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    bundle = create_sample_bundle("0.32.0")
    bundle["files"]["main.py"]["size"] = 99999

    valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
    assert valid is False
    assert "Size mismatch" in msg


def test_validate_bundle_forbidden_files(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    for forbidden in ["config.json", "config_local.py", "config.local.py", "my_local.py"]:
        bundle = create_sample_bundle(
            "0.32.0",
            files_content={forbidden: "SECRET = True\n"},
        )
        valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
        assert valid is False, f"Expected forbidden rejection for {forbidden}"
        assert "Forbidden" in msg


def test_validate_bundle_path_traversal(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    bundle = create_sample_bundle(
        "0.32.0",
        files_content={"../etc/passwd": "root:x:0:0\n"},
    )
    valid, msg = ota.validate_bundle(bundle, current_version="0.31.20")
    assert valid is False
    assert "Invalid filename" in msg


def test_stage_bundle_success_and_cleanup_on_error(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import ota

    bundle = create_sample_bundle(
        "0.32.0",
        files_content={
            "app.py": "print('app v2')\n",
            "mod.py": "x = 42\n",
        },
    )

    staged = ota.stage_bundle(bundle)
    assert set(staged) == {"app.py.new", "mod.py.new"}
    assert (tmp_path / "app.py.new").read_text() == "print('app v2')\n"
    assert (tmp_path / "mod.py.new").read_text() == "x = 42\n"

    # Test failure during staging triggers automatic cleanup
    def failing_sha(data: str | bytes) -> str:
        return "tampered_hash"

    monkeypatch.setattr(ota, "calculate_sha256", failing_sha)
    with pytest.raises(RuntimeError, match="Post-write flash verification failed"):
        ota.stage_bundle(bundle)

    # Staged files should be cleaned up
    assert not (tmp_path / "app.py.new").exists()


def test_apply_staged_update_atomic_swap(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import ota

    # Existing active files
    (tmp_path / "main.py").write_text("print('old main 0.31')\n")
    (tmp_path / "config.json").write_text('{"my_token": "secret123"}')

    bundle = create_sample_bundle(
        "0.32.0",
        files_content={"main.py": "print('new main 0.32')\n"},
    )

    staged = ota.stage_bundle(bundle)
    assert (tmp_path / "main.py.new").exists()

    success = ota.apply_staged_update(bundle, staged)
    assert success is True

    # Active file updated
    assert (tmp_path / "main.py").read_text() == "print('new main 0.32')\n"
    # Backup file preserved
    assert (tmp_path / "main.py.bak").read_text() == "print('old main 0.31')\n"
    # Staged file moved
    assert not (tmp_path / "main.py.new").exists()
    # Sensitive config file untouched
    assert (tmp_path / "config.json").read_text() == '{"my_token": "secret123"}'

    # Check ota_pending file written
    pending_file = tmp_path / "ota_pending.json"
    assert pending_file.exists()
    pending_data = json.loads(pending_file.read_text())
    assert pending_data["pending"] is True
    assert pending_data["version"] == "0.32.0"
    assert pending_data["boot_attempts"] == 0
    assert "main.py" in pending_data["files"]


def test_confirm_healthy(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import ota

    (tmp_path / "main.py.bak").write_text("print('backup')\n")
    (tmp_path / "ota_pending.json").write_text(
        json.dumps({"pending": True, "files": ["main.py"], "version": "0.32.0"})
    )

    assert ota.is_pending() is True
    res = ota.confirm_healthy()
    assert res is True
    assert not (tmp_path / "main.py.bak").exists()
    assert not (tmp_path / "ota_pending.json").exists()
    assert ota.is_pending() is False


def test_rollback_ota(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import ota

    (tmp_path / "main.py").write_text("broken new main")
    (tmp_path / "main.py.bak").write_text("working old main")
    (tmp_path / "main.py.new").write_text("leftover new")
    (tmp_path / "ota_pending.json").write_text(
        json.dumps({"pending": True, "files": ["main.py"], "version": "0.32.0"})
    )

    res = ota.rollback_ota()
    assert res is True
    assert (tmp_path / "main.py").read_text() == "working old main"
    assert not (tmp_path / "main.py.bak").exists()
    assert not (tmp_path / "main.py.new").exists()
    assert not (tmp_path / "ota_pending.json").exists()


def test_boot_check_and_handle_ota_pending_first_boot(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import boot

    # When no OTA pending, returns False
    assert boot.check_and_handle_ota_pending() is False

    # Simulate fresh OTA staged (boot_attempts = 0)
    pending_file = tmp_path / "ota_pending.json"
    pending_file.write_text(
        json.dumps({"pending": True, "boot_attempts": 0, "max_attempts": 1, "version": "0.32.0"})
    )

    # First boot increments counter
    assert boot.check_and_handle_ota_pending() is True
    updated_data = json.loads(pending_file.read_text())
    assert updated_data["boot_attempts"] == 1


def test_boot_check_and_handle_ota_pending_crash_triggers_rollback(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import boot

    (tmp_path / "main.py").write_text("crashed_firmware()")
    (tmp_path / "main.py.bak").write_text("stable_firmware()")

    # Simulate previous boot attempt reached max_attempts (device crashed / restarted)
    pending_file = tmp_path / "ota_pending.json"
    pending_file.write_text(
        json.dumps(
            {
                "pending": True,
                "boot_attempts": 1,
                "max_attempts": 1,
                "version": "0.32.0",
                "files": ["main.py"],
            }
        )
    )

    # Next boot must detect the failure and trigger rollback
    res = boot.check_and_handle_ota_pending()
    assert res is True
    assert (tmp_path / "main.py").read_text() == "stable_firmware()"
    assert not pending_file.exists()


def test_ota_client_download_with_redirect(mpy_env: MicroPythonEnvironment, tmp_path: Path) -> None:
    import ota

    bundle = create_sample_bundle("0.32.0")

    def mock_get(url: str, headers: dict | None = None, **kwargs: object) -> MockResponse:
        if "github.com" in url:
            # 302 redirect
            return MockResponse(
                status_code=302,
                headers={"Location": "https://objects.githubusercontent.com/dist/bundle.json"},
            )
        return MockResponse(status_code=200, json_data=bundle)

    mpy_env.mock_urequests.get_handler = mock_get

    client = ota.OTAClient(config={"wifi_ssid": "TestWiFi", "wifi_password": "pass"})
    downloaded = client.download_bundle(
        "https://github.com/jonasfh/snippen-sms-service/dist/firmware_bundle.json"
    )
    assert downloaded["version"] == "0.32.0"
    assert "main.py" in downloaded["files"]


def test_ota_client_perform_ota_full_workflow(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import ota

    (tmp_path / "main.py").write_text("old main\n")
    bundle = create_sample_bundle("0.32.0", {"main.py": "new main\n"})

    mpy_env.mock_urequests.get_handler = lambda *args, **kwargs: MockResponse(
        status_code=200, json_data=bundle
    )

    client = ota.OTAClient(config={"wifi_ssid": "TestSSID", "wifi_password": "pwd"})
    success = client.perform_ota(restart=False)
    assert success is True

    # Main file updated
    assert (tmp_path / "main.py").read_text() == "new main\n"
    # Backup created
    assert (tmp_path / "main.py.bak").read_text() == "old main\n"
    # Pending record present
    assert ota.is_pending() is True


def test_main_app_confirms_ota_after_stability(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import main
    import ota

    (tmp_path / "main.py").write_text("new active main")
    (tmp_path / "main.py.bak").write_text("old backup main")
    (tmp_path / "ota_pending.json").write_text(
        json.dumps({"pending": True, "files": ["main.py"], "version": "0.32.0"})
    )

    app = main.GatewayApp(config={"ota_stability_timeout_sec": 10})
    app.ota_boot_time = mpy_env.mock_time.time() - 15  # 15 seconds elapsed (> 10s)

    assert ota.is_pending() is True
    app.tick()
    assert app.ota_verified is True
    assert ota.is_pending() is False
    assert not (tmp_path / "main.py.bak").exists()


def test_main_app_ble_ota_commands(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    import main

    bundle = create_sample_bundle("0.32.0")
    mpy_env.mock_urequests.get_handler = lambda *args, **kwargs: MockResponse(
        status_code=200, json_data=bundle
    )

    app = main.GatewayApp(config={"wifi_ssid": "TestSSID", "wifi_password": "pwd"})

    # CHECK_OTA command
    res_check = app.on_ble_command("CHECK_OTA", {})
    assert res_check["cmd"] == "CHECK_OTA"
    assert res_check["status"] == "ok"
    assert res_check["update_available"] is True
    assert res_check["version"] == "0.32.0"

    # START_OTA command (with restart=False mocked to prevent machine.reset())
    monkeypatch.setattr("machine.reset", MagicMock())
    res_start = app.on_ble_command("START_OTA", {})
    assert res_start["cmd"] == "START_OTA"
    assert res_start["status"] == "ok"


def test_ota_client_resolve_bundle_url(mpy_env: MicroPythonEnvironment) -> None:
    import ota

    client_default = ota.OTAClient(config={})
    assert (
        client_default.resolve_bundle_url()
        == "https://github.com/jonasfh/snippen-sms-service/releases/latest/download/firmware_bundle.json"
    )

    client_custom_repo = ota.OTAClient(config={"ota_repo": "custom/repo"})
    assert (
        client_custom_repo.resolve_bundle_url()
        == "https://github.com/custom/repo/releases/latest/download/firmware_bundle.json"
    )

    client_custom_url = ota.OTAClient(
        config={"ota_bundle_url": "http://192.168.1.50:8080/bundle.json"}
    )
    assert client_custom_url.resolve_bundle_url() == "http://192.168.1.50:8080/bundle.json"

    assert (
        client_default.resolve_bundle_url("http://custom.com/bundle.json")
        == "http://custom.com/bundle.json"
    )


def test_check_for_update_boot_loop_guard(
    mpy_env: MicroPythonEnvironment, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify check_for_update flags update_available=False if version recently failed (Issue #130)."""
    monkeypatch.chdir(tmp_path)
    import ota

    ota.record_failed_version("0.32.0", reason="boot_rollback")

    mpy_env.mock_urequests.get_handler = lambda *args, **kwargs: MockResponse(
        status_code=200, json_data={"tag_name": "v0.32.0"}
    )

    client = ota.OTAClient(config={"wifi_ssid": "TestSSID"})
    res = client.check_for_update()
    assert res["update_available"] is False
    assert "boot-loop guard" in res["message"]

    # force=True overrides
    res_forced = client.check_for_update(force=True)
    assert res_forced["update_available"] is True
