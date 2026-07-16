import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.agent import TasteAgent
from nanotaste.calibration import (
    CalibrationInputError,
    evaluate_calibration,
    prepare_calibration,
    render_evaluation_markdown,
)


class CalibrationTests(unittest.TestCase):
    def test_prepare_calibration_writes_review_and_picks_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASTE.md").write_text(
                """# TASTE.md

## Forbidden Moves

### aesthetic
- "gradient"
""",
                encoding="utf-8",
            )
            prompt_set = root / "prompts.json"
            prompt_set.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/prompt-set/1.0",
                        "items": [
                            {
                                "id": "aesthetic_001",
                                "domain": "aesthetic",
                                "prompt": "Design a pricing page.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            paths = prepare_calibration(
                prompt_set,
                root / "calibration",
                TasteAgent.from_paths(cwd=root),
            )

            review = paths["review"].read_text(encoding="utf-8")
            picks = json.loads(paths["picks"].read_text(encoding="utf-8"))
            run = json.loads(paths["run"].read_text(encoding="utf-8"))

            self.assertIn("Candidate A", review)
            self.assertIn("Candidate order is rotated", review)
            self.assertNotIn("nanotaste_winner", review)
            self.assertEqual(picks["picks"][0]["winner"], "")
            self.assertIn("nanotaste_winner", run["items"][0])
            self.assertEqual(
                {candidate["id"] for candidate in run["items"][0]["candidates"]},
                {"A", "B", "C"},
            )

    def test_prepare_calibration_uses_external_candidates_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASTE.md").write_text(
                """# TASTE.md

## Forbidden Moves

### writing
- "seamlessly"
""",
                encoding="utf-8",
            )
            prompt_set = root / "prompts.json"
            prompt_set.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/prompt-set/1.0",
                        "items": [
                            {
                                "id": "writing_001",
                                "domain": "writing",
                                "prompt": "Write a launch note.",
                                "candidates": [
                                    {"text": "External draft one."},
                                    {"text": "External draft two."},
                                    {"text": "External draft three."},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            paths = prepare_calibration(
                prompt_set,
                root / "calibration",
                TasteAgent.from_paths(cwd=root),
            )
            run = json.loads(paths["run"].read_text(encoding="utf-8"))
            candidate_text = {item["text"] for item in run["items"][0]["candidates"]}

            self.assertEqual(
                candidate_text,
                {"External draft one.", "External draft two.", "External draft three."},
            )

    def test_evaluate_calibration_handles_pending_and_labeled_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/calibration-run/1.0",
                        "items": [
                            {
                                "id": "writing_001",
                                "domain": "writing",
                                "prompt": "Write a note.",
                                "nanotaste_winner": "B",
                                "candidates": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
                            },
                            {
                                "id": "code_001",
                                "domain": "code",
                                "prompt": "Write a parser.",
                                "nanotaste_winner": "A",
                                "candidates": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            picks.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/human-picks/1.0",
                        "picks": [
                            {"item_id": "writing_001", "winner": "B"},
                            {"item_id": "code_001", "winner": ""},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            evaluation = evaluate_calibration(run, picks)
            markdown = render_evaluation_markdown(evaluation)

            self.assertEqual(evaluation["labeled_items"], 1)
            self.assertEqual(evaluation["matches"], 1)
            self.assertEqual(evaluation["accuracy"], 1.0)
            self.assertIn("| writing_001 | writing | B | B | yes |", markdown)
            self.assertIn("| code_001 | code | - | A | pending |", markdown)

    def test_evaluate_calibration_counts_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/calibration-run/1.0",
                        "items": [
                            {
                                "id": "writing_001",
                                "domain": "writing",
                                "prompt": "Write a note.",
                                "nanotaste_winner": "B",
                                "candidates": [{"id": "A"}, {"id": "B"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            picks.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/human-picks/1.0",
                        "picks": [{"item_id": "writing_001", "winner": "A"}],
                    }
                ),
                encoding="utf-8",
            )

            evaluation = evaluate_calibration(run, picks)
            markdown = render_evaluation_markdown(evaluation)

            self.assertEqual(evaluation["matches"], 0)
            self.assertEqual(evaluation["accuracy"], 0.0)
            self.assertIn("| writing_001 | writing | A | B | no |", markdown)

    def test_evaluate_rejects_impossible_candidate_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/calibration-run/1.0",
                        "items": [
                            {
                                "id": "writing_001",
                                "domain": "writing",
                                "prompt": "Write a note.",
                                "nanotaste_winner": "B",
                                "candidates": [{"id": "A"}, {"id": "B"}, {"id": "C"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            picks.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/human-picks/1.0",
                        "picks": [{"item_id": "writing_001", "winner": "D"}],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CalibrationInputError):
                evaluate_calibration(run, picks)

    def test_evaluate_rejects_duplicate_and_unknown_picks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/calibration-run/1.0",
                        "items": [
                            {
                                "id": "code_001",
                                "domain": "code",
                                "prompt": "Write a parser.",
                                "nanotaste_winner": "A",
                                "candidates": [{"id": "A"}, {"id": "B"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            picks.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/human-picks/1.0",
                        "picks": [
                            {"item_id": "code_001", "winner": "A"},
                            {"item_id": "code_001", "winner": "B"},
                            {"item_id": "missing_001", "winner": "A"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(CalibrationInputError):
                evaluate_calibration(run, picks)


if __name__ == "__main__":
    unittest.main()
