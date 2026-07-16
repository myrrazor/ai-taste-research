import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.schema import TasteProfile


TASTE_MD = """# TASTE.md
---
schema: taste/1.0
---

## Anchors

### general
- Specific examples over generic advice.

### code
- Small explicit modules with boring tests.

## Principles

### writing
- Use concrete nouns and direct verbs.

## Forbidden Moves

### general
- "delve"

### writing
- "In today's fast-paced world"

### code
- "console.log"
"""


class TasteSchemaTests(unittest.TestCase):
    def test_parses_frontmatter_and_sections(self):
        profile = TasteProfile.from_text(TASTE_MD)

        self.assertEqual(profile.frontmatter["schema"], "taste/1.0")
        self.assertEqual(
            profile.sections["anchors"]["general"],
            ["Specific examples over generic advice."],
        )
        self.assertEqual(profile.sections["forbidden_moves"]["code"], ['"console.log"'])

    def test_retrieves_general_plus_domain_rules(self):
        profile = TasteProfile.from_text(TASTE_MD)
        rules = profile.rules_for("prose")

        self.assertEqual(rules.domain, "writing")
        self.assertIn("Specific examples over generic advice.", rules.anchors)
        self.assertIn("Use concrete nouns and direct verbs.", rules.principles)
        self.assertIn('"delve"', rules.forbidden_moves)
        self.assertIn('"In today\'s fast-paced world"', rules.forbidden_moves)

    def test_horizontal_rule_in_body_is_not_frontmatter(self):
        profile = TasteProfile.from_text(
            """# TASTE.md

## Anchors

### general
- Keep this rule.

---

## Forbidden Moves

### general
- "delve"
"""
        )
        rules = profile.rules_for("general")

        self.assertEqual(profile.frontmatter, {})
        self.assertIn("Keep this rule.", rules.anchors)
        self.assertIn('"delve"', rules.forbidden_moves)

    def test_h1_adjacent_horizontal_rule_is_not_frontmatter_without_keys(self):
        profile = TasteProfile.from_text(
            """# TASTE.md
---

## Anchors

### general
- Keep this rule.

---

## Forbidden Moves

### general
- "delve"
"""
        )
        rules = profile.rules_for("general")

        self.assertEqual(profile.frontmatter, {})
        self.assertIn("Keep this rule.", rules.anchors)
        self.assertIn('"delve"', rules.forbidden_moves)


if __name__ == "__main__":
    unittest.main()
