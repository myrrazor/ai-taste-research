"""Local NanoTaste studio: inspect hierarchy, seed taste, and run harvest."""

from __future__ import annotations

import base64
import json
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from nanotaste.catalog import catalog_payload, install_hierarchy
from nanotaste.ingest import ingest_workspace
from nanotaste.learn import learn_workspace
from nanotaste.prefer import add_example
from nanotaste.report import generate_report, write_schedule
from nanotaste.seed import list_seeds, seed_workspace
from nanotaste.setup_wizard import already_configured, run_setup
from nanotaste.sources import discover_sources
from nanotaste.workspace import (
    TasteWorkspace,
    load_config,
    next_report_due,
    report_is_due,
    resolve_workspace,
)

WEB_FILES = {"index.html": "text/html; charset=utf-8", "styles.css": "text/css", "app.js": "text/javascript"}


class TasteStudioHandler(BaseHTTPRequestHandler):
    """127.0.0.1-only handler for the local taste studio."""

    workspace: TasteWorkspace

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_static("index.html")
            return
        name = parsed.path.lstrip("/")
        if name in WEB_FILES:
            self._send_static(name)
            return
        if parsed.path == "/api/status":
            self._send_json(_status_payload(self.workspace))
            return
        if parsed.path == "/api/catalog":
            self._send_json(catalog_payload(self.workspace))
            return
        if parsed.path == "/api/sources":
            self._send_json(
                [
                    {
                        "id": source.id,
                        "name": source.name,
                        "present": source.present,
                        "detail": source.detail,
                        "session_files": source.session_files,
                    }
                    for source in discover_sources(self.workspace.home, self.workspace.root)
                ]
            )
            return
        if parsed.path == "/api/seeds":
            self._send_json({"seeds": list_seeds(self.workspace)})
            return
        if parsed.path == "/api/report":
            path = self.workspace.reports_dir / "latest.md"
            text = path.read_text(encoding="utf-8") if path.is_file() else "No report yet. Run harvest."
            self._send_json({"markdown": text, "path": str(path)})
            return
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
        except (json.JSONDecodeError, ValueError) as err:
            self._send_json({"error": str(err)}, 400)
            return
        try:
            if parsed.path == "/api/setup":
                result = run_setup(
                    self.workspace,
                    yes=True,
                    harvest=bool(payload.get("harvest", True)),
                    frequency=str(payload.get("frequency") or "weekly"),
                )
                self._send_json({"ok": True, "enabled": list(result.enabled), "taste": str(result.taste_path)})
                return
            if parsed.path == "/api/harvest":
                _ensure_ready(self.workspace)
                ingested = ingest_workspace(self.workspace)
                learned = learn_workspace(self.workspace)
                report = generate_report(self.workspace)
                self._send_json(
                    {
                        "excerpts": len(ingested.excerpts),
                        "proposal": str(learned.proposal_path),
                        "report": str(report.markdown_path),
                        "overlays": [str(path) for path in learned.overlay_paths],
                    }
                )
                return
            if parsed.path == "/api/seed":
                _ensure_ready(self.workspace)
                record = _seed_from_payload(self.workspace, payload)
                self._send_json(record.to_json())
                return
            if parsed.path == "/api/like":
                _ensure_ready(self.workspace)
                polarity = "unlike" if payload.get("unlike") else "like"
                item = str(payload.get("text") or payload.get("item") or "")
                example = add_example(self.workspace, item, polarity, str(payload.get("domain") or "general"))
                self._send_json({"path": str(example.path), "polarity": polarity})
                return
            if parsed.path == "/api/schedule":
                _ensure_ready(self.workspace)
                path = write_schedule(self.workspace, str(payload.get("every") or "weekly"))
                self._send_json({"path": str(path), "frequency": payload.get("every") or "weekly"})
                return
        except (OSError, ValueError) as err:
            self._send_json({"error": str(err)}, 400)
            return
        self._send_json({"error": "not found"}, 404)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_static(self, name: str) -> None:
        data = resources.files("nanotaste").joinpath(f"web/{name}").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", WEB_FILES[name])
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, Any] | list[Any], status: int = 200) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def serve_workspace(
    workspace: TasteWorkspace,
    host: str = "127.0.0.1",
    port: int = 7468,
    *,
    tick: bool = True,
) -> ThreadingHTTPServer:
    """Start the local studio server and optional harvest ticker."""
    if not already_configured(workspace):
        run_setup(workspace, yes=True, harvest=True)
    else:
        install_hierarchy(workspace)
    handler = partial(TasteStudioHandler)
    TasteStudioHandler.workspace = workspace
    server = ThreadingHTTPServer((host, port), handler)
    if tick:
        thread = threading.Thread(target=_tick_loop, args=(workspace,), daemon=True)
        thread.start()
    return server


def _tick_loop(workspace: TasteWorkspace) -> None:
    while True:
        try:
            if already_configured(workspace) and report_is_due(load_config(workspace)):
                ingest_workspace(workspace)
                learn_workspace(workspace)
                generate_report(workspace)
        except (OSError, ValueError):
            pass
        time.sleep(60)


def _status_payload(workspace: TasteWorkspace) -> dict[str, Any]:
    configured = already_configured(workspace)
    payload: dict[str, Any] = {
        "workspace": str(workspace.root),
        "configured": configured,
        "studio": "local",
    }
    if not configured:
        return payload
    config = load_config(workspace)
    due = next_report_due(config)
    catalog = catalog_payload(workspace)
    payload.update(
        {
            "taste_file": str(workspace.taste_path(config)),
            "enabled_sources": list(config.enabled_sources),
            "report_frequency": config.report_frequency,
            "report_due": report_is_due(config),
            "next_report_due": due.isoformat() if due else None,
            "last_ingest_at": config.last_ingest_at,
            "last_learn_at": config.last_learn_at,
            "last_report_at": config.last_report_at,
            "seed_count": len(list_seeds(workspace)),
            "catalog_nodes": len(catalog["nodes"]),
            "categories": catalog["categories"],
        }
    )
    return payload


def _ensure_ready(workspace: TasteWorkspace) -> None:
    if not already_configured(workspace):
        run_setup(workspace, yes=True, harvest=False)
    install_hierarchy(workspace)


def _seed_from_payload(workspace: TasteWorkspace, payload: dict[str, Any]) -> Any:
    domain = str(payload.get("domain") or "personal")
    if payload.get("url"):
        return seed_workspace(workspace, url=str(payload["url"]), domain=domain, label=payload.get("label"))
    if payload.get("text"):
        return seed_workspace(workspace, text=str(payload["text"]), domain=domain, label=payload.get("label"))
    if payload.get("filename") and payload.get("content"):
        raw = base64.b64decode(str(payload["content"]))
        dest = workspace.seed_files_dir / Path(str(payload["filename"])).name
        dest.write_bytes(raw)
        return seed_workspace(
            workspace,
            path=dest,
            domain=domain,
            label=payload.get("label"),
            caption=payload.get("caption"),
        )
    raise ValueError("provide url, text, or a file")


def resolve_and_serve(root: Path | None, home: Path | None, host: str, port: int) -> ThreadingHTTPServer:
    """Resolve the workspace and start the studio."""
    return serve_workspace(resolve_workspace(root, home), host=host, port=port)
