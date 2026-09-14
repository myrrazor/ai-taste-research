"""Generate local taste reports on demand or on a schedule."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanotaste.ingest import load_excerpts
from nanotaste.learn import LearnedSignals
from nanotaste.prefer import list_examples
from nanotaste.security import atomic_write_text
from nanotaste.sources import discover_sources
from nanotaste.workspace import (
    TasteConfig,
    TasteWorkspace,
    cron_snippet,
    load_config,
    next_report_due,
    now_iso,
    replace_config,
    report_is_due,
)


@dataclass(frozen=True)
class ReportResult:
    """Files written for one taste report."""

    generated_at: str
    markdown_path: Path
    json_path: Path
    due: bool
    skipped: bool
    payload: dict[str, Any]


def generate_report(
    workspace: TasteWorkspace,
    *,
    if_due: bool = False,
    now: datetime | None = None,
) -> ReportResult:
    """Write markdown and JSON reports for the current workspace."""
    config = load_config(workspace)
    current = now or datetime.now(timezone.utc)
    due = report_is_due(config, current)
    if if_due and not due:
        return ReportResult(
            generated_at=now_iso(),
            markdown_path=workspace.reports_dir / "latest.md",
            json_path=workspace.reports_dir / "latest.json",
            due=False,
            skipped=True,
            payload={"skipped": True, "reason": "report is not due yet"},
        )
    payload = build_report_payload(workspace, config, current)
    workspace.reports_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_report_markdown(payload)
    markdown_path = workspace.reports_dir / "latest.md"
    json_path = workspace.reports_dir / "latest.json"
    stamp = current.strftime("%Y-%m-%d")
    atomic_write_text(markdown_path, markdown, label="taste report")
    atomic_write_text(
        workspace.reports_dir / f"{stamp}.md",
        markdown,
        label="dated taste report",
    )
    atomic_write_text(
        json_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        label="taste report json",
    )
    replace_config(workspace, last_report_at=payload["generated_at"])
    return ReportResult(
        generated_at=str(payload["generated_at"]),
        markdown_path=markdown_path,
        json_path=json_path,
        due=due,
        skipped=False,
        payload=payload,
    )


def build_report_payload(
    workspace: TasteWorkspace,
    config: TasteConfig,
    now: datetime,
) -> dict[str, Any]:
    """Collect the local evidence summarized in a report."""
    excerpts = load_excerpts(workspace)
    likes = list_examples(workspace, "like")
    unlikes = list_examples(workspace, "unlike")
    signals = _load_signals(workspace)
    sources = [
        {
            "id": source.id,
            "name": source.name,
            "present": source.present,
            "enabled": source.id in config.enabled_sources,
            "detail": source.detail,
            "session_files": source.session_files,
        }
        for source in discover_sources(workspace.home, workspace.root)
    ]
    due_at = next_report_due(config, now)
    return {
        "schema": "nanotaste/taste-report/1.0",
        "generated_at": now.replace(microsecond=0).isoformat(),
        "workspace": str(workspace.root),
        "taste_file": str(workspace.taste_path(config)),
        "taste_exists": workspace.taste_path(config).exists(),
        "domains": list(config.domains),
        "report_frequency": config.report_frequency,
        "next_report_due": due_at.isoformat() if due_at else None,
        "last_ingest_at": config.last_ingest_at,
        "last_learn_at": config.last_learn_at,
        "sources": sources,
        "enabled_sources": list(config.enabled_sources),
        "excerpt_count": len(excerpts),
        "like_count": len(likes),
        "unlike_count": len(unlikes),
        "likes": [path.name for path in likes],
        "unlikes": [path.name for path in unlikes],
        "learned": signals.to_json() if signals else None,
        "recent_runs": _recent_runs(workspace.runs_path),
        "schedule": cron_snippet(workspace, config.report_frequency).strip(),
    }


def render_report_markdown(payload: dict[str, Any]) -> str:
    """Render a human-readable taste report."""
    learned = payload.get("learned") or {}
    principles = learned.get("principles") or []
    forbidden = learned.get("forbidden") or []
    source_rows = []
    for source in payload["sources"]:
        flag = "yes" if source["present"] else "no"
        enabled = "on" if source["enabled"] else "off"
        source_rows.append(
            f"| {source['name']} | {flag} | {enabled} | {source['session_files']} | {source['detail']} |"
        )
    principle_lines = "\n".join(f"- {item}" for item in principles) or "- No learned principles yet."
    forbidden_lines = "\n".join(f"- `{item}`" for item in forbidden) or "- No learned forbidden moves yet."
    run_lines = []
    for run in payload["recent_runs"]:
        run_lines.append(f"- `{run.get('domain', 'general')}` selected score {run.get('score', '?')}: {run.get('text', '')}")
    likes = "\n".join(f"- {name}" for name in payload["likes"]) or "- None yet. Use `nanotaste like PATH`."
    unlikes = "\n".join(f"- {name}" for name in payload["unlikes"]) or "- None yet. Use `nanotaste unlike PATH`."
    return f"""# NanoTaste taste report

Generated: {payload['generated_at']}

This report summarizes local setup, opted-in coding-agent history, and operator
likes. It is inspectable workflow evidence, not a claim that NanoTaste has
learned a preference model.

## Workspace

- Root: `{payload['workspace']}`
- Taste file: `{payload['taste_file']}` ({'present' if payload['taste_exists'] else 'missing'})
- Domains: {', '.join(payload['domains'])}
- Report frequency: `{payload['report_frequency']}`
- Next scheduled report: {payload['next_report_due'] or 'manual only'}
- Last ingest: {payload['last_ingest_at'] or 'never'}
- Last learn pass: {payload['last_learn_at'] or 'never'}

## Coding agents

| Source | Present | Integrated | Session files | Detail |
|---|---|---|---:|---|
{chr(10).join(source_rows)}

Enabled: {', '.join(payload['enabled_sources']) or 'none'}

## Harvested history

- Session excerpts: {payload['excerpt_count']}
- Liked examples: {payload['like_count']}
- Unliked examples: {payload['unlike_count']}

## Learned signals

{principle_lines}

### Forbidden-move candidates

{forbidden_lines}

## Operator likes

{likes}

## Operator unlikes

{unlikes}

## Recent NanoTaste runs

{chr(10).join(run_lines) or '- No `nanotaste run` records yet.'}

## Keep steering this

```bash
nanotaste like examples/likes/concrete-release-note.md
nanotaste unlike examples/unlikes/generic-ai-prose.md
nanotaste pick --prompt "Write a launch note" --candidate "A" --candidate "B" --choose 1
nanotaste harvest
nanotaste report
nanotaste schedule --every weekly
```

## Automation snippet

```cron
{payload['schedule']}
```
"""


def write_schedule(workspace: TasteWorkspace, frequency: str) -> Path:
    """Persist report frequency and write a crontab snippet."""
    replace_config(workspace, report_frequency=frequency)
    path = workspace.nanotaste_dir / "schedule.cron"
    atomic_write_text(path, cron_snippet(workspace, frequency), label="schedule snippet")
    return path


def _load_signals(workspace: TasteWorkspace) -> LearnedSignals | None:
    path = workspace.learned_dir / "signals.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return LearnedSignals(
        generated_at=str(data.get("generated_at") or ""),
        principles=tuple(data.get("principles") or ()),
        forbidden=tuple(data.get("forbidden") or ()),
        good_examples=tuple(data.get("good_examples") or ()),
        bad_examples=tuple(data.get("bad_examples") or ()),
        like_count=int(data.get("like_count") or 0),
        unlike_count=int(data.get("unlike_count") or 0),
        session_count=int(data.get("session_count") or 0),
    )


def _recent_runs(path: Path, limit: int = 5) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        selected = record.get("selected_candidate") or {}
        rows.append(
            {
                "domain": record.get("domain"),
                "score": selected.get("score"),
                "text": str(selected.get("text") or "")[:180],
            }
        )
    return rows
