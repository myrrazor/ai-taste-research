"""Redact secrets and oversized private text before local taste ingest."""

from __future__ import annotations

import re

from nanotaste.security import MAX_INGEST_EXCERPT_CHARS

SECRET_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]{16,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{16,}"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-=]+"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HOME_MARKERS = ("/home/", "/" + "Users/")
PATH_RE = re.compile(r"(?i)(" + "|".join(re.escape(item) for item in _HOME_MARKERS) + r")[^/\s]+")


def redact_text(text: str, limit: int = MAX_INGEST_EXCERPT_CHARS) -> str:
    """Replace secret-like spans and clip the excerpt for local storage."""
    cleaned = text.replace("\x00", "")
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted-secret]", cleaned)
    cleaned = EMAIL_RE.sub("[redacted-email]", cleaned)
    cleaned = PATH_RE.sub(lambda match: match.group(1) + "[redacted-user]", cleaned)
    compact = " ".join(cleaned.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
