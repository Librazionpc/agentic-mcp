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
    prefix = str(routes.get("backend_prefix", "TICKETING")).strip() or "TICKETING"
    route = (routes.get("routes") or {}).get(tool_name)
    if not route:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Tool is not routed on this server.")

    cfg = backend_config(prefix)
    method = str(route.get("method", "POST")).upper()
    path = _format_path(str(route.get("path", "")), args, caller)

    if method == "GET":
        return await backend_request_json(cfg, method, path, params=args)
    return await backend_request_json(cfg, method, path, json_body=args)


def _classify_message(message: str) -> dict:
    m = (message or "").lower()
    if any(k in m for k in ["fraud", "scam", "hacked", "unauthorized"]):
        return {"category": "fraud_suspected", "severity": "high", "confidence": 0.7}
    if any(k in m for k in ["refund", "duplicate", "charged twice", "debited twice", "chargeback"]):
        return {"category": "billing_dispute", "severity": "medium", "confidence": 0.65}
    if any(k in m for k in ["pending", "delayed", "failed transfer", "transfer failed"]):
        return {"category": "transaction_issue", "severity": "medium", "confidence": 0.6}
    if any(k in m for k in ["legal", "sue", "central bank", "cbn", "lawyer"]):
        return {"category": "legal_threat", "severity": "critical", "confidence": 0.75}
    return {"category": "general_complaint", "severity": "low", "confidence": 0.5}


async def _classify_complaint(caller: CallerContext, args: dict, request_id: str) -> dict:
    msg = str(args.get("message", "")).strip()
    if not msg:
        raise ToolError("INVALID_INPUT", "message is required.")
    return _classify_message(msg)


async def _suggest_resolution(caller: CallerContext, args: dict, request_id: str) -> dict:
    status = str(args.get("status", "")).strip().lower()
    service_type = str(args.get("service_type", "")).strip().lower()
    if not status or not service_type:
        raise ToolError("INVALID_INPUT", "status and service_type are required.")

    next_steps: list[str] = []
    escalate = False
    template = ""

    if status in {"pending", "processing"}:
        next_steps = ["Confirm the transaction is still processing.", "Share the expected SLA window for this channel.", "Offer to track and follow up if it exceeds SLA."]
        template = "transaction_inquiry_pending"
    elif status in {"failed", "reversed"}:
        next_steps = ["Confirm final failure status.", "Check if reversal/refund is pending per policy.", "If eligible, submit a refund approval request (HITL)."]
        template = "transaction_failed_next_steps"
    elif status in {"successful", "success"}:
        next_steps = ["Confirm completion time and beneficiary details (masked).", "If user disputes authorization, flag as potential fraud and escalate."]
        template = "transaction_success_explain"
    else:
        next_steps = ["Request transaction id or a clear screenshot.", "Run transaction status lookup.", "Proceed based on verified status."]
        template = "need_txid"

    if service_type in {"card", "pos"} and status in {"pending", "failed"}:
        next_steps.append("Explain card/POS reversal timelines and evidence requirements.")

    return {"next_steps": next_steps, "escalate": escalate, "suggested_template": template}


def _tool(tool_name: str, scopes: set[str]) -> ToolSpec:
    async def handler(caller: CallerContext, args: dict, request_id: str) -> dict:
        return await _proxy_tool(caller, args, tool_name)

    return ToolSpec(name=tool_name, required_scopes=scopes, handler=handler)


def main() -> None:
    create = {"ticket.create"}
    write = {"ticket.write"}
    assign = {"ticket.assign"}
    comment = {"ticket.comment"}
    complaints = {"complaints.write"}

    tools = [
        _tool("create_complaint_ticket", complaints | create | write),
        _tool("append_complaint_note", complaints | write | comment),
        _tool("request_refund_approval", {"billing.refund"} | write),
        _tool("ticket_create", create | write),
        _tool("ticket_comment", write | comment),
        _tool("ticket_update", write),
        _tool("ticket_status_check", write | comment | create | assign | complaints),
        _tool("sla_timer_check", write | comment | create | assign),
        _tool("workflow_state_query", write | comment | create | assign),
        _tool("ticket_assign", assign | write),
        _tool("assign_support_queue", assign | write),
        _tool("priority_ticket_update", assign | write),
        _tool("similar_ticket_search", write | comment | create | assign),
        ToolSpec(name="classify_complaint", required_scopes=complaints | write, handler=_classify_complaint),
        ToolSpec(name="suggest_resolution", required_scopes=complaints | write, handler=_suggest_resolution),
    ]

    app = create_app("ticketing-mcp", tools)
    host = os.environ.get("TICKETING_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("TICKETING_MCP_PORT", "8092"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
