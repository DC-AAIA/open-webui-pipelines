"""
Pipeline: time_unix
Purpose:
  Return machine-friendly epoch time for precise calculations and scheduling.

Inputs:
  - none

Outputs:
  - epoch_seconds: int (seconds since 1970-01-01T00:00:00Z)
  - epoch_millis: int (milliseconds since 1970-01-01T00:00:00Z)

Usage Guidance:
  - Prefer this for timers, retries, TTLs, scheduling, cache keys, and comparisons.
  - For human-readable displays/logs, use time.

Example curl:
  curl -sS "$PIPELINES_BASE_URL/pipelines/time_unix" | jq .

Notes:
  - Stable across locales/time zones; ideal for cross-service time math.
  - See also: time (human-readable) and time_info (aggregated convenience).
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
