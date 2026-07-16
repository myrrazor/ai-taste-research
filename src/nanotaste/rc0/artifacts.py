"""Canonical RC0 package artifact manifests."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from nanotaste.rc0.canonical import canonical_bytes
from nanotaste.rc0.invariants import EXPECTED_INVARIANT_DIGEST, load_invariant_manifest

ARTIFACT_MANIFEST_SCHEMA = "nanotaste/rc0-artifact-manifest/1.0"
ARTIFACT_ALGORITHM_VERSION = "nanotaste-artifact-manifest/1"


class ArtifactError(ValueError):
    """Raised when canonical package artifacts do not match their manifest."""


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact_manifest(dist_dir: Path, source_sha: str) -> dict[str, Any]:
    """Build a manifest for exactly one wheel and one verified sdist."""
    load_invariant_manifest()
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise ArtifactError(f"expected exactly one wheel, found {len(wheels)}")
    if len(sdists) != 1:
        raise ArtifactError(f"SDIST_VERIFIED requires exactly one sdist, found {len(sdists)}")
    artifacts = []
    for kind, path in (("wheel", wheels[0]), ("sdist", sdists[0])):
        artifacts.append(
            {
                "kind": kind,
                "filename": path.name,
                "bytes": path.stat().st_size,
                "sha256": _file_digest(path),
            }
        )
    return {
        "schema": ARTIFACT_MANIFEST_SCHEMA,
        "algorithm_version": ARTIFACT_ALGORITHM_VERSION,
        "invariant_manifest_digest": EXPECTED_INVARIANT_DIGEST,
        "source_sha": source_sha,
        "sdist_state": "SDIST_VERIFIED",
        "artifacts": artifacts,
    }


def verify_artifact_manifest(dist_dir: Path, manifest: dict[str, Any]) -> None:
    """Fail closed unless artifact names, sizes, hashes, and versions match."""
    load_invariant_manifest()
    allowed = {
        "schema",
        "algorithm_version",
        "invariant_manifest_digest",
        "source_sha",
        "sdist_state",
        "artifacts",
    }
    unknown = set(manifest) - allowed
    if unknown:
        raise ArtifactError(f"unknown artifact manifest fields: {', '.join(sorted(unknown))}")
    if set(manifest) != allowed:
        raise ArtifactError("artifact manifest is missing required fields")
    if manifest["schema"] != ARTIFACT_MANIFEST_SCHEMA:
        raise ArtifactError("unsupported artifact manifest schema")
    if manifest["algorithm_version"] != ARTIFACT_ALGORITHM_VERSION:
        raise ArtifactError("unsupported artifact manifest algorithm")
    if manifest["invariant_manifest_digest"] != EXPECTED_INVARIANT_DIGEST:
        raise ArtifactError("artifact manifest references the wrong RC0 invariants")
    if manifest["sdist_state"] != "SDIST_VERIFIED":
        raise ArtifactError("RC0 requires an explicitly verified sdist")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise ArtifactError("artifact manifest must contain one wheel and one sdist")
    kinds = [item.get("kind") for item in artifacts if isinstance(item, dict)]
    if kinds != ["wheel", "sdist"]:
        raise ArtifactError("artifact kinds or order do not match the RC0 contract")
    for item in artifacts:
        if set(item) != {"kind", "filename", "bytes", "sha256"}:
            raise ArtifactError("artifact entry fields do not match the RC0 contract")
        path = dist_dir / item["filename"]
        if not path.is_file():
            raise ArtifactError(f"artifact is missing: {item['filename']}")
        if path.stat().st_size != item["bytes"]:
            raise ArtifactError(f"artifact size mismatch: {item['filename']}")
        if _file_digest(path) != item["sha256"]:
            raise ArtifactError(f"artifact digest mismatch: {item['filename']}")


def write_artifact_manifest(dist_dir: Path, source_sha: str, output: Path) -> None:
    """Write the canonical artifact manifest with a final newline."""
    output.write_bytes(canonical_bytes(build_artifact_manifest(dist_dir, source_sha)) + b"\n")


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ArtifactError("artifact manifest must be a JSON object")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    """Create or verify a canonical package artifact manifest."""
    parser = argparse.ArgumentParser(prog="python -m nanotaste.rc0.artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--dist-dir", type=Path, required=True)
    create.add_argument("--source-sha", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--dist-dir", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            write_artifact_manifest(args.dist_dir, args.source_sha, args.output)
        else:
            verify_artifact_manifest(args.dist_dir, _load_manifest(args.manifest))
    except (ArtifactError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
