#!/usr/bin/env python3
"""Hardware-in-the-loop (HIL) two-way SMS integration test for Snippen SMS Service.

Drives two physical LilyGO ESP32 + SimCom A7670E boards connected over USB serial
using ``mpremote`` to send and receive real SMS messages over the cellular network.
Covers GSM-7 ASCII, GSM-7 extended characters, Norwegian characters (æ, ø, å),
emojis/UTF-16 surrogate pairs, multipart SMS (<=3 parts via AT+CMGSEX and >3 parts
via 3GPP PDU mode), and bidirectional verification.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Ensure devcontainer venv site-packages are accessible when invoked via system python
for _venv_site in Path("/home/vscode/.venv/lib").glob("python*/site-packages"):
    if _venv_site.is_dir() and str(_venv_site) not in sys.path:
        sys.path.insert(0, str(_venv_site))

_MARKER = "__HIL_JSON__:"


@dataclass(frozen=True)
class SmsTestCase:
    """Single hardware-in-the-loop SMS test case."""

    name: str
    direction: str  # "A->B" or "B->A"
    body: str
    description: str


def build_default_test_cases() -> list[SmsTestCase]:
    """Return the standard SMS test matrix covering encodings and lengths."""
    long_gsm7_3parts = (
        "Snippen test 07 (3-part GSM7): Velkommen til Snippen grendehus. "
        "Her er praktisk informasjon om oppholdet ditt. "
        "Husk a slukke alle lys, lukke vinduer og laase ytterdoren nar du forlater lokalet. "
        "Ved sporsmal kan du svare pa denne meldingen eller kontakte styret direkte. "
        "Takk for at du holder grendehuset ryddig og pent for neste gjest! "
        "Ref: HIL-3PART-GSM7."
    )
    long_gsm7_5parts_pdu = (
        "Snippen test 08 (5-part GSM7 PDU): "
        + " ".join(
            f"Seksjon {idx:02d}: Dette er en lang testmelding uten norske spesialtegn "
            "for a verifisere 3GPP PDU-modus nar meldingen overstiger tre deler."
            for idx in range(1, 6)
        )
        + " Slutt."
    )
    long_ucs2_norwegian_3parts = (
        "Snippen test 09 (3-part UCS2): Hei! Her er nøkkelinformasjon på norsk med æ, ø og å. "
        "Døren åpnes med koden på tastaturet ved inngangen. "
        "Søppel må kildesorteres før avreise. God feiring i grendehuset!"
    )
    long_ucs2_emojis_5parts_pdu = (
        "Snippen test 10 (5-part UCS2+Emoji PDU): "
        "Velkommen til Snippen grendehus! 🏠🔑🎉 "
        "Her er viktig info med æ, ø, å og emojis plassert rundt 67-tegnsgrenser: "
        "🇳🇴✅🔥🚀✨ Dette skal deles trygt uten å splitte UTF-16 surrogatpar! "
        "Husk å låse døren når dere drar hjem 🚪🔒 og sjekk at komfyr og lys er slått av 💡🔌. "
        "Takk for besøket! 🙏🎊"
    )
    booking_template_formatting = (
        'Hei "Ola Nordmann"!\n'
        "Booking #1234 bekreftet for Snippen grendehus 🏠\n"
        "Dørkode: 4829#\n"
        "Se regler: https://vestreholmensameie.no/regler?id=1234&ok=1\n"
        "Mvh Styret 🎉"
    )

    return [
        SmsTestCase(
            name="short_ascii",
            direction="A->B",
            body="Snippen test 01: Enkel ASCII SMS OK.",
            description="Short GSM-7 ASCII (A -> B)",
        ),
        SmsTestCase(
            name="short_ascii_reverse",
            direction="B->A",
            body="Snippen test 02: Retur ASCII SMS OK.",
            description="Short GSM-7 ASCII (B -> A)",
        ),
        SmsTestCase(
            name="gsm7_extended",
            direction="A->B",
            body="Pris: 150€ {test} [kode] ~ ^ | \\ end",
            description="GSM-7 extended characters",
        ),
        SmsTestCase(
            name="norwegian_short",
            direction="A->B",
            body="Hei! Nøkler til grendehuset: æøå ÆØÅ.",
            description="Short UCS-2 Norwegian (A -> B)",
        ),
        SmsTestCase(
            name="norwegian_reverse",
            direction="B->A",
            body="Svar med norske tegn: Blåbærsyltetøy på øya Å.",
            description="Short UCS-2 Norwegian (B -> A)",
        ),
        SmsTestCase(
            name="emojis_short",
            direction="A->B",
            body="Velkommen til Snippen! 🏠🔑🎉✅🇳🇴",
            description="Short UCS-2 emojis & surrogate pairs",
        ),
        SmsTestCase(
            name="long_gsm7_3parts",
            direction="A->B",
            body=long_gsm7_3parts,
            description="3-part GSM-7 concatenated SMS (AT+CMGSEX)",
        ),
        SmsTestCase(
            name="long_gsm7_5parts_pdu",
            direction="A->B",
            body=long_gsm7_5parts_pdu,
            description="5-part GSM-7 concatenated SMS (3GPP PDU)",
        ),
        SmsTestCase(
            name="long_ucs2_norwegian_3parts",
            direction="A->B",
            body=long_ucs2_norwegian_3parts,
            description="3-part UCS-2 Norwegian concatenated SMS",
        ),
        SmsTestCase(
            name="long_ucs2_emojis_5parts_pdu",
            direction="A->B",
            body=long_ucs2_emojis_5parts_pdu,
            description="5-part UCS-2 + emoji concatenated SMS (3GPP PDU)",
        ),
        SmsTestCase(
            name="booking_template_formatting",
            direction="B->A",
            body=booking_template_formatting,
            description="Realistic multi-line booking template (B -> A)",
        ),
    ]


def _build_mpremote_cmd(port: str, code: str) -> list[str]:
    """Build mpremote command to execute a MicroPython snippet on a serial port."""
    python_bin = sys.executable
    venv_python = Path("/home/vscode/.venv/bin/python")
    if "venv" not in python_bin and venv_python.exists():
        python_bin = str(venv_python)
    return [python_bin, "-m", "mpremote", "connect", port, "exec", code]


def _run_device_snippet(port: str, code: str, timeout_sec: int = 90) -> dict[str, object]:
    """Execute MicroPython snippet on device and parse base64-encoded JSON marker."""
    cmd = _build_mpremote_cmd(port, code)
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"mpremote failed on {port} (exit {res.returncode}):\n"
            f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
        )

    for line in res.stdout.splitlines():
        if line.startswith(_MARKER):
            b64_payload = line[len(_MARKER) :].strip()
            raw_json = base64.b64decode(b64_payload).decode("utf-8", errors="replace")
            return json.loads(raw_json)

    raise RuntimeError(
        f"Missing {_MARKER} marker in output from {port}:\n"
        f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )


_INIT_MODEM_SNIPPET = """
import json, ubinascii
def _hil_get_driver():
    if "_hil_driver" not in globals():
        import boot
        from config import load_config
        from modem import ModemDriver
        cfg = load_config()
        if boot.modem_uart is None:
            if not boot.is_modem_online(cfg):
                boot.power_on_modem(cfg)
            uart = boot.init_uart(cfg)
        else:
            uart = boot.modem_uart
        drv = ModemDriver(uart=uart, config=cfg)
        if not drv.check_at(retries=3, delay_ms=500):
            uart = boot.power_cycle_modem(cfg)
            drv = ModemDriver(uart=uart, config=cfg)
            if not drv.check_at(retries=5, delay_ms=500):
                raise RuntimeError("AT handshake failed")
        drv.init_modem()
        globals()["_hil_driver"] = drv
    return globals()["_hil_driver"]

def _hil_emit(obj):
    raw = json.dumps(obj).encode("utf-8")
    print("__HIL_JSON__:" + ubinascii.b2a_base64(raw).decode("ascii").strip())
"""


def init_and_drain_device(port: str) -> dict[str, object]:
    """Initialize modem on device and clear any stale SMS from SIM memory."""
    code = (
        _INIT_MODEM_SNIPPET
        + """
drv = _hil_get_driver()
stale = drv.read_inbound_sms(delete_after_read=True)
info = drv.get_modem_info()
sig = drv.get_signal_quality()
reg = drv.get_network_registration()
_hil_emit({
    "model": info.get("model"),
    "rssi": sig.get("rssi") if sig else None,
    "registered": reg.get("registered") if reg else False,
    "drained": len(stale),
})
"""
    )
    return _run_device_snippet(port, code, timeout_sec=90)


def send_sms_on_device(port: str, recipient: str, body: str) -> dict[str, object]:
    """Send an SMS from the specified device using base64-safe payload transfer."""
    body_b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
    recipient_b64 = base64.b64encode(recipient.encode("utf-8")).decode("ascii")
    code = (
        _INIT_MODEM_SNIPPET
        + f"""
import time
drv = _hil_get_driver()
target = ubinascii.a2b_base64("{recipient_b64}").decode("utf-8")
text = ubinascii.a2b_base64("{body_b64}").decode("utf-8")
t0 = time.ticks_ms()
ok, ref_or_err = drv.send_sms(target, text, timeout_ms=25000)
elapsed_ms = time.ticks_diff(time.ticks_ms(), t0)
_hil_emit({{"ok": bool(ok), "ref_or_err": ref_or_err, "elapsed_ms": elapsed_ms}})
"""
    )
    return _run_device_snippet(port, code, timeout_sec=120)


def wait_for_sms_on_device(port: str, timeout_sec: int = 60) -> dict[str, object]:
    """Poll device inbox in RAM until a complete (reassembled) SMS arrives or times out."""
    code = (
        _INIT_MODEM_SNIPPET
        + f"""
import time
drv = _hil_get_driver()
deadline = time.ticks_add(time.ticks_ms(), {timeout_sec * 1000})
found = []
while time.ticks_diff(deadline, time.ticks_ms()) > 0:
    msgs = drv.read_inbound_sms(delete_after_read=True)
    if msgs:
        found.extend(msgs)
        break
    time.sleep(2)
_hil_emit({{"messages": found}})
"""
    )
    return _run_device_snippet(port, code, timeout_sec=timeout_sec + 30)


def normalize_digits(phone: str) -> str:
    """Extract digits for loose sender comparison."""
    return "".join(ch for ch in phone if ch.isdigit())


def run_hil_suite(
    port_a: str,
    number_a: str,
    port_b: str,
    number_b: str,
    timeout_sec: int = 60,
    cases_filter: set[str] | None = None,
    skip_reverse: bool = False,
    dry_run: bool = False,
) -> int:
    """Execute the full hardware SMS integration test suite."""
    all_cases = build_default_test_cases()
    cases = [
        c
        for c in all_cases
        if (cases_filter is None or c.name in cases_filter)
        and (not skip_reverse or c.direction == "A->B")
    ]

    if not cases:
        print("[HIL] No test cases selected.")
        return 1

    print(f"[HIL] Selected {len(cases)} test case(s).")
    print(f"[HIL] Device A: {port_a} ({number_a})")
    print(f"[HIL] Device B: {port_b} ({number_b})")

    if dry_run:
        for idx, case in enumerate(cases, start=1):
            print(f"  {idx:02d}. [{case.direction}] {case.name}: {case.description}")
        return 0

    print("\n[HIL] Initializing both modems and clearing stale SIM messages...")
    status_a = init_and_drain_device(port_a)
    print(f"[HIL] Device A ready: {status_a}")
    status_b = init_and_drain_device(port_b)
    print(f"[HIL] Device B ready: {status_b}")

    if not status_a.get("registered") or not status_b.get("registered"):
        print("[HIL] ERROR: One or both modems are not registered on cellular network.")
        return 1

    passed = 0
    failed = 0

    for idx, case in enumerate(cases, start=1):
        if case.direction == "A->B":
            sender_port, receiver_port = port_a, port_b
            sender_num, target_num = number_a, number_b
        else:
            sender_port, receiver_port = port_b, port_a
            sender_num, target_num = number_b, number_a

        print(f"\n[{idx}/{len(cases)}] {case.name} ({case.direction}) - {case.description}")
        t_start = time.monotonic()

        send_res = send_sms_on_device(sender_port, target_num, case.body)
        if not send_res.get("ok"):
            print(f"  ❌ SEND FAILED: {send_res.get('ref_or_err')}")
            failed += 1
            continue

        print(
            f"  Sent in {send_res.get('elapsed_ms')} ms (ref={send_res.get('ref_or_err')}), "
            f"waiting up to {timeout_sec}s for delivery..."
        )

        recv_res = wait_for_sms_on_device(receiver_port, timeout_sec=timeout_sec)
        messages = recv_res.get("messages", [])
        total_sec = time.monotonic() - t_start

        if not isinstance(messages, list) or not messages:
            print(f"  ❌ RECEIVE TIMEOUT after {total_sec:.1f}s")
            failed += 1
            continue

        msg = messages[0]
        actual_body = msg.get("body", "")
        actual_sender = msg.get("sender", "")

        body_ok = actual_body == case.body
        sender_ok = normalize_digits(sender_num)[-8:] in normalize_digits(actual_sender)

        if body_ok and sender_ok:
            print(f"  ✅ PASS ({total_sec:.1f}s, {len(case.body)} chars)")
            passed += 1
        else:
            print(f"  ❌ MISMATCH ({total_sec:.1f}s)")
            if not sender_ok:
                print(f"     Expected sender ~{sender_num}, got {actual_sender!r}")
            if not body_ok:
                print(f"     Expected body ({len(case.body)} chars): {case.body!r}")
                print(f"     Actual body   ({len(actual_body)} chars): {actual_body!r}")
            failed += 1

    print("\n========================================")
    print(f"[HIL] Summary: {passed} passed, {failed} failed (total {len(cases)})")
    print("========================================")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run live two-way SMS integration tests between two LilyGO A7670E boards."
    )
    parser.add_argument("--port-a", default="/dev/ttyACM0", help="Serial port for device A")
    parser.add_argument("--number-a", required=True, help="Phone number for device A SIM")
    parser.add_argument("--port-b", default="/dev/ttyACM1", help="Serial port for device B")
    parser.add_argument("--number-b", required=True, help="Phone number for device B SIM")
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Receive timeout in seconds per test case (default: 60)",
    )
    parser.add_argument(
        "--cases",
        type=str,
        default=None,
        help="Comma-separated list of test case names to run (default: all)",
    )
    parser.add_argument(
        "--skip-reverse",
        action="store_true",
        help="Skip B->A reverse direction test cases",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print selected test cases without touching hardware",
    )

    args = parser.parse_args()
    cases_filter = (
        {name.strip() for name in args.cases.split(",") if name.strip()} if args.cases else None
    )
    return run_hil_suite(
        port_a=args.port_a,
        number_a=args.number_a,
        port_b=args.port_b,
        number_b=args.number_b,
        timeout_sec=args.timeout,
        cases_filter=cases_filter,
        skip_reverse=args.skip_reverse,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
