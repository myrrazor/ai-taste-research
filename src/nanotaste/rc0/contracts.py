"""Strict, versioned RC0 evidence contracts."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Collection

from nanotaste.rc0.canonical import content_digest
from nanotaste.rc0.invariants import EXPECTED_INVARIANT_DIGEST, validate_invariant_reference

PRODUCER_VERSION = "nanotaste-rc0/0.1.0"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
TOP_LEVEL_FIELDS = {
    "schema",
    "attempt_id",
    "producer_version",
    "created_at",
    "invariant_manifest_digest",
    "payload",
    "extensions",
    "digest",
}

SCHEMAS = (
    "nanotaste/rc0-trust-anchor/1.0",
    "nanotaste/rc0-control-plane-preflight/1.0",
    "nanotaste/rc0-codeowner-identity/1.0",
    "nanotaste/rc0-governance-bootstrap/1.0",
    "nanotaste/rc0-resource-binding/1.0",
    "nanotaste/rc0-operation-authorization/1.0",
    "nanotaste/rc0-action-ledger/1.0",
    "nanotaste/rc0-outcome-unknown/1.0",
    "nanotaste/rc0-expected-state/1.0",
    "nanotaste/rc0-repository-security-state/1.0",
    "nanotaste/rc0-history-scan/1.0",
    "nanotaste/rc0-github-surface-capabilities/1.0",
    "nanotaste/rc0-github-surface-inventory/1.0",
    "nanotaste/rc0-security-contact-test/1.0",
    "nanotaste/rc0-build-provenance/1.0",
    "nanotaste/rc0-hosted-artifact/1.0",
    "nanotaste/rc0-candidate-review-packet/1.0",
    "nanotaste/rc0-review-result/1.0",
    "nanotaste/rc0-aggregate-candidate/1.0",
    "nanotaste/rc0-final-packet-payload/1.0",
    "nanotaste/rc0-detached-digest/1.0",
    "nanotaste/rc0-terminal-transition/1.0",
    "nanotaste/rc0-review-derivation/1.0",
)

def _fields(*names: str) -> frozenset[str]:
    return frozenset(names)


PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    SCHEMAS[0]: _fields(
        "owner_identity", "public_key", "fingerprint", "namespaces", "valid_from",
        "valid_until", "revoked",
    ),
    SCHEMAS[1]: _fields(
        "time_zone", "delegation_digest", "delegation_expires_at", "delegation_active",
        "remaining_capacity_percent",
        "projected_capacity_percent", "reserve_floor_percent", "claude_enabled", "gstack_mode",
        "plan_digest", "review_digest", "state_digest", "source_branch", "source_commit",
        "git_clean", "remotes", "binding_graph_head", "ledger_head", "security_state_digest",
        "external_authorization_present", "decision",
    ),
    SCHEMAS[2]: _fields("login", "immutable_id", "account_type", "access", "verified"),
    SCHEMAS[3]: _fields(
        "parent_sha", "branch", "commit_sha", "changed_paths", "codeowners_blob_digest", "mode",
        "encoding", "line_endings",
    ),
    SCHEMAS[4]: _fields(
        "binding_id", "resource_type", "immutable_identifiers", "bound_fields",
        "resource_state_digest", "observation_actor", "observation_source", "observed_at",
        "issued_at", "expires_at", "trust_anchor_digest", "predecessor_binding_digests",
        "originating_authorization_digest", "terminal_event_digest", "signature",
    ),
    SCHEMAS[5]: _fields(
        "authorization_id", "operation_id", "action_type", "actor", "target",
        "primary_binding_digest", "prerequisite_evidence_digests", "expected_state_digest",
        "payload_digest", "permitted_terminal_outcomes", "issued_at", "expires_at", "nonce",
        "trust_anchor_digest", "max_uses", "signature",
    ),
    SCHEMAS[6]: _fields(
        "event_id", "operation_id", "authorization_digest", "binding_digest", "status",
        "previous_event_digest", "details",
    ),
    SCHEMAS[7]: _fields(
        "operation_id", "authorization_digest", "binding_digest", "started_event_digest",
        "ledger_head_digest", "last_terminal_predecessor", "interruption_evidence",
        "external_observations", "ambiguity", "authorization_consumed", "no_retry",
        "tool_versions", "owner_recovery_required", "incident_digest",
    ),
    SCHEMAS[8]: _fields(
        "resource_type", "immutable_identity", "visibility", "default_branch", "refs", "settings",
        "absent_surfaces",
    ),
    SCHEMAS[9]: _fields(
        "repository_identity", "observed", "required", "required_checks", "codeowner_identity",
        "publication_surface_counts", "compliant",
    ),
    SCHEMAS[10]: _fields(
        "scope", "patterns", "scanned_objects", "findings", "complete", "tool_versions",
    ),
    SCHEMAS[11]: _fields("surfaces", "capability_classes", "complete"),
    SCHEMAS[12]: _fields("surfaces", "pagination_complete", "findings", "complete"),
    SCHEMAS[13]: _fields(
        "route_type", "tested_at", "result", "signer", "signature", "message_content_stored",
    ),
    SCHEMAS[14]: _fields(
        "source_sha", "wheel_filename", "wheel_sha256", "sdist_state", "sdist_sha256", "builder",
        "build_tool_version", "algorithm_versions", "tool_versions",
    ),
    SCHEMAS[15]: _fields(
        "run_id", "artifact_id", "artifact_name", "artifact_sha256", "source_sha", "expires_at",
        "tool_versions",
    ),
    SCHEMAS[16]: _fields(
        "criteria", "release_sha", "evidence_digests", "unresolved_findings", "schema_versions",
        "algorithm_versions", "tool_versions",
    ),
    SCHEMAS[17]: _fields(
        "candidate_packet_digest", "verdict", "findings", "reviewer", "reviewed_at",
        "tool_versions",
    ),
    SCHEMAS[18]: _fields(
        "criteria", "verdict", "criterion_f", "candidate", "derivation_algorithm_version",
    ),
    SCHEMAS[19]: _fields(
        "criteria", "candidate_packet_digest", "review_record_digest", "aggregate_record_digest",
        "aggregate_candidate", "evidence_manifest", "source", "schema_versions",
        "algorithm_versions", "tool_versions",
    ),
    SCHEMAS[20]: _fields(
        "payload_schema", "payload_byte_length", "hash_algorithm", "payload_digest",
        "candidate_packet_digest", "review_record_digest", "tool_version",
    ),
    SCHEMAS[21]: _fields(
        "detached_digest_record_digest", "final_packet_digest", "candidate_packet_digest",
        "review_record_digest", "aggregate_candidate", "terminal_preflight_digest",
        "current_state_digest", "delegation_result", "reserve_result", "source_branch",
        "source_commit", "resulting_state", "reason", "tool_version",
    ),
    SCHEMAS[22]: _fields(
        "edges", "candidate_packet_digest", "review_record_digest", "verdict", "criterion_f",
        "algorithm_version",
    ),
}

REQUIRED_PAYLOAD_FIELDS: dict[str, frozenset[str]] = {
    schema: fields for schema, fields in PAYLOAD_FIELDS.items()
}


class ContractError(ValueError):
    """Raised when an RC0 record violates its versioned contract."""


def _validate_timestamp(value: Any, name: str) -> None:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise ContractError(f"{name} must be an RFC 3339 UTC timestamp")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{name} is not a valid timestamp") from exc


def _validate_fields(actual: Collection[str], allowed: Collection[str], name: str) -> None:
    unknown = set(actual) - set(allowed)
    if unknown:
        raise ContractError(f"unknown {name} fields: {', '.join(sorted(unknown))}")


def _record_without_digest(record: dict[str, Any]) -> dict[str, Any]:
    unsigned = deepcopy(record)
    unsigned.pop("digest", None)
    return unsigned


def seal_record(
    schema: str,
    attempt_id: str,
    payload: dict[str, Any],
    created_at: str,
    *,
    extensions: dict[str, Any] | None = None,
    producer_version: str = PRODUCER_VERSION,
) -> dict[str, Any]:
    """Create and validate a digest-sealed RC0 record."""
    record: dict[str, Any] = {
        "schema": schema,
        "attempt_id": attempt_id,
        "producer_version": producer_version,
        "created_at": created_at,
        "invariant_manifest_digest": EXPECTED_INVARIANT_DIGEST,
        "payload": deepcopy(payload),
        "extensions": deepcopy(extensions or {}),
    }
    record["digest"] = content_digest(record)
    validate_record(record)
    return record


def validate_record(record: dict[str, Any]) -> None:
    """Validate schema version, fields, invariant binding, and digest."""
    if not isinstance(record, dict):
        raise ContractError("record must be a JSON object")
    _validate_fields(record, TOP_LEVEL_FIELDS, "top-level")
    missing = TOP_LEVEL_FIELDS - set(record)
    if missing:
        raise ContractError(f"missing top-level fields: {', '.join(sorted(missing))}")
    schema = record.get("schema")
    if not isinstance(schema, str) or schema not in SCHEMAS:
        raise ContractError(f"unsupported RC0 schema: {schema!r}")
    if not isinstance(record.get("attempt_id"), str) or not record["attempt_id"]:
        raise ContractError("attempt_id must be a non-empty string")
    if not isinstance(record.get("producer_version"), str) or not record["producer_version"]:
        raise ContractError("producer_version must be a non-empty string")
    _validate_timestamp(record.get("created_at"), "created_at")
    validate_invariant_reference(record)
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ContractError("payload must be a JSON object")
    allowed = PAYLOAD_FIELDS[schema]
    _validate_fields(payload, allowed, "payload")
    missing_payload = REQUIRED_PAYLOAD_FIELDS[schema] - set(payload)
    if missing_payload:
        raise ContractError(f"missing payload fields: {', '.join(sorted(missing_payload))}")
    if not isinstance(record.get("extensions"), dict):
        raise ContractError("extensions must be a JSON object")
    digest = record.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError("digest must be a lowercase SHA-256 hex string")
    if digest != content_digest(_record_without_digest(record)):
        raise ContractError("record digest mismatch")
