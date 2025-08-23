"""
Pipeline: time_info
Purpose:
  Convenience aggregator that returns both human-readable and epoch fields in one response.
  Non-breaking alias that complements the separate time and time_unix pipelines.

Inputs:
  - none

Outputs:
  - iso: string (ISO-8601 UTC)
  - utc: string (human-readable UTC)
  - local: string (human-readable local time, if supported)
  - tz: string (time zone identifier/offset, when available)
  - epoch_seconds: int (seconds since 1970-01-01T00:00:00Z)
  - epoch_millis: int (milliseconds since 1970-01-01T00:00:00Z)

Usage Guidance:
  - Use when an agent or workflow wants both forms without two HTTP calls.
  - For strict single-responsibility or caching behaviors, use time and time_unix separately.

Example curl:
  curl -sS "$PIPELINES_BASE_URL/pipelines/time_info" | jq .

Notes:
  - Read-only convenience; does not alter or deprecate existing pipelines.
  - Single snapshot: values are computed from one current-time read for consistency.
"""

from datetime import datetime, timezone
import time as _time

class Pipeline:
    id = "time_info"
    name = "time_info"  # optional; id is sufficient
    description = "Aggregated current time in human-readable and Unix epoch formats."
    methods = ["GET"]  # optional; not used by the loader but harmless

    def pipe(self, body: dict | None = None):
        # Single snapshot for consistency
        now_utc = datetime.now(timezone.utc)
        iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        utc_str = now_utc.strftime("%a, %d %b %Y %H:%M:%S UTC")

        try:
            local_str = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %Z")
        except Exception:
            local_str = None

        try:
            tz_str = _time.tzname[_time.localtime().tm_isdst] if _time.tzname else None
        except Exception:
            tz_str = None

        epoch_seconds = int(now_utc.timestamp())
        epoch_millis = epoch_seconds * 1000

        return {
            "iso": iso,
            "utc": utc_str,
            "local": local_str,
            "tz": tz_str,
            "epoch_seconds": epoch_seconds,
            "epoch_millis": epoch_millis,
        }
