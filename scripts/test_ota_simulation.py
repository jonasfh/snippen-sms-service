#!/usr/bin/env python3
"""Interactive OTA Simulation Script for Snippen SMS Gateway.

Simulates both successful updates and failed/corrupted updates with Safe Mode rollback
in an isolated local sandbox directory.

Usage:
    python scripts/test_ota_simulation.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment

# ANSI colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(title: str) -> None:
    print(f"\n{BOLD}{BLUE}{'=' * 70}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 70}{RESET}")


def make_bundle(version: str, files_dict: dict[str, str]) -> dict:
    files_manifest = {}
    total_bytes = 0
    for name, content in files_dict.items():
        raw = content.encode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()
        total_bytes += len(raw)
        files_manifest[name] = {
            "sha256": sha,
            "size": len(raw),
            "content": content,
        }
    return {
        "version": version,
        "tag": f"v{version}",
        "created_at": "2026-10-11T08:30:00Z",
        "total_files": len(files_manifest),
        "total_bytes": total_bytes,
        "files": files_manifest,
    }


def run_scenario_successful_update(sandbox: Path) -> bool:
    header("SCENARIO 1: Vellykket oppgradering (Happy Path)")
    cwd = Path.cwd()
    os.chdir(sandbox)
    try:
        import boot
        import ota

        print("1. Eksisterende tilstand på flash:")
        print(f"   main.py: {sandbox.joinpath('main.py').read_text().strip()}")
        print(f"   config.json: {sandbox.joinpath('config.json').read_text().strip()}")

        bundle = make_bundle(
            "0.32.0",
            {
                "main.py": "# Firmware v0.32.0 (Ny og forbedret)\nprint('Snippen Gateway v0.32.0 running smoothly!')\n",
                "version.py": 'FIRMWARE_VERSION = "0.32.0"\n',
            },
        )

        print("\n2. Validerer bundle og SHA-256 i minnet FØR skriving...")
        valid, msg = ota.validate_bundle(bundle, current_version="0.31.21")
        if not valid:
            print(f"{RED}Validering feilet: {msg}{RESET}")
            return False
        print(f"{GREEN}✓ Bundle v0.32.0 godkjent ({msg}){RESET}")

        print("\n3. Staging av nye filer (<fil>.new) med flash-verifisering...")
        staged = ota.stage_bundle(bundle)
        print(f"{GREEN}✓ Staged filer på disk: {staged}{RESET}")

        print("\n4. Atomisk utskifting og sikkerhetskopiering til <fil>.bak...")
        ota.apply_staged_update(bundle, staged)
        print(
            f"{GREEN}✓ Ny main.py aktivert:{RESET} {sandbox.joinpath('main.py').read_text().strip()}"
        )
        print(
            f"{GREEN}✓ Backup bevart i main.py.bak:{RESET} {sandbox.joinpath('main.py.bak').read_text().strip()}"
        )
        print(f"{YELLOW}✓ Statusflagg: ota_pending.json opprettet med boot_attempts = 0{RESET}")

        print("\n5. Simulert første oppstart (boot.py)...")
        boot.check_and_handle_ota_pending()
        pending_data = json.loads(sandbox.joinpath("ota_pending.json").read_text())
        print(
            f"{GREEN}✓ boot.py registrerte oppstart (boot_attempts = {pending_data['boot_attempts']}){RESET}"
        )

        print("\n6. main.py kjører stabilt i 30 sekunder...")
        print("   Bekrefter sunn oppgradering...")
        ota.confirm_healthy()
        assert not sandbox.joinpath("main.py.bak").exists(), "Bak-fil burde vært slettet"
        assert not sandbox.joinpath("ota_pending.json").exists(), "ota_pending burde vært fjernet"
        print(
            f"{GREEN}{BOLD}✓ OPPDATERING FULLFØRT: Sikkerhetskopier er ryddet og v0.32.0 er permanent!{RESET}"
        )
        return True
    finally:
        os.chdir(cwd)


def run_scenario_failed_update_with_rollback(sandbox: Path) -> bool:
    header("SCENARIO 2: Feilende oppgradering -> Automatisk Rollback (Safe Mode)")
    cwd = Path.cwd()
    os.chdir(sandbox)
    try:
        import boot
        import ota

        print("1. Nåværende stabil versjon:")
        print(f"   main.py: {sandbox.joinpath('main.py').read_text().strip()}")

        # Buggy firmware that will crash on startup
        buggy_bundle = make_bundle(
            "0.33.0",
            {
                "main.py": "# Firmware v0.33.0 BUGGY\nraise RuntimeError('Fatal crash during peripheral init!')\n",
            },
        )

        print("\n2. Stager og aktiverer buggy v0.33.0...")
        staged = ota.stage_bundle(buggy_bundle)
        ota.apply_staged_update(buggy_bundle, staged)
        print(
            f"{YELLOW}Aktiv main.py er nå buggy v0.33.0:{RESET}\n   {sandbox.joinpath('main.py').read_text().strip()}"
        )
        print(
            f"{GREEN}Sikkerhetskopi i main.py.bak:{RESET}\n   {sandbox.joinpath('main.py.bak').read_text().strip()}"
        )

        print("\n3. Første oppstart etter OTA (boot attempt 1)...")
        boot.check_and_handle_ota_pending()

        print("\n4. Krasj i main.py eller watchdog reset utløses!")
        print(f"{RED}   [CRASH] RuntimeError: Fatal crash during peripheral init!{RESET}")
        print("   Enheten restarter automatisk (ESP32 hardware watchdog / panic)...")

        print("\n5. Neste oppstart etter krasj (boot.py detekterer boot_attempts >= 1)...")
        recovered = boot.check_and_handle_ota_pending()
        assert recovered is True, "Rollback mislyktes"

        print("\n6. Sjekker filtilstand etter Safe Mode Rollback:")
        restored_main = sandbox.joinpath("main.py").read_text().strip()
        print(
            f"{GREEN}{BOLD}✓ main.py gjenopprettet til stabil versjon:{RESET}\n   {restored_main}"
        )
        assert "v0.32.0" in restored_main, "Feil versjon gjenopprettet"
        assert not sandbox.joinpath("main.py.bak").exists(), (
            "Bak-fil burde vært ryddet etter rollback"
        )
        assert not sandbox.joinpath("ota_pending.json").exists(), "Pending flagg burde vært fjernet"
        print(
            f"{GREEN}{BOLD}✓ ROLLBACK VELLYKKET: Systemet unngikk bricking og kjører trygt videre!{RESET}"
        )
        return True
    finally:
        os.chdir(cwd)


def run_scenario_corrupt_bundle_rejection(sandbox: Path) -> bool:
    header("SCENARIO 3: Korrupt bundle / Manipulert SHA-256")
    cwd = Path.cwd()
    os.chdir(sandbox)
    try:
        import ota

        corrupt_bundle = make_bundle("0.34.0", {"main.py": "print('malicious or corrupt')\n"})
        # Intentionally alter the manifest SHA-256 to simulate packet corruption or tampering
        corrupt_bundle["files"]["main.py"]["sha256"] = "deadbeef" * 8

        print("1. Forsøker å validere bundle med korrupt SHA-256 sjekksum...")
        valid, err = ota.validate_bundle(corrupt_bundle, current_version="0.32.0")

        print(f"{YELLOW}Resultat: valid={valid}, melding='{err}'{RESET}")
        assert not valid, "Bundle med korrupt SHA-256 skulle vært avvist"
        assert "SHA-256 checksum mismatch" in err

        # Verify flash is completely untouched
        assert "v0.32.0" in sandbox.joinpath("main.py").read_text()
        assert not sandbox.joinpath("main.py.new").exists()
        print(
            f"{GREEN}{BOLD}✓ SJEKKSUM-VERN VELLYKKET: Avvist i minnet, 0 endringer på flash!{RESET}"
        )
        return True
    finally:
        os.chdir(cwd)


def run_scenario_config_protection(sandbox: Path) -> bool:
    header("SCENARIO 4: Beskyttelse av sensitive filer (config.json)")
    cwd = Path.cwd()
    os.chdir(sandbox)
    try:
        import ota

        orig_config = sandbox.joinpath("config.json").read_text()

        bundle = make_bundle(
            "0.35.0",
            {
                "config.json": '{"hacked": true}',
                "config_local.py": "SECRET_OVERWRITE = True\n",
            },
        )

        print("1. Forsøker å oppdatere en bundle som inneholder config.json / config_local.py...")
        valid, err = ota.validate_bundle(bundle, current_version="0.32.0")

        print(f"{YELLOW}Resultat: valid={valid}, melding='{err}'{RESET}")
        assert not valid
        assert "Forbidden" in err

        # Verify config.json is 100% unaltered
        assert sandbox.joinpath("config.json").read_text() == orig_config
        print(
            f"{GREEN}{BOLD}✓ KONFIGURASJONSVERN VELLYKKET: config.json kan aldri overskrives av OTA!{RESET}"
        )
        return True
    finally:
        os.chdir(cwd)


def main() -> int:
    print(f"\n{BOLD}======================================================================{RESET}")
    print(f"{BOLD}  Snippen SMS Gateway - Firmware OTA Simulerings- og Testsuite{RESET}")
    print(f"{BOLD}======================================================================{RESET}")

    mpy_env = MicroPythonEnvironment()
    mpy_env.install()

    temp_dir = tempfile.mkdtemp(prefix="snippen_ota_sim_")
    sandbox = Path(temp_dir)

    try:
        # Initialize baseline environment
        sandbox.joinpath("main.py").write_text(
            "# Firmware v0.31.21\nprint('Snippen Gateway v0.31.21')\n"
        )
        sandbox.joinpath("version.py").write_text('FIRMWARE_VERSION = "0.31.21"\n')
        sandbox.joinpath("config.json").write_text(
            '{"wifi_ssid": "SnippenNet", "api_token": "secret_abc123"}'
        )

        s1 = run_scenario_successful_update(sandbox)
        s2 = run_scenario_failed_update_with_rollback(sandbox)
        s3 = run_scenario_corrupt_bundle_rejection(sandbox)
        s4 = run_scenario_config_protection(sandbox)

        if s1 and s2 and s3 and s4:
            print(
                f"\n{BOLD}{GREEN}======================================================================{RESET}"
            )
            print(f"{BOLD}{GREEN}  🎉 ALLE 4 SCENARIER FULLFØRT UTEN FEIL!{RESET}")
            print(
                f"{BOLD}{GREEN}======================================================================{RESET}\n"
            )
            return 0
        return 1
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
