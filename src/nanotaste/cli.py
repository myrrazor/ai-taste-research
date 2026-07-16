"""Command-line interface for NanoTaste."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from nanotaste.agent import TasteAgent
from nanotaste.calibration import prepare_calibration, write_evaluation
from nanotaste.records import append_record
from nanotaste.security import MAX_CANDIDATE_FILE_BYTES, safe_for_terminal, safe_read_text


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
    parser = argparse.ArgumentParser(prog="nanotaste")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="generate or score candidate outputs")
    _add_taste_args(run)
    run.add_argument("--domain", default="general")
    run.add_argument("--prompt", required=True)
    run.add_argument("--candidate", action="append", default=[])
    run.add_argument("--count", type=int, default=3)
    run.add_argument("--record-file", default=".nanotaste/runs.jsonl")
    run.add_argument("--no-record", action="store_true")
    run.add_argument("--json", action="store_true")

    compare = sub.add_parser("compare", help="score existing candidate files")
    _add_taste_args(compare)
    compare.add_argument("--domain", default="general")
    compare.add_argument("--prompt", default="")
    compare.add_argument("--candidates", nargs="+", required=True)
    compare.add_argument("--record-file", default=".nanotaste/runs.jsonl")
    compare.add_argument("--no-record", action="store_true")
    compare.add_argument("--json", action="store_true")

    update = sub.add_parser("propose-update", help="propose taste updates from edits")
    update.add_argument("--domain", default="general")
    update.add_argument("--before", required=True)
    update.add_argument("--after", required=True)
    update.add_argument("--output-dir", default=".nanotaste/taste-updates")
    update.add_argument("--json", action="store_true")

    calibrate = sub.add_parser("calibrate", help="prepare or evaluate manual calibration")
    calibration_sub = calibrate.add_subparsers(dest="calibration_command")

    prepare = calibration_sub.add_parser("prepare", help="create human review files")
    _add_taste_args(prepare)
    prepare.add_argument("--prompt-set", required=True)
    prepare.add_argument("--output-dir", required=True)
    prepare.add_argument("--candidates-per-prompt", type=int, default=3)
    prepare.add_argument("--json", action="store_true")

    evaluate = calibration_sub.add_parser("evaluate", help="compare human picks to NanoTaste")
    evaluate.add_argument("--run", required=True)
    evaluate.add_argument("--picks", required=True)
    evaluate.add_argument("--output", required=True)
    evaluate.add_argument("--json", action="store_true")
    return parser


def _add_taste_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--taste-file")
    parser.add_argument("--taste-dir")


def _run(args: argparse.Namespace) -> int:
    try:
        agent = _load_agent(args)
        if args.candidate:
            result = agent.compare(args.candidate, args.domain, args.prompt)
        else:
            result = agent.run(args.prompt, args.domain, args.count)
        record = result.to_record(args.prompt)
        if not args.no_record:
            append_record(Path(args.record_file), record)
        _print_result(record, args.json)
        return 0
    except (OSError, ValueError) as err:
        print(f"Input error: {safe_for_terminal(str(err))}", file=sys.stderr)
        return 1


def _compare(args: argparse.Namespace) -> int:
    agent = _load_agent(args)
    try:
        candidates = [_read_text_arg(path) for path in args.candidates]
        result = agent.compare(candidates, args.domain, args.prompt)
        record = result.to_record(args.prompt)
        record["candidate_files"] = args.candidates
        if not args.no_record:
            append_record(Path(args.record_file), record)
        _print_result(record, args.json)
        return 0
    except (OSError, ValueError) as err:
        print(f"Input error: {safe_for_terminal(str(err))}", file=sys.stderr)
        return 1


def _propose_update(args: argparse.Namespace) -> int:
    agent = TasteAgent.from_paths()
    before_path = Path(args.before)
    after_path = Path(args.after)
    try:
        before = _read_text_arg(before_path)
        after = _read_text_arg(after_path)
        proposal, output_path = agent.propose_update(
            before, after, args.domain, Path(args.output_dir), before_path.stem
        )
    except (OSError, ValueError) as err:
        print(f"Input error: {safe_for_terminal(str(err))}", file=sys.stderr)
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
    agent = _load_agent(args)
    try:
        paths = prepare_calibration(
            Path(args.prompt_set),
            Path(args.output_dir),
            agent,
            args.candidates_per_prompt,
        )
    except (OSError, ValueError) as err:
        print(f"Calibration input error: {safe_for_terminal(str(err))}", file=sys.stderr)
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
        print(f"Calibration input error: {safe_for_terminal(str(err))}", file=sys.stderr)
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
    )


def _read_text_arg(path: str | Path) -> str:
    return safe_read_text(
        Path(path),
        limit_bytes=MAX_CANDIDATE_FILE_BYTES,
        label="input file",
    )


def _print_result(record: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(record, indent=2, sort_keys=True))
        return
    selected = cast(dict[str, Any], record["selected_candidate"])
    print(f"Selected candidate #{selected['index']} (score {selected['score']})")
    for reason in selected["reasons"]:
        print(f"- {safe_for_terminal(str(reason))}")
    print()
    print(safe_for_terminal(str(selected["text"])))


if __name__ == "__main__":
    raise SystemExit(main())
