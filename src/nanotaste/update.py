"""Approval-gated taste update proposals from user edits."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path

from nanotaste.security import MAX_UPDATE_INPUT_BYTES, atomic_write_text, validate_text_limit


@dataclass(frozen=True)
class TasteUpdateProposal:
    """A markdown proposal produced from before/after output edits."""

    markdown: str
    added_lines: tuple[str, ...]
    removed_lines: tuple[str, ...]


def propose_update(before: str, after: str, domain: str = "general") -> TasteUpdateProposal:
    """Create a taste-update proposal without mutating any taste file."""
    validate_text_limit(before, MAX_UPDATE_INPUT_BYTES, "before text")
    validate_text_limit(after, MAX_UPDATE_INPUT_BYTES, "after text")
    before_lines = [line.strip() for line in before.splitlines() if line.strip()]
    after_lines = [line.strip() for line in after.splitlines() if line.strip()]
    added = tuple(line for line in after_lines if line not in before_lines)
    removed = tuple(line for line in before_lines if line not in after_lines)
    before_snippet, after_snippet = _representative_change(before_lines, after_lines)
    markdown = _proposal_markdown(domain, before_snippet, after_snippet, added, removed)
    return TasteUpdateProposal(markdown=markdown, added_lines=added, removed_lines=removed)


def write_proposal(proposal: TasteUpdateProposal, output_dir: Path, stem: str) -> Path:
    """Write a pending proposal file for human approval."""
    safe_stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in stem)[:60]
    path = output_dir / f"{safe_stem or 'taste-update'}.md"
    atomic_write_text(path, proposal.markdown, label="taste update proposal")
    return path


def diff_text(before: str, after: str) -> str:
    """Return a unified diff for display in proposals or logs."""
    return "\n".join(
        unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


def _representative_change(before_lines: list[str], after_lines: list[str]) -> tuple[str, str]:
    matcher = SequenceMatcher(a=before_lines, b=after_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            return " ".join(before_lines[i1:i2])[:500], " ".join(after_lines[j1:j2])[:500]
    return " ".join(before_lines[:2])[:500], " ".join(after_lines[:2])[:500]


def _proposal_markdown(
    domain: str,
    before_snippet: str,
    after_snippet: str,
    added: tuple[str, ...],
    removed: tuple[str, ...],
) -> str:
    added_block = "\n".join(f"- Possible preference signal: {_clip(line)}" for line in added[:5]) or "- No new lines detected."
    removed_block = "\n".join(f"- Possible avoid signal: {_clip(line)}" for line in removed[:5]) or "- No removed lines detected."
    return f"""# Pending Taste Update

Domain: {domain}

NanoTaste noticed an edit. Review this before changing `TASTE.md`.
Extract a general taste rule from the evidence below; do not paste private or one-off prose directly into the taste file.

## Calibration Example

> Before: {before_snippet or "[empty]"}
> After: {after_snippet or "[empty]"}
> Why: the user edited the output in this direction.

## Candidate Preferences

{added_block}

## Candidate Forbidden Moves

{removed_block}
"""


def _clip(line: str, limit: int = 180) -> str:
    compact = " ".join(line.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."
