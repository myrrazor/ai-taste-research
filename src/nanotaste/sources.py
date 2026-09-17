"""Discover local coding agents the operator can opt into."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SESSION_NAME_MARKERS = (
    "transcript",
    "session",
    "chat",
    "history",
    "conversation",
    "composer",
    "agent",
)
SESSION_SUFFIXES = {".jsonl", ".json", ".md", ".txt"}
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "cache",
    "canvases",
    "dist",
    "mcps",
    "node_modules",
    "plugins",
    "skills-cursor",
    "venv",
}


@dataclass(frozen=True)
class AgentSource:
    """One discoverable coding-agent or history source."""

    id: str
    name: str
    present: bool
    paths: tuple[str, ...]
    detail: str
    session_files: int
    default_enabled: bool


@dataclass(frozen=True)
class SourceSpec:
    """How to look for one family of local agent history."""

    id: str
    name: str
    home_markers: tuple[str, ...]
    extra_roots: tuple[str, ...]
    cwd_markers: tuple[str, ...]
    default_enabled: bool


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec("cursor", "Cursor", (".cursor",), (), (".cursor",), True),
    SourceSpec("claude-code", "Claude Code", (".claude",), (), (), True),
    SourceSpec("codex", "OpenAI Codex", (".codex",), (), (), True),
    SourceSpec("continue", "Continue", (".continue",), (), (), True),
    SourceSpec("aider", "Aider", (".aider",), (), (".aider.chat.history.md",), True),
    SourceSpec("windsurf", "Windsurf", (".windsurf", ".codeium"), (), (), True),
    SourceSpec("cline", "Cline", (".cline",), (), (), True),
    SourceSpec("gemini", "Gemini CLI", (".gemini",), (), (), True),
    SourceSpec("zed", "Zed", (), (), (), True),
    SourceSpec("openhands", "OpenHands", (".openhands",), (), (), True),
    SourceSpec("amazon-q", "Amazon Q", (), (), (), True),
    SourceSpec("github-copilot", "GitHub Copilot", (), (), (), True),
    SourceSpec("git", "Git history", (), (), (".git",), True),
    SourceSpec("nanotaste", "NanoTaste records", (), (), (".nanotaste",), True),
)


def discover_sources(home: Path, cwd: Path) -> list[AgentSource]:
    """Return every known source and whether it is present on this machine."""
    return [_inspect_source(spec, home, cwd) for spec in SOURCE_SPECS]


def sources_by_id(home: Path, cwd: Path) -> dict[str, AgentSource]:
    """Return discovered sources keyed by id."""
    return {source.id: source for source in discover_sources(home, cwd)}


def present_sources(home: Path, cwd: Path) -> list[AgentSource]:
    """Return only sources that look installed or have local history."""
    return [source for source in discover_sources(home, cwd) if source.present]


def session_files_for(source: AgentSource, limit: int = 200) -> list[Path]:
    """Return candidate session files for an opted-in source."""
    if source.id == "git":
        return []
    files: list[Path] = []
    for raw in source.paths:
        root = Path(raw)
        if not root.exists():
            continue
        if root.is_file() and _looks_like_session(root):
            files.append(root)
            continue
        if not root.is_dir():
            continue
        files.extend(_walk_session_files(root, limit - len(files)))
        if len(files) >= limit:
            break
    return files[:limit]


def _inspect_source(spec: SourceSpec, home: Path, cwd: Path) -> AgentSource:
    roots = _source_roots(spec, home, cwd)
    if spec.id == "git":
        present = (cwd / ".git").exists()
        detail = "commit subjects from this repository" if present else "no .git directory in this workspace"
        return AgentSource(spec.id, spec.name, present, (str(cwd),) if present else (), detail, 0, spec.default_enabled)
    if spec.id == "nanotaste":
        records = cwd / ".nanotaste"
        present = records.exists()
        files = _walk_session_files(records, 50) if present else []
        detail = f"{len(files)} local NanoTaste files" if present else "no .nanotaste directory yet"
        return AgentSource(
            spec.id,
            spec.name,
            present,
            (str(records),) if present else (),
            detail,
            len(files),
            spec.default_enabled,
        )
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.is_dir():
            files.extend(_walk_session_files(root, 80 - len(files)))
    detail = f"{len(files)} likely session files" if files else "install detected; no session files found yet"
    if not roots:
        detail = "not detected on this machine"
    return AgentSource(
        spec.id,
        spec.name,
        bool(roots),
        tuple(str(path) for path in roots),
        detail,
        len(files),
        spec.default_enabled,
    )


def _source_roots(spec: SourceSpec, home: Path, cwd: Path) -> list[Path]:
    roots: list[Path] = []
    for marker in spec.home_markers:
        candidate = home / marker
        if candidate.exists():
            roots.append(candidate)
    for extra in spec.extra_roots:
        candidate = Path(extra).expanduser()
        if spec.id == "zed":
            continue
        if candidate.exists():
            roots.append(candidate)
    if spec.id == "zed":
        for candidate in (home / ".config" / "zed", home / ".zed"):
            if candidate.exists():
                roots.append(candidate)
    if spec.id == "amazon-q":
        for candidate in (home / ".aws" / "amazonq", home / ".amazon-q"):
            if candidate.exists():
                roots.append(candidate)
    if spec.id == "github-copilot":
        for candidate in (
            home / ".config" / "github-copilot",
            home / ".copilot",
            home / "Library" / "Application Support" / "github-copilot",
        ):
            if candidate.exists():
                roots.append(candidate)
    for marker in spec.cwd_markers:
        candidate = cwd / marker
        if candidate.exists() and candidate not in roots:
            roots.append(candidate)
    return _dedupe_paths(roots)


def _walk_session_files(root: Path, limit: int) -> list[Path]:
    found: list[Path] = []
    if limit <= 0:
        return found
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return found
    for entry in entries:
        if len(found) >= limit:
            break
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in SKIP_DIR_NAMES:
                    continue
                found.extend(_walk_session_files(entry, limit - len(found)))
            elif entry.is_file() and _looks_like_session(entry):
                found.append(entry)
        except OSError:
            continue
    return found[:limit]


def _looks_like_session(path: Path) -> bool:
    name = path.name.lower()
    if name in {".aider.chat.history.md", "runs.jsonl", "picks.jsonl", "human_picks.json"}:
        return True
    if path.suffix.lower() not in SESSION_SUFFIXES:
        return False
    if path.suffix.lower() == ".jsonl":
        return True
    return any(marker in name for marker in SESSION_NAME_MARKERS)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result
