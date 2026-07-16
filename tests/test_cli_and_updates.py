import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.cli import main
from nanotaste.update import propose_update, write_proposal


TASTE_MD = """# TASTE.md

## Principles

### aesthetic
- Use real product imagery and clear hierarchy.

## Forbidden Moves

### aesthetic
- "gradient"
- "floating card"
"""


class CliAndUpdateTests(unittest.TestCase):
    def test_run_command_records_selected_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taste = root / "TASTE.md"
            taste.write_text(TASTE_MD, encoding="utf-8")
            record_file = root / "runs.jsonl"

            with redirect_stdout(StringIO()):
                status = main(
                    [
                        "run",
                        "--domain",
                        "design",
                        "--prompt",
                        "Design a product page",
                        "--taste-file",
                        str(taste),
                        "--record-file",
                        str(record_file),
                        "--json",
                    ]
                )

            self.assertEqual(status, 0)
            records = [json.loads(line) for line in record_file.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertIn("selected_candidate", records[0])
            self.assertIn("rejected_candidates", records[0])
            self.assertIn("taste_hash", records[0])

    def test_propose_update_does_not_mutate_taste_file(self):
        before = "This platform empowers teams to seamlessly innovate."
        after = "Compare three drafts and keep the one with concrete evidence."
        proposal = propose_update(before, after, "writing")

        self.assertIn("Pending Taste Update", proposal.markdown)
        self.assertIn("Possible preference signal: Compare three drafts", proposal.markdown)
        self.assertIn("Possible avoid signal: This platform empowers", proposal.markdown)

    def test_write_proposal_creates_pending_file_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taste_file = root / "TASTE.md"
            taste_file.write_text(TASTE_MD, encoding="utf-8")
            original = taste_file.read_text(encoding="utf-8")
            proposal = propose_update("old vague line", "new concrete line", "writing")

            path = write_proposal(proposal, root / "taste-updates", "draft")

            self.assertTrue(path.exists())
            self.assertEqual(taste_file.read_text(encoding="utf-8"), original)

    def test_calibrate_prepare_and_evaluate_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taste = root / "TASTE.md"
            taste.write_text(
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
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_dir = root / "calibration"

            with redirect_stdout(StringIO()):
                prepare_status = main(
                    [
                        "calibrate",
                        "prepare",
                        "--prompt-set",
                        str(prompt_set),
                        "--output-dir",
                        str(output_dir),
                        "--taste-file",
                        str(taste),
                    ]
                )

            self.assertEqual(prepare_status, 0)
            self.assertTrue((output_dir / "manual_review.md").exists())
            picks_path = output_dir / "human_picks.json"
            picks = json.loads(picks_path.read_text(encoding="utf-8"))
            picks["picks"][0]["winner"] = "A"
            picks_path.write_text(json.dumps(picks), encoding="utf-8")

            with redirect_stdout(StringIO()):
                evaluate_status = main(
                    [
                        "calibrate",
                        "evaluate",
                        "--run",
                        str(output_dir / "starter_run.json"),
                        "--picks",
                        str(picks_path),
                        "--output",
                        str(output_dir / "evaluation.md"),
                    ]
                )

            self.assertEqual(evaluate_status, 0)
            self.assertTrue((output_dir / "evaluation.md").exists())

    def test_calibrate_evaluate_command_rejects_invalid_pick(self):
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
                        "picks": [{"item_id": "writing_001", "winner": "D"}],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "evaluate",
                        "--run",
                        str(run),
                        "--picks",
                        str(picks),
                        "--output",
                        str(root / "evaluation.md"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_prepare_command_reports_missing_prompt_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "prepare",
                        "--prompt-set",
                        str(root / "missing.json"),
                        "--output-dir",
                        str(root / "calibration"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_prepare_json_error_keeps_stdout_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                status = main(
                    [
                        "calibrate",
                        "prepare",
                        "--prompt-set",
                        str(root / "missing.json"),
                        "--output-dir",
                        str(root / "calibration"),
                        "--json",
                    ]
                )

            self.assertEqual(status, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("Calibration input error", stderr.getvalue())

    def test_calibrate_prepare_command_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_set = root / "prompts.json"
            prompt_set.write_text("{not json", encoding="utf-8")

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "prepare",
                        "--prompt-set",
                        str(prompt_set),
                        "--output-dir",
                        str(root / "calibration"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_prepare_command_reports_malformed_prompt_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt_set = root / "prompts.json"
            prompt_set.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/prompt-set/1.0",
                        "items": [{"id": 123, "domain": "writing", "prompt": "Write a note."}],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "prepare",
                        "--prompt-set",
                        str(prompt_set),
                        "--output-dir",
                        str(root / "calibration"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_evaluate_command_reports_missing_run_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            picks = root / "picks.json"
            picks.write_text(
                json.dumps({"schema": "nanotaste/human-picks/1.0", "picks": []}),
                encoding="utf-8",
            )

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "evaluate",
                        "--run",
                        str(root / "missing.json"),
                        "--picks",
                        str(picks),
                        "--output",
                        str(root / "evaluation.md"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_evaluate_command_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text("{not json", encoding="utf-8")
            picks.write_text(
                json.dumps({"schema": "nanotaste/human-picks/1.0", "picks": []}),
                encoding="utf-8",
            )

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "evaluate",
                        "--run",
                        str(run),
                        "--picks",
                        str(picks),
                        "--output",
                        str(root / "evaluation.md"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_calibrate_evaluate_command_reports_malformed_pick_values(self):
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
                        "picks": [1, {"item_id": "writing_001", "winner": 7}],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stderr(StringIO()) as output:
                status = main(
                    [
                        "calibrate",
                        "evaluate",
                        "--run",
                        str(run),
                        "--picks",
                        str(picks),
                        "--output",
                        str(root / "evaluation.md"),
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Calibration input error", output.getvalue())

    def test_compare_command_reads_candidate_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taste = root / "TASTE.md"
            taste.write_text(
                """# TASTE.md

## Forbidden Moves

### writing
- "seamlessly"
""",
                encoding="utf-8",
            )
            a = root / "a.md"
            b = root / "b.md"
            a.write_text("This seamlessly empowers teams.", encoding="utf-8")
            b.write_text("Compare three drafts and keep the specific one.", encoding="utf-8")

            with redirect_stdout(StringIO()):
                status = main(
                    [
                        "compare",
                        "--domain",
                        "writing",
                        "--taste-file",
                        str(taste),
                        "--candidates",
                        str(a),
                        str(b),
                        "--no-record",
                        "--json",
                    ]
                )

            self.assertEqual(status, 0)

    def test_propose_update_command_writes_pending_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root / "before.md"
            after = root / "after.md"
            before.write_text("This platform empowers teams.", encoding="utf-8")
            after.write_text("Compare three drafts.", encoding="utf-8")

            with redirect_stdout(StringIO()):
                status = main(
                    [
                        "propose-update",
                        "--domain",
                        "writing",
                        "--before",
                        str(before),
                        "--after",
                        str(after),
                        "--output-dir",
                        str(root / "updates"),
                    ]
                )

            self.assertEqual(status, 0)
            self.assertTrue((root / "updates" / "before.md").exists())


if __name__ == "__main__":
    unittest.main()
