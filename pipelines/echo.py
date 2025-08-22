"""
name: Time Unix Pipeline
id: time_unix
type: pipe
description: Returns current time in epoch seconds and ISO8601Z.
"""
import time
from datetime import datetime, timezone

class Pipeline:
    id = "time_unix"
    name = "time_unix"
    type = "pipe"

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        now_iso = datetime.now(timezone.utc).isoformat()
        if now_iso.endswith("+00:00"):
            now_iso = now_iso.replace("+00:00", "Z")
        return {"epoch": int(time.time()), "time": now_iso}
