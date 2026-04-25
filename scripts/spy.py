import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

conn = get_connection()
try:
    # Запрашиваем у SQLite физический путь к файлу
    db_info = conn.execute("PRAGMA database_list").fetchall()
    real_path = db_info[0][2] if db_info else "Неизвестно"

    print("\n[spy] Investigation:")
    print(f"Скрипт использует файл: {real_path}")

    # Закидываем тестовую задачу
    conn.execute("INSERT INTO jobs (target_url, status) VALUES ('http://books.toscrape.com/', 'pending')")
    conn.commit()

    # Проверяем, легла ли она в базу
    count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    print(f"[spy] OK. pending jobs in this DB: {count}")

except Exception as e:
    print(f"[spy] ERROR: {e}")
finally:
    conn.close()