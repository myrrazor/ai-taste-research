import base64
import json
import sys
import tempfile
import threading
from contextlib import redirect_stderr, redirect_stdout
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from pathlib import Path
from unittest import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nanotaste.catalog import CATEGORIES, catalog_payload, install_hierarchy
from nanotaste.cli import main
from nanotaste.discovery import discover_taste_paths
from nanotaste.seed import list_seeds, seed_texts, seed_workspace
from nanotaste.setup_wizard import run_setup
from nanotaste.security import SecurityInputError, validate_loopback_host, validate_seed_filename
from nanotaste.webapp import serve_workspace
from nanotaste.workspace import resolve_workspace


class _HtmlHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<html><head><title>Ada Chen</title></head><body><h1>I prefer short names and concrete bios.</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class HierarchySeedWebTests(TestCase):
    def test_setup_installs_seeded_category_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            stdout = StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "setup",
                        "--yes",
                        "--no-harvest",
                        "--workspace",
                        str(workspace),
                        "--home",
                        str(home),
                        "--seed-text",
                        "I prefer short names, concrete bios, and visible decisions.",
                        "--json",
                    ]
                )
            self.assertEqual(status, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["seeded"])
            self.assertTrue((workspace / "TASTE.md").exists())
            self.assertIn("taste/writing.md", (workspace / "TASTE.md").read_text(encoding="utf-8"))
            for category in CATEGORIES:
                self.assertTrue((workspace / "taste" / f"{category.id}.md").is_file())
            catalog = catalog_payload(resolve_workspace(workspace, home))
            self.assertEqual(catalog["index"], "TASTE.md")
            self.assertGreaterEqual(len(catalog["nodes"]), 1 + len(CATEGORIES))
            seeds = list_seeds(resolve_workspace(workspace, home))
            self.assertTrue(seeds)
            self.assertIn("concrete", seeds[0]["excerpt"])

    def test_catalog_json_and_seed_file_refresh_overlay(self) -> None:
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
            note = workspace / "about.md"
            note.write_text("Ada prefers restrained typography and concrete product loops.", encoding="utf-8")
            seed_out = StringIO()
            catalog_out = StringIO()
            with redirect_stdout(seed_out):
                self.assertEqual(
                    main(
                        [
                            "seed",
                            "--file",
                            str(note),
                            "--domain",
                            "aesthetic",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                            "--json",
                        ]
                    ),
                    0,
                )
            with redirect_stdout(catalog_out):
                self.assertEqual(
                    main(
                        [
                            "catalog",
                            "--json",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
            seeded = json.loads(seed_out.getvalue())
            catalog = json.loads(catalog_out.getvalue())
            self.assertEqual(seeded["kind"], "file")
            self.assertEqual(catalog["schema"], "nanotaste/taste-catalog/1.0")
            self.assertIn("writing", catalog["categories"])
            overlay = workspace / "taste" / "learned" / "aesthetic.md"
            self.assertTrue(overlay.is_file())
            paths = discover_taste_paths(workspace, "aesthetic")
            self.assertTrue(any(path.name == "aesthetic.md" for path in paths))
            self.assertTrue(any(path.parent.name == "learned" for path in paths))

    def test_seed_url_and_image_use_local_evidence_only(self) -> None:
        server = HTTPServer(("127.0.0.1", 0), _HtmlHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                workspace = root / "project"
                home = root / "home"
                workspace.mkdir()
                home.mkdir()
                ws = resolve_workspace(workspace, home)
                run_setup(ws, yes=True, harvest=False)
                port = server.server_address[1]
                record = seed_workspace(ws, url=f"http://127.0.0.1:{port}/about", domain="personal")
                self.assertEqual(record.kind, "url")
                self.assertIn("short names", record.excerpt)
                image = workspace / "mood.png"
                image.write_bytes(
                    base64.b64decode(
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2nkAAAAASUVORK5CYII="
                    )
                )
                pictured = seed_workspace(
                    ws,
                    path=image,
                    domain="aesthetic",
                    caption="Restrained paper and ink, no decorative blob",
                )
                self.assertEqual(pictured.kind, "image")
                self.assertIn("paper", pictured.excerpt)
                self.assertTrue((ws.seed_files_dir / "mood.png").is_file())
        finally:
            server.shutdown()
            server.server_close()

    def test_seed_rejects_non_http_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = resolve_workspace(Path(tmp), Path(tmp))
            run_setup(ws, yes=True, harvest=False)
            with self.assertRaises(ValueError):
                seed_workspace(ws, url="file:///etc/passwd")
            with self.assertRaises(ValueError):
                seed_workspace(ws, url="https://user:pass@example.com/about")

    def test_interactive_setup_can_seed_from_pasted_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            answers = StringIO("y\nwriting,code\nweekly\nn\nPrefer short names and concrete bios.\n")
            result = run_setup(
                resolve_workspace(workspace, home),
                yes=False,
                harvest=True,
                stdin=answers,
                stdout=StringIO(),
            )
            self.assertTrue(result.seeded)
            self.assertFalse(result.harvested)
            self.assertTrue(list_seeds(result.workspace))

    def test_studio_api_setup_seed_harvest_and_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            ws = resolve_workspace(workspace, home)
            install_hierarchy(ws)
            server = serve_workspace(ws, host="127.0.0.1", port=0, tick=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                catalog = _http_json("GET", port, "/api/catalog")
                self.assertEqual(catalog["schema"], "nanotaste/taste-catalog/1.0")
                seeded = _http_json(
                    "POST",
                    port,
                    "/api/seed",
                    {"text": "Prefer inspectable scores and short helpers.", "domain": "code"},
                )
                self.assertEqual(seeded["kind"], "text")
                liked = _http_json(
                    "POST",
                    port,
                    "/api/like",
                    {"text": "Return reasons with scores.", "domain": "code"},
                )
                self.assertEqual(liked["polarity"], "like")
                harvested = _http_json("POST", port, "/api/harvest", {})
                self.assertIn("report", harvested)
                status = _http_json("GET", port, "/api/status")
                self.assertTrue(status["configured"])
                self.assertGreaterEqual(status["seed_count"], 1)
                page = _http_text("GET", port, "/")
                self.assertIn("NanoTaste studio", page)
                self.assertIn("Seed the taste files", page)
                css = _http_text("GET", port, "/styles.css")
                self.assertIn("--ink", css)
                script = _http_text("GET", port, "/app.js")
                self.assertIn("loadCatalog", script)
                sources = _http_json_any("GET", port, "/api/sources")
                self.assertTrue(isinstance(sources, list))
                seeds = _http_json("GET", port, "/api/seeds")
                self.assertGreaterEqual(len(seeds["seeds"]), 1)
                report = _http_json("GET", port, "/api/report")
                self.assertIn("markdown", report)
                scheduled = _http_json("POST", port, "/api/schedule", {"every": "daily"})
                self.assertEqual(scheduled["frequency"], "daily")
                setup = _http_json("POST", port, "/api/setup", {"harvest": False, "frequency": "weekly"})
                self.assertTrue(setup["ok"])
                pictured = _http_json(
                    "POST",
                    port,
                    "/api/seed",
                    {
                        "filename": "mood.png",
                        "caption": "Restrained paper and ink",
                        "domain": "aesthetic",
                        "content": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2nkAAAAASUVORK5CYII=",
                    },
                )
                self.assertEqual(pictured["kind"], "image")
                missing = _http_status("GET", port, "/api/missing")
                self.assertEqual(missing, 404)
                bad = _http_status("POST", port, "/api/seed", b"{not-json", {"Content-Type": "application/json"})
                self.assertEqual(bad, 400)
                traversal = _http_status(
                    "POST",
                    port,
                    "/api/seed",
                    json.dumps(
                        {
                            "filename": "../secret.txt",
                            "content": "dGVzdA==",
                            "domain": "personal",
                        }
                    ).encode("utf-8"),
                    {"Content-Type": "application/json"},
                )
                self.assertEqual(traversal, 400)
            finally:
                server.shutdown()
                server.server_close()

    def test_seed_cli_requires_an_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "project"
            home = root / "home"
            workspace.mkdir()
            home.mkdir()
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["setup", "--yes", "--no-harvest", "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
            stderr = StringIO()
            with redirect_stderr(stderr):
                status = main(["seed", "--workspace", str(workspace), "--home", str(home)])
            self.assertEqual(status, 1)
            self.assertIn("provide --url", stderr.getvalue())
            catalog_out = StringIO()
            with redirect_stdout(catalog_out):
                self.assertEqual(
                    main(["catalog", "--workspace", str(workspace), "--home", str(home)]),
                    0,
                )
            self.assertIn("Writing", catalog_out.getvalue())
            seed_out = StringIO()
            with redirect_stdout(seed_out):
                self.assertEqual(
                    main(
                        [
                            "seed",
                            "--text",
                            "def parse_scores(): return reasons",
                            "--workspace",
                            str(workspace),
                            "--home",
                            str(home),
                        ]
                    ),
                    0,
                )
            self.assertIn("Seeded text", seed_out.getvalue())

    def test_seed_helpers_guess_domain_and_reject_huge_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ws = resolve_workspace(Path(tmp), Path(tmp))
            run_setup(ws, yes=True, harvest=False)
            seed_workspace(ws, text="class Parser: pass\nimport json\n", domain="", label="code-note")
            self.assertTrue(seed_texts(ws, "code"))
            huge = Path(tmp) / "huge.txt"
            huge.write_bytes(b"x" * (600 * 1024))
            with self.assertRaises(ValueError):
                seed_workspace(ws, path=huge)
            with self.assertRaises(SecurityInputError):
                validate_seed_filename("../secret.txt")
            with self.assertRaises(SecurityInputError):
                validate_loopback_host("0.0.0.0")
            self.assertEqual(validate_loopback_host("127.0.0.1"), "127.0.0.1")


def _http_json_any(method: str, port: int, path: str, payload: dict[str, object] | None = None) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    data = json.loads(raw)
    if response.status >= 400:
        raise AssertionError(f"{method} {path} failed: {response.status} {data}")
    return data


def _http_status(method: str, port: int, path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> int:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


def _http_json(method: str, port: int, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    data = json.loads(raw)
    if response.status >= 400:
        raise AssertionError(f"{method} {path} failed: {response.status} {data}")
    if not isinstance(data, dict):
        raise AssertionError(f"expected object from {path}")
    return data


def _http_text(method: str, port: int, path: str) -> str:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    if response.status >= 400:
        raise AssertionError(f"{method} {path} failed: {response.status}")
    return raw
