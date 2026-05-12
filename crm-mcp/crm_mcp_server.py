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
    prefix = str(routes.get("backend_prefix", "CRM")).strip() or "CRM"
    route = (routes.get("routes") or {}).get(tool_name)
    if not route:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Tool is not routed on this server.")

    cfg = backend_config(prefix)
    method = str(route.get("method", "POST")).upper()
    path = _format_path(str(route.get("path", "")), args, caller)

    if method == "GET":
        return await backend_request_json(cfg, method, path, params=args)
    return await backend_request_json(cfg, method, path, json_body=args)


def _tool(tool_name: str, scopes: set[str]) -> ToolSpec:
    async def handler(caller: CallerContext, args: dict, request_id: str) -> dict:
        return await _proxy_tool(caller, args, tool_name)

    return ToolSpec(name=tool_name, required_scopes=scopes, handler=handler)


def main() -> None:
    # Skills currently model CRM capabilities mostly as crm.write + ticket.read.
    read = {"ticket.read"}
    write = {"crm.write"}

    tools = [
        _tool("customer_history_fetch", read),
        _tool("customer_profile_update", write),
        _tool("customer_tag_update", write),
        _tool("crm_update", write),
        _tool("crm_upsert_note", write),
        _tool("crm_tag_customer", write),
        _tool("crm_note_write", write),
        _tool("crm_sync", write),
        _tool("interaction_log_write", write),
        _tool("segmentation_update", write),
    ]

    app = create_app("crm-mcp", tools)
    host = os.environ.get("CRM_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("CRM_MCP_PORT", "8093"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
