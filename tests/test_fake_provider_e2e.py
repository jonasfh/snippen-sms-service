"""End-to-end integration tests connecting GatewayService to a simulated Fake SMS Provider."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import pytest

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.models import MessageDirection, MessageStatus
from snippen_sms.storage import MessageStorage


class FakeSmsProviderSimulator(BaseHTTPRequestHandler):
    """Accurate in-memory HTTP server mimicking the fake SMS provider from snippen-testing."""

    messages: ClassVar[list[dict]] = []
    fail_next_outbound: ClassVar[bool] = False

    @classmethod
    def reset(cls) -> None:
        cls.messages = []
        cls.fail_next_outbound = False

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8")
        payload = json.loads(post_body) if post_body else {}

        # Outbound endpoint
        if parsed.path in ("/messages/outbound", "/sms/send", "/api/sms/send"):
            if self.__class__.fail_next_outbound:
                self.__class__.fail_next_outbound = False
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Simulated upstream provider outage"}')
                return

            recipient = payload.get("to") or payload.get("recipient")
            text = payload.get("text") or payload.get("message")
            sender = payload.get("from") or payload.get("sender") or "Snippen"

            if not recipient or not text:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Missing recipient or text"}')
                return

            msg_id = str(uuid.uuid4())
            record = {
                "id": msg_id,
                "direction": "outbound",
                "to": recipient,
                "from": sender,
                "text": text,
                "status": "sent",
                "createdAt": "2026-09-01T14:00:00.000Z",
                "metadata": payload.get("metadata", {}),
            }
            self.__class__.messages.append(record)

            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(record).encode("utf-8"))
            return

        # Test injection endpoint for inbound SMS
        if parsed.path in ("/messages/inbound", "/simulate/inbound"):
            sender = payload.get("from") or payload.get("sender")
            text = payload.get("text") or payload.get("message")
            recipient = payload.get("to") or payload.get("recipient")

            msg_id = str(uuid.uuid4())
            record = {
                "id": msg_id,
                "direction": "inbound",
                "from": sender,
                "to": recipient,
                "text": text,
                "status": "received",
                "createdAt": "2026-09-01T14:05:00.000Z",
                "metadata": payload.get("metadata", {}),
            }
            self.__class__.messages.append(record)

            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": record}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path in ("/messages", "/api/messages"):
            direction_filter = qs.get("direction", [None])[0]
            matched = self.__class__.messages
            if direction_filter:
                matched = [m for m in matched if m.get("direction") == direction_filter]

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"messages": matched, "count": len(matched)}).encode("utf-8")
            )
            return

        self.send_response(404)
        self.end_headers()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/messages", "/api/messages"):
            count = len(self.__class__.messages)
            self.__class__.messages = []
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"message": "All messages cleared", "count": count}).encode("utf-8")
            )
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress standard HTTP server logging."""


@pytest.fixture
def fake_provider_server():
    """Spin up local fake provider HTTP server."""
    FakeSmsProviderSimulator.reset()
    server = HTTPServer(("127.0.0.1", 0), FakeSmsProviderSimulator)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_e2e_outbound_sms_to_fake_provider(tmp_path, fake_provider_server):
    """Verify that an outbound SMS is dispatched to the fake provider and status transitions to 'sent'."""

    async def _test():
        db_path = str(tmp_path / "test_e2e_gateway.db")
        config = GatewayConfig(
            provider="fake",
            provider_url=fake_provider_server,
            database_path=db_path,
            sync_enabled=False,
        )
        storage = MessageStorage(db_path)
        gateway = GatewayService(config=config, storage=storage)

        await gateway.start()

        # Enqueue an outbound message
        msg = gateway.enqueue_outbox(
            recipient="+4791234567",
            body="Velkommen til Snippen! Din kode er 9911",
            sender="Snippen",
        )
        assert msg.id is not None
        assert msg.status == MessageStatus.PENDING

        # Process outbox
        processed = await gateway.process_outbox()
        assert len(processed) == 1
        assert processed[0].status == MessageStatus.SENT
        assert processed[0].modem_message_id is not None

        # Check fake provider received the message
        stored_in_provider = FakeSmsProviderSimulator.messages
        assert len(stored_in_provider) == 1
        assert stored_in_provider[0]["to"] == "+4791234567"
        assert stored_in_provider[0]["text"] == "Velkommen til Snippen! Din kode er 9911"
        assert stored_in_provider[0]["id"] == processed[0].modem_message_id

        await gateway.stop()

    asyncio.run(_test())


def test_e2e_inbound_sms_polling_and_deduplication(tmp_path, fake_provider_server):
    """Verify inbound SMS injection, polling, ingestion with 'received' status, and deduplication."""

    async def _test():
        db_path = str(tmp_path / "test_e2e_inbound.db")
        config = GatewayConfig(
            provider="fake",
            provider_url=fake_provider_server,
            database_path=db_path,
            sync_enabled=False,
            booking_resolution_enabled=False,
        )
        storage = MessageStorage(db_path)
        gateway = GatewayService(config=config, storage=storage)

        await gateway.start()

        # Inject an inbound message into fake provider
        injected_id = str(uuid.uuid4())
        FakeSmsProviderSimulator.messages.append(
            {
                "id": injected_id,
                "direction": "inbound",
                "from": "+4799887766",
                "to": "Snippen",
                "text": "Hei, når åpner døren?",
                "status": "received",
                "createdAt": "2026-09-01T14:10:00.000Z",
            }
        )

        # Poll incoming messages
        received_msgs = await gateway.poll_incoming_messages()
        assert len(received_msgs) == 1
        assert received_msgs[0].sender == "+4799887766"
        assert received_msgs[0].body == "Hei, når åpner døren?"
        assert received_msgs[0].direction == MessageDirection.INBOUND
        assert received_msgs[0].status == MessageStatus.RECEIVED
        assert received_msgs[0].modem_message_id == injected_id

        # Verify message is persisted in local database
        inbox_messages = storage.get_inbox()
        assert len(inbox_messages) == 1
        assert inbox_messages[0].modem_message_id == injected_id

        # Poll again - should deduplicate and return 0 new messages
        second_poll = await gateway.poll_incoming_messages()
        assert len(second_poll) == 0

        # Total inbox in storage should still be 1
        assert storage.count_inbox() == 1

        await gateway.stop()

    asyncio.run(_test())


def test_e2e_outbound_failure_transitions_to_failed(tmp_path, fake_provider_server):
    """Verify that when provider returns 500 or fails, outbox status transitions to 'failed'."""

    async def _test():
        db_path = str(tmp_path / "test_e2e_failed.db")
        config = GatewayConfig(
            provider="fake",
            provider_url=fake_provider_server,
            database_path=db_path,
            sync_enabled=False,
        )
        storage = MessageStorage(db_path)
        gateway = GatewayService(config=config, storage=storage)

        await gateway.start()

        # Trigger failure on next request
        FakeSmsProviderSimulator.fail_next_outbound = True

        msg = gateway.enqueue_outbox(
            recipient="+4791234567",
            body="Feilende melding test",
        )
        assert msg.id is not None

        processed = await gateway.process_outbox()
        assert len(processed) == 1
        assert processed[0].status == MessageStatus.FAILED
        assert "500" in (processed[0].error_message or "")

        await gateway.stop()

    asyncio.run(_test())
