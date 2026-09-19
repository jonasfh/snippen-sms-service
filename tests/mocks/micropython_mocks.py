"""Mock implementations of MicroPython built-in modules for host-side CPython unit testing."""

from __future__ import annotations

import sys
import types
from typing import Any, ClassVar


class MockPin:
    IN = 0
    OUT = 1
    PULL_UP = 1
    PULL_DOWN = 2

    # Class-level pin state tracker for test assertions
    instances: ClassVar[dict[int, MockPin]] = {}

    def __init__(
        self, pin_id: int, mode: int = -1, pull: int = -1, value: int | None = None
    ) -> None:
        self.pin_id = pin_id
        self.mode = mode
        self.pull = pull
        self._value = value if value is not None else 0
        self.value_history: list[int] = [self._value]
        MockPin.instances[pin_id] = self

    def value(self, val: int | None = None) -> int:
        if val is not None:
            self._value = 1 if val else 0
            self.value_history.append(self._value)
            return self._value
        return self._value

    def on(self) -> None:
        self.value(1)

    def off(self) -> None:
        self.value(0)

    @classmethod
    def reset_registry(cls) -> None:
        cls.instances.clear()


class MockUART:
    instances: ClassVar[dict[int, MockUART]] = {}

    def __init__(
        self,
        uart_id: int,
        baudrate: int = 115200,
        tx: Any = None,
        rx: Any = None,
        timeout: int = 2000,
        **kwargs: Any,
    ) -> None:
        self.uart_id = uart_id
        self.baudrate = baudrate
        self.tx = tx
        self.rx = rx
        self.timeout = timeout
        self.extra_kwargs = kwargs
        self.written_data: list[bytes] = []
        self._read_buffer = bytearray()
        self.responder: Any = None
        self.auto_responses: dict[str, str | bytes] = {}
        MockUART.instances[uart_id] = self

    def write(self, data: bytes | str) -> int:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.written_data.append(data)
        if self.responder is not None:
            res = self.responder(data)
            if res:
                self.feed_read(res)
        elif self.auto_responses:
            cmd_str = data.decode("utf-8", errors="ignore").strip()
            for pattern, resp in self.auto_responses.items():
                if pattern in cmd_str:
                    self.feed_read(resp)
                    break
        return len(data)

    def read(self, nbytes: int | None = None) -> bytes | None:
        if not self._read_buffer:
            return None
        if nbytes is None or nbytes >= len(self._read_buffer):
            out = bytes(self._read_buffer)
            self._read_buffer.clear()
            return out
        out = bytes(self._read_buffer[:nbytes])
        self._read_buffer = self._read_buffer[nbytes:]
        return out

    def readline(self) -> bytes | None:
        if not self._read_buffer:
            return None
        idx = self._read_buffer.find(b"\n")
        if idx == -1:
            return self.read()
        out = bytes(self._read_buffer[: idx + 1])
        self._read_buffer = self._read_buffer[idx + 1 :]
        return out

    def feed_read(self, data: bytes | str) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._read_buffer.extend(data)

    def any(self) -> int:
        return len(self._read_buffer)

    @classmethod
    def reset_registry(cls) -> None:
        cls.instances.clear()


class MockWDT:
    def __init__(self, id: int = 0, timeout: int = 5000) -> None:
        self.id = id
        self.timeout = timeout
        self.feed_count = 0

    def feed(self) -> None:
        self.feed_count += 1


class MockTime:
    def __init__(self) -> None:
        self.current_ms = 1_000_000
        self.sleep_history: list[tuple[str, int | float]] = []

    def sleep(self, seconds: float) -> None:
        self.sleep_history.append(("sleep", seconds))
        self.current_ms += int(seconds * 1000)

    def sleep_ms(self, ms: int) -> None:
        self.sleep_history.append(("sleep_ms", ms))
        self.current_ms += ms

    def sleep_us(self, us: int) -> None:
        self.sleep_history.append(("sleep_us", us))
        self.current_ms += max(1, us // 1000)

    def ticks_ms(self) -> int:
        return self.current_ms

    def ticks_us(self) -> int:
        return self.current_ms * 1000

    def ticks_diff(self, t1: int, t2: int) -> int:
        return t1 - t2

    def time(self) -> int:
        return self.current_ms // 1000

    def reset(self) -> None:
        self.current_ms = 1_000_000
        self.sleep_history.clear()


class MockWLAN:
    def __init__(self, interface_id: int) -> None:
        self.interface_id = interface_id
        self._is_active = False
        self._is_connected = False
        self._connected_ssid: str | None = None
        self._ip_config = ("192.168.1.100", "255.255.255.0", "192.168.1.1", "8.8.8.8")

    def active(self, is_active: bool | None = None) -> bool:
        if is_active is not None:
            self._is_active = bool(is_active)
        return self._is_active

    def connect(self, ssid: str, password: str = "") -> None:
        self._connected_ssid = ssid
        self._is_connected = True

    def disconnect(self) -> None:
        self._is_connected = False
        self._connected_ssid = None

    def isconnected(self) -> bool:
        return self._is_connected

    def ifconfig(
        self, config: tuple[str, str, str, str] | None = None
    ) -> tuple[str, str, str, str]:
        if config is not None:
            self._ip_config = config
        return self._ip_config

    def status(self) -> int:
        return 3 if self._is_connected else 0


class MicroPythonEnvironment:
    """Context manager / fixture helper to install mock MicroPython modules into sys.modules."""

    def __init__(self) -> None:
        self.mock_time = MockTime()
        self.reset_called = False

    def install(self) -> None:
        MockPin.reset_registry()
        MockUART.reset_registry()
        self.mock_time.reset()
        self.reset_called = False

        # Build machine module
        machine_mod = types.ModuleType("machine")
        machine_mod.Pin = MockPin  # type: ignore[attr-defined]
        machine_mod.UART = MockUART  # type: ignore[attr-defined]
        machine_mod.WDT = MockWDT  # type: ignore[attr-defined]

        def _reset() -> None:
            self.reset_called = True

        machine_mod.reset = _reset  # type: ignore[attr-defined]
        sys.modules["machine"] = machine_mod

        # Build network module
        network_mod = types.ModuleType("network")
        network_mod.STA_IF = 0  # type: ignore[attr-defined]
        network_mod.AP_IF = 1  # type: ignore[attr-defined]
        network_mod.WLAN = MockWLAN  # type: ignore[attr-defined]
        sys.modules["network"] = network_mod

        # Patch or provide utime / time
        utime_mod = types.ModuleType("utime")
        utime_mod.sleep = self.mock_time.sleep  # type: ignore[attr-defined]
        utime_mod.sleep_ms = self.mock_time.sleep_ms  # type: ignore[attr-defined]
        utime_mod.sleep_us = self.mock_time.sleep_us  # type: ignore[attr-defined]
        utime_mod.ticks_ms = self.mock_time.ticks_ms  # type: ignore[attr-defined]
        utime_mod.ticks_us = self.mock_time.ticks_us  # type: ignore[attr-defined]
        utime_mod.ticks_diff = self.mock_time.ticks_diff  # type: ignore[attr-defined]
        utime_mod.time = self.mock_time.time  # type: ignore[attr-defined]
        sys.modules["utime"] = utime_mod

    def uninstall(self) -> None:
        sys.modules.pop("machine", None)
        sys.modules.pop("network", None)
        sys.modules.pop("utime", None)
        MockPin.reset_registry()
        MockUART.reset_registry()
