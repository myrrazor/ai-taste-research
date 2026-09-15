import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.generator import generate_candidates
from nanotaste.schema import TasteProfile
from nanotaste.scoring import compare_candidates

EXAMPLE_TASTE = Path(__file__).resolve().parents[1] / "examples" / "TASTE.example.md"
FILLER_PHRASES = ("in today's fast-paced world", "seamless", "empower", "gradient", "console.log")


class GeneratorTests(unittest.TestCase):
    def test_official_example_never_selects_the_generic_filler_draft(self):
        profile = TasteProfile.from_paths([EXAMPLE_TASTE])
        prompts = {
            "general": "Explain why generic AI prose feels bad.",
            "writing": "Write a short launch announcement for NanoTaste.",
            "product": "Define the first useful loop for a taste-calibration tool.",
            "aesthetic": "Design a landing page hero for a pour-over coffee subscription.",
            "code": "Implement a parser for TASTE.md sections.",
        }
        for domain, prompt in prompts.items():
            with self.subTest(domain=domain):
                rules = profile.rules_for(domain)
                candidates = generate_candidates(prompt, rules, count=3)
                result = compare_candidates(candidates, profile, domain, prompt)

                self.assertNotEqual(result.selected.index, 0)
                for phrase in FILLER_PHRASES:
                    self.assertNotIn(phrase, result.selected.text.lower())
                self.assertLess(result.all_scores[0].score, result.selected.score)
                self.assertTrue(
                    any("forbidden move" in reason for reason in result.all_scores[0].reasons)
                )

    def test_subject_strips_leading_define_and_describe_verbs(self):
        rules = TasteProfile.empty().rules_for("product")

        defined = generate_candidates("Define the first useful loop for a tool.", rules)
        described = generate_candidates("Describe the smallest useful taste file editor", rules)

        self.assertIn("for the first useful loop for a tool:", defined[1])
        self.assertNotIn("define", defined[1].lower())
        self.assertIn("the smallest useful taste file editor", described[1])
        self.assertNotIn("describe", described[1].lower())

    def test_generated_candidates_strip_leading_prompt_verb(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Principles

### aesthetic
- Use real product imagery.
"""
        )
        candidates = generate_candidates(
            "Design a landing page for a coffee subscription",
            profile.rules_for("design"),
        )

        self.assertIn("a landing page", candidates[1])
        self.assertNotIn("design a landing page", candidates[1].lower())

    def test_fourth_candidate_does_not_quote_forbidden_moves(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Forbidden Moves

### aesthetic
- "gradient"
- "floating card"
"""
        )
        candidates = generate_candidates(
            "Design a landing page",
            profile.rules_for("design"),
            count=4,
        )

        self.assertEqual(len(candidates), 4)
        self.assertNotIn("gradient", candidates[3].lower())
        self.assertNotIn("floating card", candidates[3].lower())


if __name__ == "__main__":
    unittest.main()
