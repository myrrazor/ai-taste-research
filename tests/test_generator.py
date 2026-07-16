import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.generator import generate_candidates
from nanotaste.schema import TasteProfile


class GeneratorTests(unittest.TestCase):
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
