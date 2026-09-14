"""Extract inspectable taste-rule proposals from local history and likes."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nanotaste.ingest import SessionExcerpt, load_excerpts
from nanotaste.schema import TasteProfile
from nanotaste.scoring import STOP_WORDS, WORD_RE
from nanotaste.security import MAX_LEARNED_RULES, MAX_LIKE_FILE_BYTES, atomic_write_text, safe_read_text
from nanotaste.workspace import TasteWorkspace, now_iso, replace_config, starter_taste_markdown

LEARN_STOP = STOP_WORDS | {
    "avoid",
    "candidate",
    "changed",
    "down",
    "draft",
    "excerpt",
    "file",
    "from",
    "have",
    "item",
    "just",
    "keep",
    "like",
    "make",
    "nanotaste",
    "note",
    "only",
    "path",
    "session",
    "text",
    "they",
    "this",
    "three",
    "unlike",
    "user",
    "visible",
    "with",
    "write",
    "your",
}
FORBIDDEN_STOP = LEARN_STOP | {
    "empowers",
    "fast-paced",
    "solution",
    "their",
    "today",
    "today's",
    "unlock",
}


@dataclass(frozen=True)
class LearnedSignals:
    """Lexical taste signals extracted from likes, unlikes, and sessions."""

    generated_at: str
    principles: tuple[str, ...]
    forbidden: tuple[str, ...]
    good_examples: tuple[str, ...]
    bad_examples: tuple[str, ...]
    like_count: int
    unlike_count: int
    session_count: int

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "nanotaste/learned-signals/1.0",
            "generated_at": self.generated_at,
            "principles": list(self.principles),
            "forbidden": list(self.forbidden),
            "good_examples": list(self.good_examples),
            "bad_examples": list(self.bad_examples),
            "like_count": self.like_count,
            "unlike_count": self.unlike_count,
            "session_count": self.session_count,
        }


@dataclass(frozen=True)
class LearnResult:
    """Files written by one learning pass."""

    signals: LearnedSignals
    proposal_path: Path
    signals_path: Path
    taste_created: Path | None
    taste_applied: Path | None


def learn_workspace(
    workspace: TasteWorkspace,
    *,
    apply_updates: bool = False,
    create_if_missing: bool = True,
) -> LearnResult:
    """Derive pending taste rules from local evidence."""
    likes = _read_examples(workspace.likes_dir)
    unlikes = _read_examples(workspace.unlikes_dir)
    excerpts = load_excerpts(workspace)
    signals = extract_signals(likes, unlikes, excerpts)
    workspace.learned_dir.mkdir(parents=True, exist_ok=True)
    signals_path = workspace.learned_dir / "signals.json"
    proposal_path = workspace.learned_dir / "proposal.md"
    atomic_write_text(
        signals_path,
        json.dumps(signals.to_json(), indent=2, sort_keys=True) + "\n",
        label="learned signals",
    )
    atomic_write_text(proposal_path, render_proposal(signals), label="learned proposal")
    taste_path = workspace.taste_path()
    created = None
    applied = None
    if create_if_missing and not taste_path.exists():
        atomic_write_text(
            taste_path,
            merge_taste_markdown(starter_taste_markdown(), signals),
            label="taste file",
        )
        created = taste_path
    elif apply_updates and taste_path.exists():
        current = taste_path.read_text(encoding="utf-8")
        atomic_write_text(
            taste_path,
            merge_taste_markdown(current, signals),
            label="taste file",
        )
        applied = taste_path
    replace_config(workspace, last_learn_at=signals.generated_at)
    return LearnResult(
        signals=signals,
        proposal_path=proposal_path,
        signals_path=signals_path,
        taste_created=created,
        taste_applied=applied,
    )


def extract_signals(
    likes: list[str],
    unlikes: list[str],
    excerpts: list[SessionExcerpt],
) -> LearnedSignals:
    """Return deterministic lexical signals from local evidence."""
    like_words = _word_counts(likes)
    unlike_words = _word_counts(unlikes)
    session_words = _word_counts([item.excerpt for item in excerpts])
    preferred = _preferred_words(like_words, unlike_words, session_words)
    forbidden = _forbidden_phrases(unlikes, likes)
    principles = tuple(
        f"Prefer inspectable work that keeps {word} obvious." for word in preferred[:6]
    ) or ("Prefer specific, inspectable drafts over generic filler.",)
    return LearnedSignals(
        generated_at=now_iso(),
        principles=principles[:MAX_LEARNED_RULES],
        forbidden=tuple(forbidden[:12]),
        good_examples=tuple(likes[:5]),
        bad_examples=tuple(unlikes[:5]),
        like_count=len(likes),
        unlike_count=len(unlikes),
        session_count=len(excerpts),
    )


def render_proposal(signals: LearnedSignals) -> str:
    """Render an approval-gated taste-update proposal from learned signals."""
    principles = "\n".join(f"- {item}" for item in signals.principles) or "- No new principles yet."
    forbidden = "\n".join(f'- "{item}"' for item in signals.forbidden) or "- No new forbidden moves yet."
    goods = "\n".join(f"> Good: {_clip(item)}\n> Why: dropped in or harvested as preferred." for item in signals.good_examples)
    bads = "\n".join(f"> Bad: {_clip(item)}\n> Why: dropped in as something to avoid." for item in signals.bad_examples)
    return f"""# Pending learned taste update

Generated: {signals.generated_at}

NanoTaste extracted these lexical signals from likes, unlikes, and opted-in
session history. This is not a trained preference model. Review before applying
anything to `TASTE.md`.

- Liked examples: {signals.like_count}
- Unliked examples: {signals.unlike_count}
- Session excerpts: {signals.session_count}

## Proposed Principles

{principles}

## Proposed Forbidden Moves

{forbidden}

## Calibration Examples

{goods or "> Good: add a liked file with `nanotaste like PATH`"}

{bads or "> Bad: add a disliked file with `nanotaste unlike PATH`"}
"""


def merge_taste_markdown(existing: str, signals: LearnedSignals) -> str:
    """Append learned rules that are not already present in the taste file."""
    profile = TasteProfile.from_text(existing)
    current_rules = profile.rules_for("general")
    known = {item.lower() for item in current_rules.positive_rules() + current_rules.forbidden_moves}
    new_principles = [item for item in signals.principles if item.lower() not in known]
    new_forbidden = [item for item in signals.forbidden if item.lower() not in known]
    if not new_principles and not new_forbidden and not signals.good_examples and not signals.bad_examples:
        return existing
    chunks = [existing.rstrip()]
    if new_principles:
        chunks.extend(["", "## Principles", "", "### general", ""])
        chunks.extend(f"- {item}" for item in new_principles)
    if new_forbidden:
        chunks.extend(["", "## Forbidden Moves", "", "### general", ""])
        chunks.extend(f'- "{item}"' for item in new_forbidden)
    if signals.good_examples or signals.bad_examples:
        chunks.extend(["", "## Calibration Examples", "", "### general", ""])
        for item in signals.good_examples[:2]:
            chunks.append(f"> Good: {_clip(item)}")
            chunks.append("> Why: operator-liked example.")
            chunks.append("")
        for item in signals.bad_examples[:2]:
            chunks.append(f"> Bad: {_clip(item)}")
            chunks.append("> Why: operator-unliked example.")
            chunks.append("")
    return "\n".join(chunks).rstrip() + "\n"


def _read_examples(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    texts: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
            continue
        try:
            text = safe_read_text(path, limit_bytes=MAX_LIKE_FILE_BYTES, label="preference example").strip()
        except (OSError, ValueError):
            continue
        if text.startswith("#"):
            text = "\n".join(text.splitlines()[1:]).strip()
        if text:
            texts.append(" ".join(text.split()))
    return texts


def _word_counts(texts: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for word in WORD_RE.findall(text.lower()):
            if len(word) < 4 or word in LEARN_STOP:
                continue
            counts[word] += 1
    return counts


def _preferred_words(
    likes: Counter[str],
    unlikes: Counter[str],
    sessions: Counter[str],
) -> list[str]:
    scored: list[tuple[int, str]] = []
    for word, count in likes.items():
        score = count * 2 + sessions.get(word, 0) - unlikes.get(word, 0)
        if score <= 0 or unlikes.get(word, 0) >= count:
            continue
        scored.append((score, word))
    if not scored:
        for word, count in sessions.items():
            if count < 2 or unlikes.get(word, 0):
                continue
            scored.append((count, word))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [word for _score, word in scored]


def _forbidden_phrases(unlikes: list[str], likes: list[str]) -> list[str]:
    liked_text = " ".join(likes).lower()
    phrases: Counter[str] = Counter()
    for text in unlikes:
        lower = text.lower()
        for phrase in (
            "in today's fast-paced world",
            "seamlessly",
            "empower",
            "leverage",
            "cutting-edge",
            "unlock their potential",
            "this function is responsible for",
        ):
            if phrase in lower and phrase not in liked_text:
                phrases[phrase] += 2
        for word in WORD_RE.findall(lower):
            if len(word) >= 8 and word not in FORBIDDEN_STOP and word not in liked_text:
                phrases[word] += 1
    return [phrase for phrase, _count in phrases.most_common()]


def _clip(text: str, limit: int = 220) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
