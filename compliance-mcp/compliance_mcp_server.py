from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import yaml
import httpx

from agentic_mcp_shared.auth import CallerContext
from agentic_mcp_shared.errors import ToolError
from agentic_mcp_shared.http_client import backend_config, backend_request_json
from agentic_mcp_shared.server_base import ToolSpec, create_app, run_app
from agentic_mcp_shared.redaction import redact_text


_REG_CACHE: dict[str, tuple[float, dict]] = {}


def _reg_allowed_hosts() -> set[str]:
    raw = os.environ.get("REG_WEB_ALLOWED_HOSTS", "").strip()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _reg_seed_urls() -> list[str]:
    raw = os.environ.get("REG_WEB_SEED_URLS", "").strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def _strip_html(text: str) -> str:
    # Minimal stripping to avoid extra deps; keep it safe and deterministic.
    t = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    t = re.sub(r"(?is)<style.*?>.*?</style>", " ", t)
    t = re.sub(r"(?is)<.*?>", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


async def _fetch_url(url: str, timeout_s: float, max_bytes: int) -> str:
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=False) as client:
        resp = await client.get(url, headers={"user-agent": "openclaw-compliance/1.0"})
    if resp.status_code != 200:
        return ""
    content = resp.content or b""
    if len(content) > max_bytes:
        return ""
    try:
        return content.decode(resp.encoding or "utf-8", errors="ignore")
    except Exception:
        return ""


def _summarize_match(text: str, query: str) -> str:
    q = (query or "").strip().lower()
    if not q:
        return ""
    idx = text.lower().find(q)
    if idx < 0:
        return ""
    start = max(0, idx - 200)
    end = min(len(text), idx + 400)
    snippet = text[start:end].strip()
    if len(snippet) > 700:
        snippet = snippet[:700].rstrip() + "…"
    return snippet


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
    prefix = str(routes.get("backend_prefix", "COMPLIANCE")).strip() or "COMPLIANCE"
    route = (routes.get("routes") or {}).get(tool_name)
    if not route:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Tool is not routed on this server.")

    cfg = backend_config(prefix)
    method = str(route.get("method", "POST")).upper()
    path = _format_path(str(route.get("path", "")), args, caller)
    if method == "GET":
        return await backend_request_json(cfg, method, path, params=args)
    return await backend_request_json(cfg, method, path, json_body=args)


async def _regulatory_web_check(caller: CallerContext, args: dict, request_id: str) -> dict:
    # Defense-in-depth: only compliance agent scopes should call this.
    if "compliance.read" not in caller.scopes and "compliance.write" not in caller.scopes:
        raise ToolError("FORBIDDEN", "Not permitted.")

    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("INVALID_INPUT", "query is required.")

    allowed_hosts = _reg_allowed_hosts()
    seed_urls = _reg_seed_urls()
    if not allowed_hosts or not seed_urls:
        raise ToolError("FORBIDDEN", "Regulatory web checks are disabled (no allowlist/seed URLs configured).")

    max_results = int(args.get("max_results", 5))
    if max_results < 1 or max_results > 10:
        raise ToolError("INVALID_INPUT", "max_results must be between 1 and 10.")

    # Cache (10 minutes)
    now = time.time()
    cached = _REG_CACHE.get(query.lower())
    if cached and cached[0] > now:
        return cached[1]

    timeout_s = float(os.environ.get("REG_WEB_TIMEOUT_SECONDS", "10"))
    max_bytes = int(os.environ.get("REG_WEB_MAX_BYTES", "2000000"))

    results: list[dict[str, Any]] = []
    for url in seed_urls:
        try:
            host = httpx.URL(url).host.lower()
        except Exception:
            continue
        if host not in allowed_hosts:
            continue
        raw = await _fetch_url(url, timeout_s, max_bytes)
        if not raw:
            continue
        text = _strip_html(raw)
        snippet = _summarize_match(text, query)
        if not snippet:
            continue
        results.append(
            {
                "title": f"Regulatory source: {host}",
                "source": url,
                "summary": redact_text(snippet),
            }
        )
        if len(results) >= max_results:
            break

    out = {"results": results}
    _REG_CACHE[query.lower()] = (now + 600, out)
    return out


def _tool(tool_name: str, scopes: set[str]) -> ToolSpec:
    async def handler(caller: CallerContext, args: dict, request_id: str) -> dict:
        return await _proxy_tool(caller, args, tool_name)

    return ToolSpec(name=tool_name, required_scopes=scopes, handler=handler)


def main() -> None:
    read = {"compliance.read"}
    write = {"compliance.write"}

    tools = [
        _tool("compliance_case_create", write),
        _tool("risk_assessment_check", read | write),
        _tool("policy_validation", read | write),
        _tool("user_risk_profile_update", write),
        _tool("compliance_report_generate", read | write),
        _tool("transaction_audit_log", read),
        ToolSpec(name="regulatory_web_check", required_scopes={"compliance.read", "compliance.write"}, handler=_regulatory_web_check),
    ]

    app = create_app("compliance-mcp", tools)
    host = os.environ.get("COMPLIANCE_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("COMPLIANCE_MCP_PORT", "8101"))
    run_app(app, host, port)


if __name__ == "__main__":
    main()
