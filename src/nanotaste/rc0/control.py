"""Resource-binding, authorization, graph, and ledger controls."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from nanotaste.rc0.contracts import SCHEMAS, seal_record, validate_record
from nanotaste.rc0.invariants import EXPECTED_INVARIANT_DIGEST
from nanotaste.rc0.storage import ExclusiveLock, atomic_write_json, read_json

BINDING_SCHEMA = SCHEMAS[4]
AUTHORIZATION_SCHEMA = SCHEMAS[5]
LEDGER_SCHEMA = SCHEMAS[6]
OUTCOME_UNKNOWN_SCHEMA = SCHEMAS[7]
LEDGER_STATE_SCHEMA = "nanotaste/rc0-ledger-state/1.0"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "OUTCOME_UNKNOWN"}


class ControlError(ValueError):
    """Raised when an RC0 control-plane precondition fails."""


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo is None:
        raise ControlError("timestamp must include UTC timezone")
    return parsed.astimezone(timezone.utc)


def validate_acyclic_graph(nodes: Iterable[str], edges: Iterable[tuple[str, str]]) -> None:
    """Reject missing nodes, self edges, duplicate edges, and directed cycles."""
    node_set = set(nodes)
    edge_list = list(edges)
    if len(edge_list) != len(set(edge_list)):
        raise ControlError("graph contains duplicate edges")
    adjacency: dict[str, set[str]] = {node: set() for node in node_set}
    incoming = {node: 0 for node in node_set}
    for source, target in edge_list:
        if source not in node_set or target not in node_set:
            raise ControlError("graph edge references a missing node")
        if source == target:
            raise ControlError("graph contains a self edge")
        adjacency[source].add(target)
        incoming[target] += 1
    queue = sorted(node for node, count in incoming.items() if count == 0)
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for target in sorted(adjacency[node]):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if visited != len(node_set):
        raise ControlError("graph contains a cycle")


def validate_resource_binding(
    record: dict[str, Any],
    *,
    attempt_id: str,
    current_state_digest: str,
    now: datetime,
) -> None:
    """Validate a durable, reusable identity binding without consuming it."""
    validate_record(record)
    if record["schema"] != BINDING_SCHEMA:
        raise ControlError("record is not a resource binding")
    if record["attempt_id"] != attempt_id:
        raise ControlError("resource binding belongs to another attempt")
    payload = record["payload"]
    if payload["resource_state_digest"] != current_state_digest:
        raise ControlError("resource binding is stale")
    if _parse_utc(payload["expires_at"]) <= now.astimezone(timezone.utc):
        raise ControlError("resource binding is expired")
    if _parse_utc(payload["issued_at"]) > now.astimezone(timezone.utc):
        raise ControlError("resource binding was issued in the future")
    if _parse_utc(payload["observed_at"]) > now.astimezone(timezone.utc):
        raise ControlError("resource binding observation is in the future")
    if not payload["immutable_identifiers"]:
        raise ControlError("resource binding lacks immutable identity")
    forbidden = {"operation_id", "max_uses", "action_type"}
    if forbidden & set(payload):
        raise ControlError("resource binding contains mutation permission")


def validate_operation_authorization(
    authorization: dict[str, Any],
    binding: dict[str, Any],
    *,
    attempt_id: str,
    action_type: str,
    actor: str,
    target: str,
    payload_digest: str,
    expected_state_digest: str,
    consumed_digests: set[str],
    now: datetime,
) -> None:
    """Validate one exact, unconsumed mutation authorization."""
    validate_record(authorization)
    validate_record(binding)
    if authorization["schema"] != AUTHORIZATION_SCHEMA:
        raise ControlError("record is not an operation authorization")
    if binding["schema"] != BINDING_SCHEMA:
        raise ControlError("authorization does not reference a resource binding")
    if authorization["attempt_id"] != attempt_id or binding["attempt_id"] != attempt_id:
        raise ControlError("authorization or binding belongs to another attempt")
    payload = authorization["payload"]
    validate_resource_binding(
        binding,
        attempt_id=attempt_id,
        current_state_digest=expected_state_digest,
        now=now,
    )
    expected = {
        "action_type": action_type,
        "actor": actor,
        "target": target,
        "payload_digest": payload_digest,
        "expected_state_digest": expected_state_digest,
        "primary_binding_digest": binding["digest"],
    }
    for name, value in expected.items():
        if payload[name] != value:
            raise ControlError(f"authorization {name} mismatch")
    if payload["max_uses"] != 1:
        raise ControlError("operation authorization must have max_uses equal to one")
    if _parse_utc(payload["expires_at"]) <= now.astimezone(timezone.utc):
        raise ControlError("operation authorization is expired")
    if _parse_utc(payload["issued_at"]) > now.astimezone(timezone.utc):
        raise ControlError("operation authorization was issued in the future")
    outcomes = payload["permitted_terminal_outcomes"]
    if not isinstance(outcomes, list) or not outcomes or not set(outcomes) <= TERMINAL_STATUSES:
        raise ControlError("operation authorization terminal outcomes are invalid")
    if authorization["digest"] in consumed_digests:
        raise ControlError("operation authorization was already consumed")


class ActionLedger:
    """Atomic hash-chained ledger that consumes authorization at STARTED."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def _empty(self) -> dict[str, Any]:
        return {
            "schema": LEDGER_STATE_SCHEMA,
            "invariant_manifest_digest": EXPECTED_INVARIANT_DIGEST,
            "events": [],
            "consumed_authorizations": [],
            "consumed_nonces": [],
        }

    def _load(self) -> dict[str, Any]:
        state = read_json(self.path) if self.path.exists() else self._empty()
        if set(state) != {
            "schema", "invariant_manifest_digest", "events", "consumed_authorizations",
            "consumed_nonces",
        }:
            raise ControlError("ledger state fields are invalid")
        if state["schema"] != LEDGER_STATE_SCHEMA:
            raise ControlError("unsupported ledger state schema")
        if state["invariant_manifest_digest"] != EXPECTED_INVARIANT_DIGEST:
            raise ControlError("ledger state references stale RC0 invariants")
        if not isinstance(state["events"], list) or not isinstance(
            state["consumed_authorizations"], list
        ):
            raise ControlError("ledger state is corrupt")
        previous = "GENESIS"
        for event in state["events"]:
            validate_record(event)
            if event["schema"] != LEDGER_SCHEMA:
                raise ControlError("ledger contains a non-ledger record")
            if event["payload"]["previous_event_digest"] != previous:
                raise ControlError("ledger hash chain is broken")
            previous = event["digest"]
        if len(state["consumed_authorizations"]) != len(
            set(state["consumed_authorizations"])
        ):
            raise ControlError("ledger contains duplicate authorization consumption")
        if len(state["consumed_nonces"]) != len(set(state["consumed_nonces"])):
            raise ControlError("ledger contains duplicate authorization nonces")
        return state

    def begin(
        self,
        authorization: dict[str, Any],
        binding: dict[str, Any],
        *,
        action_type: str,
        actor: str,
        target: str,
        payload_digest: str,
        expected_state_digest: str,
        created_at: str,
        now: datetime,
    ) -> dict[str, Any]:
        """Persist STARTED and authorization consumption in one atomic state update."""
        with ExclusiveLock(self.lock_path):
            state = self._load()
            consumed = set(state["consumed_authorizations"])
            nonce = authorization["payload"]["nonce"]
            if nonce in set(state["consumed_nonces"]):
                raise ControlError("operation authorization nonce was already consumed")
            operation_id = authorization["payload"]["operation_id"]
            if any(event["payload"]["operation_id"] == operation_id for event in state["events"]):
                raise ControlError("operation ID already exists in the ledger")
            validate_operation_authorization(
                authorization,
                binding,
                attempt_id=authorization["attempt_id"],
                action_type=action_type,
                actor=actor,
                target=target,
                payload_digest=payload_digest,
                expected_state_digest=expected_state_digest,
                consumed_digests=consumed,
                now=now,
            )
            previous = state["events"][-1]["digest"] if state["events"] else "GENESIS"
            event = seal_record(
                LEDGER_SCHEMA,
                authorization["attempt_id"],
                {
                    "event_id": f"{authorization['payload']['operation_id']}:STARTED",
                    "operation_id": authorization["payload"]["operation_id"],
                    "authorization_digest": authorization["digest"],
                    "binding_digest": binding["digest"],
                    "status": "STARTED",
                    "previous_event_digest": previous,
                    "details": {},
                },
                created_at,
            )
            state["events"].append(event)
            state["consumed_authorizations"].append(authorization["digest"])
            state["consumed_nonces"].append(nonce)
            atomic_write_json(self.path, state)
            return event

    def finish(
        self,
        operation_id: str,
        status: str,
        *,
        attempt_id: str,
        created_at: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one trustworthy terminal event for a started operation."""
        if status not in TERMINAL_STATUSES:
            raise ControlError(f"invalid ledger terminal status: {status}")
        if status == "OUTCOME_UNKNOWN":
            raise ControlError("use reconcile() to persist an OUTCOME_UNKNOWN terminal event")
        with ExclusiveLock(self.lock_path):
            state = self._load()
            operation_events = [
                event for event in state["events"]
                if event["payload"]["operation_id"] == operation_id
            ]
            if not operation_events or operation_events[0]["payload"]["status"] != "STARTED":
                raise ControlError("operation has no durable STARTED event")
            if operation_events[0]["attempt_id"] != attempt_id:
                raise ControlError("terminal event belongs to another attempt")
            if any(event["payload"]["status"] in TERMINAL_STATUSES for event in operation_events):
                raise ControlError("operation already has a terminal event")
            started = operation_events[0]
            event = seal_record(
                LEDGER_SCHEMA,
                attempt_id,
                {
                    "event_id": f"{operation_id}:{status}",
                    "operation_id": operation_id,
                    "authorization_digest": started["payload"]["authorization_digest"],
                    "binding_digest": started["payload"]["binding_digest"],
                    "status": status,
                    "previous_event_digest": state["events"][-1]["digest"],
                    "details": details or {},
                },
                created_at,
            )
            state["events"].append(event)
            atomic_write_json(self.path, state)
            return event

    def reconcile(self, operation_id: str, created_at: str) -> tuple[str, dict[str, Any] | None]:
        """Durably map an unresolved STARTED event to outcome unknown."""
        with ExclusiveLock(self.lock_path):
            state = self._load()
            events = [
                event
                for event in state["events"]
                if event["payload"]["operation_id"] == operation_id
            ]
            if not events:
                raise ControlError("operation does not exist in the ledger")
            terminal = next(
                (event for event in events if event["payload"]["status"] in TERMINAL_STATUSES),
                None,
            )
            if terminal and terminal["payload"]["status"] != "OUTCOME_UNKNOWN":
                return terminal["payload"]["status"], None
            if terminal:
                outcome = terminal["payload"]["details"].get("outcome_unknown")
                if not isinstance(outcome, dict):
                    raise ControlError("OUTCOME_UNKNOWN event lacks its durable incident record")
                validate_record(outcome)
                if outcome["schema"] != OUTCOME_UNKNOWN_SCHEMA:
                    raise ControlError("OUTCOME_UNKNOWN event contains the wrong incident schema")
                return "OUTCOME_UNKNOWN_PRIVATE", outcome

            started = events[0]
            ledger_head = state["events"][-1]["digest"]
            outcome = seal_record(
                OUTCOME_UNKNOWN_SCHEMA,
                started["attempt_id"],
                {
                    "operation_id": operation_id,
                    "authorization_digest": started["payload"]["authorization_digest"],
                    "binding_digest": started["payload"]["binding_digest"],
                    "started_event_digest": started["digest"],
                    "ledger_head_digest": ledger_head,
                    "last_terminal_predecessor": started["payload"]["previous_event_digest"],
                    "interruption_evidence": "missing-terminal",
                    "external_observations": [],
                    "ambiguity": "external effect cannot be established",
                    "authorization_consumed": True,
                    "no_retry": True,
                    "tool_versions": {"ledger": "nanotaste-hash-chain-ledger/1"},
                    "owner_recovery_required": True,
                    "incident_digest": started["digest"],
                },
                created_at,
            )
            terminal_event = seal_record(
                LEDGER_SCHEMA,
                started["attempt_id"],
                {
                    "event_id": f"{operation_id}:OUTCOME_UNKNOWN",
                    "operation_id": operation_id,
                    "authorization_digest": started["payload"]["authorization_digest"],
                    "binding_digest": started["payload"]["binding_digest"],
                    "status": "OUTCOME_UNKNOWN",
                    "previous_event_digest": ledger_head,
                    "details": {"outcome_unknown": outcome},
                },
                created_at,
            )
            state["events"].append(terminal_event)
            atomic_write_json(self.path, state)
            return "OUTCOME_UNKNOWN_PRIVATE", outcome

    def state(self) -> dict[str, Any]:
        """Return a validated copy of the current ledger state."""
        return self._load()
