"""Local worktree and full-history privacy scanning for the pre-push gate."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_PRIVATE_PATTERNS = {
    "absolute_home_path": re.compile(b"/" + b"Users/" + rb"[^/\s]+/"),
    "github_token": re.compile(b"(?:ghp" + rb"_|github_pat_)[A-Za-z0-9_]{16,}"),
    "private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "private_strategy_doc": re.compile(
        rb"(?:TASTE_AGENT_PROJECT_PLAN|NANOTASTE_ENGINEERING_RESEARCH_AUDIT)\.md"
    ),
}
PRIVACY_SCAN_VERSION = "nanotaste-private-pattern-scan/1"


class PrivacyError(ValueError):
    """Raised when a privacy scan cannot complete reliably."""


@dataclass(frozen=True)
class PrivacyFinding:
    """One matched policy name and source location, without leaking matched text."""

    policy: str
    source: str


def _scan_bytes(data: bytes, source: str) -> list[PrivacyFinding]:
    return [
        PrivacyFinding(policy=name, source=source)
        for name, pattern in DEFAULT_PRIVATE_PATTERNS.items()
        if pattern.search(data)
    ]


def scan_worktree(root: Path) -> list[PrivacyFinding]:
    """Scan tracked and unignored files that could enter a release tree."""
    findings = []
    if (root / ".git").exists():
        listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        paths = [root / item.decode("utf-8") for item in listed.split(b"\0") if item]
    else:
        paths = sorted(root.rglob("*"))
    for path in paths:
        if ".git" in path.parts:
            continue
        if path.is_symlink():
            findings.append(PrivacyFinding(policy="symlink_release_input", source=str(path)))
            continue
        if not path.is_file():
            continue
        try:
            findings.extend(_scan_bytes(path.read_bytes(), str(path.relative_to(root))))
        except OSError as exc:
            raise PrivacyError(f"cannot read worktree path: {path}") from exc
    return findings


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PrivacyError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def scan_git_history(root: Path, *, max_blob_bytes: int = 8 * 1024 * 1024) -> list[PrivacyFinding]:
    """Scan every reachable Git blob, including content deleted from the worktree."""
    objects = _git(root, "rev-list", "--objects", "--all").decode("utf-8", errors="strict")
    findings = []
    seen = set()
    for line in objects.splitlines():
        object_id, _, path = line.partition(" ")
        if object_id in seen:
            continue
        seen.add(object_id)
        if _git(root, "cat-file", "-t", object_id).strip() != b"blob":
            continue
        size = int(_git(root, "cat-file", "-s", object_id).strip())
        if size > max_blob_bytes:
            raise PrivacyError(f"reachable blob exceeds privacy scan limit: {object_id}")
        data = _git(root, "cat-file", "blob", object_id)
        label = f"{object_id}:{path or '<unnamed>'}"
        findings.extend(_scan_bytes(data, label))
    return findings


def require_clean(findings: Iterable[PrivacyFinding]) -> None:
    """Fail without reproducing the potentially private matched content."""
    collected = list(findings)
    if collected:
        summary = ", ".join(f"{item.policy}@{item.source}" for item in collected[:10])
        raise PrivacyError(f"privacy scan found {len(collected)} match(es): {summary}")
