"""Process task 18 directly"""
import sys, json
sys.path.insert(0, 'D:/DIchAudio')
sys.path.insert(0, 'D:/DIchAudio/server')

from server.database import SyncSessionLocal
from server.tasks.video_tasks import update_task_status
from server.core.pipeline import PipelineOrchestrator
from sqlalchemy import text
from datetime import datetime

session = SyncSessionLocal()
try:
    row = session.execute(text("SELECT id, source_url, options FROM translation_tasks WHERE id=18")).first()
    tid, url, opts_raw = row
    opts = json.loads(opts_raw) if opts_raw else {}
finally:
    session.close()

# Fix options: disable subtitles to avoid MoviePy crash, disable blur to speed up
opts["subtitles"] = False
opts["whisper_model_size"] = "tiny"
opts["translation_provider"] = "auto"

# Reset to PENDING
session = SyncSessionLocal()
try:
    session.execute(text("UPDATE translation_tasks SET status='PENDING', error_message=NULL WHERE id=18"))
    session.commit()
finally:
    session.close()

print(f"Task #{tid}: {str(url)[:60]}")
sys.stdout.flush()

orch = PipelineOrchestrator(translation_provider="auto")
orch.set_status_callback(update_task_status)
try:
    result = orch.process_video(task_id=tid, source_url=url, options=opts)
    if result:
        print(f"DONE: {result[:80]}")
    else:
        print("No upload URL")
except Exception as e:
    print(f"FAILED: {e}")
    update_task_status(tid, "FAILED", error_message=str(e))
