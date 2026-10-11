"""MicroPython OTA update engine for Lilygo T-Call ESP32 (Issue #129).

Downloads firmware_bundle.json over Wi-Fi, validates SHA-256 checksums,
stages updates as <file>.new, backs up existing files as <file>.bak,
atomically activates new files, and manages boot-recovery / rollback.
"""

try:
    import ujson as json
except ImportError:
    import json

try:
    import utime as time
except ImportError:
    import time

try:
    import uos as os
except ImportError:
    import os

try:
    import uhashlib as hashlib
except ImportError:
    import hashlib

try:
    import ubinascii as binascii
except ImportError:
    import binascii

try:
    import gc
except ImportError:
    gc = None

try:
    import machine
except ImportError:
    machine = None

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None

try:
    import wifi
except ImportError:
    wifi = None

try:
    from config import load_config
except ImportError:

    def load_config():
        return {}


try:
    from version import FIRMWARE_VERSION
except ImportError:
    FIRMWARE_VERSION = "0.0.0"


# Files that must never be created, overwritten, or modified via OTA
FORBIDDEN_FILES = {
    "config.json",
    "config_local.py",
    "config.local.py",
}

OTA_PENDING_FILE = "ota_pending.json"


def calculate_sha256(data: bytes | str) -> str:
    """Compute SHA-256 hex digest of data."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.sha256()
    h.update(data)
    digest = h.digest()
    if hasattr(binascii, "hexlify"):
        return binascii.hexlify(digest).decode("utf-8")
    return "".join(f"{b:02x}" for b in digest)


def parse_semver(version_str: str) -> tuple[int, int, int]:
    """Parse version string (e.g. '0.31.20' or 'v0.31.20') into (major, minor, patch) tuple."""
    cleaned = version_str.strip().lstrip("vV")
    parts = cleaned.split(".")
    nums = []
    for part in parts:
        num_str = ""
        for ch in part:
            if ch.isdigit():
                num_str += ch
            else:
                break
        nums.append(int(num_str) if num_str else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def is_newer_version(latest_str: str, current_str: str) -> bool:
    """Return True if latest_str is strictly newer than current_str."""
    return parse_semver(latest_str) > parse_semver(current_str)


def copy_file(src: str, dst: str) -> None:
    """Copy file from src to dst in 512-byte blocks."""
    with open(src, "rb") as f_in, open(dst, "wb") as f_out:
        while True:
            chunk = f_in.read(512)
            if not chunk:
                break
            f_out.write(chunk)


def is_pending() -> bool:
    """Check if an OTA update is pending health confirmation."""
    try:
        with open(OTA_PENDING_FILE, "r") as f:
            data = json.load(f)
            return bool(isinstance(data, dict) and data.get("pending"))
    except Exception:  # noqa: BLE001
        return False


def get_ota_status() -> dict:
    """Return current OTA pending metadata or empty status dict."""
    try:
        with open(OTA_PENDING_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:  # noqa: BLE001, S110
        pass
    return {"pending": False}


def confirm_healthy() -> bool:
    """Purge .bak backup files and clear ota_pending flag after stable boot."""
    status = get_ota_status()
    if not status.get("pending"):
        return False

    files = status.get("files", [])
    if not files:
        try:
            files = [f[:-4] for f in os.listdir() if f.endswith(".bak")]
        except Exception:  # noqa: BLE001
            files = []

    purged = 0
    for filename in files:
        bak_file = f"{filename}.bak"
        try:
            os.remove(bak_file)
            purged += 1
        except Exception:  # noqa: BLE001, S110
            pass

    try:
        os.remove(OTA_PENDING_FILE)
    except Exception:  # noqa: BLE001, S110
        pass

    target_ver = status.get("version", "unknown")
    print(f"[ota] Firmware v{target_ver} verified healthy. Removed {purged} backup files.")
    return True


def rollback_ota(status: dict | None = None) -> bool:
    """Restore all active files from their .bak backups."""
    if status is None:
        status = get_ota_status()

    files = status.get("files", [])
    if not files:
        try:
            files = [f[:-4] for f in os.listdir() if f.endswith(".bak")]
        except Exception:  # noqa: BLE001
            files = []

    restored = 0
    for filename in files:
        bak_file = f"{filename}.bak"
        new_file = f"{filename}.new"

        try:
            os.remove(new_file)
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            os.stat(bak_file)
            try:
                os.remove(filename)
            except Exception:  # noqa: BLE001, S110
                pass
            os.rename(bak_file, filename)
            restored += 1
            print(f"[ota] Restored {filename} from {bak_file}")
        except Exception as exc:  # noqa: BLE001
            print(f"[ota] Warning: Could not restore {filename}: {exc}")

    try:
        os.remove(OTA_PENDING_FILE)
    except Exception:  # noqa: BLE001, S110
        pass

    print(f"[ota] Rollback completed. Restored {restored} files.")
    return True


def validate_bundle(
    bundle: dict, current_version: str | None = None, force: bool = False
) -> tuple[bool, str]:
    """Validate structure, version, file paths, and in-memory SHA-256 checksums."""
    if not isinstance(bundle, dict):
        return False, "Bundle is not a valid JSON object"

    new_version = bundle.get("version")
    if not new_version or not isinstance(new_version, str):
        return False, "Bundle missing valid version string"

    curr_version = current_version or FIRMWARE_VERSION
    if not force and not is_newer_version(new_version, curr_version):
        return (
            False,
            f"Bundle version {new_version} is not newer than current {curr_version}",
        )

    files = bundle.get("files")
    if not isinstance(files, dict) or not files:
        return False, "Bundle contains no files"

    for filename, file_info in files.items():
        if not isinstance(filename, str) or not isinstance(file_info, dict):
            return False, f"Invalid entry for file: {filename}"

        lower_name = filename.lower()
        if (
            filename in FORBIDDEN_FILES
            or "config_local" in lower_name
            or lower_name.endswith("local.py")
        ):
            return False, f"Forbidden sensitive configuration file in bundle: {filename}"

        if "/" in filename or "\\" in filename or ".." in filename:
            return False, f"Invalid filename with path traversal characters: {filename}"

        if "content" not in file_info or "sha256" not in file_info:
            return False, f"File {filename} missing required 'content' or 'sha256'"

        content = file_info["content"]
        if not isinstance(content, str):
            return False, f"Content for {filename} is not a valid UTF-8 string"

        expected_sha = str(file_info["sha256"]).strip().lower()
        actual_sha = calculate_sha256(content).lower()
        if actual_sha != expected_sha:
            return (
                False,
                f"SHA-256 checksum mismatch for {filename}: computed {actual_sha} != manifest {expected_sha}",
            )

        if "size" in file_info:
            content_bytes_len = len(content.encode("utf-8"))
            if content_bytes_len != file_info["size"]:
                return (
                    False,
                    f"Size mismatch for {filename}: computed {content_bytes_len} != manifest {file_info['size']}",
                )

    return True, "Valid"


def stage_bundle(bundle: dict) -> list[str]:
    """Write each bundle file to <filename>.new and verify on-flash SHA-256."""
    files = bundle.get("files", {})
    staged: list[str] = []
    current_stage_path = None

    try:
        for filename, file_info in files.items():
            stage_path = f"{filename}.new"
            current_stage_path = stage_path
            content = file_info["content"]
            expected_sha = str(file_info["sha256"]).strip().lower()

            with open(stage_path, "w") as f:
                f.write(content)

            # Read back from flash and verify integrity
            with open(stage_path, "r") as f:
                readback_content = f.read()

            readback_sha = calculate_sha256(readback_content).lower()
            if readback_sha != expected_sha:
                raise RuntimeError(
                    f"Post-write flash verification failed for {stage_path}: hash mismatch"
                )

            staged.append(stage_path)
            current_stage_path = None
            print(f"[ota] Staged and verified {stage_path}")

        return staged
    except Exception as exc:
        # Clean up any staged files on failure
        to_clean = set(staged)
        if current_stage_path is not None:
            to_clean.add(current_stage_path)
        for stage_file in to_clean:
            try:
                os.remove(stage_file)
            except Exception:  # noqa: BLE001, S110
                pass
        raise RuntimeError(f"OTA staging failed: {exc}") from exc


def apply_staged_update(bundle: dict, staged_paths: list[str]) -> bool:
    """Backup active files to .bak, atomically swap .new to active, and set ota_pending."""
    files = bundle.get("files", {})
    new_version = bundle.get("version", "unknown")
    file_list = list(files.keys())

    # Write ota_pending flag before any active file is changed
    pending_record = {
        "pending": True,
        "version": new_version,
        "previous_version": FIRMWARE_VERSION,
        "files": file_list,
        "boot_attempts": 0,
        "max_attempts": 1,
        "timestamp": int(time.time()),
    }
    with open(OTA_PENDING_FILE, "w") as f:
        json.dump(pending_record, f)

    try:
        for filename in file_list:
            stage_path = f"{filename}.new"
            bak_path = f"{filename}.bak"

            file_exists = False
            try:
                os.stat(filename)
                file_exists = True
            except Exception:  # noqa: BLE001
                file_exists = False

            if file_exists:
                # Backup existing active file
                try:
                    os.remove(bak_path)
                except Exception:  # noqa: BLE001, S110
                    pass
                copy_file(filename, bak_path)

                # Atomically replace active file
                try:
                    os.remove(filename)
                except Exception:  # noqa: BLE001, S110
                    pass
                os.rename(stage_path, filename)
            else:
                os.rename(stage_path, filename)

            print(f"[ota] Activated {filename} (backup at {bak_path})")

        print(f"[ota] Update to v{new_version} applied successfully. Pending verification.")
        return True
    except Exception as exc:
        print(f"[ota] CRITICAL: Failure applying update: {exc}")
        rollback_ota(pending_record)
        raise RuntimeError(f"Failed during file activation: {exc}") from exc


class OTAClient:
    """Over-The-Air firmware updater coordinating Wi-Fi download and safe flashing."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config if config is not None else load_config()

    def ensure_wifi(self) -> bool:
        """Connect to Wi-Fi if currently disconnected."""
        if wifi is None:
            print("[ota] Error: wifi module unavailable.")
            return False
        if wifi.is_connected():
            return True
        ssid = self.config.get("wifi_ssid", "")
        password = self.config.get("wifi_password", "")
        timeout = self.config.get("wifi_connect_timeout_sec", 20)
        print(f"[ota] Connecting to Wi-Fi network '{ssid}'...")
        return wifi.ensure_connected(ssid, password, timeout_sec=timeout)

    def resolve_bundle_url(self, explicit_url: str | None = None) -> str:
        """Resolve target download URL for firmware_bundle.json."""
        if explicit_url:
            return explicit_url
        cfg_url = self.config.get("ota_bundle_url") or self.config.get("ota_url")
        if cfg_url:
            return cfg_url
        repo = self.config.get("ota_repo", "jonasfh/snippen-sms-service")
        return f"https://raw.githubusercontent.com/{repo}/main/dist/firmware_bundle.json"

    def download_bundle(self, url: str | None = None, max_redirects: int = 3) -> dict:
        """Download firmware_bundle.json from URL with HTTP redirect support."""
        if requests is None:
            raise RuntimeError("HTTP requests module unavailable")

        target_url = self.resolve_bundle_url(url)
        headers = {
            "Accept": "application/json",
            "User-Agent": f"snippen-ota/{FIRMWARE_VERSION}",
        }
        token = self.config.get("ota_github_token") or self.config.get("github_token")
        if token:
            headers["Authorization"] = f"token {token}"

        print(f"[ota] Downloading firmware bundle from {target_url}...")
        cur_url = target_url
        redirect_count = 0

        while redirect_count <= max_redirects:
            res = None
            try:
                res = requests.get(cur_url, headers=headers)
                if res.status_code in (301, 302, 303, 307, 308):
                    loc = res.headers.get("Location") or res.headers.get("location")
                    if not loc:
                        raise RuntimeError(f"Redirect {res.status_code} missing Location header")
                    cur_url = loc
                    redirect_count += 1
                    continue

                if res.status_code != 200:
                    raise RuntimeError(f"HTTP error {res.status_code} fetching bundle")

                if gc is not None:
                    gc.collect()

                data = res.json()
                if not isinstance(data, dict):
                    raise TypeError("Response payload is not valid JSON dictionary")
                return data
            finally:
                if res is not None and hasattr(res, "close"):
                    try:
                        res.close()
                    except Exception:  # noqa: BLE001, S110
                        pass

        raise RuntimeError(f"Too many HTTP redirects (exceeded {max_redirects})")

    def perform_ota(
        self,
        url: str | None = None,
        force: bool = False,
        restart: bool = True,
    ) -> bool:
        """Execute complete OTA workflow: connect Wi-Fi, download, validate, stage, and apply."""
        if not self.ensure_wifi():
            raise RuntimeError("Could not establish Wi-Fi connection for OTA")

        if gc is not None:
            gc.collect()

        bundle = self.download_bundle(url)

        valid, err = validate_bundle(bundle, force=force)
        if not valid:
            raise ValueError(f"Bundle validation failed: {err}")

        print(f"[ota] Validated firmware bundle v{bundle['version']}. Staging files...")
        staged = stage_bundle(bundle)

        print("[ota] Applying staged files...")
        success = apply_staged_update(bundle, staged)

        if success and restart and machine is not None and hasattr(machine, "reset"):
            print("[ota] Rebooting device into updated firmware...")
            time.sleep(1)
            machine.reset()

        return success
