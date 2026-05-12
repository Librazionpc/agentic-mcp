from __future__ import annotations

import os
import time
from dataclasses import dataclass

import jwt

from .errors import ToolError


@dataclass(frozen=True)
class CallerContext:
    customer_id: str
    scopes: set[str]
    iss: str
    aud: str


def _required_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise RuntimeError(f"Missing required env: {name}")
    return val


def verify_bearer_jwt(authorization: str | None) -> CallerContext:
    if not authorization or not authorization.startswith("Bearer "):
        raise ToolError("FORBIDDEN", "Missing Authorization bearer token.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise ToolError("FORBIDDEN", "Missing Authorization bearer token.")

    public_pem = _required_env("MCP_JWT_PUBLIC_KEY_PEM")
    expected_iss = _required_env("MCP_JWT_ISS")
    expected_aud = _required_env("MCP_JWT_AUD")

    try:
        payload = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            audience=expected_aud,
            issuer=expected_iss,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise ToolError("FORBIDDEN", "Token expired.") from e
    except Exception as e:
        raise ToolError("FORBIDDEN", "Invalid token.") from e

    customer_id = str(payload.get("customer_id", "")).strip()
    if not customer_id:
        raise ToolError("FORBIDDEN", "Token missing customer_id claim.")

    scopes_raw = payload.get("scopes", [])
    scopes: set[str] = set()
    if isinstance(scopes_raw, list):
        scopes = {str(s) for s in scopes_raw if str(s).strip()}
    elif isinstance(scopes_raw, str) and scopes_raw.strip():
        scopes = {s.strip() for s in scopes_raw.split(",") if s.strip()}

    # Defensive: reject tokens with extremely long lifetime (misconfig).
    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and exp - time.time() > 60 * 60 * 6:
        raise ToolError("FORBIDDEN", "Token lifetime too long.")

    return CallerContext(
        customer_id=customer_id,
        scopes=scopes,
        iss=str(payload.get("iss", "")),
        aud=str(payload.get("aud", "")),
    )

