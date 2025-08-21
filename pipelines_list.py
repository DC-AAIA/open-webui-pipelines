import os
from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()

API_KEY_ENV = "API_KEY"

def require_api_key():
    async def _dep(request: Request):
        api_key_configured = os.getenv(API_KEY_ENV, "")
        provided = request.headers.get("x-api-key")
        if not api_key_configured or provided != api_key_configured:
            raise HTTPException(status_code=401, detail="Unauthorized")
    return _dep

def _discover_pipeline_ids():
    import glob
    base_dir = os.getenv("PIPELINES_DIR", "./pipelines")
    ids = []
    try:
        for p in glob.glob(os.path.join(base_dir, "*.json")):
            name = os.path.splitext(os.path.basename(p))[0]
            if name:
                ids.append(name)
    except Exception:
        pass
    return sorted(ids)

@router.get("/pipelines", dependencies=[Depends(require_api_key())])
async def list_pipelines():
    return _discover_pipeline_ids()
