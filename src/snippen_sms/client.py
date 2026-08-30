"""HTTP client for Snippen Booking API synchronization."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from snippen_sms import __version__
from snippen_sms.models import Message

logger = logging.getLogger("snippen_sms.client")


class SnippenClientError(Exception):
    """Base exception for Snippen API client errors."""


class SnippenAuthError(SnippenClientError):
    """Authentication or authorization failure (HTTP 401 / 403)."""


class SnippenNetworkError(SnippenClientError):
    """Network connection or timeout failure."""


class SnippenApiError(SnippenClientError):
    """API server response error (non-2xx)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SnippenClient:
    """HTTP client communicating with the Snippen application backend."""

    def __init__(
        self,
        api_url: str = "https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        api_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_token = api_token
        self.timeout_seconds = timeout_seconds

    def _get_endpoint_url(self, path: str) -> str:
        """Construct full URL for a subpath."""
        subpath = path.lstrip("/")
        return f"{self.api_url}/{subpath}"

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Execute HTTP request against Snippen API with auth headers and error handling."""
        url = self._get_endpoint_url(path)
        headers = {
            "Accept": "application/json",
            "User-Agent": f"snippen-sms-service/{__version__}",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            headers["X-API-Key"] = self.api_token

        data_bytes: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data_bytes = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=data_bytes,
            headers=headers,
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status_code = resp.status
                raw_body = resp.read().decode("utf-8")
                if not raw_body.strip():
                    return {}
                try:
                    return json.loads(raw_body)
                except json.JSONDecodeError as exc:
                    logger.warning("Failed to decode JSON response from %s: %s", url, exc)
                    return {"raw": raw_body}

        except urllib.error.HTTPError as exc:
            status_code = exc.code
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8")
            except (OSError, UnicodeDecodeError) as read_exc:
                logger.debug("Failed to read HTTP error response body: %s", read_exc)

            if status_code in (401, 403):
                msg = f"Snippen API authentication failed (HTTP {status_code}): {error_body or exc.reason}"
                logger.error(msg)
                raise SnippenAuthError(msg) from exc

            msg = f"Snippen API returned HTTP {status_code} for {method} {url}: {error_body or exc.reason}"
            logger.warning(msg)
            raise SnippenApiError(msg, status_code=status_code) from exc

        except urllib.error.URLError as exc:
            msg = f"Network failure connecting to Snippen API ({url}): {exc.reason}"
            logger.warning(msg)
            raise SnippenNetworkError(msg) from exc

        except TimeoutError as exc:
            msg = f"Timeout ({self.timeout_seconds}s) while connecting to Snippen API ({url})"
            logger.warning(msg)
            raise SnippenNetworkError(msg) from exc

        except Exception as exc:
            msg = f"Unexpected error during Snippen API request to {url}: {exc}"
            logger.error(msg)
            raise SnippenClientError(msg) from exc

    def fetch_pending_outbox(self) -> list[dict[str, Any]]:
        """Fetch pending outgoing SMS messages from Snippen to be dispatched."""
        data = self._request("GET", "outbox")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            messages = data.get("messages") or data.get("items") or data.get("data")
            if isinstance(messages, list):
                return messages
        return []

    def report_inbound_messages(self, messages: list[Message]) -> list[int]:
        """Report received inbound SMS messages to Snippen.

        Returns list of locally stored message database IDs that Snippen acknowledged.
        """
        if not messages:
            return []

        payload = {
            "messages": [
                {
                    "gateway_id": msg.id,
                    "sender": msg.sender,
                    "recipient": msg.recipient,
                    "body": msg.body,
                    "received_at": msg.created_at.isoformat(),
                    "modem_message_id": msg.modem_message_id,
                }
                for msg in messages
                if msg.id is not None
            ]
        }

        resp = self._request("POST", "inbox", payload=payload)

        # If response contains processed_ids list, return that; otherwise all submitted IDs
        if (
            isinstance(resp, dict)
            and "processed_ids" in resp
            and isinstance(resp["processed_ids"], list)
        ):
            return [int(x) for x in resp["processed_ids"]]

        return [msg.id for msg in messages if msg.id is not None]

    def report_outbox_status(self, statuses: list[dict[str, Any]]) -> bool:
        """Report SMS delivery statuses of outbound messages back to Snippen."""
        if not statuses:
            return True

        payload = {"statuses": statuses}
        _ = self._request("POST", "outbox/status", payload=payload)
        return True
