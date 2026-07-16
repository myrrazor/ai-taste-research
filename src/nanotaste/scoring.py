"""Deterministic taste scoring for candidate outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from nanotaste.schema import TasteProfile, TasteRules

WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*", re.IGNORECASE)
QUOTED_RE = re.compile(r'"([^"]+)"|`([^`]+)`|' + r"'([^']+)'")
STOP_WORDS = {
    "about",
    "again",
    "also",
    "and",
    "are",
    "because",
    "being",
    "but",
    "closer",
    "far",
    "from",
    "into",
    "not",
    "that",
    "the",
    "than",
    "this",
    "with",
    "without",
    "would",
}


@dataclass(frozen=True)
class ScoredCandidate:
    """A candidate output plus its deterministic taste score."""

    index: int
    text: str
    score: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class SelectionResult:
    """Selected candidate, rejected candidates, and taste metadata."""

    domain: str
    taste_hash: str
    selected: ScoredCandidate
    rejected: tuple[ScoredCandidate, ...]
    all_scores: tuple[ScoredCandidate, ...]

    def to_record(self, prompt: str) -> dict[str, object]:
        """Return a JSON-serializable output record."""
        return {
            "prompt": prompt,
            "domain": self.domain,
            "taste_hash": self.taste_hash,
            "selected_candidate": _candidate_record(self.selected),
            "rejected_candidates": [_candidate_record(item) for item in self.rejected],
            "score_reasons": list(self.selected.reasons),
        }


def compare_candidates(
    candidates: list[str],
    profile: TasteProfile,
    domain: str,
    prompt: str = "",
) -> SelectionResult:
    """Score candidate outputs and select the best taste match."""
    if not candidates:
        raise ValueError("compare_candidates needs at least one candidate")
    rules = profile.rules_for(domain)
    scored = tuple(score_candidate(i, text, rules, prompt) for i, text in enumerate(candidates))
    selected = max(scored, key=lambda item: (item.score, -item.index))
    rejected = tuple(item for item in scored if item.index != selected.index)
    return SelectionResult(
        domain=rules.domain,
        taste_hash=profile.digest,
        selected=selected,
        rejected=rejected,
        all_scores=scored,
    )


def score_candidate(
    index: int, candidate: str, rules: TasteRules, prompt: str = ""
) -> ScoredCandidate:
    """Score one candidate against domain rules."""
    text = candidate.lower()
    score = 0
    reasons: list[str] = []

    for rule in rules.forbidden_moves:
        for phrase in _rule_phrases(rule):
            if phrase and _contains_forbidden_phrase(text, phrase):
                score -= 3
                reasons.append(f"-3 forbidden move: {phrase}")
                break

    positive_score = 0
    for rule in rules.positive_rules():
        if _is_negative_rule(rule):
            continue
        matches = _content_matches(rule, text)
        if matches:
            points = min(2, len(matches))
            positive_score += points
            reasons.append(f"+{points} matches taste: {', '.join(matches[:3])}")
    score += min(positive_score, 6)

    if _has_specific_detail(candidate):
        score += 1
        reasons.append("+1 concrete detail")
    if prompt and _mentions_prompt_terms(prompt, text):
        score += 1
        reasons.append("+1 stays on brief")

    return ScoredCandidate(index=index, text=candidate, score=score, reasons=tuple(reasons))


def _candidate_record(candidate: ScoredCandidate) -> dict[str, object]:
    return {
        "index": candidate.index,
        "text": candidate.text,
        "score": candidate.score,
        "reasons": list(candidate.reasons),
    }


def _rule_phrases(rule: str) -> list[str]:
    quoted = [part for match in QUOTED_RE.findall(rule) for part in match if part]
    if quoted:
        return [item.strip().lower() for item in quoted]
    cleaned = rule.strip().lower().rstrip(".")
    cleaned = re.sub(r"^(never|avoid|do not|don't)\s+", "", cleaned)
    return [cleaned]


def _content_matches(rule: str, candidate_text: str) -> list[str]:
    candidate_words = set(WORD_RE.findall(candidate_text.lower()))
    rule = _positive_rule_text(rule)
    words = []
    for word in WORD_RE.findall(rule.lower()):
        if len(word) < 4 or word in STOP_WORDS:
            continue
        if word in candidate_words:
            words.append(word)
    return sorted(set(words))


def _is_negative_rule(rule: str) -> bool:
    lower = rule.strip().lower()
    phrase_markers = (
        "bad:",
        "far from",
        "negative",
    )
    word_markers = ("avoid", "no", "not", "never", "reject", "without")
    return any(marker in lower for marker in phrase_markers) or any(
        re.search(rf"\b{marker}\b", lower) for marker in word_markers
    )


def _positive_rule_text(rule: str) -> str:
    lower = rule.lower()
    split_markers = (" than to ", " rather than ", " instead of ")
    for marker in split_markers:
        index = lower.find(marker)
        if index != -1:
            return rule[:index]
    return rule


def _has_specific_detail(candidate: str) -> bool:
    return bool(re.search(r"\b\d+([:.]\d+)?\b|\$|%|\b(monday|tuesday|week|hour|minute)\b", candidate, re.I))


def _mentions_prompt_terms(prompt: str, candidate_text: str) -> bool:
    candidate_words = set(WORD_RE.findall(candidate_text.lower()))
    prompt_words = {
        word.lower()
        for word in WORD_RE.findall(prompt)
        if len(word) > 4 and word.lower() not in STOP_WORDS
    }
    return any(word in candidate_words for word in prompt_words)


def _contains_forbidden_phrase(candidate_text: str, phrase: str) -> bool:
    if not phrase:
        return False
    pattern = _phrase_pattern(phrase)
    for match in pattern.finditer(candidate_text):
        prefix = candidate_text[max(0, match.start() - 50) : match.start()]
        if re.search(r"\b(avoid|forbidden|no|not|never|penalize|reject|without)\b|far from", prefix):
            continue
        return True
    return False


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase)
    if re.fullmatch(r"[a-z0-9'-]+", phrase, re.IGNORECASE):
        return re.compile(rf"\b{escaped}\b", re.IGNORECASE)
    return re.compile(escaped, re.IGNORECASE)
