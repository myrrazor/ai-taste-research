"""Machine-enforced local RC0 execution preflight."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from nanotaste.rc0.contracts import SCHEMAS, seal_record
from nanotaste.rc0.invariants import load_invariant_manifest

PREFLIGHT_SCHEMA = SCHEMAS[1]
SOURCE_BRANCH = "chore/sprint-2-release-foundation"
SOURCE_COMMIT = "dd6212481ec9148f40e27c886693ed2b81cc1a0a"
TIME_ZONE = "America/New_York"


class PreflightError(ValueError):
    """Raised when local implementation cannot pass the RC0 preflight."""


@dataclass(frozen=True)
class PreflightInput:
    """Observed state required to authorize one local RC0 action."""

    attempt_id: str
    created_at: str
    delegation_digest: str
    delegation_expires_at: str
    delegation_active: bool
    remaining_capacity_percent: int
    projected_capacity_percent: int
    claude_enabled: bool
    gstack_mode: str
    plan_digest: str
    review_digest: str
    state_digest: str
    state_current: bool
    source_branch: str
    source_commit: str
    git_clean: bool
    remotes: list[str]
    binding_graph_head: str
    ledger_head: str
    security_state_digest: str
    external_authorization_present: bool
    external_action: bool = False


def build_preflight(observed: PreflightInput) -> dict[str, Any]:
    """Validate controlling state and return a digest-sealed preflight record."""
    manifest = load_invariant_manifest()
    expected = manifest["controlling_artifacts"]
    failures = []
    try:
        current = _as_utc(observed.created_at)
        expires = _as_utc(observed.delegation_expires_at)
    except ValueError:
        failures.append("invalid execution timestamp")
        current = None
        expires = None
    computed_active = current is not None and expires is not None and current <= expires
    if observed.delegation_active != computed_active:
        failures.append("delegation active flag disagrees with its expiry")
    if not computed_active:
        failures.append("owner delegation is inactive")
    if observed.remaining_capacity_percent < 5 or observed.projected_capacity_percent < 5:
        failures.append("Codex reserve would fall below five percent")
    if observed.claude_enabled:
        failures.append("Claude Code must remain disabled")
    if observed.gstack_mode != "READ_ONLY":
        failures.append("GStack must be enabled in read-only mode")
    if observed.plan_digest != expected["plan_sha256"]:
        failures.append("controlling plan digest mismatch")
    if observed.review_digest != expected["review_sha256"]:
        failures.append("approving review digest mismatch")
    if not observed.state_current or not observed.state_digest:
        failures.append("Arthur state artifact is stale or missing")
    if observed.source_branch != SOURCE_BRANCH or observed.source_commit != SOURCE_COMMIT:
        failures.append("source baseline mismatch")
    if not observed.git_clean:
        failures.append("source baseline worktree is not clean")
    if observed.remotes:
        failures.append("unexpected remote exists at local-only preflight")
    if observed.external_action and not observed.external_authorization_present:
        failures.append("external operation lacks separate owner authorization")
    decision = "STOP" if failures else "PASS_LOCAL_ONLY"
    record = seal_record(
        PREFLIGHT_SCHEMA,
        observed.attempt_id,
        {
            "time_zone": TIME_ZONE,
            "delegation_digest": observed.delegation_digest,
            "delegation_expires_at": observed.delegation_expires_at,
            "delegation_active": computed_active,
            "remaining_capacity_percent": observed.remaining_capacity_percent,
            "projected_capacity_percent": observed.projected_capacity_percent,
            "reserve_floor_percent": 5,
            "claude_enabled": observed.claude_enabled,
            "gstack_mode": observed.gstack_mode,
            "plan_digest": observed.plan_digest,
            "review_digest": observed.review_digest,
            "state_digest": observed.state_digest,
            "source_branch": observed.source_branch,
            "source_commit": observed.source_commit,
            "git_clean": observed.git_clean,
            "remotes": list(observed.remotes),
            "binding_graph_head": observed.binding_graph_head,
            "ledger_head": observed.ledger_head,
            "security_state_digest": observed.security_state_digest,
            "external_authorization_present": observed.external_authorization_present,
            "decision": {"result": decision, "failures": failures},
        },
        observed.created_at,
    )
    if failures:
        raise PreflightError("; ".join(failures))
    return record


def _as_utc(value: str) -> datetime:
    """Parse an ISO timestamp without requiring IANA tzdata on Windows."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
