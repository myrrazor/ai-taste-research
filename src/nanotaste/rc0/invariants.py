"""Load and verify the frozen RC0 invariant manifest."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from nanotaste.rc0.canonical import content_digest

EXPECTED_INVARIANT_DIGEST = "80a82bf5f0e570a72ac31e3c43fb5580afa1063e9e4f4d68db7955555c825bcf"


class InvariantError(ValueError):
    """Raised when RC0 evidence is detached from the approved invariants."""


def _manifest_bytes() -> bytes:
    resource = files("nanotaste.rc0").joinpath("rc0_invariants.json")
    return resource.read_bytes()


def load_invariant_manifest() -> dict[str, Any]:
    """Load the bundled manifest and reject any unapproved change."""
    raw = _manifest_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvariantError("RC0 invariant manifest is not valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict):
        raise InvariantError("RC0 invariant manifest must be a JSON object")
    actual = content_digest(manifest)
    if actual != EXPECTED_INVARIANT_DIGEST:
        raise InvariantError(
            f"RC0 invariant manifest digest mismatch: {actual} != {EXPECTED_INVARIANT_DIGEST}"
        )
    return manifest


def validate_invariant_reference(record: dict[str, Any]) -> None:
    """Require a record to reference the exact frozen invariant digest."""
    if record.get("invariant_manifest_digest") != EXPECTED_INVARIANT_DIGEST:
        raise InvariantError("record does not reference the frozen RC0 invariant manifest")
    load_invariant_manifest()
