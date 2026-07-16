import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.schema import TasteProfile
from nanotaste.scoring import compare_candidates


SPECIFIC_TASTE = """# TASTE.md

## Principles

### aesthetic
- Use real product imagery and clear hierarchy.
- Far from gradient decoration and floating cards.

### writing
- Use concrete nouns and direct verbs.

### code
- Return scores with reasons and keep the parser small.

## Forbidden Moves

### aesthetic
- "gradient"
- "floating card"
- "decorative blob"

### writing
- "In today's fast-paced world"
- "seamlessly"
- "empower"

### code
- "This function is responsible for"
- "console.log"
"""

GENERIC_STYLE = """# Generic Style

## Principles

### general
- Make things good.
- Keep the output acceptable.
- Follow common best practices.
"""


class TasteScoringTests(unittest.TestCase):
    def test_flags_forbidden_moves(self):
        profile = TasteProfile.from_text(SPECIFIC_TASTE)
        result = compare_candidates(
            [
                "Use a gradient hero with floating card sections and a decorative blob.",
                "Show the actual product with clear hierarchy and one primary action.",
            ],
            profile,
            "design",
            "Design a homepage for a coffee subscription.",
        )

        self.assertEqual(result.selected.index, 1)
        self.assertLess(result.all_scores[0].score, result.all_scores[1].score)
        self.assertTrue(any("forbidden move: gradient" in r for r in result.all_scores[0].reasons))

    def test_design_rejects_generic_saas_visuals(self):
        profile = TasteProfile.from_text(SPECIFIC_TASTE)
        result = compare_candidates(
            [
                "Gradient background, floating card modules, and decorative blob shapes.",
                "One product photo, clear hierarchy, visible price, and a direct checkout action.",
            ],
            profile,
            "aesthetic",
        )

        self.assertEqual(result.selected.index, 1)
        self.assertFalse(any("matches taste: decoration" in r for r in result.all_scores[0].reasons))

    def test_writing_rejects_vague_ai_prose(self):
        profile = TasteProfile.from_text(SPECIFIC_TASTE)
        result = compare_candidates(
            [
                "In today's fast-paced world, our tool empowers teams to seamlessly innovate.",
                "Compare three drafts, pick the concrete one, and write down why.",
            ],
            profile,
            "writing",
        )

        self.assertEqual(result.selected.index, 1)

    def test_code_prefers_explicit_testable_shape(self):
        profile = TasteProfile.from_text(SPECIFIC_TASTE)
        result = compare_candidates(
            [
                "This function is responsible for implementation details. Add console.log for visibility.",
                "Parse the markdown, return scores with reasons, and cover the parser with tests.",
            ],
            profile,
            "code",
        )

        self.assertEqual(result.selected.index, 1)

    def test_generic_style_guide_behaves_differently(self):
        candidates = [
            "Use a gradient hero with floating card sections and a decorative blob.",
            "Show the actual product with clear hierarchy and one primary action.",
        ]
        generic = compare_candidates(candidates, TasteProfile.from_text(GENERIC_STYLE), "design")
        specific = compare_candidates(candidates, TasteProfile.from_text(SPECIFIC_TASTE), "design")

        self.assertEqual(generic.selected.index, 0)
        self.assertEqual(specific.selected.index, 1)

    def test_positive_scoring_uses_whole_words(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Principles

### aesthetic
- Use real objects.
"""
        )
        result = compare_candidates(
            ["This unreal abstraction looks polished.", "This shows real objects."],
            profile,
            "aesthetic",
        )

        self.assertEqual(result.selected.index, 1)
        self.assertFalse(any("real" in reason for reason in result.all_scores[0].reasons))

    def test_forbidden_scoring_ignores_negated_references(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Forbidden Moves

### aesthetic
- "gradient"
"""
        )
        result = compare_candidates(
            ["Avoid gradient decoration and use the product photo.", "Use a gradient hero."],
            profile,
            "aesthetic",
        )

        self.assertEqual(result.selected.index, 0)
        self.assertFalse(any("forbidden move" in reason for reason in result.all_scores[0].reasons))

    def test_no_prefixed_rules_do_not_score_as_positive_matches(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Principles

### writing
- No generic advice.
"""
        )
        result = compare_candidates(
            ["Generic advice for modern teams.", "Use a numbered checklist."],
            profile,
            "writing",
        )

        self.assertFalse(any("generic" in reason for reason in result.all_scores[0].reasons))

    def test_no_marker_uses_word_boundaries(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Principles

### aesthetic
- Casino vibes are welcome.
"""
        )
        result = compare_candidates(
            ["Use calm enterprise blue.", "Lean into casino lighting and tables."],
            profile,
            "aesthetic",
        )

        self.assertEqual(result.selected.index, 1)
        self.assertTrue(any("casino" in reason for reason in result.all_scores[1].reasons))

    def test_prompt_matching_uses_whole_words(self):
        profile = TasteProfile.empty()
        result = compare_candidates(
            ["A transaction receipt.", "A clear action step."],
            profile,
            "general",
            "Describe an action.",
        )

        self.assertEqual(result.selected.index, 1)


if __name__ == "__main__":
    unittest.main()
