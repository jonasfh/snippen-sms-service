"""SQLite message storage layer for Snippen SMS Service."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from snippen_sms.migrations.runner import MigrationRunner
from snippen_sms.models import Message, MessageDirection, MessageStatus

logger = logging.getLogger("snippen_sms.storage")


class MessageStorage:
    """Persistent message repository backed by SQLite."""

    def __init__(
        self,
        db_path: str | Path = "data/sms_gateway.db",
        auto_migrate: bool = True,
    ) -> None:
        self.db_path = str(db_path)
        self.auto_migrate = auto_migrate
        self._conn: sqlite3.Connection | None = None
        # Ensure connection and schema are initialized
        _ = self.connection

    @property
    def connection(self) -> sqlite3.Connection:
        """Return active database connection, establishing and setting up schema if not open."""
        if self._conn is None:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if self.auto_migrate:
                self._setup_schema(conn)
            self._conn = conn
        return self._conn

    def _setup_schema(self, conn: sqlite3.Connection) -> None:
        """Initialize database schema and apply pending migrations."""
        runner = MigrationRunner(conn)
        runner.run_migrations()
        logger.debug(
            "MessageStorage initialized with backend: %s (schema v%d)",
            self.db_path,
            runner.get_current_version(),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        """Convert a database Row to a Message instance."""
        created_at_dt = datetime.fromisoformat(row["created_at"])
        if created_at_dt.tzinfo is None:
            created_at_dt = created_at_dt.replace(tzinfo=UTC)

        modified_at_dt = datetime.fromisoformat(row["modified_at"])
        if modified_at_dt.tzinfo is None:
            modified_at_dt = modified_at_dt.replace(tzinfo=UTC)

        return Message(
            id=row["id"],
            direction=MessageDirection(row["direction"]),
            sender=row["sender"],
            recipient=row["recipient"],
            body=row["body"],
            status=MessageStatus(row["status"]),
            modem_message_id=row["modem_message_id"],
            error_message=row["error_message"],
            created_at=created_at_dt,
            modified_at=modified_at_dt,
        )

    def save_message(self, message: Message) -> Message:
        """Save a new message or update an existing message."""
        now = datetime.now(UTC)
        conn = self.connection

        if message.id is None:
            message.created_at = message.created_at or now
            message.modified_at = now
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO messages (
                        direction, sender, recipient, body, status,
                        modem_message_id, error_message, created_at, modified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.direction.value,
                        message.sender,
                        message.recipient,
                        message.body,
                        message.status.value,
                        message.modem_message_id,
                        message.error_message,
                        message.created_at.isoformat(),
                        message.modified_at.isoformat(),
                    ),
                )
                message.id = cursor.lastrowid
            logger.debug("Saved new message with id=%s", message.id)
            return message

        message.modified_at = now
        with conn:
            conn.execute(
                """
                UPDATE messages SET
                    direction = ?,
                    sender = ?,
                    recipient = ?,
                    body = ?,
                    status = ?,
                    modem_message_id = ?,
                    error_message = ?,
                    modified_at = ?
                WHERE id = ?
                """,
                (
                    message.direction.value,
                    message.sender,
                    message.recipient,
                    message.body,
                    message.status.value,
                    message.modem_message_id,
                    message.error_message,
                    message.modified_at.isoformat(),
                    message.id,
                ),
            )
        logger.debug("Updated existing message with id=%s", message.id)
        return message

    def get_message(self, message_id: int) -> Message | None:
        """Retrieve a message by its ID."""
        cursor = self.connection.execute(
            "SELECT * FROM messages WHERE id = ?",
            (message_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    def get_message_by_modem_id(
        self,
        modem_message_id: str,
        direction: MessageDirection | str | None = None,
    ) -> Message | None:
        """Retrieve a message by its provider/modem message ID and optional direction."""
        query = "SELECT * FROM messages WHERE modem_message_id = ?"
        params: list[Any] = [modem_message_id]
        if direction is not None:
            dir_val = direction.value if isinstance(direction, MessageDirection) else str(direction)
            query += " AND direction = ?"
            params.append(dir_val)
        query += " ORDER BY id DESC LIMIT 1"
        cursor = self.connection.execute(query, tuple(params))
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    def list_messages(
        self,
        limit: int = 100,
        offset: int = 0,
        status: MessageStatus | str | None = None,
        direction: MessageDirection | str | None = None,
    ) -> list[Message]:
        """List messages with optional status and direction filtering and pagination."""
        query = "SELECT * FROM messages"
        conditions: list[str] = []
        params: list[Any] = []

        if status is not None:
            status_val = status.value if isinstance(status, MessageStatus) else str(status)
            conditions.append("status = ?")
            params.append(status_val)

        if direction is not None:
            dir_val = direction.value if isinstance(direction, MessageDirection) else str(direction)
            conditions.append("direction = ?")
            params.append(dir_val)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.connection.execute(query, tuple(params))
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def update_message_status(
        self,
        message_id: int,
        status: MessageStatus | str,
        error_message: str | None = None,
        modem_message_id: str | None = None,
    ) -> Message | None:
        """Update the status and optional metadata of a message."""
        status_val = status.value if isinstance(status, MessageStatus) else str(status)
        now = datetime.now(UTC).isoformat()

        # Build update dynamically to avoid overriding modem_message_id/error_message if None unless supplied
        update_clauses = ["status = ?", "modified_at = ?"]
        params: list[Any] = [status_val, now]

        if error_message is not None:
            update_clauses.append("error_message = ?")
            params.append(error_message)

        if modem_message_id is not None:
            update_clauses.append("modem_message_id = ?")
            params.append(modem_message_id)

        params.append(message_id)
        query = f"UPDATE messages SET {', '.join(update_clauses)} WHERE id = ?"

        with self.connection:
            cursor = self.connection.execute(query, tuple(params))
            if cursor.rowcount == 0:
                return None

        return self.get_message(message_id)

    def delete_message(self, message_id: int) -> bool:
        """Delete a message by its ID."""
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM messages WHERE id = ?",
                (message_id,),
            )
            return cursor.rowcount > 0

    def count_messages(
        self,
        status: MessageStatus | str | None = None,
        direction: MessageDirection | str | None = None,
    ) -> int:
        """Count total messages matching criteria."""
        query = "SELECT COUNT(*) FROM messages"
        conditions: list[str] = []
        params: list[Any] = []

        if status is not None:
            status_val = status.value if isinstance(status, MessageStatus) else str(status)
            conditions.append("status = ?")
            params.append(status_val)

        if direction is not None:
            dir_val = direction.value if isinstance(direction, MessageDirection) else str(direction)
            conditions.append("direction = ?")
            params.append(dir_val)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor = self.connection.execute(query, tuple(params))
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def enqueue_outbox(
        self,
        recipient: str,
        body: str,
        sender: str = "snippen-sms-service",
        status: MessageStatus = MessageStatus.PENDING,
    ) -> Message:
        """Add a new outbound message to the outbox."""
        message = Message(
            direction=MessageDirection.OUTBOUND,
            sender=sender,
            recipient=recipient,
            body=body,
            status=status,
        )
        return self.save_message(message)

    def get_pending_outbox(self, limit: int = 50) -> list[Message]:
        """Retrieve pending and queued messages from the outbox in FIFO order."""
        query = """
            SELECT * FROM messages
            WHERE direction = ? AND status IN (?, ?)
            ORDER BY id ASC
            LIMIT ?
        """
        cursor = self.connection.execute(
            query,
            (
                MessageDirection.OUTBOUND.value,
                MessageStatus.PENDING.value,
                MessageStatus.QUEUED.value,
                limit,
            ),
        )
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def get_outbox(
        self,
        limit: int = 100,
        offset: int = 0,
        status: MessageStatus | str | None = None,
    ) -> list[Message]:
        """Retrieve messages from the outbox with optional status filter."""
        return self.list_messages(
            limit=limit,
            offset=offset,
            status=status,
            direction=MessageDirection.OUTBOUND,
        )

    def get_inbox(
        self,
        limit: int = 100,
        offset: int = 0,
        status: MessageStatus | str | None = None,
    ) -> list[Message]:
        """Retrieve messages from the inbox with optional status filter."""
        return self.list_messages(
            limit=limit,
            offset=offset,
            status=status,
            direction=MessageDirection.INBOUND,
        )

    def get_unprocessed_inbox(self, limit: int = 100) -> list[Message]:
        """Retrieve unprocessed inbound messages in FIFO order."""
        query = """
            SELECT * FROM messages
            WHERE direction = ? AND status = ?
            ORDER BY id ASC
            LIMIT ?
        """
        cursor = self.connection.execute(
            query,
            (
                MessageDirection.INBOUND.value,
                MessageStatus.RECEIVED.value,
                limit,
            ),
        )
        return [self._row_to_message(row) for row in cursor.fetchall()]

    def mark_inbox_processed(self, message_id: int) -> Message | None:
        """Mark an inbound message as processed."""
        return self.update_message_status(
            message_id=message_id,
            status=MessageStatus.PROCESSED,
        )

    def count_outbox(self, status: MessageStatus | str | None = None) -> int:
        """Count messages in the outbox."""
        return self.count_messages(status=status, direction=MessageDirection.OUTBOUND)

    def count_inbox(self, status: MessageStatus | str | None = None) -> int:
        """Count messages in the inbox with optional status filter."""
        return self.count_messages(status=status, direction=MessageDirection.INBOUND)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Closed database connection for %s", self.db_path)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
