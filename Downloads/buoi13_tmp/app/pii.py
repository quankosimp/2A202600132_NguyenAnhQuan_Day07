from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

PII_PATTERNS: dict[str, str] = {
    "email": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
    "cccd": r"\b\d{12}\b",
    "phone_vn": r"(?:\+84|0)(?:[ .-]?\d){8,10}",
    "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
    "token": r"\b(?:sk|pk|rk|tok|bearer)[A-Za-z0-9._-]{8,}\b",
    "api_key": r"\b(?:api[_-]?key|secret|token)\b\s*[:=]\s*[A-Za-z0-9._-]{8,}",
}

SENSITIVE_KEYS = {
    "email",
    "mail",
    "phone",
    "phone_number",
    "mobile",
    "cccd",
    "id_number",
    "national_id",
    "token",
    "access_token",
    "api_key",
    "secret",
    "password",
    "authorization",
}


def _redaction_label(name: str) -> str:
    return f"[REDACTED_{name.upper()}]"


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, _redaction_label(name), safe, flags=re.IGNORECASE)
    return safe


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {key: scrub_value(_redact_key(key, inner)) for key, inner in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [scrub_value(item) for item in value]
    return value


def _redact_key(key: Any, value: Any) -> Any:
    key_name = str(key).lower()
    if any(sensitive in key_name for sensitive in SENSITIVE_KEYS):
        if isinstance(value, str) and value.strip():
            return _redaction_label(key_name.replace(" ", "_")[:32] or "sensitive")
        return _redaction_label(key_name.replace(" ", "_")[:32] or "sensitive")
    return value


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
