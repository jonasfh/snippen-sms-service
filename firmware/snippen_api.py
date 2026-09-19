"""MicroPython REST API client for Snippen Booking platform.

Synchronizes outbound SMS queue and reports inbound SMS and delivery status
against WordPress REST endpoints (https://vestreholmensameie.no/wp-json/snippen/v1/sms).
"""

import json

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None


class SnippenApiClient:
    """HTTP client communicating with Snippen Booking REST API endpoints."""

    def __init__(
        self,
        base_url: str = "https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        api_token: str = "",
        timeout_sec: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token.strip()
        self.timeout_sec = timeout_sec
        self.consecutive_errors = 0

    def _build_url(self, path: str) -> str:
        """Construct endpoint URL ensuring proper namespace."""
        endpoint = path.lstrip("/")
        base = self.base_url
        if not base.endswith("/sms") and not endpoint.startswith("sms/"):
            base = f"{base}/sms"
        return f"{base}/{endpoint}"

    def _get_headers(self) -> dict[str, str]:
        """Generate authentication and content-type headers."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            headers["X-API-Key"] = self.api_token
        return headers

    def fetch_outbox(self, limit: int = 10) -> list[dict]:
        """Fetch pending outbound SMS messages from Snippen outbox.

        GET /wp-json/snippen/v1/sms/outbox?limit=<limit>
        """
        if requests is None:
            print("[snippen_api] Error: requests library is unavailable.")
            return []

        url = f"{self._build_url('outbox')}?limit={limit}"
        headers = self._get_headers()
        res = None

        try:
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                self.consecutive_errors = 0
                data = res.json()
                if isinstance(data, dict) and "messages" in data:
                    return data["messages"]
                if isinstance(data, list):
                    return data
                return []
            if res.status_code in (401, 403):
                print(
                    f"[snippen_api] Authentication rejected (HTTP {res.status_code}). Check API token."
                )
            else:
                print(f"[snippen_api] Unexpected outbox HTTP status: {res.status_code}")
            self.consecutive_errors += 1
            return []
        except Exception as exc:  # noqa: BLE001
            self.consecutive_errors += 1
            print(f"[snippen_api] Failed to fetch outbox: {exc}")
            return []
        finally:
            if res is not None and hasattr(res, "close"):
                try:
                    res.close()
                except Exception:  # noqa: BLE001, S110
                    pass

    def report_outbox_status(self, statuses: list[dict]) -> bool:
        """Report delivery status (sent/failed) back to Snippen outbox.

        POST /wp-json/snippen/v1/sms/outbox/status
        Payload: {"statuses": [{"external_id": "...", "status": "sent|failed", ...}]}
        """
        if not statuses:
            return True

        if requests is None:
            print("[snippen_api] Error: requests library is unavailable.")
            return False

        url = self._build_url("outbox/status")
        headers = self._get_headers()
        payload = json.dumps({"statuses": statuses})
        res = None

        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code in (200, 201):
                self.consecutive_errors = 0
                return True
            print(f"[snippen_api] Outbox status update failed (HTTP {res.status_code})")
            self.consecutive_errors += 1
            return False
        except Exception as exc:  # noqa: BLE001
            self.consecutive_errors += 1
            print(f"[snippen_api] Error reporting outbox status: {exc}")
            return False
        finally:
            if res is not None and hasattr(res, "close"):
                try:
                    res.close()
                except Exception:  # noqa: BLE001, S110
                    pass

    def report_inbound_sms(self, messages: list[dict]) -> bool:
        """Forward incoming SMS messages to Snippen Booking communication history.

        POST /wp-json/snippen/v1/sms/inbox
        Payload: {"messages": [{"sender": "...", "body": "...", "timestamp": "..."}]}
        """
        if not messages:
            return True

        if requests is None:
            print("[snippen_api] Error: requests library is unavailable.")
            return False

        url = self._build_url("inbox")
        headers = self._get_headers()
        payload = json.dumps({"messages": messages})
        res = None

        try:
            res = requests.post(url, headers=headers, data=payload)
            if res.status_code in (200, 201):
                self.consecutive_errors = 0
                return True
            print(f"[snippen_api] Inbound SMS ingestion failed (HTTP {res.status_code})")
            self.consecutive_errors += 1
            return False
        except Exception as exc:  # noqa: BLE001
            self.consecutive_errors += 1
            print(f"[snippen_api] Error forwarding inbound SMS: {exc}")
            return False
        finally:
            if res is not None and hasattr(res, "close"):
                try:
                    res.close()
                except Exception:  # noqa: BLE001, S110
                    pass
