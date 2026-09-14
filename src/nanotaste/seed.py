"""Seed taste from URLs, local files, images, and pasted text."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from nanotaste.catalog import CATEGORIES, write_learned_overlay
from nanotaste.domains import normalize_domain
from nanotaste.learn import extract_signals, merge_taste_markdown, render_proposal
from nanotaste.redact import redact_text
from nanotaste.security import (
    MAX_SEED_FILE_BYTES,
    MAX_SEED_ITEMS,
    MAX_SEED_URL_BYTES,
    atomic_write_text,
    append_jsonl_record,
    safe_read_text,
    validate_seed_filename,
    validate_text_limit,
)
from nanotaste.workspace import TasteWorkspace, ensure_workspace, now_iso

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".html", ".csv", ".py"}
_SEED_HOST_RE = re.compile(
    r"^(?:(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}"
    r"|localhost|(?:\d{1,3}\.){3}\d{1,3}|::1)$"
)


@dataclass(frozen=True)
class SeedRecord:
    """One operator-provided seed used to refresh category taste files."""

    kind: str
    domain: str
    label: str
    excerpt: str
    origin: str
    path: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "nanotaste/seed/1.0",
            "kind": self.kind,
            "domain": self.domain,
            "label": self.label,
            "excerpt": self.excerpt,
            "origin": self.origin,
            "path": self.path,
            "created_at": now_iso(),
        }


def seed_workspace(
    workspace: TasteWorkspace,
    *,
    text: str | None = None,
    url: str | None = None,
    path: Path | None = None,
    domain: str = "personal",
    label: str | None = None,
    caption: str | None = None,
) -> SeedRecord:
    """Store one seed and refresh the matching learned overlay."""
    ensure_workspace(workspace)
    if url:
        record = _seed_url(workspace, url, domain, label)
    elif path is not None:
        record = _seed_path(workspace, path, domain, label, caption)
    elif text and text.strip():
        validate_text_limit(text, MAX_SEED_FILE_BYTES, "seed text")
        record = SeedRecord(
            kind="text",
            domain=normalize_domain(domain or _guess_domain(text)),
            label=label or "pasted-text",
            excerpt=redact_text(text),
            origin="pasted text",
            path=None,
        )
    else:
        raise ValueError("provide --url, --file, or --text")
    _append_seed(workspace, record)
    _refresh_overlay(workspace, record.domain)
    return record


def list_seeds(workspace: TasteWorkspace) -> list[dict[str, Any]]:
    """Return stored seed records."""
    path = workspace.seeds_dir / "seeds.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[:MAX_SEED_ITEMS]:
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def seed_texts(workspace: TasteWorkspace, domain: str | None = None) -> list[str]:
    """Return seed excerpts, optionally filtered by domain."""
    texts: list[str] = []
    for item in list_seeds(workspace):
        if domain and item.get("domain") != domain:
            continue
        excerpt = str(item.get("excerpt") or "").strip()
        if excerpt:
            texts.append(excerpt)
    return texts


def _seed_url(workspace: TasteWorkspace, url: str, domain: str, label: str | None) -> SeedRecord:
    safe_url = _safe_seed_url(url)
    parsed = urlparse(safe_url)
    request = Request(
        safe_url,
        headers={"User-Agent": "NanoTaste/0.1 (+https://github.com/myrrazor/ai-taste-research)"},
    )
    try:
        opener = build_opener(_NoRedirect())
        with opener.open(request, timeout=12) as response:
            data = response.read(MAX_SEED_URL_BYTES + 1)
            content_type = str(response.headers.get("Content-Type", ""))
    except (URLError, TimeoutError, OSError) as err:
        raise ValueError(f"could not fetch seed URL: {err}") from err
    if len(data) > MAX_SEED_URL_BYTES:
        raise ValueError("seed URL response is too large")
    if "html" in content_type or safe_url.endswith(".html"):
        extracted = _html_text(data.decode("utf-8", errors="replace"))
    else:
        extracted = data.decode("utf-8", errors="replace")
    excerpt = redact_text(extracted)
    chosen = normalize_domain(domain or _guess_domain(excerpt))
    return SeedRecord("url", chosen, label or parsed.netloc, excerpt, safe_url, None)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise URLError("seed URLs do not follow redirects")


def _safe_seed_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("seed URL must be http or https without credentials")
    host = parsed.hostname
    if not host or not _SEED_HOST_RE.fullmatch(host):
        raise ValueError("seed URL host is not allowed")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError("seed URL port is not allowed")
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))


def _seed_path(
    workspace: TasteWorkspace,
    path: Path,
    domain: str,
    label: str | None,
    caption: str | None,
) -> SeedRecord:
    suffix = path.suffix.lower()
    dest = workspace.seed_files_dir / validate_seed_filename(path.name)
    if suffix in IMAGE_SUFFIXES:
        _copy_limited(path, dest, MAX_SEED_FILE_BYTES)
        excerpt = redact_text(" ".join(part for part in (caption, path.stem.replace("-", " "), path.name) if part))
        return SeedRecord(
            "image",
            normalize_domain(domain or "aesthetic"),
            label or path.stem,
            excerpt or path.name,
            str(path),
            str(dest.relative_to(workspace.root)),
        )
    text = safe_read_text(path, limit_bytes=MAX_SEED_FILE_BYTES, label="seed file")
    dest.write_text(text, encoding="utf-8")
    excerpt = redact_text(text)
    return SeedRecord(
        "file",
        normalize_domain(domain or _guess_domain(excerpt)),
        label or path.stem,
        excerpt,
        str(path),
        str(dest.relative_to(workspace.root)),
    )


def _append_seed(workspace: TasteWorkspace, record: SeedRecord) -> None:
    append_jsonl_record(workspace.seeds_dir / "seeds.jsonl", record.to_json(), label="seed record")


def _refresh_overlay(workspace: TasteWorkspace, domain: str) -> None:
    from nanotaste.ingest import load_excerpts
    from nanotaste.learn import _read_examples

    likes = _read_examples(workspace.likes_dir) + seed_texts(workspace, domain)
    unlikes = _read_examples(workspace.unlikes_dir)
    excerpts = [item for item in load_excerpts(workspace) if item.domain == domain]
    signals = extract_signals(likes, unlikes, excerpts)
    overlay = workspace.learned_overlays_dir / f"{domain}.md"
    existing = overlay.read_text(encoding="utf-8") if overlay.exists() else _empty_overlay(domain)
    write_learned_overlay(workspace, domain, merge_taste_markdown(existing, signals))
    atomic_write_text(
        workspace.learned_dir / f"{domain}-seed-proposal.md",
        render_proposal(signals),
        label="seed proposal",
    )


def _empty_overlay(domain: str) -> str:
    return f"""# Learned {domain} overlay
---
schema: taste/1.1
kind: overlay
domain: {domain}
tags: [learned, {domain}]
parent: taste/{domain}.md
---

## Principles

### {domain}
"""


def _guess_domain(text: str) -> str:
    lower = text.lower()
    for category in CATEGORIES:
        if category.id in lower or any(tag in lower for tag in category.tags):
            return category.id
    if any(word in lower for word in ("def ", "class ", "import ", "function ")):
        return "code"
    if any(word in lower for word in ("readme", "changelog", "release")):
        return "writing"
    return "personal"


def _copy_limited(source: Path, dest: Path, limit: int) -> None:
    data = source.read_bytes()
    if len(data) > limit:
        raise ValueError(f"seed file is too large: {len(data)} bytes > {limit} bytes")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.chunks.append(alt)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.chunks.append(text)


def _html_text(markup: str) -> str:
    parser = _HTMLText()
    parser.feed(markup)
    return " ".join(parser.chunks)
