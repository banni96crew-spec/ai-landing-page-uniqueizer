import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config

conn = sqlite3.connect(Path(config.DATABASE_URL).expanduser())
res = conn.execute("SELECT target_url, status, error_message FROM jobs WHERE target_url='http://test.com'").fetchone()

print("\n--- РЕЗУЛЬТАТ ТЕСТА EC-16 ---")
if res:
    print(f"URL:    {res[0]}")
    print(f"Status: {res[1]} {'OK' if res[1] == 'failed' else 'BAD'}")
    print(f"Error:  {res[2]}")
else:
    print("ERROR: job not found in DB.")
conn.close()