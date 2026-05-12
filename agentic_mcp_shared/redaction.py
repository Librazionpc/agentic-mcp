from __future__ import annotations

import re
from typing import Any


_LONG_DIGITS = re.compile(r"\b\d{8,}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _mask_digits(match: re.Match[str]) -> str:
    s = match.group(0)
    if len(s) <= 4:
        return "****"
    return "*" * (len(s) - 4) + s[-4:]


def redact_text(text: str) -> str:
    out = text
    out = _EMAIL.sub("[redacted_email]", out)
    out = _LONG_DIGITS.sub(_mask_digits, out)
    return out


def redact_obj(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    return obj

