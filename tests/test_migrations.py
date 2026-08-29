"""Unit and integration tests for database migration management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from snippen_sms.main import build_parser, handle_migrate, handle_migrate_status
from snippen_sms.migrations import Migration, MigrationError, MigrationRunner
from snippen_sms.storage import MessageStorage


def test_migration_from_file(tmp_path: Path) -> None:
    """Test loading and parsing a migration script from file."""
    sql_content = "CREATE TABLE dummy (id INTEGER PRIMARY KEY);"
    mig_file = tmp_path / "0001_create_dummy.sql"
    mig_file.write_text(sql_content, encoding="utf-8")

    mig = Migration.from_file(mig_file)
    assert mig.version == 1
    assert mig.name == "create_dummy"
    assert mig.sql == sql_content
    assert len(mig.checksum) == 64  # SHA-256


def test_migration_from_file_invalid_name(tmp_path: Path) -> None:
    """Test that invalid migration filename raises ValueError."""
    invalid_file = tmp_path / "invalid_name.sql"
    invalid_file.write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid migration filename format"):
        Migration.from_file(invalid_file)


def test_migration_runner_fresh_memory_db() -> None:
    """Test running migrations on a fresh in-memory database."""
    conn = sqlite3.connect(":memory:")
    runner = MigrationRunner(conn)

    assert runner.get_current_version() == 0
    assert len(runner.get_applied_migrations()) == 0

    pending = runner.get_pending_migrations()
    assert len(pending) >= 1
    assert pending[0].version == 1
    assert pending[0].name == "initial_messages_schema"

    applied = runner.run_migrations()
    assert len(applied) >= 1
    assert runner.get_current_version() >= 1

    applied_list = runner.get_applied_migrations()
    assert len(applied_list) >= 1
    assert applied_list[0]["version"] == 1

    # Verify tables and indexes exist
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages';")
    assert cursor.fetchone() is not None

    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
    )
    assert cursor.fetchone() is not None


def test_migration_idempotency(tmp_path: Path) -> None:
    """Test that running migrations multiple times is idempotent."""
    db_file = tmp_path / "test_idempotent.db"
    runner = MigrationRunner(db_file)

    first_run = runner.run_migrations()
    assert len(first_run) >= 1
    current_ver = runner.get_current_version()

    second_run = runner.run_migrations()
    assert len(second_run) == 0
    assert runner.get_current_version() == current_ver
    runner.close()


def test_incremental_migrations(tmp_path: Path) -> None:
    """Test applying multiple sequential migrations."""
    mig_dir = tmp_path / "migrations"
    mig_dir.mkdir()

    (mig_dir / "0001_first.sql").write_text(
        "CREATE TABLE test_one (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, modified_at TEXT NOT NULL);",
        encoding="utf-8",
    )
    (mig_dir / "0002_second.sql").write_text(
        "CREATE TABLE test_two (id INTEGER PRIMARY KEY, title TEXT, created_at TEXT NOT NULL, modified_at TEXT NOT NULL);",
        encoding="utf-8",
    )

    db_file = tmp_path / "incremental.db"
    with MigrationRunner(db_file, migrations_dir=mig_dir) as runner:
        # Migrate up to version 1 only
        applied_v1 = runner.run_migrations(target_version=1)
        assert len(applied_v1) == 1
        assert runner.get_current_version() == 1

        pending = runner.get_pending_migrations()
        assert len(pending) == 1
        assert pending[0].version == 2

        # Migrate remaining
        applied_v2 = runner.run_migrations()
        assert len(applied_v2) == 1
        assert runner.get_current_version() == 2


def test_migration_error_and_rollback(tmp_path: Path) -> None:
    """Test that a failing migration rolls back and raises MigrationError."""
    mig_dir = tmp_path / "migrations_fail"
    mig_dir.mkdir()

    (mig_dir / "0001_good.sql").write_text(
        "CREATE TABLE table_ok (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    (mig_dir / "0002_bad.sql").write_text(
        "CREATE TABLE table_bad (id INTEGER PRIMARY KEY);\nINVALID SQL SYNTAX HERE;",
        encoding="utf-8",
    )

    db_file = tmp_path / "fail.db"
    with MigrationRunner(db_file, migrations_dir=mig_dir) as runner:
        # First good migration
        runner.apply_migration(Migration.from_file(mig_dir / "0001_good.sql"))
        assert runner.get_current_version() == 1

        # Second bad migration
        with pytest.raises(MigrationError, match="Failed to apply migration"):
            runner.apply_migration(Migration.from_file(mig_dir / "0002_bad.sql"))

        # Version should still be 1, and table_bad should not exist
        assert runner.get_current_version() == 1
        cursor = runner.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='table_bad';"
        )
        assert cursor.fetchone() is None


def test_baseline_existing_database(tmp_path: Path) -> None:
    """Test baselining an existing database that was created before migration system."""
    db_file = tmp_path / "existing.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            direction TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            modem_message_id TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            modified_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()

    # Now open with MigrationRunner
    with MigrationRunner(db_file) as runner:
        baselined = runner.baseline_existing_database()
        assert baselined is True
        assert runner.get_current_version() == 1

        # Subsequent baseline call returns False
        assert runner.baseline_existing_database() is False


def test_storage_auto_migration_disabled(tmp_path: Path) -> None:
    """Test MessageStorage with auto_migrate=False does not execute migrations."""
    db_file = tmp_path / "no_migrate.db"
    storage = MessageStorage(db_file, auto_migrate=False)
    cursor = storage.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages';"
    )
    assert cursor.fetchone() is None
    storage.close()


def test_storage_auto_migration_enabled(tmp_path: Path) -> None:
    """Test MessageStorage with auto_migrate=True automatically sets up schema."""
    db_file = tmp_path / "auto_migrate.db"
    storage = MessageStorage(db_file, auto_migrate=True)
    cursor = storage.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='messages';"
    )
    assert cursor.fetchone() is not None
    cursor = storage.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations';"
    )
    assert cursor.fetchone() is not None
    storage.close()


def test_cli_migrate_handlers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test CLI handle_migrate and handle_migrate_status."""
    db_file = str(tmp_path / "cli_test.db")

    # Initial status (not migrated)
    code = handle_migrate_status(db_file)
    assert code == 0
    captured = capsys.readouterr()
    assert "Pending Migrations (1)" in captured.out

    # Run migration
    code = handle_migrate(db_file)
    assert code == 0
    captured = capsys.readouterr()
    assert "Applied 1 migration(s)" in captured.out

    # Run migration again (up to date)
    code = handle_migrate(db_file)
    assert code == 0
    captured = capsys.readouterr()
    assert "already up to date" in captured.out

    # Check status after migration
    code = handle_migrate_status(db_file)
    assert code == 0
    captured = capsys.readouterr()
    assert "Applied Migrations (1)" in captured.out
    assert "0001" in captured.out
    assert "Pending Migrations (0)" in captured.out


def test_cli_parser() -> None:
    """Test argument parser subcommands and flags."""
    parser = build_parser()

    args_run = parser.parse_args(["run", "--poll-interval", "3.5"])
    assert args_run.command == "run"
    assert args_run.poll_interval == 3.5

    args_migrate = parser.parse_args(
        ["migrate", "--database-path", "custom.db", "--target-version", "2"]
    )
    assert args_migrate.command == "migrate"
    assert args_migrate.database_path == "custom.db"
    assert args_migrate.target_version == 2

    args_status = parser.parse_args(["migrate-status", "--database-path", "custom.db"])
    assert args_status.command == "migrate-status"
    assert args_status.database_path == "custom.db"
