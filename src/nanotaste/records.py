"""JSONL recording helpers for NanoTaste runs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanotaste.redaction import redact_payload
from nanotaste.security import append_jsonl_record


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Append one run record to a JSONL file, redacting secret-looking strings first."""
    payload = redact_payload({"timestamp": datetime.now(timezone.utc).isoformat(), **record})
    # Keep the JSON encoding here as a cheap serializability check before IO.
    json.dumps(payload, sort_keys=True)
    append_jsonl_record(path, payload, label="run record")
