"""Find taste files from the current working directory."""

from __future__ import annotations

from pathlib import Path

from nanotaste.domains import normalize_domain
from nanotaste.security import MAX_TASTE_FILE_BYTES, safe_resolve_file


def discover_taste_paths(
    cwd: Path,
    domain: str,
    taste_file: Path | None = None,
    taste_dir: Path | None = None,
) -> list[Path]:
    """Return existing global and domain-specific taste files."""
    if taste_file:
        base = safe_resolve_file(
            taste_file,
            limit_bytes=MAX_TASTE_FILE_BYTES,
            label="taste file",
        )
        discovered = [base]
        domain_root = (base.parent / "taste").expanduser()
        discovered.extend(_domain_files(domain_root, normalize_domain(domain)))
        return _dedupe(discovered)

    roots = _candidate_roots(cwd)
    explicit_taste_dir = _resolve_taste_dir(cwd, taste_dir) if taste_dir else None
    for root in roots:
        paths: list[Path] = []
        base = root / "TASTE.md"
        if base.exists() or base.is_symlink():
            paths.append(
                safe_resolve_file(
                    base,
                    root=root,
                    limit_bytes=MAX_TASTE_FILE_BYTES,
                    label="taste file",
                )
            )
        folder = explicit_taste_dir or root / "taste"
        if folder.exists():
            paths.extend(_domain_files(folder, normalize_domain(domain)))
        if paths:
            return _dedupe(paths)
    return []


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


def _resolve_taste_dir(cwd: Path, taste_dir: Path) -> Path:
    expanded = taste_dir.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (cwd.resolve() / expanded).resolve()
