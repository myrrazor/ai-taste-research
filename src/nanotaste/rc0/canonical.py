"""Canonical JSON and digest helpers for RC0 evidence."""

from __future__ import annotations

import json
import unicodedata
from hashlib import sha256
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by the RC0 JSON contract."""


def _normalize(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError("floating-point values are not allowed")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalizationError("JSON object keys must be strings")
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    raise CanonicalizationError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Return normalized, deterministic UTF-8 JSON bytes."""
    normalized = _normalize(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def content_digest(value: Any) -> str:
    """Return the SHA-256 digest of canonical JSON bytes."""
    return sha256(canonical_bytes(value)).hexdigest()
