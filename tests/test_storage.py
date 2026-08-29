"""Unit and integration tests for SQLite message storage."""

from __future__ import annotations

import time
from datetime import UTC
from pathlib import Path

import pytest

from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.storage import MessageStorage


@pytest.fixture
def memory_storage() -> MessageStorage:
    """Create an in-memory MessageStorage instance."""
    storage = MessageStorage(":memory:")
    yield storage
    storage.close()


def test_models_enum_coercion_and_to_dict() -> None:
    """Test Message model validation and dict serialization."""
    msg = Message(
        direction="inbound",  # type: ignore[arg-type]
        sender="+4712345678",
        recipient="+4787654321",
        body="Hei fra gjest",
        status="received",  # type: ignore[arg-type]
    )
    assert msg.direction == MessageDirection.INBOUND
    assert msg.status == MessageStatus.RECEIVED
    assert msg.created_at.tzinfo == UTC
    assert msg.modified_at.tzinfo == UTC

    d = msg.to_dict()
    assert d["direction"] == "inbound"
    assert d["status"] == "received"
    assert d["sender"] == "+4712345678"
    assert d["body"] == "Hei fra gjest"


def test_storage_initialization_memory(memory_storage: MessageStorage) -> None:
    """Test initializing storage in memory creates tables and indexes."""
    assert memory_storage.connection is not None
    cursor = memory_storage.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages';"
    )
    assert cursor.fetchone() is not None

    # Verify schema_migrations table and version
    cursor = memory_storage.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
    )
    assert cursor.fetchone() is not None

    cursor = memory_storage.connection.execute("PRAGMA user_version;")
    assert cursor.fetchone()[0] >= 1


def test_storage_initialization_file(tmp_path: Path) -> None:
    """Test initializing storage on disk creates directories and files."""
    db_file = tmp_path / "sub" / "dir" / "test.db"
    storage = MessageStorage(db_file)
    assert db_file.exists()
    storage.close()


def test_save_and_get_message(memory_storage: MessageStorage) -> None:
    """Test saving a new message and retrieving it by ID."""
    msg = Message(
        direction=MessageDirection.OUTBOUND,
        sender="Snippen",
        recipient="+4799887766",
        body="Din booking er bekreftet.",
        status=MessageStatus.PENDING,
    )
    saved = memory_storage.save_message(msg)
    assert saved.id is not None
    assert saved.id > 0
    assert saved.created_at is not None
    assert saved.modified_at is not None

    retrieved = memory_storage.get_message(saved.id)
    assert retrieved is not None
    assert retrieved.id == saved.id
    assert retrieved.direction == MessageDirection.OUTBOUND
    assert retrieved.sender == "Snippen"
    assert retrieved.recipient == "+4799887766"
    assert retrieved.body == "Din booking er bekreftet."
    assert retrieved.status == MessageStatus.PENDING
    assert retrieved.created_at.tzinfo == UTC
    assert retrieved.modified_at.tzinfo == UTC


def test_get_nonexistent_message(memory_storage: MessageStorage) -> None:
    """Test retrieving a non-existent message returns None."""
    assert memory_storage.get_message(99999) is None


def test_update_existing_message_via_save(memory_storage: MessageStorage) -> None:
    """Test updating an already saved message updates modified_at."""
    msg = Message(
        direction=MessageDirection.OUTBOUND,
        sender="Snippen",
        recipient="+4799887766",
        body="Initial",
        status=MessageStatus.PENDING,
    )
    saved = memory_storage.save_message(msg)
    initial_modified_at = saved.modified_at

    time.sleep(0.01)
    saved.body = "Updated body"
    saved.status = MessageStatus.SENT
    saved.modem_message_id = "modem-123"

    updated = memory_storage.save_message(saved)
    assert updated.id == saved.id
    assert updated.body == "Updated body"
    assert updated.status == MessageStatus.SENT
    assert updated.modem_message_id == "modem-123"
    assert updated.modified_at >= initial_modified_at

    fetched = memory_storage.get_message(saved.id)
    assert fetched is not None
    assert fetched.body == "Updated body"
    assert fetched.status == MessageStatus.SENT
    assert fetched.modem_message_id == "modem-123"


def test_update_message_status(memory_storage: MessageStorage) -> None:
    """Test helper method update_message_status."""
    msg = Message(
        direction=MessageDirection.OUTBOUND,
        sender="Snippen",
        recipient="+4799887766",
        body="Testing status update",
        status=MessageStatus.PENDING,
    )
    saved = memory_storage.save_message(msg)
    assert saved.id is not None

    updated = memory_storage.update_message_status(
        saved.id,
        status=MessageStatus.FAILED,
        error_message="Modem timed out",
    )
    assert updated is not None
    assert updated.status == MessageStatus.FAILED
    assert updated.error_message == "Modem timed out"

    # Non-existent ID returns None
    assert memory_storage.update_message_status(999, MessageStatus.SENT) is None


def test_list_messages_and_filtering(memory_storage: MessageStorage) -> None:
    """Test listing messages with filtering and pagination."""
    memory_storage.save_message(
        Message(
            direction=MessageDirection.OUTBOUND,
            sender="Snippen",
            recipient="+4711111111",
            body="Out 1",
            status=MessageStatus.SENT,
        )
    )
    memory_storage.save_message(
        Message(
            direction=MessageDirection.OUTBOUND,
            sender="Snippen",
            recipient="+4722222222",
            body="Out 2",
            status=MessageStatus.PENDING,
        )
    )
    memory_storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4733333333",
            recipient="Snippen",
            body="In 1",
            status=MessageStatus.RECEIVED,
        )
    )

    # All messages
    all_msgs = memory_storage.list_messages()
    assert len(all_msgs) == 3

    # Filter by status
    sent_msgs = memory_storage.list_messages(status=MessageStatus.SENT)
    assert len(sent_msgs) == 1
    assert sent_msgs[0].recipient == "+4711111111"

    # Filter by direction
    inbound_msgs = memory_storage.list_messages(direction=MessageDirection.INBOUND)
    assert len(inbound_msgs) == 1
    assert inbound_msgs[0].sender == "+4733333333"

    # Pagination
    paged = memory_storage.list_messages(limit=2, offset=1)
    assert len(paged) == 2


def test_delete_message(memory_storage: MessageStorage) -> None:
    """Test deleting messages by ID."""
    msg = memory_storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4711223344",
            recipient="Snippen",
            body="Delete me",
            status=MessageStatus.RECEIVED,
        )
    )
    assert msg.id is not None
    assert memory_storage.delete_message(msg.id) is True
    assert memory_storage.get_message(msg.id) is None
    assert memory_storage.delete_message(msg.id) is False


def test_count_messages(memory_storage: MessageStorage) -> None:
    """Test counting messages with filters."""
    assert memory_storage.count_messages() == 0

    memory_storage.save_message(
        Message(
            direction=MessageDirection.OUTBOUND,
            sender="Snippen",
            recipient="+47111",
            body="1",
            status=MessageStatus.PENDING,
        )
    )
    memory_storage.save_message(
        Message(
            direction=MessageDirection.OUTBOUND,
            sender="Snippen",
            recipient="+47222",
            body="2",
            status=MessageStatus.SENT,
        )
    )

    assert memory_storage.count_messages() == 2
    assert memory_storage.count_messages(status=MessageStatus.PENDING) == 1
    assert memory_storage.count_messages(direction=MessageDirection.INBOUND) == 0


def test_persistence_survives_restart(tmp_path: Path) -> None:
    """Test that message data persists to disk and survives service/storage restart."""
    db_file = tmp_path / "persistent_messages.db"

    # First session - write messages
    storage1 = MessageStorage(db_file)
    msg1 = storage1.save_message(
        Message(
            direction=MessageDirection.OUTBOUND,
            sender="Snippen",
            recipient="+4790000000",
            body="Persistent SMS content",
            status=MessageStatus.QUEUED,
        )
    )
    msg2 = storage1.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4791111111",
            recipient="Snippen",
            body="Persistent reply content",
            status=MessageStatus.RECEIVED,
        )
    )
    msg1_id = msg1.id
    msg2_id = msg2.id
    storage1.close()

    # Second session - simulate gateway restart and reload from database file
    storage2 = MessageStorage(db_file)
    assert storage2.count_messages() == 2

    reloaded_msg1 = storage2.get_message(msg1_id)  # type: ignore[arg-type]
    assert reloaded_msg1 is not None
    assert reloaded_msg1.body == "Persistent SMS content"
    assert reloaded_msg1.status == MessageStatus.QUEUED
    assert reloaded_msg1.direction == MessageDirection.OUTBOUND

    reloaded_msg2 = storage2.get_message(msg2_id)  # type: ignore[arg-type]
    assert reloaded_msg2 is not None
    assert reloaded_msg2.body == "Persistent reply content"
    assert reloaded_msg2.status == MessageStatus.RECEIVED
    assert reloaded_msg2.direction == MessageDirection.INBOUND

    storage2.close()


def test_context_manager(tmp_path: Path) -> None:
    """Test MessageStorage context manager usage."""
    db_file = tmp_path / "ctx.db"
    with MessageStorage(db_file) as storage:
        storage.save_message(
            Message(
                direction=MessageDirection.OUTBOUND,
                sender="Snippen",
                recipient="+4799999999",
                body="Context test",
                status=MessageStatus.PENDING,
            )
        )
        assert storage.count_messages() == 1


def test_storage_outbox_helpers(memory_storage: MessageStorage) -> None:
    """Test enqueue_outbox, get_pending_outbox, get_outbox, and count_outbox."""
    assert memory_storage.count_outbox() == 0
    assert memory_storage.get_pending_outbox() == []

    # Enqueue 3 outbound messages
    msg1 = memory_storage.enqueue_outbox(
        recipient="+4790000001",
        body="Pending msg 1",
        sender="Snippen",
        status=MessageStatus.PENDING,
    )
    msg2 = memory_storage.enqueue_outbox(
        recipient="+4790000002",
        body="Queued msg 2",
        sender="Snippen",
        status=MessageStatus.QUEUED,
    )
    msg3 = memory_storage.enqueue_outbox(
        recipient="+4790000003",
        body="Sent msg 3",
        sender="Snippen",
        status=MessageStatus.SENT,
    )

    assert msg1.id is not None
    assert msg2.id is not None
    assert msg3.id is not None
    assert memory_storage.count_outbox() == 3
    assert memory_storage.count_outbox(status=MessageStatus.PENDING) == 1
    assert memory_storage.count_outbox(status=MessageStatus.QUEUED) == 1
    assert memory_storage.count_outbox(status=MessageStatus.SENT) == 1

    # get_pending_outbox should return FIFO order of PENDING and QUEUED messages
    pending = memory_storage.get_pending_outbox()
    assert len(pending) == 2
    assert pending[0].id == msg1.id
    assert pending[0].body == "Pending msg 1"
    assert pending[1].id == msg2.id
    assert pending[1].body == "Queued msg 2"

    # get_outbox should list outbound messages ordered by id DESC
    outbox_all = memory_storage.get_outbox()
    assert len(outbox_all) == 3
    assert outbox_all[0].id == msg3.id

    outbox_filtered = memory_storage.get_outbox(status=MessageStatus.SENT)
    assert len(outbox_filtered) == 1
    assert outbox_filtered[0].id == msg3.id


def test_storage_inbox_helpers(memory_storage: MessageStorage) -> None:
    """Test get_inbox and count_inbox."""
    assert memory_storage.count_inbox() == 0
    assert memory_storage.get_inbox() == []

    memory_storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4791112233",
            recipient="Snippen",
            body="Inbound 1",
            status=MessageStatus.RECEIVED,
        )
    )
    memory_storage.save_message(
        Message(
            direction=MessageDirection.INBOUND,
            sender="+4791112244",
            recipient="Snippen",
            body="Inbound 2",
            status=MessageStatus.RECEIVED,
        )
    )
    # Also save an outbound message to ensure separation
    memory_storage.enqueue_outbox(recipient="+4791112255", body="Outbound")

    assert memory_storage.count_inbox() == 2
    inbox = memory_storage.get_inbox()
    assert len(inbox) == 2
    assert inbox[0].sender == "+4791112244"
    assert inbox[1].sender == "+4791112233"
