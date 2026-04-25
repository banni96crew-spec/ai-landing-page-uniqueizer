import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ЖЕСТКИЙ ПУТЬ К БАЗЕ
DB_PATH = os.path.abspath(r"backend\data\app.db")

def get_raw_connection():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn

def run_manual_worker():
    print("START: forced worker loop")
    print(f"DB: {DB_PATH}")

    while True:
        conn = get_raw_connection()
        try:
            # Читаем ВООБЩЕ ВСЕ что есть в таблице jobs
            rows = conn.execute("SELECT * FROM jobs").fetchall()

            if not rows:
                print("📭 База абсолютно пустая. Добавь задачу!")
            else:
                for row in rows:
                    job_id = row['id']
                    status = str(row['status']).strip().lower()
                    url = row['target_url']

                    print(f"JOB {job_id} status='{status}'")

                    if status == 'pending':
                        print(f"CLAIM job {job_id} ({url})")
                        conn.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
                        print("OK: status -> running. Simulating work...")
                        time.sleep(2)
                        conn.execute("UPDATE jobs SET status='done' WHERE id=?", (job_id,))
                        print(f"DONE: job {job_id}")

        except Exception as e:
            print(f"ERROR: {e}")
        finally:
            conn.close()

        print("sleep 5s...")
        time.sleep(5)

if __name__ == "__main__":
    run_manual_worker()