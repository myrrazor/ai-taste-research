"""Local workspace config and .nanotaste directory helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from nanotaste.security import atomic_write_text, safe_json_loads, safe_read_text

CONFIG_SCHEMA = "nanotaste/config/1.0"
CONFIG_NAME = "config.json"
FREQUENCIES = ("manual", "daily", "weekly", "monthly")
DEFAULT_DOMAINS = (
    "general",
    "writing",
    "code",
    "product",
    "aesthetic",
    "personal",
    "brand",
    "communication",
    "research",
)


@dataclass(frozen=True)
class TasteConfig:
    """Operator-facing workspace settings stored in `.nanotaste/config.json`."""

    schema: str
    created_at: str
    taste_file: str
    domains: tuple[str, ...]
    enabled_sources: tuple[str, ...]
    report_frequency: str
    last_report_at: str | None
    last_ingest_at: str | None
    last_learn_at: str | None
    auto_harvest: bool

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable config object."""
        return {
            "schema": self.schema,
            "created_at": self.created_at,
            "taste_file": self.taste_file,
            "domains": list(self.domains),
            "enabled_sources": list(self.enabled_sources),
            "report_frequency": self.report_frequency,
            "last_report_at": self.last_report_at,
            "last_ingest_at": self.last_ingest_at,
            "last_learn_at": self.last_learn_at,
            "auto_harvest": self.auto_harvest,
        }


@dataclass(frozen=True)
class TasteWorkspace:
    """Resolved project root plus the local `.nanotaste` directory."""

    root: Path
    nanotaste_dir: Path
    home: Path

    @property
    def config_path(self) -> Path:
        return self.nanotaste_dir / CONFIG_NAME

    @property
    def likes_dir(self) -> Path:
        return self.nanotaste_dir / "likes"

    @property
    def unlikes_dir(self) -> Path:
        return self.nanotaste_dir / "unlikes"

    @property
    def sessions_dir(self) -> Path:
        return self.nanotaste_dir / "sessions"

    @property
    def learned_dir(self) -> Path:
        return self.nanotaste_dir / "learned"

    @property
    def reports_dir(self) -> Path:
        return self.nanotaste_dir / "reports"

    @property
    def picks_path(self) -> Path:
        return self.nanotaste_dir / "picks.jsonl"

    @property
    def runs_path(self) -> Path:
        return self.nanotaste_dir / "runs.jsonl"

    @property
    def seeds_dir(self) -> Path:
        return self.nanotaste_dir / "seeds"

    @property
    def seed_files_dir(self) -> Path:
        return self.seeds_dir / "files"

    @property
    def taste_dir(self) -> Path:
        return self.root / "taste"

    @property
    def learned_overlays_dir(self) -> Path:
        return self.taste_dir / "learned"

    def taste_path(self, config: TasteConfig | None = None) -> Path:
        relative = Path(config.taste_file) if config else Path("TASTE.md")
        return relative if relative.is_absolute() else self.root / relative


def now_iso() -> str:
    """Return a UTC timestamp for config and reports."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def resolve_workspace(root: Path | None = None, home: Path | None = None) -> TasteWorkspace:
    """Resolve the project workspace and the operator home used for discovery."""
    workspace = TasteWorkspace(
        root=(root or Path.cwd()).expanduser().resolve(),
        nanotaste_dir=Path(),
        home=(home or Path.home()).expanduser().resolve(),
    )
    return TasteWorkspace(
        root=workspace.root,
        nanotaste_dir=workspace.root / ".nanotaste",
        home=workspace.home,
    )


def ensure_workspace(workspace: TasteWorkspace) -> None:
    """Create the local NanoTaste directories."""
    for path in (
        workspace.nanotaste_dir,
        workspace.likes_dir,
        workspace.unlikes_dir,
        workspace.sessions_dir,
        workspace.learned_dir,
        workspace.reports_dir,
        workspace.seeds_dir,
        workspace.seed_files_dir,
        workspace.taste_dir,
        workspace.learned_overlays_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def config_exists(workspace: TasteWorkspace) -> bool:
    """Return whether this workspace has already been set up."""
    return workspace.config_path.is_file()


def load_config(workspace: TasteWorkspace) -> TasteConfig:
    """Load an existing workspace config."""
    data = safe_json_loads(
        safe_read_text(workspace.config_path, label="workspace config"),
        "workspace config",
    )
    if not isinstance(data, dict):
        raise ValueError("workspace config must be a JSON object")
    if data.get("schema") != CONFIG_SCHEMA:
        raise ValueError("unsupported workspace config schema")
    frequency = str(data.get("report_frequency", "weekly"))
    if frequency not in FREQUENCIES:
        raise ValueError(f"unsupported report frequency: {frequency}")
    domains = _string_tuple(data.get("domains"), DEFAULT_DOMAINS)
    sources = _string_tuple(data.get("enabled_sources"), ())
    return TasteConfig(
        schema=CONFIG_SCHEMA,
        created_at=str(data.get("created_at") or now_iso()),
        taste_file=str(data.get("taste_file") or "TASTE.md"),
        domains=domains,
        enabled_sources=sources,
        report_frequency=frequency,
        last_report_at=_optional_str(data.get("last_report_at")),
        last_ingest_at=_optional_str(data.get("last_ingest_at")),
        last_learn_at=_optional_str(data.get("last_learn_at")),
        auto_harvest=bool(data.get("auto_harvest", True)),
    )


def write_config(workspace: TasteWorkspace, config: TasteConfig) -> Path:
    """Write workspace config atomically."""
    ensure_workspace(workspace)
    atomic_write_text(
        workspace.config_path,
        json.dumps(config.to_json(), indent=2, sort_keys=True) + "\n",
        label="workspace config",
    )
    return workspace.config_path


def replace_config(workspace: TasteWorkspace, **changes: Any) -> TasteConfig:
    """Update selected config fields and persist them."""
    current = load_config(workspace)
    payload = current.to_json()
    payload.update(changes)
    updated = load_config_from_mapping(payload)
    write_config(workspace, updated)
    return updated


def load_config_from_mapping(data: dict[str, Any]) -> TasteConfig:
    """Build a config object from an already-validated mapping."""
    frequency = str(data.get("report_frequency", "weekly"))
    if frequency not in FREQUENCIES:
        raise ValueError(f"unsupported report frequency: {frequency}")
    return TasteConfig(
        schema=CONFIG_SCHEMA,
        created_at=str(data.get("created_at") or now_iso()),
        taste_file=str(data.get("taste_file") or "TASTE.md"),
        domains=_string_tuple(data.get("domains"), DEFAULT_DOMAINS),
        enabled_sources=_string_tuple(data.get("enabled_sources"), ()),
        report_frequency=frequency,
        last_report_at=_optional_str(data.get("last_report_at")),
        last_ingest_at=_optional_str(data.get("last_ingest_at")),
        last_learn_at=_optional_str(data.get("last_learn_at")),
        auto_harvest=bool(data.get("auto_harvest", True)),
    )


def starter_taste_markdown() -> str:
    """Return the packaged starter taste file."""
    try:
        return resources.files("nanotaste").joinpath("data/TASTE.starter.md").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        return (
            "# TASTE.md\n\n## Principles\n\n### general\n- Specificity beats polish.\n\n"
            "## Update Policy\n\n### general\n- Review proposed updates before changing this file.\n"
        )


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse a stored ISO timestamp."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def next_report_due(config: TasteConfig, now: datetime | None = None) -> datetime | None:
    """Return when the next scheduled report is due, if scheduling is enabled."""
    if config.report_frequency == "manual":
        return None
    current = now or datetime.now(timezone.utc)
    last = parse_timestamp(config.last_report_at)
    if last is None:
        return current
    delta = {
        "daily": timedelta(days=1),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }[config.report_frequency]
    return last + delta


def report_is_due(config: TasteConfig, now: datetime | None = None) -> bool:
    """Return whether a scheduled report should be generated now."""
    due = next_report_due(config, now)
    if due is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current >= due


def cron_snippet(workspace: TasteWorkspace, frequency: str) -> str:
    """Return a user-crontab snippet for automated report generation."""
    schedule = {
        "daily": "15 9 * * *",
        "weekly": "15 9 * * 1",
        "monthly": "15 9 1 * *",
        "manual": "# no automatic schedule; run `nanotaste report` yourself",
    }[frequency]
    if frequency == "manual":
        return f"{schedule}\n"
    return (
        f"# NanoTaste {frequency} harvest and taste report\n"
        f"{schedule} cd {workspace.root} && nanotaste harvest --if-due\n"
    )


def _string_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError("expected a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _optional_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("expected a string or null timestamp")
    return value
