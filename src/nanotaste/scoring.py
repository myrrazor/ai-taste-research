"""Deterministic taste scoring for candidate outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nanotaste.schema import TasteProfile, TasteRules

WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*", re.IGNORECASE)
QUOTED_RE = re.compile(r'"([^"]+)"|`([^`]+)`|' + r"'([^']+)'")
MIN_ELIGIBLE_WORD_LENGTH = 4
MAX_POINTS_PER_RULE = 2
MAX_POSITIVE_POINTS = 6
# A forbidden word also matches these simple inflections of itself ("seamless" catches
# "seamlessly"). Words shorter than MIN_INFLECTION_STEM match literally.
INFLECTION_SUFFIXES = ("", "s", "es", "ed", "ing", "ly", "ness")
MIN_INFLECTION_STEM = 4
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
    taste_sources: tuple[Path, ...] = ()

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
        taste_sources=tuple(profile.source_paths),
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

    candidate_words = _eligible_words(text)
    matched_words: set[str] = set()
    positive_score = 0
    for rule in rules.positive_rules():
        if _is_negative_rule(rule):
            continue
        matches = _content_matches(rule, candidate_words)
        if matches:
            points = min(MAX_POINTS_PER_RULE, len(matches))
            positive_score += points
            matched_words.update(matches)
            reasons.append(f"+{points} matches taste: {', '.join(matches[:3])}")
    positive_score = min(positive_score, MAX_POSITIVE_POINTS)
    # Echo guard: a draft cannot earn more taste credit than it has eligible words of
    # its own, so a candidate assembled from rule vocabulary scores nothing for it.
    own_words = len(candidate_words - matched_words)
    if positive_score > own_words:
        reasons.append(
            f"-{positive_score - own_words} echo guard: {len(matched_words)} of "
            f"{len(candidate_words)} eligible words are copied from taste rules"
        )
        positive_score = own_words
    score += positive_score

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


def _eligible_words(text: str) -> set[str]:
    """Words that can carry positive taste credit: 4+ characters, not a stop word."""
    return {
        word
        for word in WORD_RE.findall(text.lower())
        if len(word) >= MIN_ELIGIBLE_WORD_LENGTH and word not in STOP_WORDS
    }


def _content_matches(rule: str, candidate_words: set[str]) -> list[str]:
    rule_words = _eligible_words(_positive_rule_text(rule))
    return sorted(rule_words & candidate_words)


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
    words = phrase.split()
    if words and all(re.fullmatch(r"[a-z0-9'-]+", word, re.IGNORECASE) for word in words):
        *head, last = words
        parts = [re.escape(word) for word in head] + [_inflected_word(last)]
        return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)
    return re.compile(re.escape(phrase), re.IGNORECASE)


def _inflected_word(word: str) -> str:
    """Regex alternation for a word and its simple suffix inflections."""
    if len(word) < MIN_INFLECTION_STEM:
        return re.escape(word)
    forms = {word + suffix for suffix in INFLECTION_SUFFIXES}
    if word.endswith("e"):
        forms.update((word + "d", word[:-1] + "ing"))
    longest_first = sorted(forms, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(form) for form in longest_first) + ")"
