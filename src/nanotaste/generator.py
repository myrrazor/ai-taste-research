"""Small deterministic draft generator used by the first NanoTaste prototype."""

from __future__ import annotations

from nanotaste.domains import normalize_domain
from nanotaste.schema import TasteRules


def generate_candidates(prompt: str, rules: TasteRules, count: int = 3) -> list[str]:
    """Generate simple candidate drafts when no external model is wired in yet."""
    if count < 2:
        raise ValueError("NanoTaste needs at least two candidates")
    domain = normalize_domain(rules.domain)
    subject = _subject_from_prompt(prompt)
    drafts = [
        _generic_candidate(subject, domain),
        _specific_candidate(subject, domain),
        _constraint_candidate(subject, domain),
        _critic_candidate(subject, domain),
    ]
    if count > len(drafts):
        raise ValueError(f"deterministic generator supports at most {len(drafts)} candidates")
    return drafts[:count]


def _subject_from_prompt(prompt: str) -> str:
    text = " ".join(prompt.strip().split())
    if not text:
        return "the idea"
    for verb in ("design ", "write ", "build ", "create ", "implement ", "make ", "draft "):
        if text.lower().startswith(verb):
            text = text[len(verb) :]
            break
    return text[:1].lower() + text[1:].rstrip(".")


def _generic_candidate(subject: str, domain: str) -> str:
    if domain == "code":
        return (
            "This function is responsible for the implementation details. "
            f"Add console.log calls while building {subject}."
        )
    if domain == "aesthetic":
        return (
            f"Use a gradient hero with floating card sections to showcase {subject}. "
            "Add decorative blob backgrounds for energy."
        )
    return (
        f"In today's fast-paced world, {subject} empowers teams to seamlessly "
        "unlock their potential."
    )


def _specific_candidate(subject: str, domain: str) -> str:
    if domain == "code":
        return (
            f"Build {subject} as a small parser, scorer, and CLI. Return scores with "
            "reasons so tests can prove the behavior."
        )
    if domain == "aesthetic":
        return (
            f"Show {subject} with one clear visual hierarchy, real content, and a "
            "single primary action above the fold."
        )
    if domain == "product":
        return (
            f"Start with one loop for {subject}: compare three drafts, pick one, "
            "and explain the decision."
        )
    return (
        f"Run {subject} on three drafts. Keep the concrete one, reject the vague "
        "one, and write down why."
    )


def _constraint_candidate(subject: str, domain: str) -> str:
    if domain == "code":
        return f"Implement {subject} with explicit return values, short helpers, and failure cases covered."
    if domain == "aesthetic":
        return f"For {subject}, lead with one real product image, a concrete detail, and one primary action."
    if domain == "product":
        return f"Frame {subject} as a narrow experiment with one observable success signal."
    return f"Make {subject} concrete: name the action, the output, and the signal that proves it worked."


def _critic_candidate(subject: str, domain: str) -> str:
    if domain == "code":
        return f"Keep {subject} boring and testable. Reject candidates that hide errors or make review harder."
    return f"Make {subject} specific enough to inspect. Reject candidates that lean on known forbidden moves."
