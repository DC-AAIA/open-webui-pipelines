"""
name: Math Add Pipeline
id: math_add
type: pipe
description: Sums a list of numbers in body.values (e.g., {"values":[1,2,3]}).
"""

class Pipeline:
    id = "math_add"
    name = "math_add"
    type = "pipe"

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        body = body or {}
        values = body.get("values", [])
        if not isinstance(values, list) or not all(isinstance(x, (int, float)) for x in values):
            return {"error": "body.values must be a list of numbers"}
        return {"sum": float(sum(values))}
