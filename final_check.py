import sqlite3

conn = sqlite3.connect('backend/data/app.db')
res = conn.execute("SELECT target_url, status, error_message FROM jobs WHERE target_url='http://test.com'").fetchone()

print("\n--- РЕЗУЛЬТАТ ТЕСТА EC-16 ---")
if res:
    print(f"URL:    {res[0]}")
    print(f"Status: {res[1]} {'✅' if res[1] == 'failed' else '❌'}")
    print(f"Error:  {res[2]}")
else:
    print("❌ Задача не найдена в базе.")
conn.close()