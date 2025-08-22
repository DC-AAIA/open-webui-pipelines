"""
name: HTTP GET Pipeline
id: http_get
type: pipe
description: Performs a simple HTTP GET to body.url and returns status, headers and text (or JSON when possible).
"""
import json
import urllib.request
from urllib.error import URLError, HTTPError

class Pipeline:
    id = "http_get"
    name = "http_get"
    type = "pipe"

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        body = body or {}
        url = body.get("url")
        if not url or not isinstance(url, str):
            return {"error": "body.url (string) is required"}

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pipelines/0.1"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.getcode()
                data = resp.read()
                text = data.decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(text)
                    content = {"json": parsed}
                except Exception:
                    content = {"text": text}
                headers = dict(resp.headers.items())
                return {"status": status, "headers": headers, **content}
        except HTTPError as e:
            return {"error": f"HTTPError {e.code}: {e.reason}"}
        except URLError as e:
            return {"error": f"URLError: {getattr(e, 'reason', str(e))}"}
        except Exception as e:
            return {"error": str(e)}
