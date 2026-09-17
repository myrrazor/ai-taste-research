from __future__ import annotations

import copy
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from nanotaste.rc0.contracts import SCHEMAS, seal_record
from nanotaste.rc0.control import (
    ActionLedger,
    ControlError,
    validate_acyclic_graph,
    validate_operation_authorization,
    validate_resource_binding,
)
from nanotaste.rc0.finalization import (
    FinalizationError,
    build_candidate_packet,
    build_detached_digest,
    build_final_packet_payload,
    build_review_result,
    build_terminal_transition,
    derive_aggregate_candidate,
    derive_criterion_f,
    guard_outcome_unknown,
    persist_terminal_transition,
    proposed_terminal_state,
    recover_terminal_transition,
    verify_detached_digest,
)
from nanotaste.rc0.invariants import load_invariant_manifest
from nanotaste.rc0.policy import (
    PolicyError,
    guard_publication_operation,
    validate_pr_topology,
    validate_required_checks,
    validate_surface_inventory,
)
from nanotaste.rc0.storage import ExclusiveLock, StorageError, atomic_write_json, read_json

NOW_TEXT = "2026-07-11T22:45:00Z"
NOW = datetime(2026, 7, 11, 22, 45, tzinfo=timezone.utc)
LATER = "2026-07-12T22:45:00Z"


def make_binding(attempt_id: str = "attempt-001", state_digest: str = "state-1") -> dict:
    return seal_record(
        SCHEMAS[4],
        attempt_id,
        {
            "binding_id": "binding-001",
            "resource_type": "github_repository",
            "immutable_identifiers": {"database_id": 1234},
            "bound_fields": {"visibility": "private"},
            "resource_state_digest": state_digest,
            "observation_actor": "owner-id-1",
            "observation_source": "github-api",
            "observed_at": NOW_TEXT,
            "issued_at": NOW_TEXT,
            "expires_at": LATER,
            "trust_anchor_digest": "trust-1",
            "predecessor_binding_digests": [],
            "originating_authorization_digest": "creation-auth",
            "terminal_event_digest": "creation-success",
            "signature": "openssh-signature",
        },
        NOW_TEXT,
    )


def make_authorization(
    binding: dict,
    attempt_id: str = "attempt-001",
    *,
    authorization_id: str = "auth-001",
    operation_id: str = "op-001",
    nonce: str = "nonce-001",
) -> dict:
    return seal_record(
        SCHEMAS[5],
        attempt_id,
        {
            "authorization_id": authorization_id,
            "operation_id": operation_id,
            "action_type": "create_pull_request",
            "actor": "automation-id-1",
            "target": "repo-id-1234",
            "primary_binding_digest": binding["digest"],
            "prerequisite_evidence_digests": ["history-clean"],
            "expected_state_digest": "state-1",
            "payload_digest": "payload-1",
            "permitted_terminal_outcomes": ["SUCCEEDED", "FAILED", "OUTCOME_UNKNOWN"],
            "issued_at": NOW_TEXT,
            "expires_at": LATER,
            "nonce": nonce,
            "trust_anchor_digest": "trust-1",
            "max_uses": 1,
            "signature": "openssh-signature",
        },
        NOW_TEXT,
    )


def complete_review_path(verdict: str = "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST"):
    criteria = {letter: "PASS" for letter in "ABCDE"}
    if verdict == "NO_GO":
        criteria["C"] = "FAIL"
    if verdict == "HUMAN_INPUT_REQUIRED":
        criteria["D"] = "BLOCKED"
    candidate = build_candidate_packet(
        attempt_id="attempt-001",
        criteria=criteria,
        release_sha="a" * 40,
        evidence_digests={"history": "h1", "artifact": "a1"},
        unresolved_findings=[] if verdict.endswith("FORK_TEST") else ["recorded issue"],
        tool_versions={"nanotaste": "0.1.0", "python": "3.14.6", "gstack": "0.7.1"},
        created_at=NOW_TEXT,
    )
    review = build_review_result(
        candidate,
        verdict=verdict,
        findings=[],
        reviewer="gstack-exact-sha",
        tool_versions={"gstack": "0.7.1", "codex": "0.144.0"},
        created_at=NOW_TEXT,
    )
    derivation = derive_criterion_f(candidate, review, NOW_TEXT)
    aggregate = derive_aggregate_candidate(candidate, review, derivation, NOW_TEXT)
    final_payload = build_final_packet_payload(
        candidate,
        review,
        aggregate,
        evidence_manifest={"history": "h1", "artifact": "a1"},
        source={"branch": "testing", "commit": "a" * 40},
        tool_versions={"nanotaste": "0.1.0", "python": "3.14.6", "gstack": "0.7.1"},
        created_at=NOW_TEXT,
    )
    detached = build_detached_digest(final_payload, candidate, review, NOW_TEXT)
    return candidate, review, derivation, aggregate, final_payload, detached


class StorageTests(unittest.TestCase):
    def test_atomic_write_round_trip_and_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "record.json"
            atomic_write_json(path, {"value": 1})
            self.assertEqual(read_json(path), {"value": 1})
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_crash_before_replace_preserves_previous_record(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "record.json"
            atomic_write_json(path, {"value": "before"})
            with self.assertRaisesRegex(StorageError, "simulated crash"):
                atomic_write_json(path, {"value": "after"}, fail_before_replace=True)
            self.assertEqual(read_json(path), {"value": "before"})
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_symlinked_output_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.json"
            target.write_text("{}")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(StorageError, "symlinked"):
                atomic_write_json(link, {"value": "no"})

    def test_symlinked_output_directory_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(StorageError, "symlinked"):
                atomic_write_json(linked / "record.json", {"value": "no"})

    def test_second_writer_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            lock = Path(temp_dir) / "ledger.lock"
            with ExclusiveLock(lock):
                with self.assertRaisesRegex(StorageError, "already exists"):
                    with ExclusiveLock(lock):
                        pass


class BindingAuthorizationLedgerTests(unittest.TestCase):
    def test_binding_validation_is_non_consuming(self) -> None:
        binding = make_binding()
        for _ in range(2):
            validate_resource_binding(
                binding,
                attempt_id="attempt-001",
                current_state_digest="state-1",
                now=NOW,
            )

    def test_stale_or_expired_binding_fails(self) -> None:
        binding = make_binding()
        with self.assertRaisesRegex(ControlError, "stale"):
            validate_resource_binding(
                binding,
                attempt_id="attempt-001",
                current_state_digest="changed",
                now=NOW,
            )
        with self.assertRaisesRegex(ControlError, "expired"):
            validate_resource_binding(
                binding,
                attempt_id="attempt-001",
                current_state_digest="state-1",
                now=datetime(2026, 7, 13, tzinfo=timezone.utc),
            )

    def test_authorization_cannot_use_a_stale_binding(self) -> None:
        binding = make_binding(state_digest="old-state")
        authorization = make_authorization(binding)
        with self.assertRaisesRegex(ControlError, "stale"):
            validate_operation_authorization(
                authorization,
                binding,
                attempt_id="attempt-001",
                action_type="create_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                consumed_digests=set(),
                now=NOW,
            )

    def test_authorization_requires_exact_action_actor_target_and_binding(self) -> None:
        binding = make_binding()
        authorization = make_authorization(binding)
        with self.assertRaisesRegex(ControlError, "action_type mismatch"):
            validate_operation_authorization(
                authorization,
                binding,
                attempt_id="attempt-001",
                action_type="merge_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                consumed_digests=set(),
                now=NOW,
            )

    def test_started_consumes_authorization_and_replay_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = ActionLedger(Path(temp_dir) / "ledger.json")
            binding = make_binding()
            authorization = make_authorization(binding)
            started = ledger.begin(
                authorization,
                binding,
                action_type="create_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                created_at=NOW_TEXT,
                now=NOW,
            )
            self.assertEqual(started["payload"]["status"], "STARTED")
            self.assertIn(authorization["digest"], ledger.state()["consumed_authorizations"])
            with self.assertRaisesRegex(ControlError, "already consumed"):
                ledger.begin(
                    authorization,
                    binding,
                    action_type="create_pull_request",
                    actor="automation-id-1",
                    target="repo-id-1234",
                    payload_digest="payload-1",
                    expected_state_digest="state-1",
                    created_at=NOW_TEXT,
                    now=NOW,
                )

    def test_crash_after_started_maps_only_to_outcome_unknown(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = ActionLedger(Path(temp_dir) / "ledger.json")
            binding = make_binding()
            authorization = make_authorization(binding)
            ledger.begin(
                authorization,
                binding,
                action_type="create_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                created_at=NOW_TEXT,
                now=NOW,
            )
            state, outcome = ledger.reconcile("op-001", NOW_TEXT)
            self.assertEqual(state, "OUTCOME_UNKNOWN_PRIVATE")
            self.assertIsNotNone(outcome)
            self.assertTrue(outcome["payload"]["authorization_consumed"])
            self.assertTrue(outcome["payload"]["no_retry"])
            persisted = ledger.state()["events"][-1]
            self.assertEqual(persisted["payload"]["status"], "OUTCOME_UNKNOWN")
            self.assertEqual(
                persisted["payload"]["details"]["outcome_unknown"]["digest"],
                outcome["digest"],
            )
            self.assertEqual(ledger.reconcile("op-001", LATER), (state, outcome))
            with self.assertRaisesRegex(ControlError, "terminal event"):
                ledger.finish(
                    "op-001",
                    "SUCCEEDED",
                    attempt_id="attempt-001",
                    created_at=LATER,
                )

    def test_reused_nonce_or_operation_id_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = ActionLedger(Path(temp_dir) / "ledger.json")
            binding = make_binding()
            first = make_authorization(binding)
            ledger.begin(
                first,
                binding,
                action_type="create_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                created_at=NOW_TEXT,
                now=NOW,
            )
            same_nonce = make_authorization(
                binding,
                authorization_id="auth-002",
                operation_id="op-002",
                nonce="nonce-001",
            )
            with self.assertRaisesRegex(ControlError, "nonce"):
                ledger.begin(
                    same_nonce,
                    binding,
                    action_type="create_pull_request",
                    actor="automation-id-1",
                    target="repo-id-1234",
                    payload_digest="payload-1",
                    expected_state_digest="state-1",
                    created_at=NOW_TEXT,
                    now=NOW,
                )
            same_operation = make_authorization(
                binding,
                authorization_id="auth-003",
                operation_id="op-001",
                nonce="nonce-003",
            )
            with self.assertRaisesRegex(ControlError, "operation ID"):
                ledger.begin(
                    same_operation,
                    binding,
                    action_type="create_pull_request",
                    actor="automation-id-1",
                    target="repo-id-1234",
                    payload_digest="payload-1",
                    expected_state_digest="state-1",
                    created_at=NOW_TEXT,
                    now=NOW,
                )

    def test_terminal_success_reconciles_without_incident(self) -> None:
        with TemporaryDirectory() as temp_dir:
            ledger = ActionLedger(Path(temp_dir) / "ledger.json")
            binding = make_binding()
            authorization = make_authorization(binding)
            ledger.begin(
                authorization,
                binding,
                action_type="create_pull_request",
                actor="automation-id-1",
                target="repo-id-1234",
                payload_digest="payload-1",
                expected_state_digest="state-1",
                created_at=NOW_TEXT,
                now=NOW,
            )
            ledger.finish("op-001", "SUCCEEDED", attempt_id="attempt-001", created_at=NOW_TEXT)
            self.assertEqual(ledger.reconcile("op-001", NOW_TEXT), ("SUCCEEDED", None))

    def test_graph_cycles_and_missing_nodes_fail(self) -> None:
        with self.assertRaisesRegex(ControlError, "cycle"):
            validate_acyclic_graph(("a", "b"), (("a", "b"), ("b", "a")))
        with self.assertRaisesRegex(ControlError, "missing node"):
            validate_acyclic_graph(("a",), (("a", "b"),))


class PolicyTests(unittest.TestCase):
    def integration_prs(self) -> list[dict]:
        return [
            {
                "class": "IMPLEMENTATION_INTEGRATION_PR",
                "merged": True,
                "author": "automation",
                "reviewer": "@myrrazor",
                "merge_sha": "a" * 40,
            },
            {
                "class": "PROMOTION_INTEGRATION_PR",
                "merged": True,
                "author": "automation",
                "reviewer": "@myrrazor",
                "merge_sha": "b" * 40,
            },
        ]

    def test_exact_two_pr_topology_and_release_identity(self) -> None:
        self.assertEqual(validate_pr_topology(self.integration_prs()), "b" * 40)

    def test_third_integration_pr_fails(self) -> None:
        prs = self.integration_prs()
        prs.append(copy.deepcopy(prs[0]))
        with self.assertRaisesRegex(PolicyError, "exactly once"):
            validate_pr_topology(prs)

    def test_self_approval_fails(self) -> None:
        prs = self.integration_prs()
        prs[0]["author"] = "@myrrazor"
        with self.assertRaisesRegex(PolicyError, "self-approval"):
            validate_pr_topology(prs)

    def test_stale_or_extra_required_check_fails(self) -> None:
        checks = {name: "success" for name in load_invariant_manifest()["required_check_contexts"]}
        validate_required_checks(checks)
        checks.pop("Artifact smoke")
        checks["Artifact smoke (old)"] = "success"
        with self.assertRaisesRegex(PolicyError, "required check mismatch"):
            validate_required_checks(checks)

    def test_unknown_or_unsupported_surface_capability_fails(self) -> None:
        manifest = load_invariant_manifest()
        surfaces = {
            name: {"capability": "api_exportable", "state": state, "evidence_complete": True}
            for name, state in manifest["required_surface_states"].items()
        }
        validate_surface_inventory(surfaces)
        surfaces["pages"]["capability"] = "unknown"
        with self.assertRaisesRegex(PolicyError, "unknown capability"):
            validate_surface_inventory(surfaces)
        surfaces["pages"]["capability"] = "unsupported"
        with self.assertRaisesRegex(PolicyError, "cannot be verified"):
            validate_surface_inventory(surfaces)

    def test_every_publication_operation_is_blocked(self) -> None:
        for operation in load_invariant_manifest()["prohibited_publication_operations"]:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(PolicyError, "outside RC0"):
                    guard_publication_operation(operation)


class ReviewFinalizationTests(unittest.TestCase):
    def test_candidate_records_all_versions_and_only_a_through_e(self) -> None:
        candidate, *_ = complete_review_path()
        payload = candidate["payload"]
        self.assertEqual(set(payload["criteria"]), set("ABCDE"))
        self.assertEqual(
            set(payload["schema_versions"]),
            set(load_invariant_manifest()["contract_schemas"]),
        )
        self.assertIn("review_derivation_algorithm", payload["algorithm_versions"])
        self.assertEqual(payload["tool_versions"]["gstack"], "0.7.1")

    def test_candidate_rejects_criterion_f_or_missing_tool_version(self) -> None:
        with self.assertRaisesRegex(FinalizationError, "A through E only"):
            build_candidate_packet(
                attempt_id="attempt-001",
                criteria={letter: "PASS" for letter in "ABCDEF"},
                release_sha="a" * 40,
                evidence_digests={},
                unresolved_findings=[],
                tool_versions={"nanotaste": "0.1.0", "python": "3.14", "gstack": "0.7"},
                created_at=NOW_TEXT,
            )
        with self.assertRaisesRegex(FinalizationError, "tool versions"):
            build_candidate_packet(
                attempt_id="attempt-001",
                criteria={letter: "PASS" for letter in "ABCDE"},
                release_sha="a" * 40,
                evidence_digests={},
                unresolved_findings=[],
                tool_versions={"nanotaste": "0.1.0", "python": "3.14"},
                created_at=NOW_TEXT,
            )

    def test_verdict_derives_f_and_aggregate_without_truthy_shortcut(self) -> None:
        expected = {
            "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST": (
                "PASS", "READY_FOR_PACKET_FINALIZATION"
            ),
            "NO_GO": ("FAIL", "NO_GO_CANDIDATE"),
            "HUMAN_INPUT_REQUIRED": ("BLOCKED", "HUMAN_INPUT_REQUIRED_CANDIDATE"),
        }
        for verdict, values in expected.items():
            with self.subTest(verdict=verdict):
                _, _, derivation, aggregate, _, _ = complete_review_path(verdict)
                self.assertEqual(derivation["payload"]["criterion_f"], values[0])
                self.assertEqual(aggregate["payload"]["candidate"], values[1])

    def test_hand_sealed_review_cannot_force_f_pass(self) -> None:
        candidate = build_candidate_packet(
            attempt_id="attempt-001",
            criteria={"A": "FAIL", **{letter: "PASS" for letter in "BCDE"}},
            release_sha="a" * 40,
            evidence_digests={},
            unresolved_findings=["criterion A failed"],
            tool_versions={"nanotaste": "0.1.0", "python": "3.14", "gstack": "0.7.1"},
            created_at=NOW_TEXT,
        )
        review = seal_record(
            SCHEMAS[17],
            "attempt-001",
            {
                "candidate_packet_digest": candidate["digest"],
                "verdict": "CONDITIONAL_GO_TO_VISIBILITY_AND_FORK_TEST",
                "findings": [],
                "reviewer": "hand-sealed",
                "reviewed_at": NOW_TEXT,
                "tool_versions": {"gstack": "0.7.1"},
            },
            NOW_TEXT,
        )
        with self.assertRaisesRegex(FinalizationError, "A-E all PASS"):
            derive_criterion_f(candidate, review, NOW_TEXT)

    def test_hand_sealed_aggregate_cannot_force_f_pass(self) -> None:
        candidate, review, _derivation, aggregate, _payload, _detached = complete_review_path(
            "NO_GO"
        )
        forged = seal_record(
            SCHEMAS[18],
            "attempt-001",
            {
                "criteria": {**candidate["payload"]["criteria"], "F": "PASS"},
                "verdict": "NO_GO",
                "criterion_f": "PASS",
                "candidate": "READY_FOR_PACKET_FINALIZATION",
                "derivation_algorithm_version": "nanotaste-review-derivation/1",
            },
            NOW_TEXT,
        )
        with self.assertRaisesRegex(FinalizationError, "fixed review derivation"):
            build_final_packet_payload(
                candidate,
                review,
                forged,
                evidence_manifest={},
                source={"branch": "testing", "commit": "a" * 40},
                tool_versions={"nanotaste": "0.1.0"},
                created_at=NOW_TEXT,
            )
        self.assertEqual(aggregate["payload"]["criterion_f"], "FAIL")

    def test_detached_digest_detects_payload_mutation(self) -> None:
        _, _, _, _, final_payload, detached = complete_review_path()
        verify_detached_digest(final_payload, detached)
        final_payload["payload"]["source"]["commit"] = "b" * 40
        with self.assertRaises((FinalizationError, ValueError)):
            verify_detached_digest(final_payload, detached)

    def test_final_payload_has_no_terminal_state_or_self_digest(self) -> None:
        _, _, _, _, final_payload, _ = complete_review_path()
        payload = final_payload["payload"]
        self.assertNotIn("terminal_state", payload)
        self.assertNotIn("final_packet_digest", payload)
        self.assertNotIn("digest", payload)

    def test_terminal_mapping_only_moves_conservatively(self) -> None:
        self.assertEqual(
            proposed_terminal_state("READY_FOR_PACKET_FINALIZATION", "PASS"),
            "RELEASE_READY_PRIVATE",
        )
        self.assertEqual(
            proposed_terminal_state("READY_FOR_PACKET_FINALIZATION", "NO_GO"),
            "NO_GO_PRIVATE",
        )
        self.assertEqual(
            proposed_terminal_state("READY_FOR_PACKET_FINALIZATION", "HUMAN_INPUT_REQUIRED"),
            "HUMAN_INPUT_REQUIRED_PRIVATE",
        )

    def make_transition(self) -> dict:
        candidate, review, _, aggregate, final_payload, detached = complete_review_path()
        return build_terminal_transition(
            attempt_id="attempt-001",
            detached=detached,
            final_payload=final_payload,
            candidate=candidate,
            review=review,
            aggregate=aggregate,
            terminal_preflight_digest="preflight-1",
            current_state_digest="state-1",
            delegation_result="ACTIVE",
            reserve_result="PASS",
            source_branch="testing",
            source_commit="a" * 40,
            preflight_result="PASS",
            reason="all evidence passed",
            created_at=NOW_TEXT,
        )

    def test_atomic_transition_crashes_recover_exact_record(self) -> None:
        transition = self.make_transition()
        for failpoint in ("after_transition_record", "during_state_update"):
            with self.subTest(failpoint=failpoint), TemporaryDirectory() as temp_dir:
                directory = Path(temp_dir)
                with self.assertRaises(StorageError):
                    persist_terminal_transition(directory, transition, failpoint=failpoint)
                self.assertFalse((directory / "terminal-state.json").exists())
                recovered = recover_terminal_transition(directory)
                self.assertEqual(recovered["transition_record_digest"], transition["digest"])
                self.assertEqual(recovered["terminal_state"], "RELEASE_READY_PRIVATE")

    def test_crash_before_transition_leaves_no_terminal_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            with self.assertRaises(StorageError):
                persist_terminal_transition(
                    directory,
                    self.make_transition(),
                    failpoint="before_transition_record",
                )
            self.assertEqual(list(directory.glob("*.json")), [])

    def test_crash_after_state_update_is_idempotently_recoverable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            transition = self.make_transition()
            with self.assertRaises(StorageError):
                persist_terminal_transition(
                    directory,
                    transition,
                    failpoint="after_state_update",
                )
            recovered = recover_terminal_transition(directory)
            self.assertEqual(recovered["transition_record_digest"], transition["digest"])

    def test_competing_transition_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            transition = self.make_transition()
            persist_terminal_transition(directory, transition)
            competing = copy.deepcopy(transition)
            competing["digest"] = "0" * 64
            with self.assertRaises((FinalizationError, ValueError)):
                persist_terminal_transition(directory, competing)

    def test_outcome_unknown_cannot_enter_finalization(self) -> None:
        with self.assertRaisesRegex(FinalizationError, "cannot enter"):
            guard_outcome_unknown("OUTCOME_UNKNOWN_PRIVATE")


if __name__ == "__main__":
    unittest.main()
