"""Fix stuck task 18"""
import sqlite3
from datetime import datetime
conn = sqlite3.connect('dichaudio.db')
c = conn.cursor()
c.execute("UPDATE translation_tasks SET status=?, error_message=?, updated_at=? WHERE id=18",
          ("FAILED", "TTS bi treo (gTTS)", datetime.utcnow()))
conn.commit()
conn.close()
print("Task 18 marked FAILED")
