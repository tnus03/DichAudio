"""Check task 14 result"""
import sqlite3
conn = sqlite3.connect('dichaudio.db')
c = conn.cursor()
c.execute("SELECT id, status, translated_url, substr(error_message, 1, 200) FROM translation_tasks WHERE id=14")
r = c.fetchone()
if r:
    tid, status, url, err = r
    print(f"#{tid}: {status}")
    print(f"URL: {url or 'None'}")
    if err:
        print(f"Error: {repr(err)}")
else:
    print("Task 14 not found")
c.execute("SELECT COUNT(*), status FROM translation_tasks GROUP BY status")
for s, cnt in c.fetchall():
    print(f"  {s}: {cnt}")
conn.close()
