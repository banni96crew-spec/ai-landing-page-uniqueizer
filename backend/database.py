import asyncio
import os
import sqlite3
import threading
from pathlib import Path

from backend import config
from backend.state import JOB_QUEUES, get_ws_broadcast_loop

# Определяем DDL (структуру базы) на случай, если файла миграции нет
INLINE_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url    TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs (status, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    file_path  TEXT    NOT NULL,
    file_size  INTEGER,
    hash       TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO settings (key, value) VALUES
    ('openai_api_key',              ''),
    ('anthropic_api_key',           ''),
    ('ai_provider',                 'openai'),
    ('openai_model',                'gpt-4o-mini'),
    ('anthropic_model',             'claude-3-haiku-20240307'),
    ('noise_intensity',             '0.01'),
    ('js_class_exclusion_prefixes', 'js-,swiper-');

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    level      TEXT    NOT NULL DEFAULT 'info',
    message    TEXT    NOT NULL,
    timestamp  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;
"""

# Canonical DDL lives at repo root: migrations/001_init.sql (not under backend/).
MIGRATIONS_PATH = Path(__file__).resolve().parents[1] / "migrations" / "001_init.sql"

_SCHEMA_LOCK = threading.Lock()
_SCHEMA_ENSURED_PATHS: set[str] = set()


def _table_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    allowed = ("jobs", "settings", "logs", "artifacts")
    if table not in allowed:
        raise ValueError(f"unsupported table for PRAGMA: {table}")
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def ensure_db_schema(conn: sqlite3.Connection) -> None:
    """Align legacy SQLite files with current DDL (additive ALTER + triggers).

    Older DBs may have ``jobs`` without ``updated_at`` while
    ``trg_jobs_updated_at`` still fires on UPDATE, causing
    ``no such column: updated_at``.
    """
    job_cols = _table_column_names(conn, "jobs")
    if not job_cols:
        return
    if "updated_at" not in job_cols:
        conn.execute("DROP TRIGGER IF EXISTS trg_jobs_updated_at")
        # SQLite ADD COLUMN allows only *constant* defaults; datetime('now') is rejected.
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''"
        )
        conn.execute(
            "UPDATE jobs SET updated_at = datetime('now') "
            "WHERE TRIM(updated_at) = '' OR updated_at IS NULL"
        )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
        AFTER UPDATE ON jobs
        BEGIN
            UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
        """
    )

    settings_cols = _table_column_names(conn, "settings")
    if settings_cols and "updated_at" not in settings_cols:
        conn.execute(
            "ALTER TABLE settings ADD COLUMN updated_at TEXT DEFAULT ''"
        )
        conn.execute(
            "UPDATE settings SET updated_at = datetime('now') "
            "WHERE TRIM(COALESCE(updated_at, '')) = ''"
        )


def get_connection():
    # Read dynamically so tests can override config.DATABASE_URL.
    db_url = str(config.DATABASE_URL)
    db_path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
    absolute_path = os.path.abspath(db_path)

    conn = sqlite3.connect(absolute_path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    with _SCHEMA_LOCK:
        if absolute_path not in _SCHEMA_ENSURED_PATHS:
            ensure_db_schema(conn)
            conn.commit()
            _SCHEMA_ENSURED_PATHS.add(absolute_path)

    return conn

def init_db() -> None:
    """Инициализирует структуру базы данных."""
    conn = get_connection()
    try:
        ddl = INLINE_DDL
        if MIGRATIONS_PATH.exists():
            ddl = MIGRATIONS_PATH.read_text(encoding="utf-8")
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()

def log_message(conn: sqlite3.Connection, job_id: int, level: str, message: str) -> None:
    """Persist log to SQLite, then enqueue a structured copy for WebSocket clients."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
        (job_id, level, message),
    )
    row_id = cursor.lastrowid
    ts_row = cursor.execute(
        "SELECT timestamp FROM logs WHERE id = ?",
        (row_id,),
    ).fetchone()
    timestamp = str(ts_row["timestamp"]) if ts_row else ""
    conn.commit()

    if job_id not in JOB_QUEUES:
        return

    queue = JOB_QUEUES[job_id]
    item: dict[str, int | str] = {
        "job_id": job_id,
        "level": level,
        "message": message,
        "timestamp": timestamp,
    }

    def _push_to_queue() -> None:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                pass

    loop = get_ws_broadcast_loop()
    if loop is not None and loop.is_running():
        loop.call_soon_threadsafe(_push_to_queue)
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        return
    running.call_soon(_push_to_queue)