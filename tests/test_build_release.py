import hashlib
import json
import re
import sys
from pathlib import Path

# Add scripts directory to path to import build_release module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from build_release import (
    build_firmware_bundle,
    calculate_sha256,
    generate_checksums,
    is_production_firmware_file,
    resolve_version,
)


def test_calculate_sha256(tmp_path: Path):
    test_file = tmp_path / "test.whl"
    content = b"sample wheel content for hashing"
    test_file.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert calculate_sha256(test_file) == expected


def test_resolve_version(tmp_path: Path):
    # From firmware/version.py
    fw_dir = tmp_path / "firmware"
    fw_dir.mkdir()
    (fw_dir / "version.py").write_text('FIRMWARE_VERSION = "0.42.0"\n', encoding="utf-8")
    assert resolve_version(repo_root=tmp_path) == "0.42.0"

    # Fallback to 0.0.0 if not found
    empty_path = tmp_path / "empty"
    empty_path.mkdir()
    assert resolve_version(repo_root=empty_path) == "0.0.0"


def test_is_production_firmware_file(tmp_path: Path):
    # Production files
    for prod_name in [
        "boot.py",
        "main.py",
        "modem.py",
        "wifi.py",
        "ble_config.py",
        "button.py",
        "config.py",
        "logger.py",
        "sms_encoding.py",
        "snippen_api.py",
        "version.py",
    ]:
        file_path = tmp_path / prod_name
        file_path.write_text("# production code", encoding="utf-8")
        assert is_production_firmware_file(file_path) is True

    # Sensitive or local files
    for sensitive_name in [
        "config.json",
        "config_local.py",
        "config.local.py",
        "settings_local.py",
        "local_debug.py",
    ]:
        file_path = tmp_path / sensitive_name
        file_path.write_text("{}", encoding="utf-8")
        assert is_production_firmware_file(file_path) is False

    # Diagnostic and test scripts
    for test_name in [
        "test_api.py",
        "test_ble_provisioning.py",
        "test_button.py",
        "test_modem.py",
        "test_wifi.py",
        "driver_test.py",
    ]:
        file_path = tmp_path / test_name
        file_path.write_text("# test code", encoding="utf-8")
        assert is_production_firmware_file(file_path) is False

    # Example templates, hidden, and non-py files
    for other_name in [
        "config.example.py",
        "wifi.example.py",
        ".env",
        ".DS_Store",
        "readme.md",
        "firmware.bin",
    ]:
        file_path = tmp_path / other_name
        file_path.write_text("test", encoding="utf-8")
        assert is_production_firmware_file(file_path) is False

    # Subdirectories
    subdir = tmp_path / "__pycache__"
    subdir.mkdir()
    assert is_production_firmware_file(subdir) is False


def test_build_firmware_bundle_mock(tmp_path: Path):
    fw_dir = tmp_path / "firmware"
    fw_dir.mkdir()
    dist_dir = tmp_path / "dist"

    # Add valid production files
    (fw_dir / "boot.py").write_text("print('boot')\n", encoding="utf-8")
    (fw_dir / "main.py").write_text("print('main')\n", encoding="utf-8")
    (fw_dir / "version.py").write_text('FIRMWARE_VERSION = "0.9.0"\n', encoding="utf-8")

    # Add sensitive, test, and template files that must be excluded
    (fw_dir / "config.json").write_text('{"token": "secret"}', encoding="utf-8")
    (fw_dir / "config_local.py").write_text('API_KEY = "sensitive"', encoding="utf-8")
    (fw_dir / "config.example.py").write_text('API_KEY = "example"', encoding="utf-8")
    (fw_dir / "test_api.py").write_text("assert True", encoding="utf-8")

    bundle_path = build_firmware_bundle(
        firmware_dir=fw_dir,
        dist_dir=dist_dir,
        version="0.9.0",
        tag="v0.9.0",
    )

    assert bundle_path.exists()
    assert bundle_path.name == "firmware_bundle.json"

    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert data["version"] == "0.9.0"
    assert data["tag"] == "v0.9.0"
    assert "created_at" in data
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", data["created_at"])
    assert data["total_files"] == 3
    assert data["total_bytes"] == len("print('boot')\n") + len("print('main')\n") + len(
        'FIRMWARE_VERSION = "0.9.0"\n'
    )

    files = data["files"]
    assert set(files.keys()) == {"boot.py", "main.py", "version.py"}

    # Excluded files must never be present
    assert "config.json" not in files
    assert "config_local.py" not in files
    assert "config.example.py" not in files
    assert "test_api.py" not in files

    # Verify per-file checksums and contents
    for filename in ["boot.py", "main.py", "version.py"]:
        orig_bytes = (fw_dir / filename).read_bytes()
        expected_sha = hashlib.sha256(orig_bytes).hexdigest()
        assert files[filename]["sha256"] == expected_sha
        assert files[filename]["size"] == len(orig_bytes)
        assert files[filename]["content"] == orig_bytes.decode("utf-8")


def test_build_firmware_bundle_real_firmware(tmp_path: Path):
    repo_root = Path(__file__).resolve().parent.parent
    fw_dir = repo_root / "firmware"
    dist_dir = tmp_path / "dist"

    bundle_path = build_firmware_bundle(firmware_dir=fw_dir, dist_dir=dist_dir)
    assert bundle_path.exists()

    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    files = data["files"]

    expected_prod_files = {
        "ble_config.py",
        "boot.py",
        "button.py",
        "config.py",
        "logger.py",
        "main.py",
        "modem.py",
        "sms_encoding.py",
        "snippen_api.py",
        "version.py",
        "wifi.py",
    }
    assert set(files.keys()) == expected_prod_files

    # Ensure sensitive and test files from repo firmware directory were excluded
    for excluded in [
        "config.json",
        "config_local.py",
        "config.example.py",
        "test_api.py",
        "test_ble_provisioning.py",
        "test_button.py",
        "test_modem.py",
        "test_wifi.py",
    ]:
        assert excluded not in files

    # ESP32 resource and memory safety validation
    # Raw source size should comfortably fit within ESP32 SPI flash and OTA staging limits (< 300 KB)
    assert data["total_bytes"] < 300_000, (
        f"Raw firmware size ({data['total_bytes']} bytes) too large for ESP32"
    )

    # Total JSON bundle size should be manageable for streaming OTA over HTTPS (< 500 KB)
    bundle_size = bundle_path.stat().st_size
    assert bundle_size < 500_000, (
        f"Firmware bundle JSON ({bundle_size} bytes) too large for ESP32 OTA"
    )

    # No single file should exceed 80 KB to prevent excessive RAM buffering on MicroPython
    for filename, info in files.items():
        assert info["size"] < 80_000, (
            f"File {filename} ({info['size']} bytes) exceeds single-file RAM buffer limit"
        )


def test_build_firmware_bundle_errors(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist"
    try:
        build_firmware_bundle(firmware_dir=non_existent, dist_dir=tmp_path / "dist")
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError:
        pass

    empty_dir = tmp_path / "empty_fw"
    empty_dir.mkdir()
    try:
        build_firmware_bundle(firmware_dir=empty_dir, dist_dir=tmp_path / "dist")
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_generate_checksums(tmp_path: Path):
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()

    file1 = dist_dir / "pkg-1.0.whl"
    file1.write_bytes(b"content 1")
    file2 = dist_dir / "pkg-1.0.tar.gz"
    file2.write_bytes(b"content 2")
    file3 = dist_dir / "firmware_bundle.json"
    file3.write_bytes(b'{"version": "1.0"}')

    checksums_file = generate_checksums(dist_dir=dist_dir)
    assert checksums_file.exists()

    content = checksums_file.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert len(lines) == 3

    assert f"{hashlib.sha256(b'content 1').hexdigest()}  pkg-1.0.whl" in lines
    assert f"{hashlib.sha256(b'content 2').hexdigest()}  pkg-1.0.tar.gz" in lines
    assert f"{hashlib.sha256(b'{"version": "1.0"}').hexdigest()}  firmware_bundle.json" in lines
