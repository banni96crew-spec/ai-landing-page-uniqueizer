import sys
from pathlib import Path

# Подключаем корень
sys.path.append(str(Path(__file__).resolve().parent.parent))
from backend.database import get_connection

def setup_mocks():
    conn = get_connection()
    try:
        # 1. Создаем задачу running с двумя логами (должно быть 40%)
        cur = conn.execute("INSERT INTO jobs (target_url, status) VALUES ('https://run.com', 'running')")
        run_id = cur.lastrowid
        # Вставляем маркеры (Cursor должен был определить их в коде, обычно это что-то вроде SCRAPER_DONE)
        # Добавим парочку любых маркеров из тех, что прописаны в jobs.py
        conn.execute("INSERT INTO logs (job_id, message) VALUES (?, 'MODULE_DONE: SCRAPER')", (run_id,))
        conn.execute("INSERT INTO logs (job_id, message) VALUES (?, 'MODULE_DONE: CLEANER')", (run_id,))

        # 2. Создаем задачу done (должно быть 100%)
        cur = conn.execute("INSERT INTO jobs (target_url, status) VALUES ('https://done.com', 'done')")
        done_id = cur.lastrowid

        conn.commit()
        print(f"✅ Готово! Иди в Swagger и проверяй:\n- ID {run_id} (статус running)\n- ID {done_id} (статус done)")
    finally:
        conn.close()

if __name__ == "__main__":
    setup_mocks()