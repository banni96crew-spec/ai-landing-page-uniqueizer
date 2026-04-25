import sys
from pathlib import Path

# Добавляем корень проекта в пути поиска Python, чтобы импорты работали
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

def run_seed():
    conn = get_connection()
    try:
        # Очищаем старые тесты и ставим статус running
        conn.execute("DELETE FROM jobs WHERE target_url='http://test.com'")
        conn.execute("INSERT INTO jobs (target_url, status) VALUES ('http://test.com', 'running')")
        conn.commit()
        print("✅ Задача 'running' добавлена в реальную базу.")
    finally:
        conn.close()

if __name__ == "__main__":
    run_seed()