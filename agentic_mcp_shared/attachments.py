from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .errors import ToolError


@dataclass(frozen=True)
class DownloadResult:
    content: bytes
    sha256: str
    content_type: str


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("ATTACHMENT_ALLOWED_HOSTS", "").strip()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _max_bytes() -> int:
    try:
        return int(os.environ.get("ATTACHMENT_MAX_BYTES", "5242880"))
    except Exception:
        return 5242880


def _timeout_seconds() -> float:
    try:
        return float(os.environ.get("ATTACHMENT_TIMEOUT_SECONDS", "10"))
    except Exception:
        return 10.0


async def download_signed_attachment(url: str) -> DownloadResult:
    url = (url or "").strip()
    if not url.startswith("https://"):
        raise ToolError("INVALID_INPUT", "Attachment URL must be https.")

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = _allowed_hosts()
    # Default-deny: if ATTACHMENT_ALLOWED_HOSTS is not configured, block downloads.
    if not allowed:
        raise ToolError("FORBIDDEN", "Attachment downloads are disabled (no allowed hosts configured).")
    if host not in allowed:
        raise ToolError("FORBIDDEN", "Attachment host is not allowed.")

    try:
        async with httpx.AsyncClient(timeout=_timeout_seconds(), follow_redirects=False) as client:
            resp = await client.get(url)
    except httpx.TimeoutException as e:
        raise ToolError("UPSTREAM_TIMEOUT", "Attachment download timed out.") from e
    except Exception as e:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Attachment download failed.") from e

    if resp.status_code != 200:
        raise ToolError("UPSTREAM_UNAVAILABLE", "Attachment download failed.")

    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type not in {"image/png", "image/jpeg", "image/jpg", "application/pdf"}:
        raise ToolError("INVALID_INPUT", "Unsupported attachment content-type.")

    data = resp.content or b""
    if len(data) > _max_bytes():
        raise ToolError("INVALID_INPUT", "Attachment too large.")

    sha = hashlib.sha256(data).hexdigest()
    return DownloadResult(content=data, sha256=sha, content_type=content_type)
