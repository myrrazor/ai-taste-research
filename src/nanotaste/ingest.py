"""Ingest opted-in coding-session history into local sanitized excerpts."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator

from nanotaste.domains import normalize_domain
from nanotaste.redact import redact_text
from nanotaste.security import (
    MAX_GIT_LOG_ITEMS,
    MAX_INGEST_FILE_BYTES,
    MAX_INGEST_FILES_PER_SOURCE,
    MAX_SESSION_RECORDS,
    atomic_write_text,
    append_jsonl_record,
)
from nanotaste.sources import AgentSource, discover_sources, session_files_for
from nanotaste.workspace import TasteWorkspace, now_iso, replace_config

TEXT_KEYS = {
    "body",
    "content",
    "excerpt",
    "input",
    "message",
    "output",
    "prompt",
    "text",
}
CODE_MARKERS = {"def ", "class ", "import ", "function ", "const ", "return ", "```"}
WRITING_MARKERS = {"readme", "changelog", "release", "announce", "copy"}


@dataclass(frozen=True)
class SessionExcerpt:
    """One sanitized snippet pulled from an opted-in source."""

    source_id: str
    session_id: str
    domain: str
    kind: str
    excerpt: str
    origin: str

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "nanotaste/session-excerpt/1.0",
            "source_id": self.source_id,
            "session_id": self.session_id,
            "domain": self.domain,
            "kind": self.kind,
            "excerpt": self.excerpt,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class IngestResult:
    """Summary of one ingest pass."""

    generated_at: str
    enabled_sources: tuple[str, ...]
    excerpts: tuple[SessionExcerpt, ...]
    skipped_sources: tuple[str, ...]
    index_path: Path

    def to_json(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for excerpt in self.excerpts:
            counts[excerpt.source_id] = counts.get(excerpt.source_id, 0) + 1
        return {
            "schema": "nanotaste/ingest-index/1.0",
            "generated_at": self.generated_at,
            "enabled_sources": list(self.enabled_sources),
            "skipped_sources": list(self.skipped_sources),
            "excerpt_count": len(self.excerpts),
            "by_source": counts,
            "index_path": str(self.index_path),
        }


def ingest_workspace(
    workspace: TasteWorkspace,
    enabled_sources: tuple[str, ...] | None = None,
) -> IngestResult:
    """Pull history from enabled sources into `.nanotaste/sessions`."""
    from nanotaste.workspace import ensure_workspace, load_config

    ensure_workspace(workspace)
    config = load_config(workspace)
    wanted = tuple(enabled_sources or config.enabled_sources)
    discovered = {source.id: source for source in discover_sources(workspace.home, workspace.root)}
    excerpts: list[SessionExcerpt] = []
    skipped: list[str] = []
    for source_id in wanted:
        source = discovered.get(source_id)
        if source is None or not source.present:
            skipped.append(source_id)
            continue
        excerpts.extend(_ingest_source(source, workspace))
        if len(excerpts) >= MAX_SESSION_RECORDS:
            excerpts = excerpts[:MAX_SESSION_RECORDS]
            break
    generated_at = now_iso()
    index_path = _write_excerpts(workspace, excerpts, generated_at)
    replace_config(workspace, last_ingest_at=generated_at)
    return IngestResult(
        generated_at=generated_at,
        enabled_sources=wanted,
        excerpts=tuple(excerpts),
        skipped_sources=tuple(skipped),
        index_path=index_path,
    )


def load_excerpts(workspace: TasteWorkspace) -> list[SessionExcerpt]:
    """Load previously ingested excerpts if present."""
    path = workspace.sessions_dir / "excerpts.jsonl"
    if not path.is_file():
        return []
    items: list[SessionExcerpt] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        items.append(
            SessionExcerpt(
                source_id=str(data["source_id"]),
                session_id=str(data["session_id"]),
                domain=str(data.get("domain", "general")),
                kind=str(data.get("kind", "session")),
                excerpt=str(data.get("excerpt", "")),
                origin=str(data.get("origin", "")),
            )
        )
    return items


def _ingest_source(source: AgentSource, workspace: TasteWorkspace) -> list[SessionExcerpt]:
    if source.id == "git":
        return list(_git_excerpts(workspace.root))
    excerpts: list[SessionExcerpt] = []
    for path in session_files_for(source, MAX_INGEST_FILES_PER_SOURCE):
        if path.stat().st_size > MAX_INGEST_FILE_BYTES:
            continue
        try:
            text = path.read_bytes()[:MAX_INGEST_FILE_BYTES].decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for excerpt in _excerpts_from_text(source.id, path, text):
            excerpts.append(excerpt)
            if len(excerpts) >= MAX_SESSION_RECORDS:
                return excerpts
    return excerpts


def _git_excerpts(root: Path) -> list[SessionExcerpt]:
    if not (root / ".git").exists():
        return []
    result = subprocess.run(
        ["git", "-C", str(root), "log", "-n", str(MAX_GIT_LOG_ITEMS), "--pretty=format:%s"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    excerpts: list[SessionExcerpt] = []
    for index, line in enumerate(result.stdout.splitlines()):
        cleaned = redact_text(line)
        if not cleaned:
            continue
        excerpts.append(
            SessionExcerpt(
                source_id="git",
                session_id=_session_id("git", f"commit-{index}", cleaned),
                domain="code",
                kind="commit",
                excerpt=cleaned,
                origin="git log --pretty=format:%s",
            )
        )
    return excerpts


def _excerpts_from_text(source_id: str, path: Path, text: str) -> Iterator[SessionExcerpt]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        for index, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                snippet = redact_text(line)
            else:
                snippet = redact_text(" ".join(_json_strings(payload)))
            if snippet:
                yield _excerpt(source_id, path, index, snippet, "session")
    elif suffix == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            snippet = redact_text(text)
            if snippet:
                yield _excerpt(source_id, path, 0, snippet, "session")
            return
        snippet = redact_text(" ".join(_json_strings(payload)))
        if snippet:
            yield _excerpt(source_id, path, 0, snippet, "session")
    else:
        for index, block in enumerate(_markdown_blocks(text)):
            yield _excerpt(source_id, path, index, redact_text(block), "note")


def _json_strings(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, str) and (key.lower() in TEXT_KEYS or len(value) > 24):
                found.append(value)
            else:
                found.extend(_json_strings(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_json_strings(item))
    elif isinstance(payload, str) and len(payload) > 24:
        found.append(payload)
    return found[:12]


def _markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                blocks.append(" ".join(current))
                current = []
            continue
        current.append(line.strip())
    if current:
        blocks.append(" ".join(current))
    return [block for block in blocks if len(block) >= 24][:20]


def _excerpt(source_id: str, path: Path, index: int, text: str, kind: str) -> SessionExcerpt:
    return SessionExcerpt(
        source_id=source_id,
        session_id=_session_id(source_id, f"{path.name}:{index}", text),
        domain=_guess_domain(text),
        kind=kind,
        excerpt=text,
        origin=path.name,
    )


def _guess_domain(text: str) -> str:
    lower = text.lower()
    if any(marker in lower for marker in CODE_MARKERS):
        return normalize_domain("code")
    if any(marker in lower for marker in WRITING_MARKERS):
        return normalize_domain("writing")
    return "general"


def _session_id(source_id: str, label: str, text: str) -> str:
    digest = sha256(f"{source_id}:{label}:{text}".encode("utf-8")).hexdigest()
    return digest[:16]


def _write_excerpts(
    workspace: TasteWorkspace, excerpts: list[SessionExcerpt], generated_at: str
) -> Path:
    excerpts_path = workspace.sessions_dir / "excerpts.jsonl"
    if excerpts_path.exists():
        excerpts_path.unlink()
    for excerpt in excerpts:
        append_jsonl_record(excerpts_path, excerpt.to_json(), label="session excerpt")
    index_path = workspace.sessions_dir / "index.json"
    counts: dict[str, int] = {}
    for excerpt in excerpts:
        counts[excerpt.source_id] = counts.get(excerpt.source_id, 0) + 1
    atomic_write_text(
        index_path,
        json.dumps(
            {
                "schema": "nanotaste/ingest-index/1.0",
                "generated_at": generated_at,
                "excerpt_count": len(excerpts),
                "by_source": counts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        label="ingest index",
    )
    return index_path
