"""
name: Time Pipeline
id: time
type: pipe
description: Returns the current UTC time in ISO 8601 format with optional echo passthrough.
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
