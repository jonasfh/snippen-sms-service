#!/usr/bin/env python3
"""Run automated cellular modem and SIM diagnostic test on connected Lilygo ESP32 using mpremote."""

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


def run_modem_test(
    port: str | None = None,
    sync_files: bool = True,
    dry_run: bool = False,
) -> int:
    """Upload modem driver and execute cellular modem diagnostic test on ESP32."""
    repo_root = Path(__file__).resolve().parent.parent
    firmware_dir = repo_root / "firmware"
    test_script = firmware_dir / "test_modem.py"

    if not test_script.exists():
        print(f"[test_modem] ERROR: Test script not found at {test_script}")
        return 1

    base_cmd = build_mpremote_base_cmd(port)

    # Optionally sync firmware files before testing
    if sync_files:
        files_to_sync = ["boot.py", "config.py", "modem.py", "test_modem.py"]
        for fname in files_to_sync:
            src = firmware_dir / fname
            if src.exists():
                cp_cmd = [*base_cmd, "cp", str(src), f":{fname}"]
                print(f"[test_modem] Syncing {fname} to device...")
                if not dry_run:
                    res = subprocess.run(cp_cmd, check=False)
                    if res.returncode != 0:
                        print(f"[test_modem] ERROR: Failed to sync {fname} to device.")
                        return res.returncode
            else:
                print(f"[test_modem] Warning: {fname} not found in {firmware_dir}, skipping.")

    # Execute test script on device
    run_cmd = [*base_cmd, "run", str(test_script)]
    print(f"[test_modem] Executing: {' '.join(run_cmd)}")
    if dry_run:
        print("[test_modem] (Dry run - command not executed)")
        return 0

    res = subprocess.run(run_cmd, check=False)
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run SimCom A7670E cellular modem diagnostic test on connected ESP32 using mpremote."
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial port of the ESP32 (auto-detected if omitted)",
    )
    parser.add_argument(
        "--no-sync",
        dest="sync_files",
        action="store_false",
        help="Skip syncing modem.py and test_modem.py to device before testing",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display commands without executing them",
    )

    args = parser.parse_args()
    port = args.port or find_default_port()
    if not port and not args.dry_run:
        print("[test_modem] ERROR: No ESP32 serial port detected (/dev/ttyACM* or /dev/ttyUSB*).")
        return 1

    return run_modem_test(
        port=port,
        sync_files=args.sync_files,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
