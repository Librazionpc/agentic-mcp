from __future__ import annotations

from dataclasses import dataclass


ALLOWED_ERROR_CODES = {
    "INVALID_INPUT",
    "NOT_FOUND",
    "FORBIDDEN",
    "RATE_LIMITED",
    "UPSTREAM_TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "CONFLICT",
}


@dataclass(frozen=True)
class ToolError(Exception):
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.code not in ALLOWED_ERROR_CODES:
            raise ValueError(f"Unsupported error code: {self.code}")


def error_payload(code: str, message: str) -> dict:
    if code not in ALLOWED_ERROR_CODES:
        code = "UPSTREAM_UNAVAILABLE"
    return {"code": code, "message": message}

