"""Manual likes, unlikes, and pairwise taste picks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from nanotaste.records import append_record
from nanotaste.security import MAX_LIKE_FILE_BYTES, atomic_write_text, safe_read_text, validate_text_limit
from nanotaste.workspace import TasteWorkspace, ensure_workspace, now_iso


@dataclass(frozen=True)
class PreferenceExample:
    """One operator-provided like or unlike."""

    polarity: str
    path: Path
    text: str
    domain: str
    label: str


@dataclass(frozen=True)
class PickRecord:
    """One manual comparison where the operator chose a preferred option."""

    prompt: str
    domain: str
    winner_index: int
    winner: str
    rejected: tuple[str, ...]
    recorded_at: str


def add_example(
    workspace: TasteWorkspace,
    item: str,
    polarity: str,
    domain: str = "general",
    label: str | None = None,
) -> PreferenceExample:
    """Store a liked or unliked example in the local workspace."""
    if polarity not in {"like", "unlike"}:
        raise ValueError("polarity must be like or unlike")
    ensure_workspace(workspace)
    text, source_name = resolve_example_text(item, roots=(workspace.root, Path.cwd()))
    validate_text_limit(text, MAX_LIKE_FILE_BYTES, f"{polarity} example")
    stem = _safe_stem(label or source_name or polarity)
    folder = workspace.likes_dir if polarity == "like" else workspace.unlikes_dir
    path = _unique_path(folder, stem)
    atomic_write_text(
        path,
        f"# {polarity} / {domain}\n\n{text.rstrip()}\n",
        label=f"{polarity} example",
    )
    return PreferenceExample(polarity=polarity, path=path, text=text, domain=domain, label=stem)


def resolve_example_text(item: str, *, roots: tuple[Path, ...] | None = None) -> tuple[str, str | None]:
    """Read a file under an approved root, or accept literal text."""
    allowed = tuple(root.expanduser().resolve() for root in (roots or (Path.cwd(),)))
    located = _existing_file_under_roots(item, allowed)
    if located is not None:
        path, root = located
        return (
            safe_read_text(path, root=root, limit_bytes=MAX_LIKE_FILE_BYTES, label="preference example"),
            path.stem,
        )
    if any(sep in item for sep in ("/", "\\")) or item.endswith((".md", ".txt", ".py", ".json")):
        raise ValueError(f"preference file not found: {item}")
    return item, None


def _existing_file_under_roots(item: str, roots: tuple[Path, ...]) -> tuple[Path, Path] | None:
    try:
        resolved = Path(item).expanduser().resolve(strict=True)
    except OSError:
        return None
    text = str(resolved)
    for root in roots:
        prefix = str(root) + os.sep
        if text == str(root) or text.startswith(prefix):
            if resolved.is_file():
                return resolved, root
    return None


def record_pick(
    workspace: TasteWorkspace,
    candidates: list[str],
    winner_index: int,
    prompt: str = "",
    domain: str = "general",
) -> PickRecord:
    """Store a manual winner and copy it into likes / unlikes."""
    if not candidates:
        raise ValueError("pick needs at least one candidate")
    if winner_index < 0 or winner_index >= len(candidates):
        raise ValueError("winner index is out of range")
    ensure_workspace(workspace)
    winner = candidates[winner_index]
    rejected = tuple(item for index, item in enumerate(candidates) if index != winner_index)
    add_example(workspace, winner, "like", domain, f"pick-{winner_index}")
    for index, text in enumerate(rejected):
        add_example(workspace, text, "unlike", domain, f"pick-reject-{index}")
    record = PickRecord(
        prompt=prompt,
        domain=domain,
        winner_index=winner_index,
        winner=winner,
        rejected=rejected,
        recorded_at=now_iso(),
    )
    append_record(
        workspace.picks_path,
        {
            "schema": "nanotaste/manual-pick/1.0",
            "prompt": record.prompt,
            "domain": record.domain,
            "winner_index": record.winner_index,
            "winner": record.winner,
            "rejected": list(record.rejected),
        },
    )
    return record


def list_examples(workspace: TasteWorkspace, polarity: str) -> list[Path]:
    """Return stored like or unlike files."""
    folder = workspace.likes_dir if polarity == "like" else workspace.unlikes_dir
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.iterdir() if path.is_file())


def _safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)[:48]
    return cleaned.strip("-_") or "example"


def _unique_path(folder: Path, stem: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{stem}.md"
    index = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{index}.md"
        index += 1
    return candidate
