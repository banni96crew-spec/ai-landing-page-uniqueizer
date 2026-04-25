import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import DATABASE_URL

# 1. Удаляем старый файл базы, чтобы исключить коррупцию
db_path = str(DATABASE_URL).replace("sqlite:///", "").replace("sqlite://", "")
abs_path = os.path.abspath(db_path)

if os.path.exists(abs_path):
    os.remove(abs_path)
    print(f"OK: old DB removed: {abs_path}")

# 2. Создаем новую базу и ВСЕ таблицы сразу
conn = sqlite3.connect(abs_path)
try:
    conn.executescript("""
        CREATE TABLE jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            level TEXT,
            message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE,
            value TEXT
        );
        -- Сразу добавляем одну чистую задачу
        INSERT INTO jobs (target_url, status) VALUES ('http://books.toscrape.com/', 'pending');
    """)
    conn.commit()
    print("OK: new DB created. Tables jobs/logs/settings ready.")
    print("OK: new DB created (jobs/logs/settings). Test job inserted.")
finally:
    conn.close()