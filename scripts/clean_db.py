import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

conn = get_connection()
try:
    # TRIM удаляет пробелы по краям, LOWER приводит к нижнему регистру
    conn.execute("UPDATE jobs SET status = TRIM(LOWER(status))")
    # На всякий случай пропишем явно еще раз
    conn.execute("UPDATE jobs SET status = 'pending' WHERE status LIKE 'pending%'")
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0]
    print(f"OK: pending jobs now: {count}")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    conn.close()