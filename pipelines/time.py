"""
Pipeline: time
Purpose:
  Return human-readable current time fields for UI/logs and agent responses.

Inputs:
  - none

Outputs:
  - iso: string (ISO-8601 UTC, e.g., "2025-08-22T17:35:12Z")
  - utc: string (human-readable UTC, e.g., "Fri, 22 Aug 2025 17:35:12 UTC")
  - local: string (human-readable local time, if supported by runtime)
  - tz: string (time zone identifier/offset, when available)

Usage Guidance:
  - Prefer this for user-facing messages, logs, and quick debugging.
  - For arithmetic, scheduling, TTLs, cache keys, or comparisons, use time_unix.

Example curl:
  # Windows PowerShell or bash (assuming $PIPELINES_BASE_URL is set)
  curl -sS "$PIPELINES_BASE_URL/pipelines/time" | jq .

Notes:
  - Human-friendly; not intended for precise time math.
  - See also: time_unix (epoch-based) and time_info (aggregated convenience).
"""

from datetime import datetime, timezone


class Pipeline:
    # Minimal metadata used by your existing main.py loader
    id = "time"
    name = "time"
    type = "pipe"

    def __init__(self):
        # No valves required for this simple pipeline
        pass

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        """
        Contract:
          - Input: body is a dict (optional), may include { "echo": "..." }
          - Output: dict { "time": "<ISO8601Z>", "echo": "<same as input>"? }

        Notes:
          - Keeps changes minimal and compatible with your current main.py dispatcher
            and /chat/completions path (when model_id == "time").
        """
        now = datetime.now(timezone.utc).isoformat()
        # Normalize the trailing Z for UTC
        if now.endswith("+00:00"):
            now = now.replace("+00:00", "Z")

        result = {"time": now}

        if isinstance(body, dict) and "echo" in body:
            # Echo back any provided value (string or otherwise) without mutation
            result["echo"] = body["echo"]

        return result
