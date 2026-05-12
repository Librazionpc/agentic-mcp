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
    path = _here() / "tool_routes.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _format_path(template: str, args: dict, caller: CallerContext) -> str:
    # Tool arguments may not include customer_id (it comes from auth context).
    merged = dict(args)
    merged.setdefault("customer_id", caller.customer_id)
    try:
        return template.format(**merged)
    except KeyError as e:
        raise ToolError("INVALID_INPUT", f"Missing required path parameter: {e}") from e


async def _proxy_tool(caller: CallerContext, args: dict, request_id: str, tool_name: str) -> dict:
    routes = _load_routes()
    backend_prefix = str(routes.get("backend_prefix", "PAYMENTS")).strip() or "PAYMENTS"
    route = (routes.get("routes") or {}).get(tool_name)
    if not route:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Tool is not routed on this server.")

    cfg = backend_config(backend_prefix)
    method = str(route.get("method", "GET")).upper()
    path_tmpl = str(route.get("path", "")).strip()
    if not path_tmpl.startswith("/"):
        raise ToolError("UPSTREAM_UNAVAILABLE", "Invalid route path configuration.")

    path = _format_path(path_tmpl, args, caller)

    # GET tools use query params; POST tools use json body (not used in payments-mcp read-only flows).
    if method == "GET":
        return await backend_request_json(cfg, method, path, params=args)
    return await backend_request_json(cfg, method, path, json_body=args)


def _tool(tool_name: str, required_scopes: set[str]) -> ToolSpec:
    async def handler(caller: CallerContext, args: dict, request_id: str) -> dict:
        return await _proxy_tool(caller, args, request_id, tool_name)

    return ToolSpec(name=tool_name, required_scopes=required_scopes, handler=handler)


def main() -> None:
    # Minimal scope map (defense-in-depth). Runtime remains the primary enforcement point.
    # You can tighten this later.
    read_scope = {"txn.read", "billing.read", "account.read"}

    tools = [
        _tool("get_transaction_status", read_scope),
        _tool("transaction_lookup", read_scope),
        _tool("transaction_status_check", read_scope),
        _tool("transaction_trace", read_scope),
        _tool("fetch_payment_trace", read_scope),
        _tool("settlement_status_query", read_scope),
        _tool("bank_confirmation_check", read_scope),
        _tool("ledger_reconciliation_check", read_scope),
        _tool("search_transactions", read_scope),
        _tool("payment_status_check", read_scope),
        _tool("ledger_trace", read_scope),
        _tool("fee_breakdown", read_scope),
    ]

    app = create_app("payments-mcp", tools)
    host = os.environ.get("PAYMENTS_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("PAYMENTS_MCP_PORT", "8091"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
