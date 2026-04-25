import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

def check():
    conn = get_connection()
    try:
        res = conn.execute(
            "SELECT status, error_message FROM jobs WHERE target_url='http://test.com'"
        ).fetchone()

        if res:
            status = res['status']
            error = res['error_message']
            icon = "✅" if status == "failed" else "❌"
            print(f"\n--- ИТОГ ТЕСТА ---")
            print(f"СТАТУС: {status} {icon}")
            print(f"ОШИБКА: {error}")
        else:
            print("❌ Задача не найдена.")
    finally:
        conn.close()

if __name__ == "__main__":
    check()