"""Acyclic review derivation and crash-safe terminal finalization."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from nanotaste.rc0.canonical import canonical_bytes, content_digest
from nanotaste.rc0.contracts import SCHEMAS, seal_record, validate_record
from nanotaste.rc0.control import validate_acyclic_graph
from nanotaste.rc0.invariants import EXPECTED_INVARIANT_DIGEST, load_invariant_manifest
from nanotaste.rc0.storage import StorageError, atomic_write_json, read_json

CANDIDATE_SCHEMA = SCHEMAS[16]
REVIEW_SCHEMA = SCHEMAS[17]
AGGREGATE_SCHEMA = SCHEMAS[18]
FINAL_PAYLOAD_SCHEMA = SCHEMAS[19]
DETACHED_SCHEMA = SCHEMAS[20]
TRANSITION_SCHEMA = SCHEMAS[21]
DERIVATION_SCHEMA = SCHEMAS[22]

VERDICTS = {
    "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST",
    "NO_GO",
    "HUMAN_INPUT_REQUIRED",
}
CRITERION_F = {
    "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST": "PASS",
    "NO_GO": "FAIL",
    "HUMAN_INPUT_REQUIRED": "BLOCKED",
}
AGGREGATE_BY_VERDICT = {
    "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST": "READY_FOR_PACKET_FINALIZATION",
    "NO_GO": "NO_GO_CANDIDATE",
    "HUMAN_INPUT_REQUIRED": "HUMAN_INPUT_REQUIRED_CANDIDATE",
}
TERMINAL_BY_AGGREGATE = {
    "READY_FOR_PACKET_FINALIZATION": "RELEASE_READY_PRIVATE",
    "NO_GO_CANDIDATE": "NO_GO_PRIVATE",
    "HUMAN_INPUT_REQUIRED_CANDIDATE": "HUMAN_INPUT_REQUIRED_PRIVATE",
}
FINALIZATION_NODES = (
    "criterion_f",
    "aggregate_candidate",
    "final_packet_payload",
    "detached_digest",
    "terminal_transition",
    "terminal_state",
)
FINALIZATION_EDGES = (
    ("criterion_f", "aggregate_candidate"),
    ("aggregate_candidate", "final_packet_payload"),
    ("final_packet_payload", "detached_digest"),
    ("detached_digest", "terminal_transition"),
    ("terminal_transition", "terminal_state"),
)
TERMINAL_POINTER_SCHEMA = "nanotaste/rc0-terminal-state-pointer/1.0"


class FinalizationError(ValueError):
    """Raised when review or terminal state would violate the acyclic contract."""


def build_candidate_packet(
    *,
    attempt_id: str,
    criteria: dict[str, str],
    release_sha: str,
    evidence_digests: dict[str, str],
    unresolved_findings: list[str],
    tool_versions: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    """Freeze A-E only, including every schema, algorithm, and tool version."""
    if set(criteria) != set("ABCDE"):
        raise FinalizationError("candidate packet must contain criteria A through E only")
    if any(value not in {"PASS", "FAIL", "BLOCKED"} for value in criteria.values()):
        raise FinalizationError("candidate criteria use an unsupported state")
    required_tools = {"nanotaste", "python", "gstack"}
    if not required_tools <= set(tool_versions):
        raise FinalizationError("candidate packet lacks required tool versions")
    manifest = load_invariant_manifest()
    return seal_record(
        CANDIDATE_SCHEMA,
        attempt_id,
        {
            "criteria": deepcopy(criteria),
            "release_sha": release_sha,
            "evidence_digests": deepcopy(evidence_digests),
            "unresolved_findings": list(unresolved_findings),
            "schema_versions": list(manifest["contract_schemas"]),
            "algorithm_versions": deepcopy(manifest["versions"]),
            "tool_versions": deepcopy(tool_versions),
        },
        created_at,
    )


def build_review_result(
    candidate: dict[str, Any],
    *,
    verdict: str,
    findings: list[dict[str, str]],
    reviewer: str,
    tool_versions: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    """Bind one explicit review verdict to the immutable A-E packet."""
    validate_record(candidate)
    if candidate["schema"] != CANDIDATE_SCHEMA:
        raise FinalizationError("review input is not a candidate packet")
    if verdict not in VERDICTS:
        raise FinalizationError("review verdict is unsupported")
    if verdict == "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST":
        if set(candidate["payload"]["criteria"].values()) != {"PASS"}:
            raise FinalizationError("conditional-go requires A-E all PASS")
        if candidate["payload"]["unresolved_findings"]:
            raise FinalizationError("conditional-go cannot carry unresolved findings")
    return seal_record(
        REVIEW_SCHEMA,
        candidate["attempt_id"],
        {
            "candidate_packet_digest": candidate["digest"],
            "verdict": verdict,
            "findings": deepcopy(findings),
            "reviewer": reviewer,
            "reviewed_at": created_at,
            "tool_versions": deepcopy(tool_versions),
        },
        created_at,
    )


def derive_criterion_f(
    candidate: dict[str, Any], review: dict[str, Any], created_at: str
) -> dict[str, Any]:
    """Derive F after review; caller-supplied or truthy verdicts are impossible."""
    validate_record(candidate)
    validate_record(review)
    if review["payload"]["candidate_packet_digest"] != candidate["digest"]:
        raise FinalizationError("review references another candidate packet")
    verdict = review["payload"]["verdict"]
    if verdict not in CRITERION_F:
        raise FinalizationError("review verdict cannot derive criterion F")
    edges = [
        ["criteria_a_e", "candidate_packet"],
        ["candidate_packet", "review_verdict"],
        ["review_verdict", "criterion_f"],
    ]
    validate_acyclic_graph(
        ("criteria_a_e", "candidate_packet", "review_verdict", "criterion_f"),
        ((source, target) for source, target in edges),
    )
    return seal_record(
        DERIVATION_SCHEMA,
        candidate["attempt_id"],
        {
            "edges": edges,
            "candidate_packet_digest": candidate["digest"],
            "review_record_digest": review["digest"],
            "verdict": verdict,
            "criterion_f": CRITERION_F[verdict],
            "algorithm_version": "nanotaste-review-derivation/1",
        },
        created_at,
    )


def derive_aggregate_candidate(
    candidate: dict[str, Any],
    review: dict[str, Any],
    derivation: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Derive the immutable provisional aggregate without reading a final digest."""
    for record in (candidate, review, derivation):
        validate_record(record)
    verdict = review["payload"]["verdict"]
    if derivation["payload"]["verdict"] != verdict:
        raise FinalizationError("criterion F derivation and review verdict differ")
    if derivation["payload"]["candidate_packet_digest"] != candidate["digest"]:
        raise FinalizationError("criterion F derivation references another candidate")
    if derivation["payload"]["review_record_digest"] != review["digest"]:
        raise FinalizationError("criterion F derivation references another review")
    criterion_f = derivation["payload"]["criterion_f"]
    if criterion_f != CRITERION_F[verdict]:
        raise FinalizationError("criterion F does not follow the fixed verdict mapping")
    criteria = {**candidate["payload"]["criteria"], "F": criterion_f}
    return seal_record(
        AGGREGATE_SCHEMA,
        candidate["attempt_id"],
        {
            "criteria": criteria,
            "verdict": verdict,
            "criterion_f": criterion_f,
            "candidate": AGGREGATE_BY_VERDICT[verdict],
            "derivation_algorithm_version": "nanotaste-review-derivation/1",
        },
        created_at,
    )


def build_final_packet_payload(
    candidate: dict[str, Any],
    review: dict[str, Any],
    aggregate: dict[str, Any],
    *,
    evidence_manifest: dict[str, str],
    source: dict[str, str],
    tool_versions: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    """Build an immutable payload containing no terminal state or self-digest."""
    for record in (candidate, review, aggregate):
        validate_record(record)
    validate_acyclic_graph(FINALIZATION_NODES, FINALIZATION_EDGES)
    manifest = load_invariant_manifest()
    payload = {
        "criteria": deepcopy(aggregate["payload"]["criteria"]),
        "candidate_packet_digest": candidate["digest"],
        "review_record_digest": review["digest"],
        "aggregate_record_digest": aggregate["digest"],
        "aggregate_candidate": aggregate["payload"]["candidate"],
        "evidence_manifest": deepcopy(evidence_manifest),
        "source": deepcopy(source),
        "schema_versions": list(manifest["contract_schemas"]),
        "algorithm_versions": deepcopy(manifest["versions"]),
        "tool_versions": deepcopy(tool_versions),
    }
    forbidden = {"terminal_state", "resulting_state", "final_packet_digest", "digest"}
    if forbidden & set(payload):
        raise FinalizationError("final packet payload contains a back-edge or self-digest")
    return seal_record(FINAL_PAYLOAD_SCHEMA, candidate["attempt_id"], payload, created_at)


def build_detached_digest(
    final_payload: dict[str, Any],
    candidate: dict[str, Any],
    review: dict[str, Any],
    created_at: str,
) -> dict[str, Any]:
    """Hash the exact final-payload record bytes and store the digest separately."""
    for record in (final_payload, candidate, review):
        validate_record(record)
    payload_bytes = canonical_bytes(final_payload)
    return seal_record(
        DETACHED_SCHEMA,
        final_payload["attempt_id"],
        {
            "payload_schema": final_payload["schema"],
            "payload_byte_length": len(payload_bytes),
            "hash_algorithm": "sha256/1",
            "payload_digest": content_digest(final_payload),
            "candidate_packet_digest": candidate["digest"],
            "review_record_digest": review["digest"],
            "tool_version": "nanotaste-rc0/0.1.0",
        },
        created_at,
    )


def verify_detached_digest(final_payload: dict[str, Any], detached: dict[str, Any]) -> None:
    """Independently recompute payload length and digest."""
    validate_record(final_payload)
    validate_record(detached)
    if detached["schema"] != DETACHED_SCHEMA:
        raise FinalizationError("record is not a detached packet digest")
    payload = detached["payload"]
    if payload["payload_schema"] != final_payload["schema"]:
        raise FinalizationError("detached digest references another payload schema")
    if payload["payload_byte_length"] != len(canonical_bytes(final_payload)):
        raise FinalizationError("final payload byte length changed")
    if payload["payload_digest"] != content_digest(final_payload):
        raise FinalizationError("final payload digest changed")


def proposed_terminal_state(aggregate_candidate: str, preflight_result: str) -> str:
    """Purely compute a terminal state; conservative results cannot become ready."""
    if preflight_result == "NO_GO":
        return "NO_GO_PRIVATE"
    if preflight_result == "HUMAN_INPUT_REQUIRED":
        return "HUMAN_INPUT_REQUIRED_PRIVATE"
    if preflight_result != "PASS":
        raise FinalizationError("terminal preflight result is unsupported")
    try:
        return TERMINAL_BY_AGGREGATE[aggregate_candidate]
    except KeyError as exc:
        raise FinalizationError("aggregate candidate is unsupported") from exc


def build_terminal_transition(
    *,
    attempt_id: str,
    detached: dict[str, Any],
    final_payload: dict[str, Any],
    candidate: dict[str, Any],
    review: dict[str, Any],
    aggregate: dict[str, Any],
    terminal_preflight_digest: str,
    current_state_digest: str,
    delegation_result: str,
    reserve_result: str,
    source_branch: str,
    source_commit: str,
    preflight_result: str,
    reason: str,
    created_at: str,
) -> dict[str, Any]:
    """Build the durable transition record before any state pointer changes."""
    for record in (detached, final_payload, candidate, review, aggregate):
        validate_record(record)
    verify_detached_digest(final_payload, detached)
    if final_payload["payload"]["candidate_packet_digest"] != candidate["digest"]:
        raise FinalizationError("final payload references another candidate")
    if final_payload["payload"]["aggregate_record_digest"] != aggregate["digest"]:
        raise FinalizationError("final payload references another aggregate")
    state = proposed_terminal_state(aggregate["payload"]["candidate"], preflight_result)
    return seal_record(
        TRANSITION_SCHEMA,
        attempt_id,
        {
            "detached_digest_record_digest": detached["digest"],
            "final_packet_digest": detached["payload"]["payload_digest"],
            "candidate_packet_digest": candidate["digest"],
            "review_record_digest": review["digest"],
            "aggregate_candidate": aggregate["payload"]["candidate"],
            "terminal_preflight_digest": terminal_preflight_digest,
            "current_state_digest": current_state_digest,
            "delegation_result": delegation_result,
            "reserve_result": reserve_result,
            "source_branch": source_branch,
            "source_commit": source_commit,
            "resulting_state": state,
            "reason": reason,
            "tool_version": "nanotaste-terminal-transition/1",
        },
        created_at,
    )


def persist_terminal_transition(
    directory: Path,
    transition: dict[str, Any],
    *,
    failpoint: str | None = None,
) -> dict[str, Any]:
    """Persist record, verify it, then atomically advance the state pointer."""
    validate_record(transition)
    if transition["schema"] != TRANSITION_SCHEMA:
        raise FinalizationError("record is not a terminal transition")
    transition_path = directory / "terminal-transition.json"
    state_path = directory / "terminal-state.json"
    if failpoint == "before_transition_record":
        raise StorageError("simulated crash before transition record")
    if transition_path.exists():
        existing = read_json(transition_path)
        if existing.get("digest") != transition["digest"]:
            raise FinalizationError("a competing terminal transition already exists")
    else:
        atomic_write_json(transition_path, transition)
    persisted = read_json(transition_path)
    validate_record(persisted)
    if persisted["digest"] != transition["digest"]:
        raise FinalizationError("persisted transition digest differs")
    if failpoint == "after_transition_record":
        raise StorageError("simulated crash after transition record")
    pointer = {
        "schema": TERMINAL_POINTER_SCHEMA,
        "invariant_manifest_digest": EXPECTED_INVARIANT_DIGEST,
        "transition_record_digest": transition["digest"],
        "terminal_state": transition["payload"]["resulting_state"],
    }
    if state_path.exists():
        current = read_json(state_path)
        if current != pointer:
            raise FinalizationError("terminal state pointer conflicts with durable transition")
        return current
    atomic_write_json(
        state_path,
        pointer,
        fail_before_replace=failpoint == "during_state_update",
    )
    if failpoint == "after_state_update":
        raise StorageError("simulated crash after state update")
    return pointer


def recover_terminal_transition(directory: Path) -> dict[str, Any]:
    """Complete one exact recorded transition or fail without inventing another."""
    transition_path = directory / "terminal-transition.json"
    state_path = directory / "terminal-state.json"
    transition = read_json(transition_path)
    validate_record(transition)
    expected = {
        "schema": TERMINAL_POINTER_SCHEMA,
        "invariant_manifest_digest": EXPECTED_INVARIANT_DIGEST,
        "transition_record_digest": transition["digest"],
        "terminal_state": transition["payload"]["resulting_state"],
    }
    if state_path.exists():
        current = read_json(state_path)
        if current != expected:
            raise FinalizationError("terminal state pointer conflicts with durable transition")
        return current
    atomic_write_json(state_path, expected)
    return expected


def guard_outcome_unknown(state: str) -> None:
    """Prevent uncertain attempts from entering review or packet finalization."""
    if state == "OUTCOME_UNKNOWN_PRIVATE":
        raise FinalizationError("outcome-unknown attempts cannot enter review finalization")
