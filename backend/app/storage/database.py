"""SQLite database initialization and connection management."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import Settings

# SQL for creating tables
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    market_mode TEXT NOT NULL DEFAULT 'auto',
    save_dir TEXT NOT NULL,
    request_interval_seconds REAL NOT NULL DEFAULT 2.0,
    concurrency INTEGER NOT NULL DEFAULT 1,
    auto_slowdown INTEGER NOT NULL DEFAULT 1,
    overwrite_existing INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS task_items (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    code TEXT NOT NULL,
    market TEXT NOT NULL,
    year INTEGER NOT NULL,
    report_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    message TEXT NOT NULL DEFAULT '',
    file_path TEXT,
    file_size INTEGER,
    name TEXT,
    announcement_title TEXT,
    pdf_url TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS report_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_item_id TEXT,
    announcement_title TEXT NOT NULL,
    announcement_date TEXT,
    pdf_url TEXT,
    score INTEGER,
    raw_json TEXT,
    FOREIGN KEY (task_item_id) REFERENCES task_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    code TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_items_task_id ON task_items(task_id);
CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs(task_id);
CREATE INDEX IF NOT EXISTS idx_report_candidates_item_id ON report_candidates(task_item_id);
"""


class Database:
    """SQLite database wrapper with initialization."""

    _MIGRATIONS = [
        # Add new columns here as (table, column, definition) tuples
        ("task_items", "file_size", "INTEGER"),
    ]

    def __init__(self, settings: Settings) -> None:
        self._db_path = settings.database_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_CREATE_TABLES_SQL)
            self._run_migrations()
            self._conn.commit()
        return self._conn

    def _run_migrations(self) -> None:
        """Apply missing column additions (best-effort ALTER TABLE)."""
        for table, column, col_def in self._MIGRATIONS:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
            except sqlite3.OperationalError:
                # Column already exists — skip
                pass

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()
