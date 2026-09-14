import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import unittest

from nanotaste.cli import main
from nanotaste.redact import redact_text
from nanotaste.workspace import report_is_due, resolve_workspace, load_config_from_mapping


class SetupHarvestTests(unittest.TestCase):
    def test_setup_discovers_and_integrates_present_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            session_dir = home / ".cursor" / "projects" / "demo"
            session_dir.mkdir(parents=True)
            (session_dir / "chat-session.jsonl").write_text(
                json.dumps({"text": "Build a small parser and return scores with reasons."}) + "\n",
                encoding="utf-8",
            )
            (home / ".claude").mkdir()
            (workspace / ".aider.chat.history.md").write_text(
                "User: keep the concrete draft and reject generic filler.\n",
                encoding="utf-8",
            )

            stdout = StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "setup",
                        "--yes",
                        "--workspace",
                        str(workspace),
                        "--home",
                        str(home),
                        "--every",
                        "weekly",
                        "--json",
                    ]
                )

            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            self.assertIn("cursor", payload["enabled_sources"])
            self.assertIn("claude-code", payload["enabled_sources"])
            self.assertIn("aider", payload["enabled_sources"])
            self.assertTrue((workspace / "TASTE.md").exists())
            self.assertTrue((workspace / ".nanotaste" / "config.json").exists())
            self.assertTrue((workspace / ".nanotaste" / "reports" / "latest.md").exists())
            excerpts = (workspace / ".nanotaste" / "sessions" / "excerpts.jsonl").read_text(encoding="utf-8")
            self.assertIn("small parser", excerpts)

    def test_like_unlike_pick_and_learn_update_local_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "setup",
                            "--yes",
                            "--no-harvest",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
            like = workspace / "good.md"
            unlike = workspace / "bad.md"
            like.write_text("Keep concrete drafts and record the decision.", encoding="utf-8")
            unlike.write_text("In today's fast-paced world this empowers teams seamlessly.", encoding="utf-8")

            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["like", str(like), "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
                self.assertEqual(
                    main(["unlike", str(unlike), "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "pick",
                            "--candidate",
                            "Return scores with reasons.",
                            "--candidate",
                            "This function is responsible for magic.",
                            "--choose",
                            "1",
                            "--domain",
                            "code",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "learn",
                            "--apply",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )

            taste = (workspace / "TASTE.md").read_text(encoding="utf-8")
            self.assertIn("Prefer inspectable work", taste)
            self.assertIn("seamlessly", taste)
            self.assertTrue(list((workspace / ".nanotaste" / "likes").glob("*.md")))
            self.assertTrue(list((workspace / ".nanotaste" / "unlikes").glob("*.md")))

    def test_report_schedule_and_if_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "setup",
                            "--yes",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--every",
                            "weekly",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "schedule",
                            "--every",
                            "daily",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
                skip_status = main(
                    [
                        "report",
                        "--if-due",
                        "--workspace",
                        str(workspace),
                        "--home",
                        str(home),
                        "--json",
                    ]
                )
            self.assertEqual(skip_status, 0)
            config = json.loads((workspace / ".nanotaste" / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["report_frequency"], "daily")
            self.assertFalse(report_is_due(load_config_from_mapping(config)))

    def test_ingest_requires_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with redirect_stderr(StringIO()) as err:
                status = main(["ingest", "--workspace", str(root), "--home", str(root)])
            self.assertEqual(status, 1)
            self.assertIn("no local setup", err.getvalue())

    def test_redact_strips_secrets_and_home_paths(self):
        github = "ghp" + "_" + ("abcd" * 6)
        openai = "sk" + "-" + ("abcd" * 6)
        text = redact_text(f"token {github} and /home/alice/secret {openai}")
        self.assertNotIn(github, text)
        self.assertNotIn(openai, text)
        self.assertNotIn("/home/alice", text)
        self.assertIn("[redacted-secret]", text)

    def test_sources_json_lists_known_agents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stdout = StringIO()
            with redirect_stdout(stdout):
                status = main(["sources", "--workspace", str(root), "--home", str(root), "--json"])
            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            ids = {item["id"] for item in payload}
            self.assertIn("cursor", ids)
            self.assertIn("claude-code", ids)
            self.assertIn("codex", ids)
            self.assertIn("git", ids)

    def test_harvest_from_sample_session_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            cursor = home / ".cursor" / "projects" / "demo"
            cursor.mkdir(parents=True)
            fixture = Path(__file__).resolve().parents[1] / "examples" / "sessions" / "cursor-sample.jsonl"
            (cursor / "transcript.jsonl").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "setup",
                            "--yes",
                            "--no-harvest",
                            "--source",
                            "cursor",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "prefer",
                            "--like",
                            str(Path(__file__).resolve().parents[1] / "examples" / "likes" / "concrete-release-note.md"),
                            "--unlike",
                            str(Path(__file__).resolve().parents[1] / "examples" / "unlikes" / "generic-ai-prose.md"),
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
                status = main(
                    [
                        "harvest",
                        "--workspace",
                        str(workspace),
                        "--home",
                        str(home),
                        "--json",
                    ]
                )
            self.assertEqual(status, 0)
            report = (workspace / ".nanotaste" / "reports" / "latest.md").read_text(encoding="utf-8")
            self.assertIn("NanoTaste taste report", report)
            self.assertIn("Cursor", report)

    def test_workspace_helper_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = resolve_workspace(Path(tmp), Path(tmp))
            self.assertEqual(workspace.root, Path(tmp).resolve())
            self.assertFalse((workspace.config_path).exists())

    def test_status_sources_ingest_learn_and_report_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            (home / ".codex").mkdir()
            (home / ".codex" / "session-history.json").write_text(
                json.dumps({"prompt": "Implement tests for a deterministic candidate generator."}),
                encoding="utf-8",
            )
            (workspace / "notes.md").write_text("Keep the concrete draft and reject generic filler.\n\n", encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["status", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(main(["sources", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(
                    main(
                        [
                            "setup",
                            "--yes",
                            "--source",
                            "codex",
                            "--source",
                            "missing-agent",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--every",
                            "manual",
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["status", "--workspace", str(workspace), "--home", str(home), "--json"]), 0)
                self.assertEqual(main(["ingest", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(main(["learn", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(main(["report", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(main(["harvest", "--if-due", "--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(
                    main(
                        [
                            "like",
                            "Prefer explicit return values and short helpers.",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )
            text = stdout.getvalue()
            self.assertIn("not set up", text)
            self.assertIn("OpenAI Codex", text)
            self.assertIn("Ingested", text)
            self.assertIn("Learned proposal", text)
            self.assertIn("Report:", text)

    def test_interactive_setup_and_manual_pick_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            (home / ".continue").mkdir()
            (home / ".continue" / "chat-history.md").write_text(
                "A longer session note about keeping concrete drafts visible in review.\n",
                encoding="utf-8",
            )
            answers = StringIO("n\ny\ny\ncode,writing\ndaily\ny\n")
            stdout = StringIO()
            from nanotaste.setup_wizard import run_setup
            from nanotaste.workspace import resolve_workspace

            result = run_setup(
                resolve_workspace(workspace, home),
                yes=False,
                harvest=True,
                stdin=answers,
                stdout=stdout,
            )
            self.assertIn("continue", result.enabled)
            self.assertEqual(result.config.report_frequency, "daily")
            err = StringIO()
            with redirect_stderr(err):
                self.assertEqual(
                    main(
                        [
                            "pick",
                            "--candidate",
                            "only-one",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    1,
                )
                self.assertEqual(
                    main(
                        [
                            "like",
                            str(workspace / "missing-file.md"),
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    1,
                )
            self.assertIn("Pick error", err.getvalue())

    def test_git_history_ingest_and_root_help(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "repo"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            import subprocess

            subprocess.run(["git", "init"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            (workspace / "README.md").write_text("demo\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=workspace, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(
                ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Dev", "commit", "-m", "Keep concrete parser tests visible"],
                cwd=workspace,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "setup",
                            "--yes",
                            "--source",
                            "git",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )
            excerpts = (workspace / ".nanotaste" / "sessions" / "excerpts.jsonl").read_text(encoding="utf-8")
            self.assertIn("concrete parser", excerpts)
            help_out = StringIO()
            with redirect_stdout(help_out):
                status = main([])
            self.assertEqual(status, 2)
            self.assertIn("nanotaste setup", help_out.getvalue())

    def test_calibrate_without_subcommand_and_long_redaction(self):
        with redirect_stderr(StringIO()) as err:
            status = main(["calibrate"])
        self.assertEqual(status, 2)
        self.assertIn("calibrate", err.getvalue())
        clipped = redact_text("word " * 400, limit=40)
        self.assertTrue(clipped.endswith("…"))
        self.assertLessEqual(len(clipped), 40)

    def test_root_command_status_helpers_and_error_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            (home / ".cursor" / "projects" / "demo").mkdir(parents=True)
            (home / ".cursor" / "projects" / "demo" / "agent-transcript.json").write_text(
                "{not-json",
                encoding="utf-8",
            )
            from nanotaste.prefer import list_examples
            from nanotaste.setup_wizard import default_enabled_ids
            from nanotaste.sources import present_sources, session_files_for, sources_by_id
            from nanotaste.workspace import resolve_workspace

            discovered = sources_by_id(home, workspace)
            self.assertTrue(discovered["cursor"].present)
            self.assertTrue(present_sources(home, workspace))
            self.assertTrue(session_files_for(discovered["cursor"]))
            self.assertIn("cursor", default_enabled_ids(home, workspace))

            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["setup", "--yes", "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
            ws = resolve_workspace(workspace, home)
            self.assertTrue(list_examples(ws, "like") or True)
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--workspace", str(workspace), "--home", str(home)]), 0)
                self.assertEqual(
                    main(
                        [
                            "schedule",
                            "--every",
                            "manual",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "prefer",
                            "--like",
                            "Keep the concrete draft.",
                            "--unlike",
                            "This function is responsible for filler.",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(
                        [
                            "learn",
                            "--apply",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    main(["report", "--if-due", "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
            self.assertIn("Workspace:", stdout.getvalue())
            from argparse import Namespace
            from nanotaste.cli import _setup, _setup_defaults

            fresh = root / "fresh"
            fresh.mkdir()
            with redirect_stdout(StringIO()):
                status = _setup(
                    _setup_defaults(Namespace(workspace=str(fresh), home=str(home)))
                )
            self.assertEqual(status, 0)

    def test_extra_sources_workspace_errors_and_recent_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            workspace = root / "project"
            home.mkdir()
            workspace.mkdir()
            for rel in (
                Path(".config") / "zed",
                Path(".aws") / "amazonq",
                Path(".copilot"),
                Path(".windsurf"),
                Path(".gemini"),
                Path(".openhands"),
                Path(".cline"),
            ):
                (home / rel).mkdir(parents=True, exist_ok=True)
            from nanotaste.prefer import add_example
            from nanotaste.sources import session_files_for, sources_by_id
            from nanotaste.workspace import load_config, resolve_workspace, starter_taste_markdown

            found = sources_by_id(home, workspace)
            self.assertTrue(found["zed"].present)
            self.assertTrue(found["amazon-q"].present)
            self.assertTrue(found["github-copilot"].present)
            self.assertEqual(session_files_for(found["git"]), [])
            self.assertIn("Specificity beats polish", starter_taste_markdown())

            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["setup", "--yes", "--no-harvest", "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
            ws = resolve_workspace(workspace, home)
            (ws.runs_path).write_text(
                json.dumps({"domain": "writing", "selected_candidate": {"score": 3, "text": "Keep the concrete draft."}})
                + "\n{not json\n",
                encoding="utf-8",
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["report", "--workspace", str(workspace), "--home", str(home)]), 0)
            report = (ws.reports_dir / "latest.md").read_text(encoding="utf-8")
            self.assertIn("Keep the concrete draft", report)
            bad = ws.config_path
            bad.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(ws)
            with self.assertRaises(ValueError):
                add_example(ws, "text", "maybe")
            from nanotaste.setup_wizard import run_setup

            with self.assertRaises(ValueError):
                run_setup(ws, yes=True, frequency="yearly")


if __name__ == "__main__":
    unittest.main()



