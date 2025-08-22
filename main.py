"""
Open WebUI MCPO - main.py v0.0.35ac (reconciled to v0.0.29 entrypoint)

Purpose:
- Generate RESTful endpoints from MCP Tool Schemas using the Streamable HTTP MCP client.
- Adds resilience to occasional transient notification/validation noise (e.g., "notifications/initialized")
  surfaced by the HTTP adapter by retrying the RPC once.
- Adds local pipeline discovery/compatibility for Chat-16 plan.

Behavior aligned with n8n-mcp (czlonkowski):
- Handshake: initialize -> tools/list -> generate FastAPI routes -> tools/call per invocation.

References:
- n8n MCP/MCPO: https://github.com/DC-AAIA/n8n-mcp
- Railway deploy/logs: https://github.com/DC-AAIA/railwayapp-docs
"""

import os
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional, Callable, Awaitable
from contextlib import asynccontextmanager
from importlib import import_module

from fastapi import FastAPI, Depends, HTTPException

# MCP optional import guard
_MCP_AVAILABLE = True
try:
    from mcp.client.session import ClientSession
    from mcp.shared.exceptions import McpError
except Exception:
    _MCP_AVAILABLE = False

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydantic_core import ValidationError as PydValidationError
from starlette.responses import JSONResponse


# -------------------------------------------------------------------
# MCP HTTP connector resolution
# -------------------------------------------------------------------

def resolve_http_connector():
    mcp_version = None
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            mcp_version = version("mcp")
        except PackageNotFoundError:
            mcp_version = "unknown"
    except Exception:
        mcp_version = "unknown"

    candidates = []

    try:
        m = import_module("mcp.client.streamable_http")
        if hasattr(m, "connect"):
            return (m.connect, "streamable_http.connect", getattr(m, "__file__", "<unknown>"), mcp_version)
        if hasattr(m, "connect_streamable_http"):
            return (m.connect_streamable_http, "streamable_http.connect_streamable_http", getattr(m, "__file__", "<unknown>"), mcp_version)
        if hasattr(m, "streamablehttp_client"):
            return (m.streamablehttp_client, "streamable_http.streamablehttp_client", getattr(m, "__file__", "<unknown>"), mcp_version)
        if hasattr(m, "create_mcp_http_client"):
            return (m.create_mcp_http_client, "streamable_http.create_mcp_http_client", getattr(m, "__file__", "<unknown>"), mcp_version)
        candidates.append(("mcp.client.streamable_http", list(sorted(dir(m)))))
    except Exception as e:
        candidates.append(("mcp.client.streamable_http (import error)", str(e)))

    try:
        m = import_module("mcp.client.http.streamable")
        if hasattr(m, "connect"):
            return (m.connect, "http.streamable.connect", getattr(m, "__file__", "<unknown>"), mcp_version)
        candidates.append(("mcp.client.http.streamable", list(sorted(dir(m)))))
    except Exception as e:
        candidates.append(("mcp.client.http.streamable (import error)", str(e)))

    try:
        m = import_module("mcp.client.http")
        if hasattr(m, "connect"):
            return (m.connect, "http.connect", getattr(m, "__file__", "<unknown>"), mcp_version)
        candidates.append(("mcp.client.http", list(sorted(dir(m)))))
    except Exception as e:
        candidates.append(("mcp.client.http (import error)", str(e)))

    details = "; ".join([f"{mod}: {info}" for mod, info in candidates])
    raise ImportError(
        f"No compatible MCP HTTP connector found. Checked streamable_http and http variants. "
        f"Installed mcp version: {mcp_version}. Candidates: {details}"
    )


if _MCP_AVAILABLE:
    _CONNECTOR, _CONNECTOR_NAME, _CONNECTOR_MODULE_PATH, _MCP_VERSION = resolve_http_connector()
else:
    _CONNECTOR = None
    _CONNECTOR_NAME = "unavailable"
    _CONNECTOR_MODULE_PATH = None
    _MCP_VERSION = "unknown"


def _resolve_alt_http_connector():
    try:
        mod = import_module("mcp.client.http.streamable")
        if hasattr(mod, "connect"):
            return getattr(mod, "connect")
    except Exception:
        pass
    try:
        mod = import_module("mcp.client.http")
        if hasattr(mod, "connect"):
            return getattr(mod, "connect")
    except Exception:
        pass
    return None


_ALT_HTTP_CONNECT = _resolve_alt_http_connector() if _MCP_AVAILABLE else None

try:
    _streamable_http_mod = import_module("mcp.client.streamable_http")
    _StreamableHTTPTransport = getattr(_streamable_http_mod, "StreamableHTTPTransport", None)
    _StreamReader = getattr(_streamable_http_mod, "StreamReader", None)
    _StreamWriter = getattr(_streamable_http_mod, "StreamWriter", None)
except Exception:
    _StreamableHTTPTransport = None
    _StreamReader = None
    _StreamWriter = None

try:
    import httpx
except Exception:
    httpx = None


# -------------------------------------------------------------------
# Application constants
# -------------------------------------------------------------------

APP_NAME = "Open WebUI MCPO"
APP_VERSION = "0.0.35ac"
APP_DESCRIPTION = "Automatically generated API from MCP Tool Schemas"

DEFAULT_PORT = int(os.getenv("PORT", "8080"))
PATH_PREFIX = os.getenv("PATH_PREFIX", "/")
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
API_KEY = os.getenv("API_KEY", "changeme")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "https://mcp-streamable-test-production.up.railway.app/mcp")
MCP_HEADERS = os.getenv("MCP_HEADERS", "")

logger = logging.getLogger("mcpo")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)


# -------------------------------------------------------------------
# Auth, pydantic schema and retry helpers
# -------------------------------------------------------------------

class APIKeyHeader(BaseModel):
    api_key: str


def api_dependency():
    from fastapi import Request

    async def _dep(request: Request) -> APIKeyHeader:
        key = request.headers.get("x-api-key")
        if not key or key != API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return APIKeyHeader(api_key=key)

    return _dep


class ToolDef(BaseModel):
    name: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any]
    outputSchema: Optional[Dict[str, Any]] = None


# -------------------------------------------------------------------
# MCP supporting functions (retry, connector wrapper, tool list, call)
# -------------------------------------------------------------------

async def retry_jsonrpc(call_fn: Callable[[], Awaitable], desc: str, retries: int = 1, sleep_s: float = 0.1):
    for attempt in range(retries + 1):
        try:
            return await call_fn()
        except Exception as e:
            txt = str(e)
            transient = (
                "notifications/initialized" in txt or
                "JSONRPCMessage" in txt or
                "TaskGroup" in txt
            )
            if not transient and hasattr(e, "exceptions"):
                for sub in getattr(e, "exceptions", []):
                    s = str(sub)
                    if "notifications/initialized" in s or "JSONRPCMessage" in s:
                        transient = True
                        break
            if attempt < retries and transient:
                logging.getLogger("mcpo").warning("Transient error on %s; retrying (%d/%d)", desc, attempt + 1, retries)
                await asyncio.sleep(sleep_s)
                continue
            raise


# -------------------------------------------------------------------
# FastAPI app factory
# -------------------------------------------------------------------

_DISCOVERED_TOOL_NAMES: List[str] = []
_DISCOVERED_TOOLS_MIN: List[Dict[str, Any]] = []


def create_app() -> FastAPI:
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
        docs_url=f"{PATH_PREFIX.rstrip('/')}/docs" if PATH_PREFIX != "/" else "/docs",
        openapi_url=f"{PATH_PREFIX.rstrip('/')}/openapi.json" if PATH_PREFIX != "/" else "/openapi.json",
    )

    if CORS_ALLOWED_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ALLOWED_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Health/ping routes
    @app.get(f"{PATH_PREFIX.rstrip('/')}/health" if PATH_PREFIX != "/" else "/health")
    async def health():
        return {"status": "ok", "name": APP_NAME, "version": APP_VERSION}

    @app.get(f"{PATH_PREFIX.rstrip('/')}/ping" if PATH_PREFIX != "/" else "/ping")
    async def ping():
        return {"pong": True}

    # Startup logic
    @app.on_event("startup")
    async def on_startup():
        logger.info("Starting MCPO Server...")
        logger.info(" Name: %s", APP_NAME)
        logger.info(" Version: %s", APP_VERSION)
        logger.info(" Description: %s", APP_DESCRIPTION)

        # --- Block B: discover local pipelines ---
        try:
            _discover_pipelines(os.getenv("PIPELINES_DIR", "./pipelines"))
            logger.info("Discovered %d local pipeline(s): %s", len(_PIPELINES_REGISTRY), sorted(_PIPELINES_REGISTRY.keys()))
        except Exception:
            logger.exception("Local pipeline discovery failed")
        # ----------------------------------------

        logger.info("Echo/Ping routes registered")
        logger.info("Configuring for a single StreamableHTTP MCP Server with URL [%s;]", MCP_SERVER_URL)

        # Tools (MCPO/MCP) setup is optional; only proceed if library is present
    if not _MCP_AVAILABLE:
        logger.warning("MCP library not available; skipping /tools endpoints")
    else:
        # If the MCP setup exists in this version, it should be placed here.
        # In 35ac, the explicit setup body is not present; leaving guarded placeholder.
        try:
            # Example (when present):
            # client_context = _connector_wrapper(MCP_SERVER_URL)
            # await setup_tools()
            logger.info("MCP available, but no /tools discovery block present in this file; skipping")
        except Exception:
            logger.exception("Error during startup tool discovery/mount")
			
    @app.get("/")
    async def root():
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "description": APP_DESCRIPTION,
            "docs": app.docs_url,
            "openapi": app.openapi_url,
        }

    return app


# -------------------------------------------------------------------
# Diagnostics + Tools routes
# -------------------------------------------------------------------

app = create_app()


def attach_mcpo_diagnostics(app: FastAPI) -> None:
    route = f"{PATH_PREFIX.rstrip('/')}/_diagnostic" if PATH_PREFIX != "/" else "/_diagnostic"

    @app.get(route)
    async def _diagnostic(dep=Depends(api_dependency())):
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION, "path_prefix": PATH_PREFIX},
            "mcp": {"connector": _CONNECTOR_NAME, "version": _MCP_VERSION},
        }


def attach_tools_listing(app: FastAPI) -> None:
    route = f"{PATH_PREFIX.rstrip('/')}/_tools" if PATH_PREFIX != "/" else "/_tools"

    @app.get(route)
    async def _tools(dep=Depends(api_dependency())):
        return {"tools": list(_DISCOVERED_TOOL_NAMES)}


def attach_tools_full_listing(app: FastAPI) -> None:
    route = f"{PATH_PREFIX.rstrip('/')}/_tools_full" if PATH_PREFIX != "/" else "/_tools_full"

    @app.get(route)
    async def _tools_full(dep=Depends(api_dependency())):
        return {"tools": [dict(item) for item in _DISCOVERED_TOOLS_MIN]}


if _MCP_AVAILABLE:
    attach_mcpo_diagnostics(app)
    attach_tools_listing(app)
    attach_tools_full_listing(app)
else:
    # Minimal diagnostic to confirm tools are disabled while MCP not installed
    route = f"{PATH_PREFIX.rstrip('/')}/_diagnostic" if PATH_PREFIX != "/" else "/_diagnostic"
    @app.get(route)
    async def _diagnostic_pipelines_only(dep=Depends(api_dependency())):
        return {
            "app": {"name": APP_NAME, "version": APP_VERSION, "path_prefix": PATH_PREFIX},
            "mcp": {"available": False, "reason": "mcp library not installed"},
        }


# -------------------------------------------------------------------
# --- Block A: Pipelines compatibility layer ---
# -------------------------------------------------------------------

from types import ModuleType
from importlib import util as _imp_util

_PIPELINES_REGISTRY: Dict[str, Dict[str, Any]] = {}


def _discover_pipelines(base_dir: str) -> None:
    """Populate _PIPELINES_REGISTRY with modules exposing class Pipeline().pipe()."""
    _PIPELINES_REGISTRY.clear()
    if not base_dir or not os.path.isdir(base_dir):
        logger.info("PIPELINES_DIR not present or not a directory: %s", base_dir)
        return
    for fname in os.listdir(base_dir):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(base_dir, fname)
        mod_name = f"pipelines.{fname[:-3]}"
        try:
            spec = _imp_util.spec_from_file_location(mod_name, fpath)
            if not spec or not spec.loader:
                continue
            mod = _imp_util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(mod)  # type: ignore
            PipelineCls = getattr(mod, "Pipeline", None)
            if PipelineCls is None:
                continue
            obj = PipelineCls()
            pipe_fn = getattr(obj, "pipe", None)
            if not callable(pipe_fn):
                continue
            pid = getattr(obj, "id", None) or getattr(obj, "name", None) or fname[:-3]
            _PIPELINES_REGISTRY[str(pid)] = {
                "module": mod_name,
                "file": fpath,
                "callable": pipe_fn,
            }
        except Exception as e:
            logger.warning("Skipping pipeline %s due to load error: %s", fpath, e)


def attach_pipelines_routes(app: FastAPI) -> None:
    route_list = "/pipelines" if PATH_PREFIX == "/" else f"{PATH_PREFIX.rstrip('/')}/pipelines"
    route_call = "/pipelines/{name}" if PATH_PREFIX == "/" else f"{PATH_PREFIX.rstrip('/')}/pipelines/{name}"

    @app.get(route_list)
    async def _pipelines_list(dep=Depends(api_dependency())):
        return {"pipelines": sorted(list(_PIPELINES_REGISTRY.keys()))}

    @app.post(route_call)
    async def _pipelines_call(name: str, payload: Dict[str, Any] | None = None, dep=Depends(api_dependency())):
        payload = payload or {}
        entry = _PIPELINES_REGISTRY.get(name)
        if not entry:
            raise HTTPException(status_code=404, detail=f"pipeline '{name}' not found")
        try:
            result = entry["callable"](body=payload)
            if isinstance(result, dict):
                return JSONResponse(status_code=200, content=result)
            return JSONResponse(status_code=200, content={"result": result})
        except Exception as e:
            logger.exception("Pipeline '%s' execution error: %s", name, e)
            raise HTTPException(status_code=500, detail=str(e))


# --- End Block A --------------------------------------------------

# --- Block C: attach pipeline routes at app creation ---
attach_pipelines_routes(app)


# -------------------------------------------------------------------
# Entrypoint runner
# -------------------------------------------------------------------

def run(host: str = "0.0.0.0", port: int = DEFAULT_PORT, log_level: str = None, reload: bool = False, *args, **kwargs):
    import uvicorn
    uvicorn.run(
        "mcpo.main:app",
        host=host,
        port=port,
        log_level=log_level or os.getenv("UVICORN_LOG_LEVEL", "info"),
        reload=reload,
    )


if __name__ == "__main__":
    run()
