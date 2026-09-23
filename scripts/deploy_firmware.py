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
import time
from pathlib import Path

# Ensure devcontainer venv site-packages are accessible even if run via system python
for venv_site in Path("/home/vscode/.venv/lib").glob("python*/site-packages"):
    if venv_site.is_dir() and str(venv_site) not in sys.path:
        sys.path.insert(0, str(venv_site))


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
    follow: bool = False,
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
        "logger.py",
        "modem.py",
        "sms_encoding.py",
        "snippen_api.py",
        "button.py",
        "ble_config.py",
        "wifi.py",
        "test_ble_provisioning.py",
        "test_button.py",
        "test_modem.py",
        "test_api.py",
        "test_wifi.py",
    ]

    if include_config:
        local_cfg = firmware_dir / "config_local.py"
        if local_cfg.exists():
            files_to_deploy.append("config_local.py")
        config_json = firmware_dir / "config.json"
        if config_json.exists():
            files_to_deploy.append("config.json")

    base_cmd = build_mpremote_base_cmd(port)

    existing_files: list[Path] = []
    for filename in files_to_deploy:
        local_path = firmware_dir / filename
        if local_path.exists():
            existing_files.append(local_path)
        else:
            print(f"[deploy] Warning: Skipping missing file {local_path}")

    print(
        f"[deploy] Preparing to deploy {len(existing_files)} firmware files from {firmware_dir}: {[f.name for f in existing_files]}"
    )

    if not existing_files:
        print("[deploy] No firmware files found to deploy.")
        return 0

    batch_cp_cmd = [*base_cmd, "cp", *[str(p) for p in existing_files], ":"]
    ret = run_mpremote_command(batch_cp_cmd, dry_run=dry_run)
    if ret != 0 and not dry_run and port:
        print(
            "[deploy] Device unresponsive to raw REPL handshake. Attempting hardware reset recovery..."
        )
        hardware_reset_device(port)
        time.sleep(1.0)
        ret = run_mpremote_command(batch_cp_cmd, dry_run=dry_run)

    if ret != 0:
        print(
            "[deploy] Warning: Batch transfer failed, falling back to sequential file deployment..."
        )
        for filename in files_to_deploy:
            local_path = firmware_dir / filename
            if not local_path.exists():
                continue
            remote_dest = f":{filename}"
            cp_cmd = [*base_cmd, "cp", str(local_path), remote_dest]
            ret = run_mpremote_command(cp_cmd, dry_run=dry_run)
            if ret != 0:
                print(f"[deploy] ERROR: Failed to copy {filename}")
                return ret

    print("[deploy] All firmware files copied successfully.")

    if do_reset:
        if dry_run:
            print(f"[dry-run] Would perform hardware reset on {port}...")
        else:
            print("[deploy] Performing hardware reset on device...")
            ret = hardware_reset_device(port)
            if ret != 0:
                print("[deploy] Warning: Hardware reset failed, attempting soft-reset fallback...")
                reset_cmd = [*build_mpremote_base_cmd(port), "soft-reset"]
                run_mpremote_command(reset_cmd, dry_run=dry_run)

        if follow:
            return monitor_device(port=port, dry_run=dry_run)

    return 0


def hardware_reset_device(port: str | None) -> int:
    """Perform physical hardware reset of ESP32 via RTS line pulse."""
    if not port:
        print("[reset] Error: No serial port specified or detected.")
        return 1
    try:
        import serial
    except ImportError:
        print("[reset] Error: pyserial is required for hardware reset. Run: pip install pyserial")
        return 1

    try:
        print(f"[reset] Triggering physical hardware reset via RTS line on {port}...")
        with serial.Serial(port, 115200) as ser:
            ser.setDTR(False)
            ser.setRTS(True)
            time.sleep(0.1)
            ser.setRTS(False)
            time.sleep(0.2)
        print("[reset] Hardware reset pulse completed.")
        return 0
    except (serial.SerialException, OSError) as exc:
        print(f"[reset] Error during hardware reset: {exc}")
        return 1


def monitor_device(port: str | None, baudrate: int = 115200, dry_run: bool = False) -> int:
    """Stream live serial stdout from device like 'tail -f' without interrupting MicroPython execution."""
    if dry_run:
        print(f"[dry-run] Would monitor serial port {port} at {baudrate} baud.")
        return 0

    if not port:
        print("[monitor] Error: No serial port specified or detected.")
        return 1

    try:
        import serial
    except ImportError:
        print(
            "[monitor] Error: pyserial is required for serial monitoring. Run: pip install pyserial"
        )
        return 1

    print(f"[monitor] Listening to serial output on {port} ({baudrate} baud)...")
    print("[monitor] Device is running in background. Press Ctrl+C to exit monitor.")

    try:
        with serial.Serial(port, baudrate=baudrate, timeout=0.1) as ser:
            while True:
                line = ser.readline()
                if line:
                    try:
                        text = line.decode("utf-8", errors="replace")
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    except (UnicodeDecodeError, OSError):
                        pass
    except KeyboardInterrupt:
        print("\n[monitor] Monitoring stopped. (Device continues running).")
        return 0
    except (serial.SerialException, OSError) as exc:
        print(f"\n[monitor] Serial error: {exc}")
        return 1


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
    if hard:
        if dry_run:
            print(f"[dry-run] Would trigger physical hardware reset via RTS on {port}")
            return 0
        return hardware_reset_device(port)
    action = "soft-reset"
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
    common_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output logging",
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
    deploy_parser.add_argument(
        "--follow",
        "-f",
        action="store_true",
        dest="follow",
        help="Follow live output from device (like 'tail -f') after deploy and reset",
    )

    # Subcommand: monitor
    monitor_parser = subparsers.add_parser(
        "monitor",
        parents=[common_parser],
        help="Stream live stdout output from device (like 'tail -f') without interrupting execution",
    )
    monitor_parser.add_argument(
        "--baudrate",
        "-b",
        type=int,
        default=115200,
        help="Serial baud rate",
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
            follow=args.follow,
            dry_run=dry_run,
        )
    elif args.command == "monitor":
        return monitor_device(port=port, baudrate=args.baudrate, dry_run=dry_run)
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
