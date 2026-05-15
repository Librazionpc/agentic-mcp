from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

from .errors import ToolError


@dataclass(frozen=True)
class BackendConfig:
    base_url: str
    api_key: str
    timeout_seconds: float


def backend_config(prefix: str) -> BackendConfig:
    base_url = os.environ.get(f"{prefix}_BASE_URL", "").strip()
    api_key = os.environ.get(f"{prefix}_API_KEY", "").strip()
    timeout = float(os.environ.get(f"{prefix}_TIMEOUT_SECONDS", "10"))
    if not base_url or not api_key:
        raise ToolError("UPSTREAM_UNAVAILABLE", f"{prefix} backend is not configured.")
    # Linux Docker often lacks host.docker.internal DNS; use default bridge gateway fallback.
    if "host.docker.internal" in base_url:
        base_url = base_url.replace("host.docker.internal", "172.17.0.1")
    return BackendConfig(base_url=base_url.rstrip("/"), api_key=api_key, timeout_seconds=timeout)


async def backend_request_json(
    cfg: BackendConfig,
    method: str,
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    url = f"{cfg.base_url}{path}"
    headers = {"X-API-Key": cfg.api_key}
    try:
        async with httpx.AsyncClient(timeout=cfg.timeout_seconds) as client:
            resp = await client.request(method.upper(), url, headers=headers, json=json_body, params=params)
    except httpx.TimeoutException as e:
        raise ToolError("UPSTREAM_TIMEOUT", "Upstream timed out.") from e
    except Exception as e:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Upstream unavailable.") from e

    if resp.status_code == 404:
        raise ToolError("NOT_FOUND", "Not found.")
    if resp.status_code in (401, 403):
        raise ToolError("FORBIDDEN", "Upstream forbids this request.")
    if resp.status_code == 409:
        raise ToolError("CONFLICT", "Conflict.")
    if resp.status_code >= 500:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Upstream error.")

    try:
        return resp.json()
    except Exception as e:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Upstream returned non-JSON response.") from e

