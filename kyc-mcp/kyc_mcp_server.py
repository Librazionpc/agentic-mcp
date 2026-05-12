from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from agentic_mcp_shared.auth import CallerContext
from agentic_mcp_shared.errors import ToolError
from agentic_mcp_shared.http_client import backend_config, backend_request_json
from agentic_mcp_shared.server_base import ToolSpec, create_app, run_app


def _here() -> Path:
    return Path(__file__).resolve().parent


def _load_routes() -> dict[str, Any]:
    return yaml.safe_load((_here() / "tool_routes.yaml").read_text(encoding="utf-8")) or {}


def _format_path(template: str, args: dict, caller: CallerContext) -> str:
    merged = dict(args)
    merged.setdefault("customer_id", caller.customer_id)
    try:
        return template.format(**merged)
    except KeyError as e:
        raise ToolError("INVALID_INPUT", f"Missing required path parameter: {e}") from e


async def _proxy_tool(caller: CallerContext, args: dict, tool_name: str) -> dict:
    routes = _load_routes()
    prefix = str(routes.get("backend_prefix", "KYC")).strip() or "KYC"
    route = (routes.get("routes") or {}).get(tool_name)
    if not route:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Tool is not routed on this server.")

    cfg = backend_config(prefix)
    method = str(route.get("method", "GET")).upper()
    path = _format_path(str(route.get("path", "")), args, caller)

    if method == "GET":
        return await backend_request_json(cfg, method, path, params=args)
    return await backend_request_json(cfg, method, path, json_body=args)


def _tool(tool_name: str, scopes: set[str]) -> ToolSpec:
    async def handler(caller: CallerContext, args: dict, request_id: str) -> dict:
        return await _proxy_tool(caller, args, tool_name)

    return ToolSpec(name=tool_name, required_scopes=scopes, handler=handler)


def main() -> None:
    read = {"kyc.read"}
    write = {"kyc.write"}
    comment = {"ticket.comment"}

    tools = [
        _tool("kyc_verification_status", read),
        _tool("kyc_status_update", write),
        _tool("document_verification", write),
        _tool("identity_lookup", read),
        _tool("face_match_check", write),
        _tool("liveness_detection", write),
        _tool("sanction_list_check", read),
        _tool("kyc_status_lookup", read),
        _tool("kyc_resubmit_request", write | comment),
    ]

    app = create_app("kyc-mcp", tools)
    host = os.environ.get("KYC_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("KYC_MCP_PORT", "8094"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
