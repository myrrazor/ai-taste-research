"""Command-line interface for NanoTaste."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, TextIO, cast

from nanotaste import __version__
from nanotaste.agent import TasteAgent
from nanotaste.calibration import prepare_calibration, write_evaluation
from nanotaste.discovery import TasteFileNotFoundError, resolve_taste_dir
from nanotaste.ingest import ingest_workspace
from nanotaste.learn import learn_workspace
from nanotaste.prefer import add_example, record_pick
from nanotaste.records import append_record
from nanotaste.report import generate_report, write_schedule
from nanotaste.scoring import SelectionResult
from nanotaste.security import (
    MAX_CANDIDATE_FILE_BYTES,
    RootEscapeError,
    SecurityInputError,
    safe_for_terminal,
    safe_read_text,
)
from nanotaste.setup_wizard import already_configured, render_discovery, run_setup
from nanotaste.sources import discover_sources
from nanotaste.workspace import (
    FREQUENCIES,
    TasteWorkspace,
    config_exists,
    load_config,
    next_report_due,
    report_is_due,
    resolve_workspace,
)

DESCRIPTION = (
    "Compare candidate outputs against a markdown taste file (TASTE.md) with a "
    "deterministic, lexical critic, and record the decision locally. First-run "
    "setup can also harvest coding-agent history and open a localhost studio."
)
TASTE_DISCOVERY_EPILOG = """\
taste discovery:
  Without --taste-file, NanoTaste looks for TASTE.md and taste/<domain>.md in the
  working directory, then in each parent directory, and uses the first directory
  that has either. It fails if nothing is found: create TASTE.md, pass
  --taste-file PATH, or pass --no-taste for an explicit no-rules baseline. A note
  is printed on stderr when rules come from outside the working directory.
  --taste-file is a deliberate choice and may point anywhere.
"""
INPUT_FILES_EPILOG = """\
input files:
  Candidate and edit files must be regular UTF-8 files that resolve (after
  following symlinks) inside the working directory. Pass --allow-outside-paths to
  read files elsewhere.
"""
MISSING_TASTE_HINT = (
    "Create TASTE.md in the project, pass --taste-file PATH, or pass --no-taste to score "
    "without taste rules."
)
OUTSIDE_PATH_HINT = "Pass --allow-outside-paths to read input files outside the working directory."


def main(argv: list[str] | None = None) -> int:
    """Run the NanoTaste CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return _root_command(args, parser)
    handlers = {
        "setup": _setup,
        "status": _status,
        "sources": _sources,
        "ingest": _ingest,
        "learn": _learn,
        "harvest": _harvest,
        "like": _like,
        "unlike": _unlike,
        "pick": _pick,
        "prefer": _prefer,
        "report": _report,
        "schedule": _schedule,
        "seed": _seed,
        "catalog": _catalog,
        "serve": _serve,
        "run": _run,
        "compare": _compare,
        "propose-update": _propose_update,
        "calibrate": _calibrate,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nanotaste",
        description=DESCRIPTION,
        epilog="Run 'nanotaste <command> --help' for the options of one command.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--workspace", help="project root (defaults to the current directory)")
    parser.add_argument("--home", help="home directory used for agent discovery")
    sub = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="<command>",
        help="one of the commands below",
    )

    setup = sub.add_parser("setup", help="discover coding agents and walk through first-run setup")
    _add_workspace_args(setup)
    setup.add_argument("--yes", action="store_true", help="accept defaults and integrate every present source")
    setup.add_argument("--no-harvest", action="store_true", help="skip the first harvest after setup")
    setup.add_argument("--every", choices=FREQUENCIES, default="weekly", help="report cadence (default: weekly)")
    setup.add_argument("--source", action="append", default=[], help="source id to integrate (repeatable)")
    setup.add_argument("--domain", action="append", default=[], help="domain to include (repeatable)")
    setup.add_argument("--seed-url", help="seed a personal site during first-run setup")
    setup.add_argument("--seed-file", help="seed a local file or image during first-run setup")
    setup.add_argument("--seed-text", help="seed a pasted note during first-run setup")
    _add_json_arg(setup, "print setup result as JSON")

    status = sub.add_parser("status", help="show workspace setup, sources, and report schedule")
    _add_workspace_args(status)
    _add_json_arg(status, "print workspace status as JSON")

    sources = sub.add_parser("sources", help="list discovered coding agents and history sources")
    _add_workspace_args(sources)
    _add_json_arg(sources, "print discovered sources as JSON")

    ingest = sub.add_parser("ingest", help="pull opted-in coding-session history")
    _add_workspace_args(ingest)
    _add_json_arg(ingest, "print ingest result as JSON")

    learn = sub.add_parser("learn", help="extract taste-rule proposals from history and likes")
    _add_workspace_args(learn)
    learn.add_argument("--apply", action="store_true", help="merge new learned rules into TASTE.md")
    _add_json_arg(learn, "print learn result as JSON")

    harvest = sub.add_parser("harvest", help="ingest history, learn taste signals, and write a report")
    _add_workspace_args(harvest)
    harvest.add_argument("--if-due", action="store_true", help="skip the report when the schedule is not due")
    harvest.add_argument("--apply", action="store_true", help="merge new learned rules into TASTE.md")
    _add_json_arg(harvest, "print harvest result as JSON")

    like = sub.add_parser("like", help="drop in an example you prefer")
    _add_workspace_args(like)
    like.add_argument("item", help="file path or literal text")
    like.add_argument("--domain", default="general", help="taste domain for this example (default: general)")
    like.add_argument("--label", help="optional stem used when storing the example file")
    _add_json_arg(like, "print the stored like as JSON")

    unlike = sub.add_parser("unlike", help="drop in an example you want the critic to avoid")
    _add_workspace_args(unlike)
    unlike.add_argument("item", help="file path or literal text")
    unlike.add_argument("--domain", default="general", help="taste domain for this example (default: general)")
    unlike.add_argument("--label", help="optional stem used when storing the example file")
    _add_json_arg(unlike, "print the stored unlike as JSON")

    pick = sub.add_parser("pick", help="manually choose the better option from a short list")
    _add_workspace_args(pick)
    pick.add_argument("--prompt", default="", help="optional prompt stored with the pick")
    pick.add_argument("--domain", default="general", help="taste domain for this pick (default: general)")
    pick.add_argument("--candidate", action="append", default=[], help="candidate text (repeatable)")
    pick.add_argument("--choose", type=int, help="1-based winner index for non-interactive picks")
    _add_json_arg(pick, "print the pick record as JSON")

    prefer = sub.add_parser("prefer", help="store one liked example against one disliked example")
    _add_workspace_args(prefer)
    prefer.add_argument("--like", required=True, help="liked file path or literal text")
    prefer.add_argument("--unlike", required=True, help="disliked file path or literal text")
    prefer.add_argument("--domain", default="general", help="taste domain for this pair (default: general)")
    _add_json_arg(prefer, "print the stored pair as JSON")

    report = sub.add_parser("report", help="generate a taste report now, or only if scheduled")
    _add_workspace_args(report)
    report.add_argument("--if-due", action="store_true", help="skip the report when the schedule is not due")
    _add_json_arg(report, "print report metadata as JSON")

    schedule = sub.add_parser("schedule", help="set how often automated session harvests should run")
    _add_workspace_args(schedule)
    schedule.add_argument("--every", choices=FREQUENCIES, required=True, help="report cadence")
    schedule.add_argument("--install", action="store_true", help="append the crontab snippet if crontab is available")
    _add_json_arg(schedule, "print the schedule as JSON")

    seed = sub.add_parser("seed", help="seed taste from a URL, file, image, or pasted note")
    _add_workspace_args(seed)
    seed.add_argument("--url", action="append", default=[], help="repeatable personal-site or page URL")
    seed.add_argument("--file", action="append", default=[], help="repeatable local file or image path")
    seed.add_argument("--text", action="append", default=[], help="repeatable pasted note")
    seed.add_argument("--domain", default="personal", help="taste domain to refresh (default: personal)")
    seed.add_argument("--label", help="optional label stored with the seed")
    seed.add_argument("--caption", help="optional caption used for image seeds")
    _add_json_arg(seed, "print seed records as JSON")

    catalog = sub.add_parser("catalog", help="show the taste-file hierarchy, categories, and tags")
    _add_workspace_args(catalog)
    _add_json_arg(catalog, "print the catalog as JSON")

    serve = sub.add_parser("serve", help="open the local taste studio web app")
    _add_workspace_args(serve)
    serve.add_argument("--host", default="127.0.0.1", help="loopback address to bind (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=7468, help="port to bind (default: 7468)")
    serve.add_argument("--no-tick", action="store_true", help="do not run the in-process harvest ticker")

    run = sub.add_parser(
        "run",
        help="generate or score candidate outputs for one prompt",
        description=_wrap(
            "Score candidates for one prompt and print the selected candidate with its "
            "score reasons. Without --candidate/--candidate-file, the built-in generator "
            "produces synthetic drafts; it never calls a model."
        ),
        epilog=TASTE_DISCOVERY_EPILOG + "\n" + INPUT_FILES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_taste_args(run)
    _add_domain_arg(run)
    run.add_argument(
        "--prompt",
        required=True,
        help="task prompt; a candidate sharing a word of 5+ letters with it earns +1",
    )
    run.add_argument(
        "--candidate",
        action="append",
        default=[],
        metavar="TEXT",
        help="inline candidate text (repeatable); disables the built-in generator",
    )
    run.add_argument(
        "--candidate-file",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "read one candidate from a UTF-8 file (repeatable); file candidates are "
            "scored after inline --candidate values, in the order given"
        ),
    )
    run.add_argument(
        "--count",
        type=int,
        default=3,
        help="synthetic drafts to generate when no candidates are given, 2-4 (default: 3)",
    )
    _add_input_path_arg(run)
    _add_record_args(run)
    _add_json_arg(run, "print the run record as JSON instead of the readable summary")

    compare = sub.add_parser(
        "compare",
        help="score existing candidate files",
        description=_wrap("Score two or more candidate files and select the best taste match."),
        epilog=TASTE_DISCOVERY_EPILOG + "\n" + INPUT_FILES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_taste_args(compare)
    _add_domain_arg(compare)
    compare.add_argument(
        "--prompt",
        default="",
        help="optional task prompt used for the +1 stays-on-brief point",
    )
    compare.add_argument(
        "--candidates",
        nargs="+",
        required=True,
        metavar="PATH",
        help="candidate files to score, in order (ties go to the earlier file)",
    )
    _add_input_path_arg(compare)
    _add_record_args(compare)
    _add_json_arg(compare, "print the run record as JSON instead of the readable summary")

    update = sub.add_parser(
        "propose-update",
        help="turn a before/after edit into a pending taste-update proposal",
        description=_wrap(
            "Diff an output before and after a human edit and write a pending taste-update "
            "proposal for review. TASTE.md itself is never modified."
        ),
        epilog=INPUT_FILES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_domain_arg(update)
    update.add_argument(
        "--before", required=True, metavar="PATH", help="file holding the output before the edit"
    )
    update.add_argument(
        "--after", required=True, metavar="PATH", help="file holding the output after the edit"
    )
    update.add_argument(
        "--output-dir",
        default=".nanotaste/taste-updates",
        metavar="DIR",
        help="directory for the proposal markdown (default: .nanotaste/taste-updates)",
    )
    _add_input_path_arg(update)
    _add_json_arg(update, "print the proposal summary as JSON")

    calibrate = sub.add_parser(
        "calibrate",
        help="prepare or evaluate a manual calibration packet",
        description=(
            "Manual calibration compares NanoTaste picks with a human reviewer's picks. "
            "Unless the prompt set supplies candidates, the drafts are synthetic output of "
            "the built-in generator, so agreement rates are a workflow smoke test, not "
            "evidence of preference alignment."
        ),
    )
    calibration_sub = calibrate.add_subparsers(
        dest="calibration_command",
        title="calibration steps",
        metavar="<step>",
        help="run 'prepare' first, then 'evaluate' once the picks file is filled in",
    )

    prepare = calibration_sub.add_parser(
        "prepare",
        help="write the review sheet, picks template, and NanoTaste run",
        description=_wrap(
            "Score each prompt-set item and write starter_run.json (NanoTaste picks), "
            "manual_review.md (candidates with scores hidden), and human_picks.json "
            "(template for the reviewer)."
        ),
        epilog=TASTE_DISCOVERY_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_taste_args(prepare)
    prepare.add_argument(
        "--prompt-set",
        required=True,
        metavar="PATH",
        help="prompt-set JSON (schema nanotaste/prompt-set/1.0); items may carry candidates",
    )
    prepare.add_argument(
        "--output-dir", required=True, metavar="DIR", help="directory for the packet files"
    )
    prepare.add_argument(
        "--candidates-per-prompt",
        type=int,
        default=3,
        metavar="N",
        help="synthetic drafts per item when the prompt set has none, 2-4 (default: 3)",
    )
    _add_json_arg(prepare, "print the written paths as JSON")

    evaluate = calibration_sub.add_parser(
        "evaluate",
        help="compare human picks to NanoTaste picks",
        description=(
            "Compare a filled human_picks.json with starter_run.json and write a markdown "
            "report plus a JSON twin. Agreement with synthetic drafts is not alignment "
            "evidence."
        ),
    )
    evaluate.add_argument(
        "--run", required=True, metavar="PATH", help="starter_run.json from 'calibrate prepare'"
    )
    evaluate.add_argument(
        "--picks", required=True, metavar="PATH", help="human_picks.json filled in by a reviewer"
    )
    evaluate.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="markdown report path; a .json report is written beside it",
    )
    _add_json_arg(evaluate, "print the evaluation as JSON")
    return parser


def _wrap(text: str) -> str:
    """Pre-wrap a description for parsers that keep their epilog raw."""
    return textwrap.fill(" ".join(text.split()), width=78)


def _add_taste_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("taste rules")
    source = group.add_mutually_exclusive_group()
    source.add_argument(
        "--taste-file",
        metavar="PATH",
        help="taste markdown file to load instead of discovering TASTE.md upward",
    )
    source.add_argument(
        "--no-taste",
        action="store_true",
        help="skip taste discovery and score with no rules (explicit baseline run)",
    )
    group.add_argument(
        "--taste-dir",
        metavar="DIR",
        help=(
            "directory holding <domain>.md rule files (default: taste/ beside the "
            "discovered or explicit taste file); relative to the working directory"
        ),
    )


def _add_domain_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--domain",
        default="general",
        help=(
            "task domain whose rules apply on top of general rules; aliases such as "
            "design, ui, python, copy are normalized (default: general)"
        ),
    )


def _add_input_path_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--allow-outside-paths",
        action="store_true",
        help="allow input files that resolve outside the working directory",
    )


def _add_record_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("run records")
    group.add_argument(
        "--record-file",
        default=".nanotaste/runs.jsonl",
        metavar="PATH",
        help=(
            "JSONL file that receives one record per run; secret-looking strings are "
            "redacted before writing (default: .nanotaste/runs.jsonl)"
        ),
    )
    group.add_argument("--no-record", action="store_true", help="do not write a run record")


def _add_json_arg(parser: argparse.ArgumentParser, help_text: str) -> None:
    parser.add_argument("--json", action="store_true", help=help_text)


def _add_workspace_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", help="project root (defaults to the current directory)")
    parser.add_argument("--home", help="home directory used for agent discovery")


def _root_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    workspace = _workspace(args)
    if not already_configured(workspace) and sys.stdin.isatty() and sys.stdout.isatty():
        print("First run: no local config yet. Starting setup.")
        return _setup(_setup_defaults(args))
    parser.print_help()
    if already_configured(workspace):
        print()
        print(_status_text(workspace))
        return 0
    print()
    print("First-run tip: nanotaste setup")
    print("Non-interactive install: nanotaste setup --yes")
    return 2


def _setup_defaults(args: argparse.Namespace) -> argparse.Namespace:
    defaults = argparse.Namespace(
        command="setup",
        workspace=getattr(args, "workspace", None),
        home=getattr(args, "home", None),
        yes=False,
        no_harvest=False,
        every="weekly",
        source=[],
        domain=[],
        seed_url=None,
        seed_file=None,
        seed_text=None,
        json=False,
    )
    return defaults


def _setup(args: argparse.Namespace) -> int:
    try:
        workspace = _workspace(args)
        result = run_setup(
            workspace,
            yes=args.yes,
            harvest=not args.no_harvest,
            frequency=args.every,
            domains=tuple(args.domain) or None,
            sources=tuple(args.source) or None,
            seed_url=args.seed_url,
            seed_file=args.seed_file,
            seed_text=args.seed_text,
            stdin=sys.stdin,
            stdout=None if args.json else sys.stdout,
        )
        record = {
            "workspace": str(result.workspace.root),
            "taste_file": str(result.taste_path),
            "enabled_sources": list(result.enabled),
            "report_frequency": result.config.report_frequency,
            "harvested": result.harvested,
            "seeded": result.seeded,
            "report": str(result.report_path) if result.report_path else None,
            "discovered": [
                {"id": source.id, "name": source.name, "present": source.present}
                for source in result.discovered
            ],
        }
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print()
            print(render_discovery(result.discovered))
            print()
            print(f"Workspace config: {result.workspace.config_path}")
            print(f"Taste file: {result.taste_path}")
            print(f"Integrated: {', '.join(result.enabled) or 'none'}")
            print(f"Reports: {result.config.report_frequency}")
            if result.report_path:
                print(f"First report: {result.report_path}")
            print()
            print("Next:")
            print("  nanotaste serve               # local studio for hierarchy, seeds, and harvest")
            print("  nanotaste seed --url URL      # seed from a personal site or note")
            print("  nanotaste harvest             # pull sessions and refresh overlays")
            print("  nanotaste schedule --every weekly --install")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Setup error", err)


def _status(args: argparse.Namespace) -> int:
    try:
        workspace = _workspace(args)
        if args.json:
            print(json.dumps(_status_record(workspace), indent=2, sort_keys=True))
        else:
            print(_status_text(workspace))
        return 0
    except (OSError, ValueError) as err:
        return _fail("Status error", err)


def _sources(args: argparse.Namespace) -> int:
    try:
        workspace = _workspace(args)
        sources = discover_sources(workspace.home, workspace.root)
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "id": source.id,
                            "name": source.name,
                            "present": source.present,
                            "paths": list(source.paths),
                            "detail": source.detail,
                            "session_files": source.session_files,
                        }
                        for source in sources
                    ],
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(render_discovery(sources))
        return 0
    except (OSError, ValueError) as err:
        return _fail("Source discovery error", err)


def _ingest(args: argparse.Namespace) -> int:
    try:
        workspace = _require_config(args)
        result = ingest_workspace(workspace)
        if args.json:
            print(json.dumps(result.to_json(), indent=2, sort_keys=True))
        else:
            print(f"Ingested {len(result.excerpts)} excerpts from {', '.join(result.enabled_sources) or 'no sources'}")
            print(f"Index: {result.index_path}")
            if result.skipped_sources:
                print(f"Skipped missing sources: {', '.join(result.skipped_sources)}")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Ingest error", err)


def _learn(args: argparse.Namespace) -> int:
    try:
        workspace = _require_config(args)
        result = learn_workspace(workspace, apply_updates=args.apply)
        record = {
            "proposal": str(result.proposal_path),
            "signals": str(result.signals_path),
            "taste_created": str(result.taste_created) if result.taste_created else None,
            "taste_applied": str(result.taste_applied) if result.taste_applied else None,
            "overlays": [str(path) for path in result.overlay_paths],
            "principles": list(result.signals.principles),
            "forbidden": list(result.signals.forbidden),
        }
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print(f"Learned proposal: {result.proposal_path}")
            for principle in result.signals.principles[:5]:
                print(f"- {safe_for_terminal(principle)}")
            if result.taste_created:
                print(f"Created taste file: {result.taste_created}")
            if result.taste_applied:
                print(f"Applied learned rules: {result.taste_applied}")
            elif not args.apply:
                print("TASTE.md was not rewritten. Re-run with --apply after review.")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Learn error", err)


def _harvest(args: argparse.Namespace) -> int:
    try:
        workspace = _require_config(args)
        ingested = ingest_workspace(workspace)
        learned = learn_workspace(workspace, apply_updates=args.apply)
        report = generate_report(workspace, if_due=args.if_due)
        record = {
            "excerpts": len(ingested.excerpts),
            "proposal": str(learned.proposal_path),
            "overlays": [str(path) for path in learned.overlay_paths],
            "report": str(report.markdown_path),
            "skipped_report": report.skipped,
        }
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print(f"Harvested {len(ingested.excerpts)} session excerpts")
            print(f"Learned proposal: {learned.proposal_path}")
            if learned.overlay_paths:
                print(f"Updated overlays: {len(learned.overlay_paths)}")
            if report.skipped:
                print("Report not due yet; skipped.")
            else:
                print(f"Report: {report.markdown_path}")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Harvest error", err)


def _like(args: argparse.Namespace) -> int:
    return _store_example(args, "like")


def _unlike(args: argparse.Namespace) -> int:
    return _store_example(args, "unlike")


def _store_example(args: argparse.Namespace, polarity: str) -> int:
    try:
        workspace = _workspace(args)
        example = add_example(workspace, args.item, polarity, args.domain, args.label)
        record = {"polarity": polarity, "path": str(example.path), "domain": example.domain}
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print(f"Stored {polarity}: {example.path}")
        return 0
    except (OSError, ValueError) as err:
        return _fail(f"{polarity.title()} error", err)


def _pick(args: argparse.Namespace) -> int:
    try:
        workspace = _workspace(args)
        candidates = list(args.candidate)
        if not candidates:
            raise ValueError("provide at least two --candidate values")
        if len(candidates) < 2:
            raise ValueError("pick needs at least two candidates")
        winner = args.choose
        if winner is None:
            winner = _interactive_choice(candidates, sys.stdin, sys.stdout)
        else:
            winner = winner - 1
        pick = record_pick(workspace, candidates, winner, args.prompt, args.domain)
        if args.json:
            print(
                json.dumps(
                    {
                        "winner_index": pick.winner_index,
                        "winner": pick.winner,
                        "rejected": list(pick.rejected),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"Preferred candidate #{pick.winner_index + 1}")
            print(safe_for_terminal(pick.winner))
        return 0
    except (OSError, ValueError) as err:
        return _fail("Pick error", err)


def _prefer(args: argparse.Namespace) -> int:
    try:
        workspace = _workspace(args)
        liked = add_example(workspace, args.like, "like", args.domain, "prefer-like")
        unliked = add_example(workspace, args.unlike, "unlike", args.domain, "prefer-unlike")
        record = {"like": str(liked.path), "unlike": str(unliked.path), "domain": args.domain}
        if args.json:
            print(json.dumps(record, indent=2, sort_keys=True))
        else:
            print(f"Liked: {liked.path}")
            print(f"Unliked: {unliked.path}")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Prefer error", err)


def _report(args: argparse.Namespace) -> int:
    try:
        workspace = _require_config(args)
        result = generate_report(workspace, if_due=args.if_due)
        if args.json:
            print(json.dumps({"path": str(result.markdown_path), "skipped": result.skipped, **result.payload}, indent=2, sort_keys=True))
        elif result.skipped:
            print("Report not due yet. Use `nanotaste report` to generate one now.")
        else:
            print(f"Report: {result.markdown_path}")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Report error", err)


def _schedule(args: argparse.Namespace) -> int:
    try:
        workspace = _require_config(args)
        path = write_schedule(workspace, args.every)
        installed = False
        if args.install:
            installed = _install_crontab(path)
        if args.json:
            print(json.dumps({"frequency": args.every, "path": str(path), "installed": installed}, indent=2, sort_keys=True))
        else:
            print(f"Session harvest frequency: {args.every}")
            print(f"Crontab snippet: {path}")
            if args.install:
                print("Crontab install: yes" if installed else "Crontab install skipped or unavailable")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Schedule error", err)


def _seed(args: argparse.Namespace) -> int:
    try:
        from nanotaste.seed import seed_workspace

        workspace = _require_config(args)
        records = []
        for url in args.url:
            records.append(seed_workspace(workspace, url=url, domain=args.domain, label=args.label))
        for path in args.file:
            records.append(
                seed_workspace(
                    workspace,
                    path=Path(path),
                    domain=args.domain,
                    label=args.label,
                    caption=args.caption,
                )
            )
        for text in args.text:
            records.append(seed_workspace(workspace, text=text, domain=args.domain, label=args.label))
        if not records:
            raise ValueError("provide --url, --file, or --text")
        payload = [item.to_json() for item in records]
        if args.json:
            print(json.dumps(payload if len(payload) > 1 else payload[0], indent=2, sort_keys=True))
        else:
            for record in records:
                print(f"Seeded {record.kind} into {record.domain}: {record.label}")
                print(safe_for_terminal(record.excerpt[:240]))
        return 0
    except (OSError, ValueError) as err:
        return _fail("Seed error", err)


def _catalog(args: argparse.Namespace) -> int:
    try:
        from nanotaste.catalog import catalog_payload, install_hierarchy

        workspace = _workspace(args)
        install_hierarchy(workspace)
        payload = catalog_payload(workspace)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for node in payload["nodes"]:
                flag = "yes" if node["exists"] else "no"
                tags = ",".join(node["tags"])
                print(f"{node['title']:<28} {node['kind']:<10} {flag:<4} {node['rule_count']:>3}  {tags}")
        return 0
    except (OSError, ValueError) as err:
        return _fail("Catalog error", err)


def _serve(args: argparse.Namespace) -> int:
    try:
        from nanotaste.webapp import serve_workspace

        workspace = _workspace(args)
        server = serve_workspace(workspace, host=args.host, port=args.port, tick=not args.no_tick)
        print(f"Taste studio: http://{args.host}:{server.server_address[1]}")
        print("This is the local app, not the marketing site in website/.")
        server.serve_forever()
        return 0
    except (OSError, ValueError, KeyboardInterrupt) as err:
        if isinstance(err, KeyboardInterrupt):
            return 0
        return _fail("Studio error", err)


def _install_crontab(snippet_path: Path) -> bool:
    import subprocess

    try:
        current = subprocess.run(["crontab", "-l"], check=False, capture_output=True, text=True)
        existing = current.stdout if current.returncode == 0 else ""
        addition = snippet_path.read_text(encoding="utf-8")
        if addition.strip() in existing:
            return True
        merged = existing.rstrip() + "\n" + addition
        installed = subprocess.run(["crontab", "-"], input=merged, check=False, capture_output=True, text=True)
        return installed.returncode == 0
    except OSError:
        return False


def _run(args: argparse.Namespace) -> int:
    try:
        agent = _load_agent(args)
        candidates = list(args.candidate)
        candidates.extend(
            _read_text_arg(path, args.allow_outside_paths, "candidate file")
            for path in args.candidate_file
        )
        if candidates:
            result = agent.compare(candidates, args.domain, args.prompt)
        else:
            result = agent.run(args.prompt, args.domain, args.count)
        record = result.to_record(args.prompt)
        if args.candidate_file:
            record["candidate_files"] = list(args.candidate_file)
        _note_taste_sources(args, result)
        if not args.no_record:
            append_record(Path(args.record_file), record)
        _print_result(record, args.json)
        return 0
    except (OSError, ValueError) as err:
        _report_input_error("Input error", err)
        return 1


def _compare(args: argparse.Namespace) -> int:
    try:
        agent = _load_agent(args)
        candidates = [
            _read_text_arg(path, args.allow_outside_paths, "candidate file")
            for path in args.candidates
        ]
        result = agent.compare(candidates, args.domain, args.prompt)
        record = result.to_record(args.prompt)
        record["candidate_files"] = args.candidates
        _note_taste_sources(args, result)
        if not args.no_record:
            append_record(Path(args.record_file), record)
        _print_result(record, args.json)
        return 0
    except (OSError, ValueError) as err:
        _report_input_error("Input error", err)
        return 1


def _propose_update(args: argparse.Namespace) -> int:
    agent = TasteAgent.from_paths()
    before_path = Path(args.before)
    after_path = Path(args.after)
    try:
        before = _read_text_arg(before_path, args.allow_outside_paths, "before file")
        after = _read_text_arg(after_path, args.allow_outside_paths, "after file")
        proposal, output_path = agent.propose_update(
            before, after, args.domain, Path(args.output_dir), before_path.stem
        )
    except (OSError, ValueError) as err:
        _report_input_error("Input error", err)
        return 1
    record = {
        "domain": args.domain,
        "proposal_file": str(output_path),
        "added_lines": list(proposal.added_lines),
        "removed_lines": list(proposal.removed_lines),
    }
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"Proposal written: {output_path}")
        print(safe_for_terminal(proposal.markdown))
    return 0


def _calibrate(args: argparse.Namespace) -> int:
    if args.calibration_command == "prepare":
        return _calibrate_prepare(args)
    if args.calibration_command == "evaluate":
        return _calibrate_evaluate(args)
    print("Usage: nanotaste calibrate {prepare,evaluate}", file=sys.stderr)
    return 2


def _calibrate_prepare(args: argparse.Namespace) -> int:
    try:
        agent = _load_agent(args)
        paths = prepare_calibration(
            Path(args.prompt_set),
            Path(args.output_dir),
            agent,
            args.candidates_per_prompt,
        )
    except (OSError, ValueError) as err:
        _report_input_error("Calibration input error", err)
        return 1
    record = {key: str(path) for key, path in paths.items()}
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(f"Review sheet: {paths['review']}")
        print(f"Human picks: {paths['picks']}")
        print(f"NanoTaste run: {paths['run']}")
    return 0


def _calibrate_evaluate(args: argparse.Namespace) -> int:
    try:
        evaluation = write_evaluation(Path(args.run), Path(args.picks), Path(args.output))
    except (OSError, ValueError) as err:
        _report_input_error("Calibration input error", err)
        return 1
    if args.json:
        print(json.dumps(evaluation, indent=2, sort_keys=True))
    else:
        accuracy = evaluation["accuracy"]
        text = "pending" if accuracy is None else f"{accuracy:.1%}"
        print(f"Labeled: {evaluation['labeled_items']} / {evaluation['total_items']}")
        print(f"Accuracy: {text}")
        print(f"Report: {args.output}")
    return 0


def _load_agent(args: argparse.Namespace) -> TasteAgent:
    return TasteAgent.from_paths(
        Path.cwd(),
        Path(args.taste_file) if getattr(args, "taste_file", None) else None,
        Path(args.taste_dir) if getattr(args, "taste_dir", None) else None,
        no_taste=bool(getattr(args, "no_taste", False)),
    )


def _workspace(args: argparse.Namespace) -> TasteWorkspace:
    root = Path(args.workspace) if getattr(args, "workspace", None) else None
    home = Path(args.home) if getattr(args, "home", None) else None
    return resolve_workspace(root, home)


def _require_config(args: argparse.Namespace) -> TasteWorkspace:
    workspace = _workspace(args)
    if not config_exists(workspace):
        raise ValueError("no local setup yet; run `nanotaste setup` first")
    return workspace


def _status_record(workspace: TasteWorkspace) -> dict[str, Any]:
    configured = config_exists(workspace)
    record: dict[str, Any] = {
        "workspace": str(workspace.root),
        "configured": configured,
        "config_path": str(workspace.config_path),
    }
    if not configured:
        return record
    config = load_config(workspace)
    due = next_report_due(config)
    record.update(
        {
            "taste_file": str(workspace.taste_path(config)),
            "enabled_sources": list(config.enabled_sources),
            "report_frequency": config.report_frequency,
            "last_ingest_at": config.last_ingest_at,
            "last_learn_at": config.last_learn_at,
            "last_report_at": config.last_report_at,
            "report_due": report_is_due(config),
            "next_report_due": due.isoformat() if due else None,
        }
    )
    return record


def _status_text(workspace: TasteWorkspace) -> str:
    record = _status_record(workspace)
    if not record["configured"]:
        return f"Workspace {record['workspace']} is not set up. Run `nanotaste setup`."
    return "\n".join(
        [
            f"Workspace: {record['workspace']}",
            f"Taste file: {record['taste_file']}",
            f"Integrated sources: {', '.join(record['enabled_sources']) or 'none'}",
            f"Report frequency: {record['report_frequency']}",
            f"Last harvest ingest: {record['last_ingest_at'] or 'never'}",
            f"Last learn pass: {record['last_learn_at'] or 'never'}",
            f"Last report: {record['last_report_at'] or 'never'}",
            f"Report due now: {'yes' if record['report_due'] else 'no'}",
        ]
    )


def _interactive_choice(candidates: list[str], stdin: TextIO, stdout: TextIO) -> int:
    for index, candidate in enumerate(candidates, start=1):
        stdout.write(f"[{index}] {safe_for_terminal(candidate)}\n")
    stdout.write("Pick the option you prefer: ")
    stdout.flush()
    if not stdin.isatty():
        raise ValueError("non-interactive pick requires --choose")
    raw = stdin.readline().strip()
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(candidates):
            return index
    raise ValueError("choose a listed candidate number")


def _read_text_arg(path: str | Path, allow_outside: bool, label: str) -> str:
    """Read an operator-supplied text file, confined to the working directory by default."""
    root = None if allow_outside else Path.cwd()
    try:
        return safe_read_text(
            Path(path),
            root=root,
            limit_bytes=MAX_CANDIDATE_FILE_BYTES,
            label=label,
        )
    except RootEscapeError as err:
        raise SecurityInputError(f"{err}. {OUTSIDE_PATH_HINT}") from err


def _report_input_error(prefix: str, err: Exception) -> None:
    message = str(err)
    if isinstance(err, TasteFileNotFoundError):
        message = f"{message}. {MISSING_TASTE_HINT}"
    print(f"{prefix}: {safe_for_terminal(message)}", file=sys.stderr)


def _note_taste_sources(args: argparse.Namespace, result: SelectionResult) -> None:
    """Warn on stderr when discovered taste rules come from outside the working directory."""
    if args.taste_file or not result.taste_sources:
        return
    cwd = Path.cwd().resolve()
    allowed_roots = [cwd]
    if args.taste_dir:
        allowed_roots.append(resolve_taste_dir(cwd, Path(args.taste_dir)))
    outside = [
        str(path)
        for path in result.taste_sources
        if not any(path.is_relative_to(root) for root in allowed_roots)
    ]
    if outside:
        print(
            "Note: taste rules were discovered outside the working directory: "
            f"{safe_for_terminal(', '.join(outside))}. Pass --taste-file to choose explicitly.",
            file=sys.stderr,
        )


def _print_result(record: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(record, indent=2, sort_keys=True))
        return
    selected = cast(dict[str, Any], record["selected_candidate"])
    rejected = cast(list[dict[str, Any]], record["rejected_candidates"])
    tied = [str(item["index"]) for item in rejected if item["score"] == selected["score"]]
    header = f"Selected candidate #{selected['index']} (score {selected['score']}"
    if tied:
        header += f"; tied with #{', #'.join(tied)}, earlier candidate wins"
    print(header + ")")
    for reason in selected["reasons"]:
        print(f"- {safe_for_terminal(str(reason))}")
    print()
    print(safe_for_terminal(str(selected["text"])))


def _fail(label: str, err: Exception) -> int:
    print(f"{label}: {safe_for_terminal(str(err))}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
