"""Deterministic redaction of secret-looking strings before run records reach disk.

The patterns are intentionally narrow: well-known credential prefixes, PEM private
key blocks, JWTs, bearer tokens, and ``key = value`` assignments whose key name
says "secret". Ordinary prose, hyphenated words, and short identifiers pass through
unchanged. This is a footgun guard for local JSONL records, not a secret scanner.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

REDACTED_FORMAT = "[REDACTED-{kind}]"

_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token"
    r"|client[_-]?secret|password|passwd|token|secret)\b(\s*[:=]\s*)(['\"]?)([^\s'\"]{12,})"
)

# Whole-match patterns, applied in order. Each replaces the entire match.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", _PRIVATE_KEY_BLOCK),
    # OpenAI/Anthropic-style keys: sk-..., sk-proj-..., sk-ant-...; no leading word char
    # so "risk-adjusted" or "desk-based" never match.
    ("api-key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}")),
    (
        "github-token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})\b"),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abeprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
)


def redact_secrets(text: str) -> str:
    """Replace secret-looking substrings with ``[REDACTED-<kind>]`` markers."""
    return replace_secrets(text, lambda kind: REDACTED_FORMAT.format(kind=kind))


def replace_secrets(text: str, replacement: Callable[[str], str]) -> str:
    """Replace every supported secret shape using one shared pattern set."""
    for kind, pattern in SECRET_PATTERNS:
        def replace_match(_match: re.Match[str], secret_kind: str = kind) -> str:
            return replacement(secret_kind)

        text = pattern.sub(replace_match, text)
    return _SECRET_ASSIGNMENT.sub(
        lambda match: _redact_assignment_value(match, replacement("assigned-secret")),
        text,
    )


def redact_payload(value: Any) -> Any:
    """Recursively redact every string value inside a JSON-like payload."""
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, dict):
        return {key: redact_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_payload(item) for item in value]
    return value


def _redact_assignment_value(match: re.Match[str], replacement: str) -> str:
    key, separator, quote, _value = match.groups()
    # Any closing quote sits after the match and is left in place.
    return f"{key}{separator}{quote}{replacement}"
