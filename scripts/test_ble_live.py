#!/usr/bin/env python3
"""Run interactive on-device BLE provisioning test on connected Lilygo ESP32 using mpremote."""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
from pathlib import Path


def find_default_port() -> str | None:
    """Find the default serial port connected to the ESP32."""
    patterns = ["/dev/ttyACM*", "/dev/ttyUSB*"]
    ports: list[str] = []
    for pat in patterns:
        ports.extend(sorted(glob.glob(pat)))

    if not ports:
        return None
    return ports[0]


def build_mpremote_base_cmd(port: str | None) -> list[str]:
    """Construct base command invoking mpremote with optional port specification."""
    python_bin = sys.executable
    venv_python = Path("/home/vscode/.venv/bin/python")
    if "venv" not in python_bin and venv_python.exists():
        python_bin = str(venv_python)

    cmd = [python_bin, "-m", "mpremote"]
    if port:
        cmd.extend(["connect", port])
    return cmd


def run_ble_live_test(
    port: str | None = None,
    dry_run: bool = False,
) -> int:
    """Upload required firmware dependencies and execute interactive BLE provisioning test."""
    repo_root = Path(__file__).resolve().parent.parent
    firmware_dir = repo_root / "firmware"
    test_script = firmware_dir / "test_ble_provisioning.py"

    if not test_script.exists():
        print(f"[test_ble_live] ERROR: Test script not found at {test_script}")
        return 1

    base_cmd = build_mpremote_base_cmd(port)

    # Sync required modules to ensure device has latest firmware
    modules_to_copy = ["config.py", "button.py", "ble_config.py", "wifi.py"]
    for mod in modules_to_copy:
        local_file = firmware_dir / mod
        if local_file.exists():
            cp_cmd = [*base_cmd, "cp", str(local_file), f":{mod}"]
            print(f"[test_ble_live] Syncing {mod} to device...")
            if not dry_run:
                try:
                    res = subprocess.run(cp_cmd, check=False)
                    if res.returncode != 0:
                        print(f"[test_ble_live] Warning: Failed to sync {mod}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[test_ble_live] Error during cp: {exc}")

    # Run test script interactively
    run_cmd = [*base_cmd, "run", str(test_script)]
    print(f"[test_ble_live] Executing on device: {' '.join(run_cmd)}")
    if dry_run:
        print("[test_ble_live] (Dry run - command not executed)")
        return 0

    try:
        proc = subprocess.run(run_cmd, check=False)
        return proc.returncode
    except KeyboardInterrupt:
        print("\n[test_ble_live] Test aborted by user.")
        return 0
    except FileNotFoundError:
        print("[test_ble_live] ERROR: mpremote is not installed in the current Python environment.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run interactive BLE provisioning manual test on Lilygo ESP32."
    )
    parser.add_argument(
        "--port",
        default=None,
        help="Serial port of the ESP32 (e.g., /dev/ttyACM0). Auto-detected if omitted.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them.",
    )

    args = parser.parse_args()
    port = args.port or find_default_port()

    if not port and not args.dry_run:
        print(
            "[test_ble_live] WARNING: No ESP32 serial port detected (/dev/ttyACM* or /dev/ttyUSB*)."
        )
        print("Please verify the Lilygo board is connected via USB, or specify --port manually.")

    return run_ble_live_test(port=port, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
