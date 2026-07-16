from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nanotaste.rc0.canonical import CanonicalizationError, canonical_bytes, content_digest
from nanotaste.rc0.contracts import (
    PAYLOAD_FIELDS,
    SCHEMAS,
    ContractError,
    seal_record,
    validate_record,
)
from nanotaste.rc0.invariants import (
    EXPECTED_INVARIANT_DIGEST,
    InvariantError,
    load_invariant_manifest,
    validate_invariant_reference,
)

NOW = "2026-07-11T22:45:00Z"


def full_payload(schema: str) -> dict[str, object]:
    return {name: f"value:{name}" for name in PAYLOAD_FIELDS[schema]}


class CanonicalJsonTests(unittest.TestCase):
    def test_canonical_json_normalizes_unicode_and_key_order(self) -> None:
        composed = {"b": 2, "a": "e\u0301"}
        normalized = {"a": "\u00e9", "b": 2}
        self.assertEqual(canonical_bytes(composed), canonical_bytes(normalized))

    def test_canonical_json_preserves_array_order(self) -> None:
        self.assertNotEqual(content_digest(["a", "b"]), content_digest(["b", "a"]))

    def test_canonical_json_rejects_floats(self) -> None:
        with self.assertRaises(CanonicalizationError):
            canonical_bytes({"confidence": 0.9})


class InvariantManifestTests(unittest.TestCase):
    def test_manifest_digest_is_frozen(self) -> None:
        manifest = load_invariant_manifest()
        self.assertEqual(content_digest(manifest), EXPECTED_INVARIANT_DIGEST)

    def test_every_contract_and_algorithm_version_is_recorded(self) -> None:
        manifest = load_invariant_manifest()
        self.assertEqual(set(manifest["contract_schemas"]), set(SCHEMAS))
        self.assertIn("review_derivation_algorithm", manifest["versions"])
        self.assertIn("terminal_transition_algorithm", manifest["versions"])
        self.assertIn("control_tool", manifest["versions"])

    def test_required_approval_invariants_are_frozen(self) -> None:
        manifest = load_invariant_manifest()
        topology = manifest["pr_topology"]
        self.assertEqual(len(topology), 4)
        self.assertEqual(topology["IMPLEMENTATION_INTEGRATION_PR"]["cardinality"], "exactly_one")
        self.assertTrue(manifest["reviewer_separation"]["self_approval_prohibited"])
        self.assertIn("Artifact smoke", manifest["required_check_contexts"])
        self.assertEqual(manifest["github_surface_capabilities"]["unsupported"], "fail_closed")
        self.assertIn("publish_pypi", manifest["prohibited_publication_operations"])

    def test_any_manifest_change_changes_digest(self) -> None:
        manifest = load_invariant_manifest()
        changed = copy.deepcopy(manifest)
        changed["required_check_contexts"].remove("Artifact smoke")
        self.assertNotEqual(content_digest(changed), EXPECTED_INVARIANT_DIGEST)

    def test_dependent_evidence_rejects_wrong_manifest_digest(self) -> None:
        with self.assertRaises(InvariantError):
            validate_invariant_reference({"invariant_manifest_digest": "0" * 64})


class ContractTests(unittest.TestCase):
    def test_all_versioned_contracts_can_be_sealed_and_validated(self) -> None:
        for schema in SCHEMAS:
            with self.subTest(schema=schema):
                record = seal_record(schema, "attempt-001", full_payload(schema), NOW)
                validate_record(record)

    def test_unknown_top_level_field_is_rejected(self) -> None:
        schema = SCHEMAS[0]
        record = seal_record(schema, "attempt-001", full_payload(schema), NOW)
        record["ignored_future_field"] = True
        with self.assertRaisesRegex(ContractError, "unknown top-level"):
            validate_record(record)

    def test_unknown_payload_field_is_rejected(self) -> None:
        schema = SCHEMAS[0]
        payload = full_payload(schema)
        payload["surprise"] = "ignored"
        with self.assertRaisesRegex(ContractError, "unknown payload"):
            seal_record(schema, "attempt-001", payload, NOW)

    def test_extensions_are_explicit_and_digest_bound(self) -> None:
        schema = SCHEMAS[0]
        record = seal_record(
            schema,
            "attempt-001",
            full_payload(schema),
            NOW,
            extensions={"vendor.example/field": "value"},
        )
        validate_record(record)
        record["extensions"]["vendor.example/field"] = "changed"
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_record(record)

    def test_unsupported_schema_version_is_rejected(self) -> None:
        schema = SCHEMAS[0]
        record = seal_record(schema, "attempt-001", full_payload(schema), NOW)
        record["schema"] = schema.replace("/1.0", "/2.0")
        with self.assertRaisesRegex(ContractError, "unsupported"):
            validate_record(record)

    def test_record_mutation_invalidates_digest(self) -> None:
        schema = SCHEMAS[0]
        record = seal_record(schema, "attempt-001", full_payload(schema), NOW)
        record["payload"]["owner_identity"] = "different-owner"
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_record(record)

    def test_timestamp_must_be_utc_rfc3339(self) -> None:
        schema = SCHEMAS[0]
        with self.assertRaisesRegex(ContractError, "RFC 3339"):
            seal_record(schema, "attempt-001", full_payload(schema), "2026-07-11 22:45:00")

    def test_manifest_is_packaged_as_json(self) -> None:
        manifest = load_invariant_manifest()
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_bytes(canonical_bytes(manifest))
            self.assertEqual(json.loads(path.read_text()), manifest)


if __name__ == "__main__":
    unittest.main()
