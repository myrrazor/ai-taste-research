"""Find taste files from the current working directory."""

from __future__ import annotations

from pathlib import Path

from nanotaste.domains import normalize_domain
from nanotaste.security import MAX_TASTE_FILE_BYTES, safe_resolve_file

TASTE_FILE_NAME = "TASTE.md"
TASTE_DIR_NAME = "taste"


class TasteFileNotFoundError(ValueError):
    """Raised when no taste file exists anywhere in the discovery search path."""


def discover_taste_paths(
    cwd: Path,
    domain: str,
    taste_file: Path | None = None,
    taste_dir: Path | None = None,
) -> list[Path]:
    """Return existing global and domain-specific taste files.

    Discovery rules:

    * ``taste_file`` disables upward discovery. It is loaded together with companion
      ``<domain>.md`` files from ``taste_dir`` (default: ``taste/`` beside the file),
      including ``taste/learned/<domain>.md``.
    * Otherwise ``cwd`` and then each parent directory is checked, nearest first, for
      ``TASTE.md`` and ``taste/<domain>.md`` (or ``taste_dir/<domain>.md``). The first
      directory that holds either supplies every rule; the walk stops there.
    * An empty list means nothing was found anywhere on that path. Callers decide
      whether that is an error; ``TasteRouter`` fails unless ``no_taste`` is set.
    """
    if taste_file:
        base = safe_resolve_file(
            taste_file,
            limit_bytes=MAX_TASTE_FILE_BYTES,
            label="taste file",
        )
        discovered = [base]
        if taste_dir:
            domain_root = resolve_taste_dir(cwd, taste_dir)
        else:
            domain_root = (base.parent / TASTE_DIR_NAME).expanduser()
        discovered.extend(_domain_files(domain_root, normalize_domain(domain)))
        return _dedupe(discovered)

    roots = _candidate_roots(cwd)
    explicit_taste_dir = resolve_taste_dir(cwd, taste_dir) if taste_dir else None
    for root in roots:
        paths: list[Path] = []
        base = root / TASTE_FILE_NAME
        if base.exists() or base.is_symlink():
            paths.append(
                safe_resolve_file(
                    base,
                    root=root,
                    limit_bytes=MAX_TASTE_FILE_BYTES,
                    label="taste file",
                )
            )
        folder = explicit_taste_dir or root / TASTE_DIR_NAME
        if folder.exists():
            paths.extend(_domain_files(folder, normalize_domain(domain)))
        if paths:
            return _dedupe(paths)
    return []


def describe_search(cwd: Path, domain: str, taste_dir: Path | None = None) -> str:
    """Human-readable summary of where discovery looked, for not-found messages."""
    canonical = normalize_domain(domain)
    start = cwd.resolve()
    if taste_dir:
        return (
            f"looked for {TASTE_FILE_NAME} in {start} and its parent directories, and for "
            f"{canonical}.md in {resolve_taste_dir(cwd, taste_dir)}"
        )
    return (
        f"looked for {TASTE_FILE_NAME} and {TASTE_DIR_NAME}/{canonical}.md in {start} "
        "and its parent directories"
    )


def resolve_taste_dir(cwd: Path, taste_dir: Path) -> Path:
    """Resolve an explicit taste directory relative to ``cwd`` when it is not absolute."""
    expanded = taste_dir.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (cwd.resolve() / expanded).resolve()


def _candidate_roots(cwd: Path) -> list[Path]:
    current = cwd.resolve()
    roots = [current]
    roots.extend(current.parents)
    return roots


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def _domain_files(folder: Path, domain: str) -> list[Path]:
    files: list[Path] = []
    for candidate in (folder / f"{domain}.md", folder / "learned" / f"{domain}.md"):
        if candidate.exists() or candidate.is_symlink():
            files.append(
                safe_resolve_file(
                    candidate,
                    root=folder,
                    limit_bytes=MAX_TASTE_FILE_BYTES,
                    label="domain taste file",
                )
            )
    return files
