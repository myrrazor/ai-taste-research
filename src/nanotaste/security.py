"""Small safety helpers for local NanoTaste file IO."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

KIB = 1024
MIB = 1024 * KIB

MAX_TASTE_FILE_BYTES = 256 * KIB
MAX_TASTE_RULES = 2_000
MAX_PROMPT_SET_BYTES = 1 * MIB
MAX_CALIBRATION_RUN_BYTES = 4 * MIB
MAX_HUMAN_PICKS_BYTES = 1 * MIB
MAX_CANDIDATE_FILE_BYTES = 512 * KIB
MAX_PROMPT_BYTES = 20 * KIB
MAX_CANDIDATE_BYTES = 100 * KIB
MAX_PROMPT_ITEMS = 500
MAX_CANDIDATES_PER_PROMPT = 26
MAX_RECORD_LINE_BYTES = 4 * MIB
MAX_UPDATE_INPUT_BYTES = 512 * KIB

DOMAIN_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
BIDI_CONTROLS = {
    "\u061c",
    "\u200e",
    "\u200f",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}
DISPLAY_SEPARATORS = {"\u2028", "\u2029"}


class SecurityInputError(ValueError):
    """Raised when an input violates NanoTaste's local safety policy."""


def validate_domain_id(domain: str) -> str:
    """Return a validated domain identifier safe for path construction."""
    if not DOMAIN_RE.fullmatch(domain):
        raise SecurityInputError(
            f"invalid domain {domain!r}; use lowercase letters, numbers, hyphen, or underscore"
        )
    return domain


def validate_text_limit(text: str, limit_bytes: int, label: str) -> None:
    """Reject text that exceeds a byte limit after UTF-8 encoding."""
    size = len(text.encode("utf-8"))
    if size > limit_bytes:
        raise SecurityInputError(f"{label} is too large: {size} bytes > {limit_bytes} bytes")


def safe_resolve_file(
    path: Path,
    *,
    root: Path | None = None,
    limit_bytes: int | None = None,
    label: str = "file",
) -> Path:
    """Resolve an existing regular file and optionally require root containment."""
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as err:
        raise SecurityInputError(f"{label} is not readable: {path}") from err

    if root is not None:
        _assert_under_root(resolved, root, label)
    if not resolved.is_file():
        raise SecurityInputError(f"{label} is not a regular file: {path}")
    if limit_bytes is not None:
        size = resolved.stat().st_size
        if size > limit_bytes:
            raise SecurityInputError(f"{label} is too large: {size} bytes > {limit_bytes} bytes")
    return resolved


def safe_read_text(
    path: Path,
    *,
    root: Path | None = None,
    limit_bytes: int | None = None,
    label: str = "file",
) -> str:
    """Read a regular UTF-8 file without following symlinks outside a root."""
    resolved = safe_resolve_file(path, root=root, limit_bytes=limit_bytes, label=label)
    with resolved.open("rb") as handle:
        data = handle.read(limit_bytes + 1 if limit_bytes is not None else -1)
    if limit_bytes is not None and len(data) > limit_bytes:
        raise SecurityInputError(f"{label} is too large: {len(data)} bytes > {limit_bytes} bytes")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise SecurityInputError(f"{label} is not valid UTF-8: {path}") from err


def safe_json_loads(text: str, label: str) -> Any:
    """Parse JSON and label decode errors for CLI-facing messages."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise SecurityInputError(f"{label} is not valid JSON: {err}") from err


def atomic_write_text(path: Path, text: str, *, label: str = "file") -> None:
    """Write UTF-8 text with same-directory atomic replacement."""
    target = path.expanduser()
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    resolved_parent = parent.resolve(strict=True)
    _reject_existing_bad_output(target, label)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=resolved_parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
        _fsync_directory(resolved_parent)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def append_jsonl_record(path: Path, payload: dict[str, Any], *, label: str = "record") -> None:
    """Append one JSONL record while rejecting symlink targets and giant lines."""
    line = json.dumps(payload, sort_keys=True) + "\n"
    size = len(line.encode("utf-8"))
    if size > MAX_RECORD_LINE_BYTES:
        raise SecurityInputError(f"{label} line is too large: {size} bytes > {MAX_RECORD_LINE_BYTES} bytes")

    target = path.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    _reject_existing_bad_output(target, label)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())


def safe_for_terminal(text: str) -> str:
    """Escape display-control characters for human-readable terminal output."""
    rendered: list[str] = []
    for char in text:
        code = ord(char)
        if char in ("\n", "\t"):
            rendered.append(char)
        elif (
            char in BIDI_CONTROLS
            or char in DISPLAY_SEPARATORS
            or code < 32
            or code == 127
            or 0x80 <= code <= 0x9F
        ):
            rendered.append(_escape_codepoint(code))
        else:
            rendered.append(char)
    return "".join(rendered)


def _assert_under_root(path: Path, root: Path, label: str) -> None:
    try:
        root_resolved = root.expanduser().resolve(strict=True)
    except OSError as err:
        raise SecurityInputError(f"{label} root is not readable: {root}") from err
    try:
        path.relative_to(root_resolved)
    except ValueError as err:
        raise SecurityInputError(f"{label} escapes approved root: {path}") from err


def _reject_existing_bad_output(path: Path, label: str) -> None:
    if path.is_symlink():
        raise SecurityInputError(f"{label} output target must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise SecurityInputError(f"{label} output target must be a regular file: {path}")


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _escape_codepoint(code: int) -> str:
    if code <= 0xFFFF:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"
