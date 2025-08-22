class Pipeline:
    id = "echo"
    name = "echo"
    type = "pipe"

    def pipe(self, user_message=None, model_id=None, messages=None, body=None):
        # Echo back whatever JSON body was sent. Default to empty dict.
        return body or {}
