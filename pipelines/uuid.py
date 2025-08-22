"""
name: UUID Pipeline
id: uuid
type: pipe
description: Generates a UUIDv4 on demand.
"""
import uuid

class Pipeline:
    id = "uuid"
    name = "uuid"
    type = "pipe"

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        return {"uuid": str(uuid.uuid4())}
