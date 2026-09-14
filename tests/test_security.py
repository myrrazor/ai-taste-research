import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.calibration import evaluate_calibration, load_prompt_set
from nanotaste.cli import main
from nanotaste.discovery import discover_taste_paths
from nanotaste.domains import normalize_domain
from nanotaste.prefer import resolve_example_text
from nanotaste.records import append_record
from nanotaste.schema import TasteProfile
from nanotaste.security import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATE_FILE_BYTES,
    MAX_CALIBRATION_RUN_BYTES,
    MAX_HUMAN_PICKS_BYTES,
    MAX_LIKE_FILE_BYTES,
    MAX_PROMPT_BYTES,
    MAX_PROMPT_SET_BYTES,
    MAX_RECORD_LINE_BYTES,
    MAX_TASTE_FILE_BYTES,
    SecurityInputError,
    atomic_write_text,
    read_existing_text_under_roots,
    safe_for_terminal,
    safe_read_text,
)


class SecurityTests(unittest.TestCase):
    def test_preference_files_must_stay_under_an_approved_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            other = root / "other"
            workspace.mkdir()
            other.mkdir()
            inside = workspace / "note.md"
            inside.write_text("Keep the decision visible.", encoding="utf-8")
            outside = other / "secret.md"
            outside.write_text("do not read me", encoding="utf-8")
            nested = workspace / "docs"
            nested.mkdir()
            nested_file = nested / "inside.md"
            nested_file.write_text("nested like", encoding="utf-8")

            loaded = read_existing_text_under_roots(
                str(inside),
                (workspace,),
                limit_bytes=MAX_LIKE_FILE_BYTES,
                label="preference example",
            )
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded[0], "Keep the decision visible.")

            relative = read_existing_text_under_roots(
                "docs/inside.md",
                (workspace,),
                limit_bytes=MAX_LIKE_FILE_BYTES,
                label="preference example",
            )
            self.assertIsNotNone(relative)
            assert relative is not None
            self.assertEqual(relative[0], "nested like")

            self.assertIsNone(
                read_existing_text_under_roots(
                    str(outside),
                    (workspace,),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            )
            self.assertIsNone(
                read_existing_text_under_roots(
                    "../other/secret.md",
                    (workspace,),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            )

            via_resolved_root = read_existing_text_under_roots(
                str(inside),
                (workspace.resolve(),),
                limit_bytes=MAX_LIKE_FILE_BYTES,
                label="preference example",
            )
            self.assertIsNotNone(via_resolved_root)
            assert via_resolved_root is not None
            self.assertEqual(via_resolved_root[0], "Keep the decision visible.")

            alias = root / "alias-project"
            try:
                alias.symlink_to(workspace, target_is_directory=True)
            except (NotImplementedError, OSError):
                alias = None
            if alias is not None:
                aliased = read_existing_text_under_roots(
                    str(alias / "note.md"),
                    (workspace.resolve(),),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
                self.assertIsNotNone(aliased)
                assert aliased is not None
                self.assertEqual(aliased[0], "Keep the decision visible.")

            text, stem = resolve_example_text(str(inside), roots=(workspace,))
            self.assertEqual(text, "Keep the decision visible.")
            self.assertEqual(stem, "note")
            with self.assertRaises(ValueError):
                resolve_example_text(str(outside), roots=(workspace,))
            literal, literal_stem = resolve_example_text(
                "Keep concrete drafts and record the decision.",
                roots=(workspace,),
            )
            self.assertEqual(literal, "Keep concrete drafts and record the decision.")
            self.assertIsNone(literal_stem)

            self.assertIsNone(
                read_existing_text_under_roots(
                    str(inside),
                    (root / "missing",),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            )
            huge = workspace / "huge.md"
            huge.write_text("x" * (MAX_LIKE_FILE_BYTES + 1), encoding="utf-8")
            with self.assertRaises(SecurityInputError):
                read_existing_text_under_roots(
                    str(huge),
                    (workspace,),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            invalid = workspace / "bad.md"
            invalid.write_bytes(b"\xff")
            with self.assertRaises(SecurityInputError):
                read_existing_text_under_roots(
                    str(invalid),
                    (workspace,),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            outside_link = workspace / "escape.md"
            self._symlink_or_skip(outside, outside_link)
            self.assertIsNone(
                read_existing_text_under_roots(
                    str(outside_link),
                    (workspace,),
                    limit_bytes=MAX_LIKE_FILE_BYTES,
                    label="preference example",
                )
            )

    def test_domain_aliases_still_normalize(self):
        self.assertEqual(normalize_domain("design"), "aesthetic")
        self.assertEqual(normalize_domain("python"), "code")
        self.assertEqual(normalize_domain("custom_domain"), "custom-domain")

    def test_domain_rejects_pathlike_or_control_values(self):
        bad_domains = ("../secret", "bad/name", "bad\\name", ".hidden", "bad\x1b[31m")
        for domain in bad_domains:
            with self.subTest(domain=domain):
                with self.assertRaises(SecurityInputError):
                    normalize_domain(domain)

    def test_discovery_rejects_domain_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            outside = Path(tmp) / "outside.md"
            outside.write_text("# outside", encoding="utf-8")
            taste_dir = root / "taste"
            taste_dir.mkdir()
            self._symlink_or_skip(outside, taste_dir / "code.md")

            with self.assertRaises(SecurityInputError):
                discover_taste_paths(root, "code")

    def test_explicit_taste_file_companion_must_stay_under_companion_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            private = root / "private"
            private.mkdir()
            taste = private / "TASTE.md"
            taste.write_text("# private taste", encoding="utf-8")
            outside = root / "outside.md"
            outside.write_text("# outside", encoding="utf-8")
            companion_dir = private / "taste"
            companion_dir.mkdir()
            self._symlink_or_skip(outside, companion_dir / "code.md")

            with self.assertRaises(SecurityInputError):
                discover_taste_paths(project, "code", taste_file=taste)

    def test_explicit_taste_dir_must_contain_domain_file_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            taste_dir = root / "taste-files"
            taste_dir.mkdir()
            outside = root / "outside.md"
            outside.write_text("# outside", encoding="utf-8")
            self._symlink_or_skip(outside, taste_dir / "writing.md")

            with self.assertRaises(SecurityInputError):
                discover_taste_paths(project, "writing", taste_dir=taste_dir)

    def test_taste_profile_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            taste = Path(tmp) / "TASTE.md"
            taste.write_bytes(b"\xff\xfe")

            with self.assertRaises(SecurityInputError):
                TasteProfile.from_paths([taste])

    def test_merged_taste_profile_enforces_total_rule_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "TASTE.md"
            second = root / "code.md"
            first.write_text(_rules_markdown("first", 1_001), encoding="utf-8")
            second.write_text(_rules_markdown("second", 1_000), encoding="utf-8")

            with self.assertRaises(ValueError):
                TasteProfile.from_paths([first, second])

    def test_file_size_limits_reject_oversized_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            taste = root / "TASTE.md"
            taste.write_text("x" * (MAX_TASTE_FILE_BYTES + 1), encoding="utf-8")
            with self.assertRaises(SecurityInputError):
                safe_read_text(taste, limit_bytes=MAX_TASTE_FILE_BYTES, label="taste file")

            prompt_set = root / "prompts.json"
            prompt_set.write_text(" " * (MAX_PROMPT_SET_BYTES + 1), encoding="utf-8")
            with self.assertRaises(SecurityInputError):
                load_prompt_set(prompt_set)

            run = root / "run.json"
            picks = root / "picks.json"
            run.write_text(" " * (MAX_CALIBRATION_RUN_BYTES + 1), encoding="utf-8")
            picks.write_text(
                json.dumps({"schema": "nanotaste/human-picks/1.0", "picks": []}),
                encoding="utf-8",
            )
            with self.assertRaises(SecurityInputError):
                evaluate_calibration(run, picks)

            run.write_text(
                json.dumps({"schema": "nanotaste/calibration-run/1.0", "items": []}),
                encoding="utf-8",
            )
            picks.write_text(" " * (MAX_HUMAN_PICKS_BYTES + 1), encoding="utf-8")
            with self.assertRaises(SecurityInputError):
                evaluate_calibration(run, picks)

    def test_prompt_set_rejects_oversized_candidate_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_set = Path(tmp) / "prompts.json"
            prompt_set.write_text(
                json.dumps(
                    {
                        "schema": "nanotaste/prompt-set/1.0",
                        "items": [
                            {
                                "id": "writing_001",
                                "domain": "writing",
                                "prompt": "Write a note.",
                                "candidates": ["short", "x" * (MAX_CANDIDATE_BYTES + 1)],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SecurityInputError):
                load_prompt_set(prompt_set)

    def test_cli_rejects_oversized_candidate_file_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            large = root / "large.md"
            small = root / "small.md"
            large.write_text("x" * (MAX_CANDIDATE_FILE_BYTES + 1), encoding="utf-8")
            small.write_text("short", encoding="utf-8")

            with redirect_stderr(StringIO()) as error:
                compare_status = main(
                    [
                        "compare",
                        "--domain",
                        "writing",
                        "--candidates",
                        str(large),
                        str(small),
                        "--no-record",
                    ]
                )

            self.assertEqual(compare_status, 1)
            self.assertIn("too large", error.getvalue())

            with redirect_stderr(StringIO()) as error:
                run_status = main(
                    [
                        "run",
                        "--domain",
                        "writing",
                        "--prompt",
                        "x" * (MAX_PROMPT_BYTES + 1),
                        "--no-record",
                    ]
                )

            self.assertEqual(run_status, 1)
            self.assertIn("too large", error.getvalue())

    def test_atomic_write_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real.md"
            real.write_text("old", encoding="utf-8")
            link = root / "out.md"
            self._symlink_or_skip(real, link)

            with self.assertRaises(SecurityInputError):
                atomic_write_text(link, "new", label="test output")
            self.assertEqual(real.read_text(encoding="utf-8"), "old")

    def test_run_record_refuses_symlink_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "records.jsonl"
            real.write_text("", encoding="utf-8")
            link = root / "link.jsonl"
            self._symlink_or_skip(real, link)

            with self.assertRaises(SecurityInputError):
                append_record(link, {"prompt": "x"})

    def test_record_line_limit_rejects_oversized_jsonl_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.jsonl"

            with self.assertRaises(SecurityInputError):
                append_record(path, {"payload": "x" * MAX_RECORD_LINE_BYTES})

    def test_terminal_renderer_neutralizes_display_controls(self):
        text = "red\x1b]0;title\x07 \x9dosc \u202awrong\u2028next\u2029para"
        rendered = safe_for_terminal(text)

        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\x9d", rendered)
        self.assertNotIn("\u202a", rendered)
        self.assertNotIn("\u2028", rendered)
        self.assertNotIn("\u2029", rendered)
        self.assertIn("\\u001b", rendered)
        self.assertIn("\\u009d", rendered)
        self.assertIn("\\u202a", rendered)
        self.assertIn("\\u2028", rendered)
        self.assertIn("\\u2029", rendered)

    def test_cli_non_json_output_escapes_candidate_text(self):
        with redirect_stdout(StringIO()) as output:
            status = main(
                [
                    "run",
                    "--prompt",
                    "Pick one",
                    "--candidate",
                    "red\x1b[31m text \u202ewrong",
                    "--candidate",
                    "plain text",
                    "--no-record",
                ]
            )

        self.assertEqual(status, 0)
        rendered = output.getvalue()
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn("\\u001b", rendered)
        self.assertIn("\\u202e", rendered)

    def test_cli_json_output_preserves_decoded_candidate_text(self):
        candidate = "red\x1b[31m text \u202ewrong"
        with redirect_stdout(StringIO()) as output:
            status = main(
                [
                    "run",
                    "--prompt",
                    "Pick one",
                    "--candidate",
                    candidate,
                    "--candidate",
                    "plain text",
                    "--no-record",
                    "--json",
                ]
            )

        self.assertEqual(status, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["selected_candidate"]["text"], candidate)

    def test_jsonl_record_preserves_decoded_candidate_text_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            record_file = Path(tmp) / "runs.jsonl"
            candidate = "red\x1b[31m text \u202ewrong"

            with redirect_stdout(StringIO()):
                status = main(
                    [
                        "run",
                        "--prompt",
                        "Pick one",
                        "--candidate",
                        candidate,
                        "--candidate",
                        "plain text",
                        "--record-file",
                        str(record_file),
                        "--json",
                    ]
                )

            self.assertEqual(status, 0)
            record = json.loads(record_file.read_text(encoding="utf-8"))
            self.assertEqual(record["selected_candidate"]["text"], candidate)

    def test_compare_rejects_invalid_utf8_candidate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.md"
            path.write_bytes(b"\xff")

            with redirect_stderr(StringIO()) as error:
                status = main(
                    [
                        "compare",
                        "--domain",
                        "writing",
                        "--candidates",
                        str(path),
                        str(path),
                        "--no-record",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertIn("not valid UTF-8", error.getvalue())

    def _symlink_or_skip(self, target: Path, link: Path) -> None:
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError) as err:
            self.skipTest(f"symlinks unavailable: {err}")


def _rules_markdown(prefix: str, count: int) -> str:
    lines = ["# TASTE.md", "", "## Principles", ""]
    lines.extend(f"- {prefix} rule {index}" for index in range(count))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    unittest.main()
