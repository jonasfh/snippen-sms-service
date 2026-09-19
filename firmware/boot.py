"""Boot initialization for Lilygo T-Call A7670E (MicroPython).

Powers up the SimCom A7670E 4G LTE cellular modem and initializes UART communication.
Executed automatically by MicroPython upon boot.
"""

try:
    import utime as time
except ImportError:
    import time

from machine import UART, Pin

try:
    from config import load_config
except ImportError:

    def load_config():  # type: ignore[misc]
        return {
            "pin_modem_power": 12,
            "pin_modem_reset": 5,
            "pin_modem_pwrkey": 4,
            "pin_modem_tx": 26,
            "pin_modem_rx": 25,
            "modem_uart_id": 1,
            "modem_baudrate": 115200,
            "modem_uart_timeout_ms": 2000,
            "modem_pwrkey_pulse_ms": 1500,
            "modem_boot_wait_sec": 6,
        }


# Global hardware references accessible by main.py
modem_uart = None
pin_pwr = None
pin_rst = None
pin_pwrkey = None


def power_on_modem(cfg: dict | None = None) -> tuple[Pin, Pin, Pin]:
    """Power on SimCom A7670E modem via GPIO power rails and PWRKEY pulse.

    1. Set RESET high (inactive).
    2. Set POWER high (enables power rail).
    3. Pulse PWRKEY high for 1500ms, then pull low.
    4. Wait for modem boot initialization.
    """
    global pin_pwr, pin_rst, pin_pwrkey
    if cfg is None:
        cfg = load_config()

    pwr_pin_id = cfg.get("pin_modem_power", 12)
    rst_pin_id = cfg.get("pin_modem_reset", 5)
    pwrkey_pin_id = cfg.get("pin_modem_pwrkey", 4)
    pulse_ms = cfg.get("modem_pwrkey_pulse_ms", 1500)
    boot_wait_sec = cfg.get("modem_boot_wait_sec", 6)

    print(
        f"[boot] Initializing modem GPIO pins (Power: {pwr_pin_id}, Reset: {rst_pin_id}, PWRKEY: {pwrkey_pin_id})..."
    )
    pin_pwr = Pin(pwr_pin_id, Pin.OUT)
    pin_rst = Pin(rst_pin_id, Pin.OUT)
    pin_pwrkey = Pin(pwrkey_pin_id, Pin.OUT)

    # Deassert reset & apply power rail
    pin_rst.value(1)
    pin_pwr.value(1)
    time.sleep_ms(100)

    # Pulse PWRKEY to boot modem
    print(f"[boot] Pulsing PWRKEY for {pulse_ms} ms...")
    pin_pwrkey.value(1)
    time.sleep_ms(pulse_ms)
    pin_pwrkey.value(0)

    print(f"[boot] Waiting {boot_wait_sec}s for modem radio to initialize...")
    time.sleep(boot_wait_sec)
    print("[boot] Modem power sequence completed.")

    return pin_pwr, pin_rst, pin_pwrkey


def init_uart(cfg: dict | None = None) -> UART:
    """Initialize hardware UART communication with SimCom A7670E."""
    global modem_uart
    if cfg is None:
        cfg = load_config()

    uart_id = cfg.get("modem_uart_id", 1)
    baudrate = cfg.get("modem_baudrate", 115200)
    tx_pin = cfg.get("pin_modem_tx", 26)
    rx_pin = cfg.get("pin_modem_rx", 25)
    timeout = cfg.get("modem_uart_timeout_ms", 2000)

    print(
        f"[boot] Configuring UART{uart_id} at {baudrate} baud (TX: Pin {tx_pin}, RX: Pin {rx_pin})..."
    )
    modem_uart = UART(
        uart_id,
        baudrate=baudrate,
        tx=Pin(tx_pin),
        rx=Pin(rx_pin),
        timeout=timeout,
    )
    return modem_uart


def power_off_modem(cfg: dict | None = None) -> None:
    """Power down SimCom A7670E modem by disabling power rail and asserting reset."""
    global pin_pwr, pin_rst, pin_pwrkey
    if cfg is None:
        cfg = load_config()

    pwr_pin_id = cfg.get("pin_modem_power", 12)
    rst_pin_id = cfg.get("pin_modem_reset", 5)
    pwrkey_pin_id = cfg.get("pin_modem_pwrkey", 4)

    if pin_pwr is None:
        pin_pwr = Pin(pwr_pin_id, Pin.OUT)
    if pin_rst is None:
        pin_rst = Pin(rst_pin_id, Pin.OUT)
    if pin_pwrkey is None:
        pin_pwrkey = Pin(pwrkey_pin_id, Pin.OUT)

    print("[boot] Powering down modem (disabling power rail and asserting reset)...")
    pin_pwrkey.value(0)
    pin_rst.value(0)
    pin_pwr.value(0)
    time.sleep_ms(500)


def power_cycle_modem(cfg: dict | None = None) -> UART:
    """Perform full hardware power-cycle recovery and re-initialize UART."""
    if cfg is None:
        cfg = load_config()
    print("[boot] Initiating modem hardware power-cycle recovery...")
    power_off_modem(cfg)
    time.sleep_ms(1000)
    power_on_modem(cfg)
    return init_uart(cfg)


def boot() -> bool:
    """Run full hardware boot sequence."""
    print("[boot] Lilygo T-Call A7670E starting cold boot sequence...")
    try:
        config = load_config()
        power_on_modem(config)
        init_uart(config)
        print("[boot] Hardware initialization successful.")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[boot] ERROR during hardware initialization: {exc}")
        return False


# Execute boot sequence upon boot
if __name__ == "__main__":
    boot()
