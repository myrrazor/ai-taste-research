"""First-run setup: discover agents, write config, and optionally harvest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import IO

from nanotaste.catalog import install_hierarchy
from nanotaste.ingest import ingest_workspace
from nanotaste.learn import learn_workspace
from nanotaste.report import generate_report, write_schedule
from nanotaste.sources import AgentSource, discover_sources, present_sources
from nanotaste.workspace import (
    DEFAULT_DOMAINS,
    FREQUENCIES,
    TasteConfig,
    TasteWorkspace,
    config_exists,
    ensure_workspace,
    now_iso,
    write_config,
)


@dataclass(frozen=True)
class SetupResult:
    """Outcome of first-run setup."""

    workspace: TasteWorkspace
    config: TasteConfig
    discovered: tuple[AgentSource, ...]
    enabled: tuple[str, ...]
    taste_path: Path
    harvested: bool
    report_path: Path | None
    seeded: bool = False


def run_setup(
    workspace: TasteWorkspace,
    *,
    yes: bool = False,
    harvest: bool = True,
    frequency: str = "weekly",
    domains: tuple[str, ...] | None = None,
    sources: tuple[str, ...] | None = None,
    seed_url: str | None = None,
    seed_file: str | None = None,
    seed_text: str | None = None,
    stdin: IO[str] | None = None,
    stdout: IO[str] | None = None,
) -> SetupResult:
    """Create local config, optionally integrate discovered agents, and harvest."""
    if frequency not in FREQUENCIES:
        raise ValueError(f"unsupported report frequency: {frequency}")
    ensure_workspace(workspace)
    discovered = tuple(discover_sources(workspace.home, workspace.root))
    present = [source for source in discovered if source.present]
    enabled = tuple(sources if sources is not None else _choose_sources(present, yes, stdin, stdout))
    chosen_domains = domains or DEFAULT_DOMAINS
    if not yes:
        chosen_domains = _choose_domains(chosen_domains, stdin, stdout)
        frequency = _choose_frequency(frequency, stdin, stdout)
        harvest = _ask(
            f"Pull coding sessions now and start {frequency} taste training?",
            True,
            stdin,
            stdout,
        )
    install_hierarchy(workspace)
    taste_path = workspace.root / "TASTE.md"
    config = TasteConfig(
        schema="nanotaste/config/1.0",
        created_at=now_iso(),
        taste_file="TASTE.md",
        domains=tuple(chosen_domains),
        enabled_sources=enabled,
        report_frequency=frequency,
        last_report_at=None,
        last_ingest_at=None,
        last_learn_at=None,
        auto_harvest=harvest,
    )
    write_config(workspace, config)
    write_schedule(workspace, frequency)
    seeded = _apply_seed(
        workspace,
        seed_url=seed_url,
        seed_file=seed_file,
        seed_text=seed_text,
        yes=yes,
        stdin=stdin,
        stdout=stdout,
    )
    report_path = None
    did_harvest = False
    if harvest:
        if enabled:
            ingest_workspace(workspace, enabled)
        learn_workspace(workspace, create_if_missing=True)
        report_path = generate_report(workspace).markdown_path
        did_harvest = True
    return SetupResult(
        workspace=workspace,
        config=config,
        discovered=discovered,
        enabled=tuple(enabled),
        taste_path=taste_path,
        harvested=did_harvest,
        report_path=report_path,
        seeded=seeded,
    )


def render_discovery(sources: list[AgentSource] | tuple[AgentSource, ...]) -> str:
    """Render a table of discovered coding agents."""
    lines = [
        "Coding agents and history sources",
        "",
        f"{'Source':<18} {'Present':<9} {'Files':>5}  Detail",
        "-" * 72,
    ]
    for source in sources:
        present = "yes" if source.present else "no"
        lines.append(f"{source.name:<18} {present:<9} {source.session_files:>5}  {source.detail}")
    present_ids = [source.id for source in sources if source.present]
    lines.extend(["", f"Present now: {', '.join(present_ids) or 'none'}"])
    return "\n".join(lines)


def default_enabled_ids(home: Path, cwd: Path) -> tuple[str, ...]:
    """Return default integrations for a non-interactive install."""
    return tuple(source.id for source in present_sources(home, cwd) if source.default_enabled)


def already_configured(workspace: TasteWorkspace) -> bool:
    """Return whether setup has already been completed."""
    return config_exists(workspace)


def _choose_sources(
    present: list[AgentSource],
    yes: bool,
    stdin: IO[str] | None,
    stdout: IO[str] | None,
) -> list[str]:
    ids = [source.id for source in present]
    if yes or not present:
        return ids
    _write(stdout, render_discovery(present))
    if _ask("Integrate all present coding agents and history sources?", True, stdin, stdout):
        return ids
    chosen: list[str] = []
    for source in present:
        if _ask(f"Integrate {source.name} ({source.detail})?", True, stdin, stdout):
            chosen.append(source.id)
    return chosen


def _choose_domains(
    default: tuple[str, ...],
    stdin: IO[str] | None,
    stdout: IO[str] | None,
) -> tuple[str, ...]:
    answer = _prompt(
        f"Domains to keep in TASTE.md [{', '.join(default)}]",
        ",".join(default),
        stdin,
        stdout,
    )
    items = tuple(item.strip() for item in answer.split(",") if item.strip())
    return items or default


def _apply_seed(
    workspace: TasteWorkspace,
    *,
    seed_url: str | None,
    seed_file: str | None,
    seed_text: str | None,
    yes: bool,
    stdin: IO[str] | None,
    stdout: IO[str] | None,
) -> bool:
    from nanotaste.seed import seed_workspace

    if seed_url or seed_file or seed_text:
        if seed_url:
            seed_workspace(workspace, url=seed_url, domain="personal", label="setup-url")
        if seed_file:
            seed_workspace(workspace, path=Path(seed_file), label="setup-file")
        if seed_text:
            seed_workspace(workspace, text=seed_text, domain="personal", label="setup-text")
        _write(stdout, "Seed recorded. Harvest will fold it into learned overlays.")
        return True
    if yes:
        return False
    hint = _prompt(
        "Seed taste from a personal site, file, or note? "
        "Paste a URL, path, short text, or press Enter to skip",
        "",
        stdin,
        stdout,
    ).strip()
    if not hint:
        return False
    if hint.startswith("http://") or hint.startswith("https://"):
        seed_workspace(workspace, url=hint, domain="personal", label="setup-url")
    else:
        candidate = Path(hint).expanduser()
        if candidate.exists():
            seed_workspace(workspace, path=candidate, label="setup-file")
        else:
            seed_workspace(workspace, text=hint, domain="personal", label="setup-text")
    _write(stdout, "Seed recorded. Harvest will fold it into learned overlays.")
    return True


def _choose_frequency(default: str, stdin: IO[str] | None, stdout: IO[str] | None) -> str:
    answer = _prompt(
        "How often should NanoTaste pull coding sessions and refresh taste? (manual, daily, weekly, monthly)",
        default,
        stdin,
        stdout,
    ).strip().lower()
    return answer if answer in FREQUENCIES else default


def _ask(question: str, default: bool, stdin: IO[str] | None, stdout: IO[str] | None) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = _prompt(f"{question} [{suffix}]", "y" if default else "n", stdin, stdout)
    normalized = answer.strip().lower()
    if not normalized:
        return default
    return normalized in {"y", "yes"}


def _prompt(question: str, default: str, stdin: IO[str] | None, stdout: IO[str] | None) -> str:
    _write(stdout, f"{question}")
    if stdin is None:
        return default
    try:
        line = stdin.readline()
    except EOFError:
        return default
    if line == "":
        return default
    return line.strip() or default


def _write(stdout: IO[str] | None, text: str) -> None:
    if stdout is not None:
        stdout.write(text + "\n")
        stdout.flush()
