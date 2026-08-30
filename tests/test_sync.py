"""Unit tests for SyncService coordinating storage and API synchronization."""

from __future__ import annotations

from unittest.mock import MagicMock

from snippen_sms.client import SnippenClient, SnippenNetworkError
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.storage import MessageStorage
from snippen_sms.sync import SyncService


def test_sync_inbox_success() -> None:
    """Test reporting unhandled inbound messages and transitioning them to PROCESSED."""
    storage = MessageStorage(":memory:")
    msg1 = storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4790000001",
            recipient="snippen-sms-service",
            body="JA",
            status=MessageStatus.RECEIVED,
        )
    )
    msg2 = storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4790000002",
            recipient="snippen-sms-service",
            body="NEI",
            status=MessageStatus.RECEIVED,
        )
    )

    mock_client = MagicMock(spec=SnippenClient)
    assert msg1.id is not None
    assert msg2.id is not None
    mock_client.report_inbound_messages.return_value = [msg1.id, msg2.id]

    sync = SyncService(storage=storage, client=mock_client)
    acked = sync.sync_inbox()

    assert acked == [msg1.id, msg2.id]
    mock_client.report_inbound_messages.assert_called_once()

    # Verify both messages are marked PROCESSED in DB
    updated1 = storage.get_message(msg1.id)
    updated2 = storage.get_message(msg2.id)
    assert updated1 is not None and updated1.status == MessageStatus.PROCESSED
    assert updated2 is not None and updated2.status == MessageStatus.PROCESSED


def test_sync_inbox_failure_resilience() -> None:
    """Test that inbound messages remain RECEIVED if network reporting fails."""
    storage = MessageStorage(":memory:")
    msg = storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4790000001",
            recipient="snippen-sms-service",
            body="JA",
            status=MessageStatus.RECEIVED,
        )
    )

    mock_client = MagicMock(spec=SnippenClient)
    mock_client.report_inbound_messages.side_effect = SnippenNetworkError("Connection refused")

    sync = SyncService(storage=storage, client=mock_client)
    res = sync.sync_all()

    assert res["inbox_synced"] == 0
    assert "Connection refused" in (res["error"] or "")

    # Message must NOT be marked processed or lost
    assert msg.id is not None
    stored_msg = storage.get_message(msg.id)
    assert stored_msg is not None and stored_msg.status == MessageStatus.RECEIVED


def test_sync_outbox_success_and_deduplication() -> None:
    """Test fetching outbox messages from Snippen and preventing duplicates."""
    storage = MessageStorage(":memory:")
    mock_client = MagicMock(spec=SnippenClient)
    mock_client.fetch_pending_outbox.return_value = [
        {
            "id": "ext-101",
            "recipient": "+4791111111",
            "body": "Welcome to Snippen!",
            "sender": "Snippen",
        },
        {
            "id": "ext-102",
            "recipient": "+4792222222",
            "body": "Door code: 1234",
        },
    ]

    sync = SyncService(storage=storage, client=mock_client)
    enqueued = sync.sync_outbox()

    assert len(enqueued) == 2
    assert enqueued[0].external_id == "ext-101"
    assert enqueued[0].status == MessageStatus.PENDING
    assert enqueued[1].external_id == "ext-102"
    assert enqueued[1].status == MessageStatus.PENDING

    # Second sync tick with duplicate items from Snippen
    mock_client.fetch_pending_outbox.return_value = [
        {
            "id": "ext-101",
            "recipient": "+4791111111",
            "body": "Welcome to Snippen!",
        },
        {
            "id": "ext-103",
            "recipient": "+4793333333",
            "body": "New message",
        },
    ]

    enqueued_second = sync.sync_outbox()
    # ext-101 should be skipped, only ext-103 enqueued
    assert len(enqueued_second) == 1
    assert enqueued_second[0].external_id == "ext-103"
    assert storage.count_outbox() == 3


def test_sync_statuses_reporting() -> None:
    """Test reporting SENT and FAILED message statuses back to Snippen."""
    storage = MessageStorage(":memory:")
    sent_msg = storage.enqueue_outbox(
        recipient="+4791111111",
        body="Booking confirmed",
        external_id="ext-sent-1",
        status=MessageStatus.SENT,
    )
    failed_msg = storage.enqueue_outbox(
        recipient="+4792222222",
        body="Door code",
        external_id="ext-fail-1",
        status=MessageStatus.FAILED,
    )

    assert sent_msg.id is not None
    assert failed_msg.id is not None
    storage.update_message_status(
        failed_msg.id,
        status=MessageStatus.FAILED,
        error_message="Modem timeout",
    )

    mock_client = MagicMock(spec=SnippenClient)
    sync = SyncService(storage=storage, client=mock_client)

    reported_count = sync.sync_statuses()
    assert reported_count == 2
    mock_client.report_outbox_status.assert_called_once()

    # Sent message should transition to DELIVERED
    updated_sent = storage.get_message(sent_msg.id)
    assert updated_sent is not None and updated_sent.status == MessageStatus.DELIVERED

    # Subsequent sync should report 0 messages
    reported_second = sync.sync_statuses()
    assert reported_second == 0


def test_sync_all_e2e() -> None:
    """Test complete sync cycle execution."""
    storage = MessageStorage(":memory:")
    mock_client = MagicMock(spec=SnippenClient)
    mock_client.fetch_pending_outbox.return_value = [
        {"id": "ext-1", "recipient": "+4799999999", "body": "Hello"}
    ]
    mock_client.report_inbound_messages.return_value = []
    mock_client.report_outbox_status.return_value = True

    sync = SyncService(storage=storage, client=mock_client)
    res = sync.sync_all()

    assert res["inbox_synced"] == 0
    assert res["outbox_enqueued"] == 1
    assert res["statuses_reported"] == 0
    assert res["error"] is None
