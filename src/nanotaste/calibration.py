"""Calibration workflow for comparing NanoTaste picks to human picks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from nanotaste.agent import TasteAgent
from nanotaste.security import (
    MAX_CALIBRATION_RUN_BYTES,
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATES_PER_PROMPT,
    MAX_HUMAN_PICKS_BYTES,
    MAX_PROMPT_BYTES,
    MAX_PROMPT_ITEMS,
    MAX_PROMPT_SET_BYTES,
    atomic_write_text,
    safe_json_loads,
    safe_read_text,
    validate_text_limit,
)

CANDIDATE_IDS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


class CalibrationInputError(ValueError):
    """Raised when human calibration picks cannot be evaluated safely."""


@dataclass(frozen=True)
class CalibrationCandidate:
    """One candidate shown to the human reviewer."""

    id: str
    text: str


@dataclass(frozen=True)
class CalibrationItem:
    """One prompt and its candidate outputs."""

    id: str
    domain: str
    prompt: str
    candidates: tuple[CalibrationCandidate, ...]


def load_prompt_set(path: Path) -> list[dict[str, Any]]:
    """Load a prompt-set JSON file."""
    data = safe_json_loads(
        safe_read_text(path, limit_bytes=MAX_PROMPT_SET_BYTES, label="prompt set"),
        "prompt set",
    )
    if not isinstance(data, dict):
        raise ValueError("prompt set must be a JSON object")
    if data.get("schema") != "nanotaste/prompt-set/1.0":
        raise ValueError("unsupported prompt set schema")
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError("prompt set items must be a list")
    if len(items) > MAX_PROMPT_ITEMS:
        raise ValueError(f"prompt set has too many items: {len(items)} > {MAX_PROMPT_ITEMS}")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"prompt item #{index} must be an object")
        for field in ("id", "domain", "prompt"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"prompt item #{index} missing string {field}")
        validate_text_limit(item["prompt"], MAX_PROMPT_BYTES, f"prompt item {item['id']!r} prompt")
        if "candidates" in item:
            candidates = item["candidates"]
            if not isinstance(candidates, list) or len(candidates) < 2:
                raise ValueError(f"{item['id']}: candidates must contain at least two items")
            if len(candidates) > MAX_CANDIDATES_PER_PROMPT:
                raise ValueError(
                    f"{item['id']}: too many candidates: {len(candidates)} > {MAX_CANDIDATES_PER_PROMPT}"
                )
            for candidate_index, candidate in enumerate(candidates, start=1):
                if isinstance(candidate, dict):
                    if not isinstance(candidate.get("text"), str) or not candidate["text"].strip():
                        raise ValueError(
                            f"{item['id']}: candidate #{candidate_index} missing string text"
                        )
                    validate_text_limit(
                        candidate["text"],
                        MAX_CANDIDATE_BYTES,
                        f"{item['id']} candidate #{candidate_index}",
                    )
                elif not isinstance(candidate, str) or not candidate.strip():
                    raise ValueError(f"{item['id']}: candidate #{candidate_index} must be text")
                else:
                    validate_text_limit(
                        candidate,
                        MAX_CANDIDATE_BYTES,
                        f"{item['id']} candidate #{candidate_index}",
                    )
    return items


def prepare_calibration(
    prompt_set: Path,
    output_dir: Path,
    agent: TasteAgent,
    candidates_per_prompt: int = 3,
) -> dict[str, Path]:
    """Generate candidates, machine picks, review sheet, and pick template."""
    prompts = load_prompt_set(prompt_set)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_items: list[dict[str, Any]] = []
    review_items: list[CalibrationItem] = []
    picks = []
    for item in prompts:
        context = agent.router.resolve(item["domain"])
        generated = _item_candidates(item)
        if generated is None:
            generated = agent.generator.generate(item["prompt"], context, candidates_per_prompt)
        rotated = _rotate_candidates(generated, item["id"])
        result = agent.critic.select(rotated, context, item["prompt"])
        if len(result.all_scores) > len(CANDIDATE_IDS):
            raise ValueError(f"{item['id']}: too many candidates for available labels")
        candidates = [
            CalibrationCandidate(id=CANDIDATE_IDS[i], text=scored.text)
            for i, scored in enumerate(result.all_scores)
        ]
        winner = CANDIDATE_IDS[result.selected.index]
        run_items.append(
            {
                "id": item["id"],
                "domain": result.domain,
                "prompt": item["prompt"],
                "taste_hash": result.taste_hash,
                "nanotaste_winner": winner,
                "scores": [
                    {
                        "candidate_id": CANDIDATE_IDS[scored.index],
                        "score": scored.score,
                        "reasons": list(scored.reasons),
                    }
                    for scored in result.all_scores
                ],
                "candidates": [
                    {"id": candidate.id, "text": candidate.text}
                    for candidate in candidates
                ],
            }
        )
        review_items.append(
            CalibrationItem(
                id=item["id"],
                domain=result.domain,
                prompt=item["prompt"],
                candidates=tuple(candidates),
            )
        )
        picks.append({"item_id": item["id"], "winner": "", "notes": ""})

    run_path = output_dir / "starter_run.json"
    review_path = output_dir / "manual_review.md"
    picks_path = output_dir / "human_picks.json"
    atomic_write_text(
        run_path,
        json.dumps(
            {
                "schema": "nanotaste/calibration-run/1.0",
                "generated_at": _now(),
                "items": run_items,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        label="calibration run",
    )
    atomic_write_text(review_path, render_review_markdown(review_items), label="review sheet")
    atomic_write_text(
        picks_path,
        json.dumps(
            {
                "schema": "nanotaste/human-picks/1.0",
                "instructions": "Fill winner with one of the candidate IDs shown for each item. Leave blank until picked.",
                "picks": picks,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        label="human picks template",
    )
    return {"run": run_path, "review": review_path, "picks": picks_path}


def render_review_markdown(items: list[CalibrationItem]) -> str:
    """Render a bias-resistant manual review sheet."""
    lines = [
        "# NanoTaste Manual Calibration Review",
        "",
        "Pick the candidate you actually prefer for each prompt. Do not try to guess NanoTaste's pick; this sheet intentionally hides scores and model winners.",
        "",
        "Candidate order is rotated per prompt so the weaker draft is not always Candidate A.",
        "",
        "Write your choices in `human_picks.json` using the candidate IDs shown for each item.",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item.id}",
                "",
                f"- Domain: `{item.domain}`",
                f"- Prompt: {item.prompt}",
                "",
            ]
        )
        for candidate in item.candidates:
            lines.extend([f"### Candidate {candidate.id}", "", candidate.text, ""])
    return "\n".join(lines).rstrip() + "\n"


def evaluate_calibration(run_path: Path, picks_path: Path) -> dict[str, Any]:
    """Compare human picks against NanoTaste winners."""
    run = safe_json_loads(
        safe_read_text(run_path, limit_bytes=MAX_CALIBRATION_RUN_BYTES, label="calibration run"),
        "calibration run",
    )
    picks = safe_json_loads(
        safe_read_text(picks_path, limit_bytes=MAX_HUMAN_PICKS_BYTES, label="human picks"),
        "human picks",
    )
    _validate_run_shape(run)
    _validate_picks_shape(picks)
    pick_map = _validated_pick_map(run.get("items", []), picks.get("picks", []))
    rows = []
    domain_stats: dict[str, dict[str, int]] = {}
    for item in run.get("items", []):
        human = pick_map.get(item["id"], "")
        machine = item["nanotaste_winner"]
        labeled = human in CANDIDATE_IDS
        match = labeled and human == machine
        stats = domain_stats.setdefault(item["domain"], {"labeled": 0, "matches": 0})
        if labeled:
            stats["labeled"] += 1
            stats["matches"] += int(match)
        rows.append(
            {
                "id": item["id"],
                "domain": item["domain"],
                "human_winner": human,
                "nanotaste_winner": machine,
                "match": match if labeled else None,
            }
        )

    labeled_count = sum(1 for row in rows if row["match"] is not None)
    matches = sum(1 for row in rows if row["match"] is True)
    return {
        "schema": "nanotaste/calibration-evaluation/1.0",
        "evaluated_at": _now(),
        "total_items": len(rows),
        "labeled_items": labeled_count,
        "matches": matches,
        "accuracy": matches / labeled_count if labeled_count else None,
        "by_domain": {
            domain: {
                **stats,
                "accuracy": stats["matches"] / stats["labeled"] if stats["labeled"] else None,
            }
            for domain, stats in sorted(domain_stats.items())
        },
        "items": rows,
    }


def render_evaluation_markdown(evaluation: dict[str, Any]) -> str:
    """Render a human-readable evaluation report."""
    accuracy = evaluation["accuracy"]
    accuracy_text = "pending" if accuracy is None else f"{accuracy:.1%}"
    lines = [
        "# NanoTaste Calibration Evaluation",
        "",
        f"- Labeled items: {evaluation['labeled_items']} / {evaluation['total_items']}",
        f"- Matches: {evaluation['matches']}",
        f"- Accuracy: {accuracy_text}",
        "",
        "## By Domain",
        "",
        "| Domain | Labeled | Matches | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for domain, stats in evaluation["by_domain"].items():
        domain_accuracy = stats["accuracy"]
        domain_text = "pending" if domain_accuracy is None else f"{domain_accuracy:.1%}"
        lines.append(f"| {domain} | {stats['labeled']} | {stats['matches']} | {domain_text} |")
    lines.extend(["", "## Items", "", "| ID | Domain | Human | NanoTaste | Match |", "|---|---|---|---|---|"])
    for item in evaluation["items"]:
        match = "pending" if item["match"] is None else ("yes" if item["match"] else "no")
        lines.append(
            f"| {item['id']} | {item['domain']} | {item['human_winner'] or '-'} | {item['nanotaste_winner']} | {match} |"
        )
    return "\n".join(lines) + "\n"


def write_evaluation(run_path: Path, picks_path: Path, output_path: Path) -> dict[str, Any]:
    """Write calibration evaluation JSON and markdown report."""
    evaluation = evaluate_calibration(run_path, picks_path)
    atomic_write_text(output_path, render_evaluation_markdown(evaluation), label="evaluation report")
    json_path = output_path.with_suffix(".json")
    atomic_write_text(
        json_path,
        json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
        label="evaluation json",
    )
    return evaluation


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rotate_candidates(candidates: list[str], item_id: str) -> list[str]:
    if not candidates:
        return candidates
    offset = int(sha256(item_id.encode("utf-8")).hexdigest()[:4], 16) % len(candidates)
    return candidates[offset:] + candidates[:offset]


def _item_candidates(item: dict[str, Any]) -> list[str] | None:
    candidates = item.get("candidates")
    if candidates is None:
        return None
    result = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            result.append(candidate["text"])
        else:
            result.append(str(candidate))
    return result


def _validate_run_shape(run: dict[str, Any]) -> None:
    if not isinstance(run, dict):
        raise CalibrationInputError("calibration run must be a JSON object")
    if run.get("schema") != "nanotaste/calibration-run/1.0":
        raise CalibrationInputError("unsupported calibration run schema")
    items = run.get("items", [])
    if not isinstance(items, list):
        raise CalibrationInputError("calibration run items must be a list")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise CalibrationInputError(f"run item #{index} must be an object")
        for field in ("id", "domain", "prompt", "nanotaste_winner", "candidates"):
            if field not in item:
                raise CalibrationInputError(f"run item #{index} missing {field}")
        for field in ("id", "domain", "prompt", "nanotaste_winner"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise CalibrationInputError(f"run item #{index} missing string {field}")
        if not isinstance(item["candidates"], list) or not item["candidates"]:
            raise CalibrationInputError(f"run item {item['id']!r} has no candidates")
        for candidate_index, candidate in enumerate(item["candidates"], start=1):
            if (
                not isinstance(candidate, dict)
                or not isinstance(candidate.get("id"), str)
                or not candidate["id"].strip()
            ):
                raise CalibrationInputError(
                    f"run item {item['id']!r} candidate #{candidate_index} missing id"
                )


def _validate_picks_shape(picks: dict[str, Any]) -> None:
    if not isinstance(picks, dict):
        raise CalibrationInputError("human picks must be a JSON object")
    if picks.get("schema") != "nanotaste/human-picks/1.0":
        raise CalibrationInputError("unsupported human picks schema")
    if not isinstance(picks.get("picks", []), list):
        raise CalibrationInputError("human picks must contain a picks list")


def _validated_pick_map(
    run_items: list[dict[str, Any]], picks: list[dict[str, Any]]
) -> dict[str, str]:
    valid_by_item = {
        item["id"]: {candidate["id"] for candidate in item.get("candidates", [])}
        for item in run_items
    }
    seen: dict[str, str] = {}
    errors: list[str] = []
    for index, pick in enumerate(picks, start=1):
        if not isinstance(pick, dict):
            errors.append(f"pick #{index} must be an object")
            continue
        item_id = pick.get("item_id", "")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"pick #{index} missing string item_id")
            continue
        if item_id not in valid_by_item:
            errors.append(f"pick #{index} references unknown item_id {item_id!r}")
            continue
        if item_id in seen:
            errors.append(f"duplicate pick for item_id {item_id!r}")
            continue
        raw_winner = pick.get("winner", "")
        if not isinstance(raw_winner, str):
            errors.append(f"{item_id}: winner must be a string")
            continue
        winner = raw_winner.strip().upper()
        if winner and winner not in valid_by_item[item_id]:
            allowed = ", ".join(sorted(valid_by_item[item_id]))
            errors.append(f"{item_id}: winner {winner!r} is not one of {allowed}")
            continue
        seen[item_id] = winner
    if errors:
        raise CalibrationInputError("; ".join(errors))
    return seen
