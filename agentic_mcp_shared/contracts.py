from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from .errors import ToolError


def _workspace_root() -> Path:
    # Prefer explicit override, then common container path, then source-relative fallback.
    env_root_raw = (os.environ.get("MCP_WORKSPACE_ROOT") or "").strip()
    if env_root_raw:
        env_root = Path(env_root_raw)
        if env_root.exists():
            return env_root
    app_root = Path("/app")
    if app_root.exists():
        return app_root
    return Path(__file__).resolve().parents[2]


def _contracts_root() -> Path:
    env_contracts = (os.environ.get("MCP_CONTRACTS_ROOT") or "").strip()
    if env_contracts:
        return Path(env_contracts)
    return _workspace_root() / "agentic-skills" / "contracts"


@lru_cache(maxsize=512)
def load_tool_contract(tool_name: str) -> dict:
    path = _contracts_root() / "tools" / f"{tool_name}.json"
    if not path.exists():
        raise ToolError("INVALID_INPUT", f"Unknown tool contract: {tool_name}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1024)
def _validator(schema_json: str) -> Draft202012Validator:
    schema = json.loads(schema_json)
    return Draft202012Validator(schema)


def validate_request(tool_name: str, arguments: dict) -> dict:
    contract = load_tool_contract(tool_name)
    schema = contract.get("request_schema") or {}
    v = _validator(json.dumps(schema, sort_keys=True))
    errors = sorted(v.iter_errors(arguments), key=lambda e: e.path)
    if errors:
        raise ToolError("INVALID_INPUT", errors[0].message)
    return contract


def validate_response(tool_name: str, result: dict) -> None:
    contract = load_tool_contract(tool_name)
    schema = contract.get("response_schema") or {}
    v = _validator(json.dumps(schema, sort_keys=True))
    errors = sorted(v.iter_errors(result), key=lambda e: e.path)
    if errors:
        raise ToolError("UPSTREAM_UNAVAILABLE", f"Tool produced invalid response: {errors[0].message}")

