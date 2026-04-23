import sqlite3
from pathlib import Path
from backend.config import DATABASE_URL  # Берем путь из единого конфига

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

def get_connection() -> sqlite3.Connection:
    """Создает подключение к БД с правильными настройками для FastAPI."""
    # Превращаем строку из конфига в объект Path и создаем папки, если их нет
    db_path = Path(DATABASE_URL).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False, # Важно для асинхронности FastAPI
        timeout=10,
    )
    # Позволяет обращаться к полям по именам: row['status'] вместо row[2]
    conn.row_factory = sqlite3.Row

    # Включаем WAL-режим (ускоряет работу при одновременном чтении и записи)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db() -> None:
    """Инициализирует структуру базы данных."""
    conn = get_connection()
    try:
        conn.executescript(INLINE_DDL)
        conn.commit()
    finally:
        conn.close()

def log_message(conn: sqlite3.Connection, job_id: int, level: str, message: str) -> None:
    """Записывает лог в базу данных."""
    conn.execute(
        "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
        (job_id, level, message),
    )
    conn.commit()