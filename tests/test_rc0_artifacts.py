from __future__ import annotations

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nanotaste.rc0.artifacts import (
    ARTIFACT_ALGORITHM_VERSION,
    ArtifactError,
    build_artifact_manifest,
    verify_artifact_manifest,
    write_artifact_manifest,
)
from nanotaste.rc0.invariants import EXPECTED_INVARIANT_DIGEST


class ArtifactManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.dist = Path(self.temp.name)
        (self.dist / "ai_taste_research-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
        (self.dist / "ai_taste_research-0.1.0.tar.gz").write_bytes(b"sdist")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_build_and_verify_manifest(self) -> None:
        manifest = build_artifact_manifest(self.dist, "a" * 40)
        verify_artifact_manifest(self.dist, manifest)
        self.assertEqual(manifest["algorithm_version"], ARTIFACT_ALGORITHM_VERSION)
        self.assertEqual(manifest["invariant_manifest_digest"], EXPECTED_INVARIANT_DIGEST)
        self.assertEqual(manifest["sdist_state"], "SDIST_VERIFIED")

    def test_artifact_mutation_fails(self) -> None:
        manifest = build_artifact_manifest(self.dist, "a" * 40)
        (self.dist / "ai_taste_research-0.1.0-py3-none-any.whl").write_bytes(b"changed")
        with self.assertRaisesRegex(ArtifactError, "mismatch"):
            verify_artifact_manifest(self.dist, manifest)

    def test_manifest_invariant_change_fails(self) -> None:
        manifest = build_artifact_manifest(self.dist, "a" * 40)
        changed = copy.deepcopy(manifest)
        changed["invariant_manifest_digest"] = "0" * 64
        with self.assertRaisesRegex(ArtifactError, "wrong RC0 invariants"):
            verify_artifact_manifest(self.dist, changed)

    def test_missing_or_extra_sdist_fails(self) -> None:
        (self.dist / "ai_taste_research-0.1.0.tar.gz").unlink()
        with self.assertRaisesRegex(ArtifactError, "SDIST_VERIFIED"):
            build_artifact_manifest(self.dist, "a" * 40)

    def test_unknown_manifest_field_fails(self) -> None:
        manifest = build_artifact_manifest(self.dist, "a" * 40)
        manifest["future"] = "silently ignored"
        with self.assertRaisesRegex(ArtifactError, "unknown"):
            verify_artifact_manifest(self.dist, manifest)

    def test_written_manifest_is_canonical_and_verifiable(self) -> None:
        output = self.dist / "ARTIFACT_MANIFEST.json"
        write_artifact_manifest(self.dist, "a" * 40, output)
        self.assertTrue(output.read_bytes().endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
