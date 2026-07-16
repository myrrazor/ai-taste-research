"""Composable NanoTaste agent parts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from nanotaste.discovery import discover_taste_paths
from nanotaste.domains import normalize_domain
from nanotaste.generator import generate_candidates
from nanotaste.schema import TasteProfile, TasteRules
from nanotaste.scoring import SelectionResult, compare_candidates
from nanotaste.security import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATES_PER_PROMPT,
    MAX_PROMPT_BYTES,
    validate_text_limit,
)
from nanotaste.update import TasteUpdateProposal, propose_update, write_proposal


@dataclass(frozen=True)
class TasteContext:
    """Resolved taste state for one task."""

    domain: str
    profile: TasteProfile
    rules: TasteRules
    source_paths: tuple[Path, ...]


class CandidateGenerator(Protocol):
    """Candidate generator interface used by TasteAgent."""

    def generate(self, prompt: str, context: TasteContext, count: int = 3) -> list[str]:
        """Return candidate outputs for the prompt."""


class TasteRouter:
    """Routes a task to the right taste domain and files."""

    def __init__(
        self,
        cwd: Path | None = None,
        taste_file: Path | None = None,
        taste_dir: Path | None = None,
    ) -> None:
        self.cwd = cwd or Path.cwd()
        self.taste_file = taste_file
        self.taste_dir = taste_dir

    def resolve(self, domain: str | None = None) -> TasteContext:
        """Load the taste profile and domain rules for one task."""
        canonical = normalize_domain(domain)
        paths = discover_taste_paths(self.cwd, canonical, self.taste_file, self.taste_dir)
        profile = TasteProfile.from_paths(paths) if paths else TasteProfile.empty()
        return TasteContext(
            domain=canonical,
            profile=profile,
            rules=profile.rules_for(canonical),
            source_paths=tuple(paths),
        )


class DeterministicGenerator:
    """Built-in generator for calibration and local smoke tests."""

    def generate(self, prompt: str, context: TasteContext, count: int = 3) -> list[str]:
        """Generate deterministic candidates without calling an LLM."""
        return generate_candidates(prompt, context.rules, count)


class TasteCritic:
    """Selects the candidate that best matches the loaded taste rules."""

    def select(
        self, candidates: list[str], context: TasteContext, prompt: str = ""
    ) -> SelectionResult:
        """Score candidates and return the selected output."""
        return compare_candidates(candidates, context.profile, context.domain, prompt)


class TasteUpdater:
    """Creates approval-gated taste update proposals from human edits."""

    def propose(self, before: str, after: str, domain: str = "general") -> TasteUpdateProposal:
        """Return a pending taste update proposal."""
        return propose_update(before, after, normalize_domain(domain))

    def write(self, proposal: TasteUpdateProposal, output_dir: Path, stem: str) -> Path:
        """Write a pending proposal file for later approval."""
        return write_proposal(proposal, output_dir, stem)


class TasteAgent:
    """Small orchestrator composed from router, generator, critic, and updater."""

    def __init__(
        self,
        router: TasteRouter,
        generator: CandidateGenerator | None = None,
        critic: TasteCritic | None = None,
        updater: TasteUpdater | None = None,
    ) -> None:
        self.router = router
        self.generator = generator or DeterministicGenerator()
        self.critic = critic or TasteCritic()
        self.updater = updater or TasteUpdater()

    @classmethod
    def from_paths(
        cls,
        cwd: Path | None = None,
        taste_file: Path | None = None,
        taste_dir: Path | None = None,
    ) -> "TasteAgent":
        """Create an agent that discovers taste files from the supplied paths."""
        return cls(TasteRouter(cwd=cwd, taste_file=taste_file, taste_dir=taste_dir))

    def run(
        self, prompt: str, domain: str = "general", count: int = 3
    ) -> SelectionResult:
        """Generate candidates and select the best taste match."""
        validate_text_limit(prompt, MAX_PROMPT_BYTES, "prompt")
        if count > MAX_CANDIDATES_PER_PROMPT:
            raise ValueError(
                f"candidate count is too large: {count} > {MAX_CANDIDATES_PER_PROMPT}"
            )
        context = self.router.resolve(domain)
        candidates = self.generator.generate(prompt, context, count)
        return self.critic.select(candidates, context, prompt)

    def compare(
        self, candidates: list[str], domain: str = "general", prompt: str = ""
    ) -> SelectionResult:
        """Select the best candidate from caller-provided outputs."""
        validate_text_limit(prompt, MAX_PROMPT_BYTES, "prompt")
        if len(candidates) > MAX_CANDIDATES_PER_PROMPT:
            raise ValueError(
                f"too many candidates: {len(candidates)} > {MAX_CANDIDATES_PER_PROMPT}"
            )
        for index, candidate in enumerate(candidates, start=1):
            validate_text_limit(candidate, MAX_CANDIDATE_BYTES, f"candidate #{index}")
        context = self.router.resolve(domain)
        return self.critic.select(candidates, context, prompt)

    def propose_update(
        self,
        before: str,
        after: str,
        domain: str = "general",
        output_dir: Path | None = None,
        stem: str = "taste-update",
    ) -> tuple[TasteUpdateProposal, Path | None]:
        """Create an update proposal and optionally write it to disk."""
        proposal = self.updater.propose(before, after, domain)
        path = self.updater.write(proposal, output_dir, stem) if output_dir else None
        return proposal, path
