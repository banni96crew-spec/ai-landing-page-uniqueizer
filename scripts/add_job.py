import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

conn = get_connection()
url = 'http://books.toscrape.com/' # Нормальный сайт без защиты

try:
    conn.execute("INSERT INTO jobs (target_url, status) VALUES (?, ?)", (url, 'pending'))
    conn.commit()
    print("OK: job inserted into DB")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    conn.close()