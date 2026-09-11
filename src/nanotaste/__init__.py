"""NanoTaste: a tiny taste-file harness for comparing AI outputs."""

from nanotaste.schema import TasteProfile, TasteRules
from nanotaste.scoring import SelectionResult, ScoredCandidate, compare_candidates
from nanotaste.agent import TasteAgent, TasteCritic, TasteRouter, TasteUpdater

# Keep in sync with [project].version in pyproject.toml; a test checks the two agree.
__version__ = "0.1.0rc0"

__all__ = [
    "SelectionResult",
    "ScoredCandidate",
    "TasteProfile",
    "TasteRules",
    "TasteAgent",
    "TasteCritic",
    "TasteRouter",
    "TasteUpdater",
    "__version__",
    "compare_candidates",
]
