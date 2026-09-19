#!/usr/bin/env python3
"""Automated firmware deployment and management script for Lilygo T-Call A7670E using mpremote.

Usage:
    python scripts/deploy_firmware.py deploy [--port /dev/ttyACM0] [--reset] [--dry-run]
    python scripts/deploy_firmware.py ls [--port /dev/ttyACM0]
    python scripts/deploy_firmware.py repl [--port /dev/ttyACM0]
    python scripts/deploy_firmware.py reset [--port /dev/ttyACM0]
    python scripts/deploy_firmware.py run <script.py> [--port /dev/ttyACM0]
"""

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
    # Return first detected port
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


def run_mpremote_command(cmd: list[str], dry_run: bool = False) -> int:
    """Execute mpremote command safely."""
    print(f"[deploy] Running: {' '.join(cmd)}")
    if dry_run:
        print("[deploy] (Dry run - command not executed)")
        return 0

    try:
        res = subprocess.run(cmd, check=False)
        return res.returncode
    except FileNotFoundError:
        print("[deploy] ERROR: mpremote is not installed in the current Python environment.")
        return 1
    except KeyboardInterrupt:
        print("\n[deploy] Aborted by user.")
        return 0


def deploy_firmware(
    repo_root: Path,
    port: str | None,
    include_config: bool = False,
    do_reset: bool = True,
    dry_run: bool = False,
) -> int:
    """Deploy firmware files to target ESP32 flash root."""
    firmware_dir = repo_root / "firmware"
    if not firmware_dir.exists():
        print(f"[deploy] ERROR: Firmware directory not found at {firmware_dir}")
        return 1

    files_to_deploy = [
        "boot.py",
        "main.py",
        "config.py",
        "modem.py",
        "button.py",
        "ble_config.py",
        "wifi.py",
        "test_ble_provisioning.py",
    ]

    if include_config:
        local_cfg = firmware_dir / "config_local.py"
        dot_cfg = firmware_dir / "config.local.py"
        json_cfg = firmware_dir / "config.json"
        if local_cfg.exists():
            files_to_deploy.append("config_local.py")
        elif dot_cfg.exists():
            files_to_deploy.append("config.local.py")
        elif json_cfg.exists():
            files_to_deploy.append("config.json")

    print(f"[deploy] Preparing to deploy firmware files from {firmware_dir}: {files_to_deploy}")

    for filename in files_to_deploy:
        local_path = firmware_dir / filename
        if not local_path.exists():
            print(f"[deploy] Warning: {filename} does not exist in {firmware_dir}, skipping.")
            continue

        base_cmd = build_mpremote_base_cmd(port)
        cp_cmd = [*base_cmd, "cp", str(local_path), f":{filename}"]
        ret = run_mpremote_command(cp_cmd, dry_run=dry_run)
        if ret != 0:
            print(f"[deploy] Failed to copy {filename} to device.")
            return ret

    print("[deploy] All firmware files copied successfully.")

    if do_reset:
        print("[deploy] Performing soft reset on device...")
        reset_cmd = [*build_mpremote_base_cmd(port), "soft-reset"]
        return run_mpremote_command(reset_cmd, dry_run=dry_run)

    return 0


def list_device_files(port: str | None, dry_run: bool = False) -> int:
    """List files on device filesystem."""
    cmd = [*build_mpremote_base_cmd(port), "ls", ":"]
    return run_mpremote_command(cmd, dry_run=dry_run)


def open_repl(port: str | None, dry_run: bool = False) -> int:
    """Open interactive MicroPython REPL."""
    cmd = [*build_mpremote_base_cmd(port), "repl"]
    return run_mpremote_command(cmd, dry_run=dry_run)


def reset_device(port: str | None, hard: bool = False, dry_run: bool = False) -> int:
    """Reset device."""
    action = "reset" if hard else "soft-reset"
    cmd = [*build_mpremote_base_cmd(port), action]
    return run_mpremote_command(cmd, dry_run=dry_run)


def run_script_on_device(script_path: str, port: str | None, dry_run: bool = False) -> int:
    """Run a local script on device without copying permanently."""
    cmd = [*build_mpremote_base_cmd(port), "run", script_path]
    return run_mpremote_command(cmd, dry_run=dry_run)


def main() -> int:
    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        "--port",
        "-p",
        help="Serial port (e.g. /dev/ttyACM0 or /dev/ttyUSB0). If omitted, attempts auto-detection.",
        default=argparse.SUPPRESS,
    )
    common_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without communicating with hardware.",
        default=argparse.SUPPRESS,
    )

    parser = argparse.ArgumentParser(
        description="Lilygo T-Call A7670E Firmware Deployment Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        parents=[common_parser],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: deploy
    deploy_parser = subparsers.add_parser(
        "deploy",
        parents=[common_parser],
        help="Deploy firmware files to ESP32",
    )
    deploy_parser.add_argument(
        "--include-config",
        action="store_true",
        help="Also upload config_local.py or config.json if present",
    )
    deploy_parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Do not reset device after uploading",
    )

    # Subcommand: ls
    subparsers.add_parser(
        "ls", parents=[common_parser], help="List files in root filesystem of device"
    )

    # Subcommand: repl
    subparsers.add_parser("repl", parents=[common_parser], help="Open interactive MicroPython REPL")

    # Subcommand: reset
    reset_parser = subparsers.add_parser(
        "reset", parents=[common_parser], help="Reset the microcontroller"
    )
    reset_parser.add_argument(
        "--hard",
        action="store_true",
        help="Perform hard reset instead of soft reset",
    )

    # Subcommand: run
    run_parser = subparsers.add_parser(
        "run", parents=[common_parser], help="Run a local script on device"
    )
    run_parser.add_argument("script", help="Path to local python script to execute")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent

    # Port and dry-run resolution
    port = getattr(args, "port", None)
    dry_run = bool(getattr(args, "dry_run", False))

    if not port and not dry_run:
        detected = find_default_port()
        if detected:
            print(f"[deploy] Auto-detected serial port: {detected}")
            port = detected
        else:
            print("[deploy] Warning: No serial port auto-detected (/dev/ttyACM* or /dev/ttyUSB*).")

    if args.command == "deploy":
        return deploy_firmware(
            repo_root=repo_root,
            port=port,
            include_config=args.include_config,
            do_reset=not args.no_reset,
            dry_run=dry_run,
        )
    elif args.command == "ls":
        return list_device_files(port=port, dry_run=dry_run)
    elif args.command == "repl":
        return open_repl(port=port, dry_run=dry_run)
    elif args.command == "reset":
        return reset_device(port=port, hard=args.hard, dry_run=dry_run)
    elif args.command == "run":
        return run_script_on_device(args.script, port=port, dry_run=dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
