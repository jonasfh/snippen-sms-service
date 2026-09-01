"""HTTP SMS provider for external and simulated SMS gateways (e.g. snippen-testing)."""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from snippen_sms import __version__
from snippen_sms.providers.base import IncomingMessage, SendResult, SmsProvider

logger = logging.getLogger("snippen_sms.providers.http")


class HttpSmsProvider(SmsProvider):
    """SMS provider communicating via HTTP REST APIs (compatible with snippen-testing fake SMS provider)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:3000",
        timeout_seconds: float = 10.0,
        sender_id: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (base_url or "http://127.0.0.1:3000").rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.sender_id = sender_id
        self.api_key = api_key

    def _sync_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Execute synchronous HTTP request with error translation."""
        subpath = path.lstrip("/")
        url = f"{self.base_url}/{subpath}"
        if query_params:
            encoded_params = urllib.parse.urlencode(query_params)
            url = f"{url}?{encoded_params}"

        headers = {
            "Accept": "application/json",
            "User-Agent": f"snippen-sms-service/{__version__}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key

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
                    return status_code, {}
                try:
                    return status_code, json.loads(raw_body)
                except json.JSONDecodeError:
                    return status_code, {"raw": raw_body}

        except urllib.error.HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                pass
            raise RuntimeError(
                f"HTTP {exc.code} from {method.upper()} {url}: {error_body or exc.reason}"
            ) from exc

        except urllib.error.URLError as exc:
            raise ConnectionError(f"Connection failed to {url}: {exc.reason}") from exc

        except TimeoutError as exc:
            raise TimeoutError(f"Request to {url} timed out after {self.timeout_seconds}s") from exc

    async def _async_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Execute request non-blockingly using thread pool."""
        return await asyncio.to_thread(self._sync_request, method, path, payload, query_params)

    async def open(self) -> None:
        """Initialize provider interface."""
        logger.debug("Initialized HttpSmsProvider targeting %s", self.base_url)

    async def close(self) -> None:
        """Release provider resources."""
        logger.debug("Closed HttpSmsProvider targeting %s", self.base_url)

    async def send_sms(self, recipient: str, body: str) -> SendResult:
        """Send an SMS message via HTTP to the remote provider gateway.

        Args:
            recipient: The destination phone number.
            body: The text message content.

        Returns:
            SendResult indicating status and message reference or error details.
        """
        payload: dict[str, Any] = {
            "to": recipient.strip(),
            "text": body.strip(),
        }
        if self.sender_id:
            payload["from"] = self.sender_id.strip()

        try:
            status_code, response_data = await self._async_request(
                method="POST",
                path="messages/outbound",
                payload=payload,
            )

            if status_code in (200, 201):
                msg_id = None
                if isinstance(response_data, dict):
                    msg_id = (
                        response_data.get("id")
                        or response_data.get("message_id")
                        or response_data.get("messageId")
                    )
                provider_msg_id = str(msg_id) if msg_id is not None else None
                logger.info(
                    "Successfully transmitted SMS to %s via %s (Provider ID: %s)",
                    recipient,
                    self.base_url,
                    provider_msg_id,
                )
                return SendResult(success=True, message_id=provider_msg_id)

            err_msg = f"Unexpected response status {status_code} from provider"
            logger.warning("Failed to send SMS to %s: %s", recipient, err_msg)
            return SendResult(success=False, error_message=err_msg)

        except Exception as exc:  # noqa: BLE001
            err_msg = str(exc)
            logger.warning("Error sending SMS to %s via %s: %s", recipient, self.base_url, err_msg)
            return SendResult(success=False, error_message=err_msg)

    async def receive_sms(self) -> list[IncomingMessage]:
        """Fetch and drain pending incoming SMS messages from the HTTP provider.

        Returns:
            List of IncomingMessage instances retrieved from provider.
        """
        try:
            status_code, response_data = await self._async_request(
                method="GET",
                path="messages",
                query_params={"direction": "inbound"},
            )

            if status_code != 200:
                logger.warning(
                    "Provider returned HTTP %s when polling inbound messages", status_code
                )
                return []

            raw_messages: list[dict[str, Any]] = []
            if isinstance(response_data, list):
                raw_messages = response_data
            elif isinstance(response_data, dict):
                items = (
                    response_data.get("messages")
                    or response_data.get("items")
                    or response_data.get("data")
                )
                if isinstance(items, list):
                    raw_messages = items

            inbound_list: list[IncomingMessage] = []
            for item in raw_messages:
                sender = str(item.get("from") or item.get("sender") or "").strip()
                text = str(
                    item.get("text") or item.get("message") or item.get("body") or ""
                ).strip()

                if not sender or not text:
                    continue

                provider_msg_id = item.get("id") or item.get("message_id")
                str_msg_id = str(provider_msg_id) if provider_msg_id is not None else None

                created_raw = (
                    item.get("createdAt") or item.get("created_at") or item.get("timestamp")
                )
                received_dt = datetime.now(UTC)
                if created_raw:
                    try:
                        parsed_dt = datetime.fromisoformat(str(created_raw))
                        if parsed_dt.tzinfo is None:
                            parsed_dt = parsed_dt.replace(tzinfo=UTC)
                        received_dt = parsed_dt
                    except (ValueError, TypeError) as parse_exc:
                        logger.debug("Could not parse timestamp %s: %s", created_raw, parse_exc)

                inbound_list.append(
                    IncomingMessage(
                        sender=sender,
                        body=text,
                        received_at=received_dt,
                        provider_message_id=str_msg_id,
                    )
                )

            return inbound_list

        except Exception as exc:  # noqa: BLE001
            logger.warning("Error polling incoming SMS messages from %s: %s", self.base_url, exc)
            return []
