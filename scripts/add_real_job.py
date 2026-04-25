import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import get_connection

conn = get_connection()
url = "http://books.toscrape.com/"
conn.execute("INSERT INTO jobs (target_url, status) VALUES (?, 'pending')", (url,))
conn.commit()
conn.close()
print("OK: new pending job inserted")