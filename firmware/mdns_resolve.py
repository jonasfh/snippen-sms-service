"""Lightweight MicroPython mDNS (.local) A-record resolver for ESP32.

Allows the Lilygo gateway to reach a local development machine (e.g.
``http://jonas-mac.local:8081/wp-json/snippen/v1``) without hardcoding its
LAN IP address, even when MicroPython's ``socket.getaddrinfo()`` does not
query multicast DNS (224.0.0.251:5353).
"""

try:
    import usocket as socket
except ImportError:
    import socket  # type: ignore[no-redef]

try:
    import ustruct as struct
except ImportError:
    import struct  # type: ignore[no-redef]

try:
    import utime as time
except ImportError:
    import time  # type: ignore[no-redef]

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353
_CACHE_TTL_MS = 60000
_cache = {}  # type: dict[str, tuple[str, int]]


def _ticks_ms() -> int:
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _ticks_diff(a: int, b: int) -> int:
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


def _build_mdns_query(hostname: str) -> bytes:
    """Build a minimal DNS A-record query packet for ``hostname``."""
    header = struct.pack(">HHHHHH", 0x0000, 0x0000, 1, 0, 0, 0)
    qname = bytearray()
    for label in hostname.rstrip(".").split("."):
        encoded = label.encode("utf-8")
        qname.append(len(encoded))
        qname.extend(encoded)
    qname.append(0)
    # QTYPE=1 (A), QCLASS=1 (IN)
    question = bytes(qname) + struct.pack(">HH", 1, 1)
    return header + question


def _skip_dns_name(data: bytes, offset: int) -> int:
    """Advance ``offset`` past a DNS name (handling compression pointers)."""
    length = len(data)
    while offset < length:
        byte = data[offset]
        if byte == 0:
            return offset + 1
        if (byte & 0xC0) == 0xC0:
            return offset + 2
        offset += 1 + byte
    return length


def _parse_mdns_a_response(data: bytes) -> str | None:
    """Extract the first IPv4 A record from an mDNS response packet."""
    if len(data) < 12:
        return None
    _, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", data[:12])
    if (flags & 0x8000) == 0 or ancount == 0:
        return None

    offset = 12
    for _ in range(qdcount):
        offset = _skip_dns_name(data, offset)
        offset += 4  # QTYPE + QCLASS

    for _ in range(ancount):
        if offset >= len(data):
            break
        offset = _skip_dns_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, _, _, rdlength = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        if rtype == 1 and rdlength == 4 and offset + 4 <= len(data):
            b0, b1, b2, b3 = data[offset : offset + 4]
            return f"{b0}.{b1}.{b2}.{b3}"
        offset += rdlength

    return None


def resolve_mdns(hostname: str, timeout_ms: int = 1500) -> str | None:
    """Resolve a ``.local`` hostname to an IPv4 address via multicast UDP."""
    host = hostname.strip().lower().rstrip(".")
    if not host.endswith(".local"):
        return None

    now = _ticks_ms()
    cached = _cache.get(host)
    if cached is not None:
        ip, expires_at = cached
        if _ticks_diff(expires_at, now) > 0:
            return ip

    query = _build_mdns_query(host)
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout_ms / 1000.0)
        sock.sendto(query, (MDNS_ADDR, MDNS_PORT))

        deadline = now + timeout_ms
        while _ticks_diff(deadline, _ticks_ms()) > 0:
            try:
                data, _ = sock.recvfrom(512)
            except OSError:
                break
            ip = _parse_mdns_a_response(data)
            if ip:
                _cache[host] = (ip, _ticks_ms() + _CACHE_TTL_MS)
                return ip
    except Exception:  # noqa: BLE001, S110
        pass
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa: BLE001, S110
                pass

    return None


def resolve_url_host(url: str, headers: dict[str, str] | None = None) -> str:
    """Rewrite ``http://<host>.local[:port]/...`` to use its resolved LAN IP.

    Preserves the original ``Host`` header when ``headers`` is provided.
    HTTPS URLs and non-``.local`` hosts are returned unchanged.
    """
    if not url.startswith("http://"):
        return url

    rest = url[7:]
    slash_idx = rest.find("/")
    authority = rest if slash_idx == -1 else rest[:slash_idx]
    path = "" if slash_idx == -1 else rest[slash_idx:]

    colon_idx = authority.find(":")
    host = authority if colon_idx == -1 else authority[:colon_idx]
    port_part = "" if colon_idx == -1 else authority[colon_idx:]

    if not host.lower().endswith(".local"):
        return url

    ip = resolve_mdns(host)
    if not ip:
        return url

    if headers is not None and "Host" not in headers:
        headers["Host"] = authority

    return f"http://{ip}{port_part}{path}"
