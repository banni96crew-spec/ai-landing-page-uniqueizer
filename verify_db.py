import sqlite3
from pathlib import Path

# Путь к базе данных (согласно твоему PRD)
DB_PATH = Path("backend/data/app.db")

def verify():
    if not DB_PATH.exists():
        print(f"❌ Файл базы данных не найден по пути: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print(f"--- Проверка структуры {DB_PATH.name} ---")

    # 1. Проверка таблиц
    expected_tables = {'jobs', 'artifacts', 'settings', 'logs'}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    actual_tables = {row[0] for row in cursor.fetchall()}

    for table in expected_tables:
        status = "✅" if table in actual_tables else "❌ MISSING"
        print(f"Таблица '{table}': {status}")

    # 2. Проверка индексов
    expected_indexes = {'idx_jobs_status_created_at', 'idx_logs_job_id_timestamp'}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    actual_indexes = {row[0] for row in cursor.fetchall()}

    for idx in expected_indexes:
        status = "✅" if idx in actual_indexes else "❌ MISSING"
        print(f"Индекс '{idx}': {status}")

    # 3. Проверка триггера
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='trg_jobs_updated_at'")
    trigger_exists = cursor.fetchone()
    print(f"Триггер 'trg_jobs_updated_at': {'✅' if trigger_exists else '❌ MISSING'}")

    # 4. Проверка дефолтных настроек
    cursor.execute("SELECT key FROM settings")
    settings_count = len(cursor.fetchall())
    print(f"Записей в settings: {settings_count} {'✅' if settings_count >= 7 else '⚠️'}")

    conn.close()

if __name__ == "__main__":
    verify()