import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.agent import TasteAgent, TasteRouter
from nanotaste.discovery import discover_taste_paths


class TasteAgentTests(unittest.TestCase):
    def test_router_loads_domain_specific_taste(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASTE.md").write_text(
                """# TASTE.md

## Principles

### general
- Specificity beats polish.
""",
                encoding="utf-8",
            )
            (root / "taste").mkdir()
            (root / "taste" / "code.md").write_text(
                """# Code Taste

## Forbidden Moves

### code
- "console.log"
""",
                encoding="utf-8",
            )

            context = TasteRouter(cwd=root).resolve("python")

            self.assertEqual(context.domain, "code")
            self.assertEqual(len(context.source_paths), 2)
            self.assertIn('"console.log"', context.rules.forbidden_moves)

    def test_agent_composes_router_generator_and_critic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASTE.md").write_text(
                """# TASTE.md

## Principles

### aesthetic
- Use real product imagery and clear hierarchy.

## Forbidden Moves

### aesthetic
- "gradient"
- "floating card"
""",
                encoding="utf-8",
            )

            result = TasteAgent.from_paths(cwd=root).run(
                "Design a landing page for a coffee subscription",
                "design",
            )

            self.assertEqual(result.domain, "aesthetic")
            self.assertNotEqual(result.selected.index, 0)
            self.assertTrue(result.selected.reasons)

    def test_relative_taste_dir_resolves_against_router_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            custom = project / "custom-taste"
            custom.mkdir()
            (custom / "code.md").write_text(
                """# Code

## Forbidden Moves

### code
- "console.log"
""",
                encoding="utf-8",
            )

            paths = discover_taste_paths(project, "code", taste_dir=Path("custom-taste"))

            self.assertEqual(paths, [(custom / "code.md").resolve()])

    def test_discovery_stops_at_nearest_taste_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outer = root / "outer"
            project = outer / "project"
            child = project / "nested"
            child.mkdir(parents=True)
            (outer / "TASTE.md").write_text(
                """# Outer

## Forbidden Moves

### general
- "outer-only"
""",
                encoding="utf-8",
            )
            (project / "TASTE.md").write_text(
                """# Project

## Forbidden Moves

### general
- "project-only"
""",
                encoding="utf-8",
            )

            paths = discover_taste_paths(child, "general")

            self.assertEqual(paths, [(project / "TASTE.md").resolve()])


if __name__ == "__main__":
    unittest.main()
