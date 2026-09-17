"""Redact secrets and oversized private text before local taste ingest."""

from __future__ import annotations

import re

from nanotaste.redaction import replace_secrets
from nanotaste.security import MAX_INGEST_EXCERPT_CHARS

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_HOME_MARKERS = ("/home/", "/" + "Users/")
PATH_RE = re.compile(r"(?i)(" + "|".join(re.escape(item) for item in _HOME_MARKERS) + r")[^/\s]+")


def redact_text(text: str, limit: int = MAX_INGEST_EXCERPT_CHARS) -> str:
    """Replace secret-like spans and clip the excerpt for local storage."""
    cleaned = replace_secrets(text.replace("\x00", ""), lambda _kind: "[redacted-secret]")
    cleaned = EMAIL_RE.sub("[redacted-email]", cleaned)
    cleaned = PATH_RE.sub(lambda match: match.group(1) + "[redacted-user]", cleaned)
    compact = " ".join(cleaned.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
