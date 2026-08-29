"""Database migration runner and version management for SQLite."""

from __future__ import annotations

import hashlib
import importlib.resources
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

logger = logging.getLogger("snippen_sms.migrations")

MIGRATION_FILENAME_PATTERN = re.compile(r"^(\d+)_(.+)\.sql$")


@dataclass(frozen=True)
class Migration:
    """Represents a database migration script."""

    version: int
    name: str
    sql: str
    checksum: str

    @classmethod
    def from_file(cls, path: Path) -> Migration:
        """Parse a migration script from a file path."""
        match = MIGRATION_FILENAME_PATTERN.match(path.name)
        if not match:
            raise ValueError(
                f"Invalid migration filename format: '{path.name}'. Expected '0001_name.sql'."
            )
        version = int(match.group(1))
        name = match.group(2)
        sql = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
        return cls(version=version, name=name, sql=sql, checksum=checksum)


class MigrationError(Exception):
    """Raised when a database migration fails or schema integrity is compromised."""


class MigrationRunner:
    """Lightweight SQLite database migration runner."""

    def __init__(
        self,
        db_path: str | Path | sqlite3.Connection = "data/sms_gateway.db",
        migrations_dir: Path | None = None,
    ) -> None:
        if isinstance(db_path, sqlite3.Connection):
            self._conn: sqlite3.Connection | None = db_path
            self._external_conn = True
            self.db_path = ":external:"
        else:
            self._conn = None
            self._external_conn = False
            self.db_path = str(db_path)

        self.migrations_dir = migrations_dir

    @property
    def connection(self) -> sqlite3.Connection:
        """Return an active database connection."""
        if self._conn is None:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            if self.db_path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._conn = conn
        return self._conn

    def _ensure_migration_table(self, conn: sqlite3.Connection) -> None:
        """Ensure schema_migrations table exists."""
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    checksum TEXT NOT NULL
                );
                """
            )

    def _discover_migration_files(self) -> list[Path]:
        """Find all migration .sql files."""
        if self.migrations_dir is not None:
            dir_path = Path(self.migrations_dir)
            if not dir_path.exists():
                return []
            return sorted(dir_path.glob("*.sql"))

        # Try importlib.resources first for packaged distributions
        try:
            sql_resource = importlib.resources.files("snippen_sms.migrations").joinpath("sql")
            files: list[Path] = []
            for item in sql_resource.iterdir():
                if item.name.endswith(".sql"):
                    files.append(Path(str(item)))
            return sorted(files, key=lambda p: p.name)
        except (TypeError, ModuleNotFoundError, AttributeError, FileNotFoundError):
            fallback_dir = Path(__file__).parent / "sql"
            if fallback_dir.exists():
                return sorted(fallback_dir.glob("*.sql"))
            return []

    @staticmethod
    def _split_sql_statements(sql: str) -> list[str]:
        """Split SQL script into individual executable statements without comments."""
        cleaned_lines: list[str] = []
        for line in sql.splitlines():
            line_strip = line.strip()
            if line_strip.startswith("--"):
                continue
            cleaned_lines.append(line)
        cleaned_sql = "\n".join(cleaned_lines)

        statements: list[str] = []
        for stmt in cleaned_sql.split(";"):
            stmt_clean = stmt.strip()
            if stmt_clean:
                statements.append(stmt_clean)
        return statements

    def get_available_migrations(self) -> list[Migration]:
        """Return all available migrations defined in the repository."""
        files = self._discover_migration_files()
        migrations: list[Migration] = []
        for file in files:
            migrations.append(Migration.from_file(file))
        migrations.sort(key=lambda m: m.version)
        return migrations

    def get_applied_migrations(self) -> list[dict[str, Any]]:
        """Return list of applied migrations from the database."""
        conn = self.connection
        self._ensure_migration_table(conn)
        cursor = conn.execute(
            "SELECT version, name, applied_at, checksum FROM schema_migrations ORDER BY version ASC;"
        )
        return [
            {
                "version": row[0],
                "name": row[1],
                "applied_at": row[2],
                "checksum": row[3],
            }
            for row in cursor.fetchall()
        ]

    def get_current_version(self) -> int:
        """Return current database schema version."""
        conn = self.connection
        self._ensure_migration_table(conn)
        cursor = conn.execute("SELECT MAX(version) AS max_version FROM schema_migrations;")
        row = cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])

        # Check PRAGMA user_version as secondary source
        cursor = conn.execute("PRAGMA user_version;")
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def get_pending_migrations(self) -> list[Migration]:
        """Return migrations that have not yet been applied to the database."""
        available = self.get_available_migrations()
        applied_map = {m["version"]: m for m in self.get_applied_migrations()}

        pending: list[Migration] = []
        for migration in available:
            if migration.version in applied_map:
                applied = applied_map[migration.version]
                if applied["checksum"] != migration.checksum:
                    logger.warning(
                        "Migration %04d_%s checksum mismatch! Recorded: %s, Current: %s",
                        migration.version,
                        migration.name,
                        applied["checksum"],
                        migration.checksum,
                    )
            else:
                pending.append(migration)

        return pending

    def baseline_existing_database(self) -> bool:
        """Baseline an existing pre-migration database if it already contains tables."""
        conn = self.connection
        self._ensure_migration_table(conn)

        # Check if schema_migrations already has entries
        applied = self.get_applied_migrations()
        if applied:
            return False

        # Check if messages table already exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages';"
        )
        if cursor.fetchone() is None:
            return False

        # Existing database detected without migration tracking. Baseline to version 1.
        available = self.get_available_migrations()
        if not available:
            return False

        v1_migration = available[0]
        now = datetime.now(UTC).isoformat()
        with conn:
            conn.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at, checksum)
                VALUES (?, ?, ?, ?)
                """,
                (v1_migration.version, v1_migration.name, now, v1_migration.checksum),
            )
            conn.execute(f"PRAGMA user_version = {v1_migration.version};")
        logger.info(
            "Baselined existing database at schema version %d (%s)",
            v1_migration.version,
            v1_migration.name,
        )
        return True

    def apply_migration(self, migration: Migration) -> None:
        """Apply a single migration atomically."""
        conn = self.connection
        self._ensure_migration_table(conn)
        now = datetime.now(UTC).isoformat()
        statements = self._split_sql_statements(migration.sql)

        logger.info("Applying migration %04d_%s...", migration.version, migration.name)
        try:
            conn.execute("BEGIN IMMEDIATE;")
            for stmt in statements:
                conn.execute(stmt)
            conn.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at, checksum)
                VALUES (?, ?, ?, ?)
                """,
                (migration.version, migration.name, now, migration.checksum),
            )
            conn.execute(f"PRAGMA user_version = {migration.version};")
            conn.commit()
            logger.info("Successfully applied migration %04d_%s", migration.version, migration.name)
        except Exception as exc:
            try:
                conn.rollback()
            except sqlite3.Error as rb_exc:
                logger.debug("Rollback failed: %s", rb_exc)
            logger.exception(
                "Failed to apply migration %04d_%s",
                migration.version,
                migration.name,
            )
            raise MigrationError(
                f"Failed to apply migration {migration.version:04d}_{migration.name}: {exc}"
            ) from exc

    def run_migrations(self, target_version: int | None = None) -> list[Migration]:
        """Apply all pending migrations up to target_version (or latest)."""
        self.baseline_existing_database()
        pending = self.get_pending_migrations()

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            logger.debug(
                "Database is already up to date at version %d.", self.get_current_version()
            )
            return []

        applied: list[Migration] = []
        for migration in pending:
            self.apply_migration(migration)
            applied.append(migration)

        return applied

    def close(self) -> None:
        """Close managed database connection if not external."""
        if not self._external_conn and self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
