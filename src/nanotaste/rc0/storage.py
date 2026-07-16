"""Crash-safe local storage for private RC0 control records."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from nanotaste.rc0.canonical import canonical_bytes


class StorageError(OSError):
    """Raised when evidence storage cannot provide the promised durability."""


def _reject_symlink_components(path: Path) -> None:
    current = path.absolute()
    if current.exists() and stat.S_ISLNK(current.lstat().st_mode):
        raise StorageError(f"symlinked evidence path is not allowed: {current}")


def atomic_write_json(path: Path, value: Any, *, fail_before_replace: bool = False) -> None:
    """Persist canonical JSON with fsync and same-directory atomic replacement."""
    _reject_symlink_components(path)
    _reject_symlink_components(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(path.parent)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(temp, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        if fail_before_replace:
            raise StorageError("simulated crash before atomic replacement")
        os.replace(temp, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object from a regular, non-symlink file."""
    _reject_symlink_components(path)
    _reject_symlink_components(path.parent)
    if not path.is_file():
        raise StorageError(f"evidence record is not a regular file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError(f"evidence record is corrupt: {path}") from exc
    if not isinstance(value, dict):
        raise StorageError(f"evidence record must be a JSON object: {path}")
    return value


class ExclusiveLock:
    """Fail-closed process lock; stale locks require explicit reconciliation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._held = False

    def __enter__(self) -> "ExclusiveLock":
        _reject_symlink_components(self.path)
        _reject_symlink_components(self.path.parent)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise StorageError(f"evidence lock already exists: {self.path}") from exc
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(f"pid={os.getpid()}\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._held = True
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._held:
            self.path.unlink()
            self._held = False
