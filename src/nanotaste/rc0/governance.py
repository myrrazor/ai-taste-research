"""Deterministic CODEOWNERS governance-bootstrap validation."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from nanotaste.rc0.invariants import load_invariant_manifest

CODEOWNERS_BYTES = (
    b"* @masterhit\n"
    b".github/workflows/ @masterhit\n"
    b".github/dependabot.yml @masterhit\n"
    b".github/CODEOWNERS @masterhit\n"
)


class GovernanceError(ValueError):
    """Raised when the bootstrap commit or base governance is not exact."""


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
        raise GovernanceError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def governance_recipe() -> dict[str, Any]:
    """Return the frozen local recipe without creating refs or commits."""
    return dict(load_invariant_manifest()["governance_bootstrap"])


def validate_codeowners_bytes(data: bytes) -> None:
    """Require exact content, mode-independent bytes, and the frozen digest."""
    expected = governance_recipe()
    if data != CODEOWNERS_BYTES:
        raise GovernanceError("CODEOWNERS content, line endings, or final newline differ")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected["codeowners_blob_sha256"]:
        raise GovernanceError("CODEOWNERS bytes do not match the frozen digest")


def validate_governance_commit(repo: Path, commit: str) -> None:
    """Validate the deterministic bootstrap commit without mutating any ref."""
    recipe = governance_recipe()
    parents = _git(repo, "show", "-s", "--format=%P", commit).decode().strip().split()
    if parents != [recipe["parent_commit"]]:
        raise GovernanceError("governance commit has the wrong parent")
    changed = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", commit)
    changed_paths = [line for line in changed.decode().splitlines() if line]
    if changed_paths != recipe["changed_paths"]:
        raise GovernanceError("governance commit changes an unapproved path")
    tree_entry = _git(repo, "ls-tree", commit, recipe["codeowners_path"]).decode().strip()
    if not tree_entry.startswith(f"{recipe['codeowners_mode']} blob "):
        raise GovernanceError("CODEOWNERS mode or object type differs")
    data = _git(repo, "show", f"{commit}:{recipe['codeowners_path']}")
    validate_codeowners_bytes(data)


def validate_base_codeowners(repo: Path, base_ref: str) -> None:
    """Require the exact CODEOWNERS blob on an integration PR base ref."""
    recipe = governance_recipe()
    data = _git(repo, "show", f"{base_ref}:{recipe['codeowners_path']}")
    validate_codeowners_bytes(data)
