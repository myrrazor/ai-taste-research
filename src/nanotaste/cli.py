"""Command-line interface for NanoTaste."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

from nanotaste import __version__
from nanotaste.agent import TasteAgent
from nanotaste.calibration import prepare_calibration, write_evaluation
from nanotaste.discovery import TasteFileNotFoundError, resolve_taste_dir
from nanotaste.records import append_record
from nanotaste.scoring import SelectionResult
from nanotaste.security import (
    MAX_CANDIDATE_FILE_BYTES,
    RootEscapeError,
    SecurityInputError,
    safe_for_terminal,
    safe_read_text,
)

DESCRIPTION = (
    "Compare candidate outputs against a markdown taste file (TASTE.md) with a "
    "deterministic, lexical critic, and record the decision locally."
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
    if args.command == "run":
        return _run(args)
    if args.command == "compare":
        return _compare(args)
    if args.command == "propose-update":
        return _propose_update(args)
    if args.command == "calibrate":
        if args.calibration_command == "prepare":
            return _calibrate_prepare(args)
        if args.calibration_command == "evaluate":
            return _calibrate_evaluate(args)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nanotaste",
        description=DESCRIPTION,
        epilog="Run 'nanotaste <command> --help' for the options of one command.",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="<command>",
        help="one of the commands below",
    )

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


if __name__ == "__main__":
    raise SystemExit(main())
