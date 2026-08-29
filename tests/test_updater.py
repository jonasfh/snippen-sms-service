"""Unit and integration tests for GitHub release version checking and updater."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from snippen_sms.updater import (
    ReleaseInfo,
    SoftwareUpdater,
    UpdateCheckResult,
    is_newer_version,
    parse_semver,
)


def test_parse_semver_valid():
    assert parse_semver("1.2.3") == (1, 2, 3)
    assert parse_semver("v0.8.0") == (0, 8, 0)
    assert parse_semver("V10.20.30-beta1") == (10, 20, 30)


def test_parse_semver_invalid():
    with pytest.raises(ValueError):
        parse_semver("invalid-semver")


def test_is_newer_version():
    assert is_newer_version("0.8.0", "0.7.0") is True
    assert is_newer_version("v1.0.0", "0.9.9") is True
    assert is_newer_version("0.7.0", "0.7.0") is False
    assert is_newer_version("0.6.0", "0.7.0") is False


def test_updater_check_for_update_newer_version():
    mock_payload = {
        "tag_name": "v0.9.0",
        "published_at": "2026-08-30T10:00:00Z",
        "html_url": "https://github.com/jonasfh/snippen-sms-service/releases/tag/v0.9.0",
        "body": "Release notes for 0.9.0",
        "assets": [
            {
                "name": "snippen_sms-0.9.0-py3-none-any.whl",
                "browser_download_url": "https://github.com/jonasfh/snippen-sms-service/releases/download/v0.9.0/snippen_sms-0.9.0-py3-none-any.whl",
            },
            {
                "name": "snippen_sms-0.9.0.tar.gz",
                "browser_download_url": "https://github.com/jonasfh/snippen-sms-service/releases/download/v0.9.0/snippen_sms-0.9.0.tar.gz",
            },
        ],
    }

    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = updater.check_for_update(current_version="0.8.0")

    assert result.update_available is True
    assert result.current_version == "0.8.0"
    assert result.latest_version == "0.9.0"
    assert result.error is None
    assert result.release_info is not None
    assert result.release_info.wheel_url is not None
    assert "snippen_sms-0.9.0-py3-none-any.whl" in result.release_info.wheel_url
    assert result.release_info.release_notes == "Release notes for 0.9.0"

    d = result.to_dict()
    assert d["update_available"] is True
    assert d["latest_version"] == "0.9.0"


def test_updater_check_for_update_same_version():
    mock_payload = {
        "tag_name": "v0.8.0",
        "published_at": "2026-08-29T10:00:00Z",
        "html_url": "https://github.com/jonasfh/snippen-sms-service/releases/tag/v0.8.0",
        "body": "Up to date",
        "assets": [],
    }

    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(mock_payload).encode("utf-8")
    mock_response.__enter__.return_value = mock_response

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = updater.check_for_update(current_version="0.8.0")

    assert result.update_available is False
    assert result.latest_version == "0.8.0"
    assert result.error is None


def test_updater_check_for_update_http_error():
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.HTTPError(
            url="http://test",
            code=404,
            msg="Not Found",
            hdrs={},  # type: ignore[arg-type]
            fp=io.BytesIO(b""),
        ),
    ):
        result = updater.check_for_update(current_version="0.8.0")

    assert result.update_available is False
    assert result.latest_version is None
    assert result.error is not None
    assert "404" in result.error


def test_updater_check_for_update_network_exception():
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        result = updater.check_for_update(current_version="0.8.0")

    assert result.update_available is False
    assert result.error is not None
    assert "timed out" in result.error


def test_updater_download_artifact(tmp_path: Path):
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")
    rel = ReleaseInfo(
        version="0.9.0",
        tag_name="v0.9.0",
        published_at="",
        wheel_url="https://example.com/downloads/snippen_sms-0.9.0-py3-none-any.whl",
        tarball_url=None,
        html_url="",
        release_notes="",
    )

    mock_response = MagicMock()
    mock_response.read.side_effect = [b"MOCK_WHEEL_DATA_CHUNK_1", b"MOCK_WHEEL_DATA_CHUNK_2", b""]
    mock_response.__enter__.return_value = mock_response

    dest_dir = tmp_path / "downloads"
    with patch("urllib.request.urlopen", return_value=mock_response):
        downloaded = updater.download_artifact(rel, dest_dir)

    assert downloaded.exists()
    assert downloaded.name == "snippen_sms-0.9.0-py3-none-any.whl"
    assert downloaded.read_bytes() == b"MOCK_WHEEL_DATA_CHUNK_1MOCK_WHEEL_DATA_CHUNK_2"


def test_updater_download_artifact_no_url():
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")
    rel = ReleaseInfo(
        version="0.9.0",
        tag_name="v0.9.0",
        published_at="",
        wheel_url=None,
        tarball_url=None,
        html_url="",
        release_notes="",
    )

    with pytest.raises(ValueError, match="No downloadable asset"):
        updater.download_artifact(rel, Path("/tmp"))


def test_updater_install_release(tmp_path: Path):
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")
    fake_artifact = tmp_path / "fake.whl"
    fake_artifact.write_bytes(b"dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "Successfully installed"

    with patch("subprocess.run", return_value=mock_proc) as mock_run:
        success = updater.install_release(fake_artifact, database_path=":memory:")

    assert success is True
    assert mock_run.called
    args = mock_run.call_args[0][0]
    assert "pip" in args
    assert "install" in args
    assert str(fake_artifact) in args


def test_updater_install_release_failure(tmp_path: Path):
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")
    fake_artifact = tmp_path / "fake.whl"
    fake_artifact.write_bytes(b"dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "pip error: unsatisfied dependencies"

    with patch("subprocess.run", return_value=mock_proc):
        success = updater.install_release(fake_artifact, database_path=":memory:")

    assert success is False


def test_updater_perform_upgrade_end_to_end(tmp_path: Path):
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    mock_check = UpdateCheckResult(
        update_available=True,
        current_version="0.8.0",
        latest_version="0.9.0",
        release_info=ReleaseInfo(
            version="0.9.0",
            tag_name="v0.9.0",
            published_at="",
            wheel_url="https://example.com/snippen_sms-0.9.0.whl",
            tarball_url=None,
            html_url="",
            release_notes="",
        ),
    )

    fake_file = tmp_path / "snippen_sms-0.9.0.whl"
    fake_file.write_bytes(b"dummy")

    with (
        patch.object(updater, "check_for_update", return_value=mock_check),
        patch.object(updater, "download_artifact", return_value=fake_file),
        patch.object(updater, "install_release", return_value=True),
    ):
        success, msg = updater.perform_upgrade(database_path=":memory:")

    assert success is True
    assert "Successfully upgraded" in msg
    assert "v0.9.0" in msg


def test_updater_perform_upgrade_already_up_to_date():
    updater = SoftwareUpdater(github_repo="test-owner/test-repo")

    mock_check = UpdateCheckResult(
        update_available=False,
        current_version="0.8.0",
        latest_version="0.8.0",
    )

    with patch.object(updater, "check_for_update", return_value=mock_check):
        success, msg = updater.perform_upgrade()

    assert success is True
    assert "already up-to-date" in msg
