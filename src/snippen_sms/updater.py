"""GitHub release version checking and self-update facility."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from snippen_sms import __version__
from snippen_sms.migrations.runner import MigrationRunner

logger = logging.getLogger("snippen_sms.updater")


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parse a semantic version string (e.g. 'v1.2.3' or '1.2.3') into a numeric tuple."""
    cleaned = version_str.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", cleaned)
    if not match:
        raise ValueError(f"Invalid SemVer string: {version_str}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer_version(latest_str: str, current_str: str) -> bool:
    """Return True if latest_str is strictly greater than current_str."""
    try:
        from packaging.version import Version

        return Version(latest_str.lstrip("vV")) > Version(current_str.lstrip("vV"))
    except Exception:  # noqa: BLE001
        # Fallback to tuple comparison
        return parse_semver(latest_str) > parse_semver(current_str)


def calculate_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 hexadecimal hash digest of a file."""
    import hashlib

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def parse_checksums_file(content: str) -> dict[str, str]:
    """Parse a standard sha256sum formatted text into a mapping of filename -> sha256 digest."""
    checksums: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            digest, name = parts[0].strip(), parts[1].strip().lstrip("*")
            checksums[name] = digest.lower()
    return checksums


@dataclass
class ReleaseInfo:
    """Metadata about a GitHub release."""

    version: str
    tag_name: str
    published_at: str = ""
    wheel_url: str | None = None
    tarball_url: str | None = None
    checksums_url: str | None = None
    html_url: str = ""
    release_notes: str = ""


@dataclass
class UpdateCheckResult:
    """Outcome of checking for available updates."""

    update_available: bool
    current_version: str
    latest_version: str | None
    release_info: ReleaseInfo | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "update_available": self.update_available,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "error": self.error,
            "tag_name": self.release_info.tag_name if self.release_info else None,
            "html_url": self.release_info.html_url if self.release_info else None,
        }


class SoftwareUpdater:
    """Manages version checking and package upgrades from GitHub Releases."""

    def __init__(
        self,
        github_repo: str = "jonasfh/snippen-sms-service",
        github_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.github_repo = github_repo.strip()
        self.github_token = github_token
        self.timeout_seconds = timeout_seconds

    def check_for_update(self, current_version: str | None = None) -> UpdateCheckResult:
        """Query GitHub Releases API and determine if a newer version is published."""
        curr_ver = current_version or __version__
        api_url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"snippen-sms-service/{curr_ver}",
        }
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"

        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                if response.status != 200:
                    err_msg = f"GitHub API returned status code {response.status}"
                    logger.warning("Version check failed: %s", err_msg)
                    return UpdateCheckResult(
                        update_available=False,
                        current_version=curr_ver,
                        latest_version=None,
                        error=err_msg,
                    )

                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug(
                    "No published GitHub releases found for %s (HTTP 404).",
                    self.github_repo,
                )
                return UpdateCheckResult(
                    update_available=False,
                    current_version=curr_ver,
                    latest_version=None,
                    error=None,
                )
            err_msg = f"GitHub API HTTP error: {exc.code} {exc.reason}"
            logger.warning("Version check failed: %s", err_msg)
            return UpdateCheckResult(
                update_available=False,
                current_version=curr_ver,
                latest_version=None,
                error=err_msg,
            )
        except Exception as exc:  # noqa: BLE001
            err_msg = f"Failed to check GitHub releases: {exc}"
            logger.debug("Version check exception: %s", exc)
            return UpdateCheckResult(
                update_available=False,
                current_version=curr_ver,
                latest_version=None,
                error=err_msg,
            )

        tag_name = data.get("tag_name", "")
        latest_version = tag_name.lstrip("vV")
        published_at = data.get("published_at", "")
        html_url = data.get("html_url", "")
        release_notes = data.get("body", "")

        # Look for wheel (.whl), tarball (.tar.gz), and checksums assets
        wheel_url: str | None = None
        tarball_url: str | None = data.get("tarball_url")
        checksums_url: str | None = None

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            download_url = asset.get("browser_download_url")
            if name.endswith(".whl") and download_url:
                wheel_url = download_url
            elif name.endswith(".tar.gz") and download_url:
                tarball_url = download_url
            elif name in ("checksums.txt", "SHA256SUMS", "sha256sums.txt") and download_url:
                checksums_url = download_url

        release_info = ReleaseInfo(
            version=latest_version,
            tag_name=tag_name,
            published_at=published_at,
            wheel_url=wheel_url,
            tarball_url=tarball_url,
            checksums_url=checksums_url,
            html_url=html_url,
            release_notes=release_notes,
        )

        try:
            update_available = is_newer_version(latest_version, curr_ver)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to compare versions '%s' and '%s': %s", latest_version, curr_ver, exc
            )
            return UpdateCheckResult(
                update_available=False,
                current_version=curr_ver,
                latest_version=latest_version,
                release_info=release_info,
                error=f"Version comparison error: {exc}",
            )

        return UpdateCheckResult(
            update_available=update_available,
            current_version=curr_ver,
            latest_version=latest_version,
            release_info=release_info,
            error=None,
        )

    def download_artifact(self, release_info: ReleaseInfo, dest_dir: Path) -> Path:
        """Download release asset (wheel preferred, then tarball) to destination directory and verify checksum."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        download_url = release_info.wheel_url or release_info.tarball_url

        if not download_url:
            raise ValueError(f"No downloadable asset found for release {release_info.tag_name}")

        parsed_url = urlparse(download_url)
        filename = Path(parsed_url.path).name or f"snippen_sms-{release_info.version}.whl"
        dest_file = dest_dir / filename

        logger.info("Downloading release artifact from %s to %s...", download_url, dest_file)
        headers = {"User-Agent": f"snippen-sms-service/{__version__}"}
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"

        req = urllib.request.Request(download_url, headers=headers)
        with urllib.request.urlopen(req, timeout=60.0) as response, open(dest_file, "wb") as out_f:
            while chunk := response.read(65536):
                out_f.write(chunk)

        logger.info("Downloaded %d bytes to %s", dest_file.stat().st_size, dest_file)

        # Verify SHA-256 checksum if available
        if release_info.checksums_url:
            try:
                logger.info("Fetching release checksums from %s...", release_info.checksums_url)
                chk_req = urllib.request.Request(release_info.checksums_url, headers=headers)
                with urllib.request.urlopen(chk_req, timeout=30.0) as chk_resp:
                    chk_content = chk_resp.read().decode("utf-8")
                checksums_map = parse_checksums_file(chk_content)

                if dest_file.name in checksums_map:
                    expected_sha = checksums_map[dest_file.name]
                    actual_sha = calculate_sha256(dest_file)
                    if actual_sha != expected_sha:
                        raise ValueError(
                            f"SHA-256 digest mismatch for {dest_file.name}: "
                            f"expected {expected_sha}, calculated {actual_sha}"
                        )
                    logger.info("SHA-256 checksum verified successfully for %s", dest_file.name)
                else:
                    logger.warning("Artifact %s not found in checksums.txt", dest_file.name)
            except Exception as exc:
                if isinstance(exc, ValueError):
                    raise
                logger.warning(
                    "Could not verify checksum against %s: %s", release_info.checksums_url, exc
                )

        return dest_file

    def install_release(
        self, artifact_path: Path, database_path: str = "data/sms_gateway.db"
    ) -> bool:
        """Install package artifact via pip and execute database migrations."""
        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact does not exist at {artifact_path}")

        logger.info("Installing package artifact via pip: %s...", artifact_path)
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--no-cache-dir",
            str(artifact_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("pip install failed (exit %d):\n%s", result.returncode, result.stderr)
            return False

        logger.info("Successfully installed %s via pip.", artifact_path.name)

        # Run database migrations if any exist
        try:
            with MigrationRunner(database_path) as runner:
                applied = runner.run_migrations()
                if applied:
                    logger.info("Applied %d new database migration(s) post-upgrade.", len(applied))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Post-upgrade database migration check encountered issue: %s", exc)

        return True

    def perform_upgrade(
        self,
        force: bool = False,
        database_path: str = "data/sms_gateway.db",
    ) -> tuple[bool, str]:
        """Perform end-to-end version check, download, and installation.

        Returns (success: bool, message: str).
        """
        check = self.check_for_update()
        if check.error:
            return False, f"Check for updates failed: {check.error}"

        if not check.update_available and not force:
            return True, f"Service is already up-to-date at version {check.current_version}."

        if not check.release_info:
            return False, "No release metadata available for upgrade."

        with tempfile.TemporaryDirectory(prefix="snippen_upgrade_") as temp_dir:
            temp_path = Path(temp_dir)
            try:
                artifact = self.download_artifact(check.release_info, temp_path)
            except Exception as exc:  # noqa: BLE001
                return False, f"Failed to download release artifact: {exc}"

            success = self.install_release(artifact, database_path=database_path)
            if not success:
                return False, f"Installation of release {check.release_info.tag_name} failed."

            return (
                True,
                f"Successfully upgraded from v{check.current_version} to {check.release_info.tag_name}.",
            )
