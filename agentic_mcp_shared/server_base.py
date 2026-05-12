from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from .auth import CallerContext, verify_bearer_jwt
from .contracts import validate_request, validate_response
from .errors import ToolError, error_payload
from .redaction import redact_obj


logger = logging.getLogger("agentic-mcp")


ToolHandler = Callable[[CallerContext, dict, str], Awaitable[dict]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    required_scopes: set[str]
    handler: ToolHandler


def _configure_logging(service_name: str) -> None:
    level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format=f"%(asctime)s {service_name} %(levelname)s %(message)s")


def _max_body_bytes() -> int:
    try:
        return int(os.environ.get("MCP_MAX_BODY_BYTES", "1048576"))
    except Exception:
        return 1048576


def create_app(service_name: str, tools: list[ToolSpec]) -> FastAPI:
    _configure_logging(service_name)
    # Fail fast on missing auth config (security-invariant).
    for env_name in ("MCP_JWT_PUBLIC_KEY_PEM", "MCP_JWT_ISS", "MCP_JWT_AUD"):
        if not os.environ.get(env_name, "").strip():
            raise RuntimeError(f"{service_name} missing required env: {env_name}")

    app = FastAPI(title=service_name, version="1.0")
    tools_by_name = {t.name: t for t in tools}

    @app.middleware("http")
    async def body_limit_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()
            if len(body) > _max_body_bytes():
                return JSONResponse(status_code=413, content={"ok": False, "error": error_payload("INVALID_INPUT", "Request too large.")})
            request._body = body  # type: ignore[attr-defined]
        return await call_next(request)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/tools")
    async def list_tools(authorization: str | None = Header(default=None)) -> dict:
        _ = verify_bearer_jwt(authorization)
        return {"tools": sorted(tools_by_name.keys())}

    @app.post("/tools/call")
    async def call_tool(
        payload: dict,
        authorization: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
    ) -> dict:
        started = time.time()
        request_id = (x_request_id or "").strip() or "no-request-id"

        try:
            caller = verify_bearer_jwt(authorization)
            name = str(payload.get("name", "")).strip()
            args = payload.get("arguments")
            if not name or not isinstance(args, dict):
                raise ToolError("INVALID_INPUT", "Payload must include {name, arguments}.")

            tool = tools_by_name.get(name)
            if not tool:
                raise ToolError("INVALID_INPUT", f"Unknown tool: {name}")

            # Contract validation (request)
            validate_request(name, args)

            # Scope enforcement (defense-in-depth)
            if tool.required_scopes and not (tool.required_scopes & caller.scopes):
                raise ToolError("FORBIDDEN", "Missing required scope for this tool.")

            result = await tool.handler(caller, args, request_id)
            result = redact_obj(result)
            validate_response(name, result)

            logger.info(json.dumps({"event": "tool_ok", "tool": name, "request_id": request_id, "customer_id": caller.customer_id, "latency_ms": int((time.time() - started) * 1000)}))
            return {"ok": True, "result": result}
        except ToolError as e:
            logger.warning(json.dumps({"event": "tool_error", "request_id": request_id, "code": e.code, "message": e.message}))
            return {"ok": False, "error": error_payload(e.code, e.message)}
        except Exception as e:
            logger.exception("Unhandled error")
            return {"ok": False, "error": error_payload("UPSTREAM_UNAVAILABLE", "Unhandled server error.")}

    return app


def run_app(app: FastAPI, host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, reload=False)
