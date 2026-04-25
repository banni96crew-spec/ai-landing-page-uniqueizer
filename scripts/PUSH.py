import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

conn = get_connection()
try:
    # 1. Сбрасываем ID 1 и 2 обратно в pending
    conn.execute("UPDATE jobs SET status = 'pending' WHERE id IN (1, 2)")

    # 2. Добавляем новую, третью задачу для чистоты эксперимента
    url = "http://books.toscrape.com/"
    conn.execute("INSERT INTO jobs (target_url, status) VALUES (?, 'pending')", (url,))

    conn.commit()

    # Проверка
    rows = conn.execute("SELECT id, status FROM jobs WHERE status = 'pending'").fetchall()
    print(f"OK: pending jobs in queue: {len(rows)}")
    for r in rows:
        print(f"   - Задача ID {r['id']} ждет воркера")

except Exception as e:
    print(f"ERROR: {e}")
finally:
    conn.close()