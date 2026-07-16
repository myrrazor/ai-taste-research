from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from nanotaste.rc0.contracts import SCHEMAS, seal_record
from nanotaste.rc0.invariants import load_invariant_manifest
from nanotaste.rc0.preflight import (
    SOURCE_BRANCH,
    SOURCE_COMMIT,
    PreflightError,
    PreflightInput,
    build_preflight,
)
from nanotaste.rc0.privacy import PrivacyError, require_clean, scan_git_history, scan_worktree
from nanotaste.rc0.signatures import SignatureError, signature_message, verify_ssh_signature

NOW = "2026-07-11T22:45:00Z"


def valid_preflight(**changes):
    artifacts = load_invariant_manifest()["controlling_artifacts"]
    values = {
        "attempt_id": "attempt-001",
        "created_at": NOW,
        "delegation_digest": "delegation-1",
        "delegation_expires_at": "2026-07-11T23:59:59-04:00",
        "delegation_active": True,
        "remaining_capacity_percent": 94,
        "projected_capacity_percent": 90,
        "claude_enabled": False,
        "gstack_mode": "READ_ONLY",
        "plan_digest": artifacts["plan_sha256"],
        "review_digest": artifacts["review_sha256"],
        "state_digest": "state-1",
        "state_current": True,
        "source_branch": SOURCE_BRANCH,
        "source_commit": SOURCE_COMMIT,
        "git_clean": True,
        "remotes": [],
        "binding_graph_head": "ABSENT",
        "ledger_head": "ABSENT",
        "security_state_digest": "UNOBSERVED",
        "external_authorization_present": False,
        "external_action": False,
    }
    values.update(changes)
    return PreflightInput(**values)


def signed_binding(signature: str) -> dict:
    return seal_record(
        SCHEMAS[4],
        "attempt-001",
        {
            "binding_id": "binding-1",
            "resource_type": "repository",
            "immutable_identifiers": {"id": 1},
            "bound_fields": {"visibility": "private"},
            "resource_state_digest": "state-1",
            "observation_actor": "owner",
            "observation_source": "api",
            "observed_at": NOW,
            "issued_at": NOW,
            "expires_at": "2026-07-12T22:45:00Z",
            "trust_anchor_digest": "trust-1",
            "predecessor_binding_digests": [],
            "originating_authorization_digest": "auth-1",
            "terminal_event_digest": "event-1",
            "signature": signature,
        },
        NOW,
    )


class PreflightTests(unittest.TestCase):
    def test_valid_local_only_preflight_passes_and_is_versioned(self) -> None:
        record = build_preflight(valid_preflight())
        self.assertEqual(record["payload"]["decision"]["result"], "PASS_LOCAL_ONLY")
        self.assertEqual(record["schema"], SCHEMAS[1])

    def test_reserve_missing_delegation_or_stale_state_fails(self) -> None:
        cases = (
            ({"remaining_capacity_percent": 4}, "five percent"),
            ({"delegation_active": False}, "delegation"),
            ({"delegation_expires_at": "2026-07-11T17:00:00-04:00"}, "inactive"),
            ({"state_current": False}, "stale"),
            ({"claude_enabled": True}, "Claude"),
            ({"gstack_mode": "WRITE"}, "read-only"),
        )
        for changes, message in cases:
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(PreflightError, message):
                    build_preflight(valid_preflight(**changes))

    def test_stale_plan_review_or_source_fails(self) -> None:
        for changes in (
            {"plan_digest": "old"},
            {"review_digest": "old"},
            {"source_commit": "0" * 40},
            {"source_branch": "wrong"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PreflightError):
                    build_preflight(valid_preflight(**changes))

    def test_plan_approval_never_implies_external_authorization(self) -> None:
        with self.assertRaisesRegex(PreflightError, "external operation"):
            build_preflight(valid_preflight(external_action=True))


class SignatureTests(unittest.TestCase):
    def test_signature_message_excludes_signature_and_outer_digest(self) -> None:
        record = signed_binding("-----BEGIN SSH SIGNATURE-----\nsig\n-----END SSH SIGNATURE-----")
        message = signature_message(record)
        self.assertNotIn(b"SSH SIGNATURE", message)
        self.assertNotIn(record["digest"].encode(), message)

    def test_verifier_uses_argument_vector_and_message_stdin(self) -> None:
        record = signed_binding("-----BEGIN SSH SIGNATURE-----\nsig\n-----END SSH SIGNATURE-----")
        with TemporaryDirectory() as temp_dir:
            signers = Path(temp_dir) / "allowed_signers"
            signers.write_text("owner ssh-ed25519 AAAA\n")
            completed = subprocess.CompletedProcess([], 0, b"Good signature", b"")
            with patch("nanotaste.rc0.signatures.subprocess.run", return_value=completed) as run:
                verify_ssh_signature(
                    record,
                    allowed_signers_file=signers,
                    identity="owner",
                    namespace="nanotaste-rc0-binding",
                )
            args = run.call_args.args[0]
            self.assertEqual(args[:3], ["ssh-keygen", "-Y", "verify"])
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertEqual(run.call_args.kwargs["input"], signature_message(record))

    def test_missing_or_bad_signature_fails_closed(self) -> None:
        record = signed_binding("not-armored")
        with self.assertRaisesRegex(SignatureError, "armored"):
            verify_ssh_signature(
                record,
                allowed_signers_file=Path("missing"),
                identity="owner",
                namespace="binding",
            )


class PrivacyTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE)

    def test_worktree_scan_reports_policy_without_echoing_secret(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            secret = "ghp" + "_1234567890abcdefghijklmnop"
            (root / "leak.txt").write_text(secret)
            findings = scan_worktree(root)
            self.assertEqual(findings[0].policy, "github_token")
            with self.assertRaises(PrivacyError) as raised:
                require_clean(findings)
            self.assertNotIn(secret, str(raised.exception))

    def test_full_history_finds_deleted_private_path(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.email", "test@example.invalid")
            self.git(root, "config", "user.name", "NanoTaste Test")
            leak = root / "leak.txt"
            leak.write_text("private at /" + "Users/example/private/TASTE.md")
            self.git(root, "add", "leak.txt")
            self.git(root, "commit", "-qm", "add leak")
            leak.unlink()
            self.git(root, "add", "-u")
            self.git(root, "commit", "-qm", "remove leak")
            findings = scan_git_history(root)
            self.assertTrue(any(item.policy == "absolute_home_path" for item in findings))

    def test_clean_tree_passes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "safe.txt").write_text("public example")
            require_clean(scan_worktree(root))

    @unittest.skipIf(os.name == "nt", "symlink creation is privilege-dependent")
    def test_release_symlink_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target.txt"
            target.write_text("safe")
            (root / "linked.txt").symlink_to(target)
            findings = scan_worktree(root)
            self.assertTrue(any(item.policy == "symlink_release_input" for item in findings))


if __name__ == "__main__":
    unittest.main()
