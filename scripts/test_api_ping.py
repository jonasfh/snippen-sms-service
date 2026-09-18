#!/usr/bin/env python3
"""Run automated Snippen API connectivity test on connected Lilygo ESP32 using mpremote."""

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


def run_api_test(
    port: str | None = None,
    sync_config: bool = True,
    dry_run: bool = False,
) -> int:
    """Upload local config and execute Snippen API ping test on ESP32."""
    repo_root = Path(__file__).resolve().parent.parent
    firmware_dir = repo_root / "firmware"
    test_script = firmware_dir / "test_api.py"

    if not test_script.exists():
        print(f"[test_api] ERROR: Test script not found at {test_script}")
        return 1

    base_cmd = build_mpremote_base_cmd(port)

    # Optionally sync config to device before testing
    if sync_config:
        config_files = ["config_local.py", "config.local.py", "config.json"]
        found_config = None
        for cfg_name in config_files:
            candidate = firmware_dir / cfg_name
            if candidate.exists():
                found_config = candidate
                break

        if found_config:
            print(f"[test_api] Syncing {found_config.name} to ESP32...")
            cp_cmd = [*base_cmd, "cp", str(found_config), f":{found_config.name}"]
            if dry_run:
                print(f"[test_api] (Dry run) {' '.join(cp_cmd)}")
            else:
                try:
                    subprocess.run(cp_cmd, check=True)
                except subprocess.CalledProcessError as exc:
                    print(f"[test_api] Warning: Failed to sync config: {exc}")

    # Run test_api.py on device
    run_cmd = [*base_cmd, "run", str(test_script)]
    print(f"[test_api] Running Snippen API test on ESP32: {' '.join(run_cmd)}")

    if dry_run:
        print("[test_api] (Dry run - test not executed)")
        return 0

    try:
        res = subprocess.run(run_cmd, check=False)
        return res.returncode
    except FileNotFoundError:
        print("[test_api] ERROR: mpremote is not installed in the environment.")
        return 1
    except KeyboardInterrupt:
        print("\n[test_api] Aborted by user.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lilygo ESP32 Snippen API Ping Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--port",
        "-p",
        help="Serial port of ESP32 (default: auto-detect)",
        default=None,
    )
    parser.add_argument(
        "--no-sync-config",
        action="store_true",
        help="Skip uploading local config file before running test",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without communicating with hardware",
    )

    args = parser.parse_args()

    port = args.port
    if not port and not args.dry_run:
        port = find_default_port()
        if port:
            print(f"[test_api] Auto-detected serial port: {port}")
        else:
            print(
                "[test_api] Warning: No serial port auto-detected (/dev/ttyACM* or /dev/ttyUSB*)."
            )

    return run_api_test(
        port=port,
        sync_config=not args.no_sync_config,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
