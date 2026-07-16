"""Frozen RC0 repository, PR, and publication policy checks."""

from __future__ import annotations

from collections import Counter
from typing import Any

from nanotaste.rc0.invariants import load_invariant_manifest


class PolicyError(ValueError):
    """Raised when observed release state violates a frozen RC0 invariant."""


def validate_pr_topology(prs: list[dict[str, Any]]) -> str:
    """Validate all four PR classes and return the promotion merge SHA."""
    manifest = load_invariant_manifest()
    topology = manifest["pr_topology"]
    allowed = set(topology)
    counts = Counter(item.get("class") for item in prs)
    unknown = set(counts) - allowed
    if unknown:
        raise PolicyError(f"unknown PR class: {', '.join(sorted(str(item) for item in unknown))}")
    for required in ("IMPLEMENTATION_INTEGRATION_PR", "PROMOTION_INTEGRATION_PR"):
        if counts[required] != 1:
            raise PolicyError(f"{required} must appear exactly once")
    if counts["FORK_SAFETY_TEST_PR"] > 1:
        raise PolicyError("at most one fork safety test PR is allowed")
    integration = [item for item in prs if item["class"].endswith("INTEGRATION_PR")]
    if len(integration) != 2 or any(not item.get("merged") for item in integration):
        raise PolicyError("exactly two merged integration PRs are required")
    reviewer = manifest["reviewer_separation"]["reviewer_login"]
    for item in integration:
        if item.get("author") == item.get("reviewer"):
            raise PolicyError("integration PR self-approval is prohibited")
        if item.get("reviewer") != reviewer:
            raise PolicyError("integration PR reviewer does not match the bound CODEOWNER")
    forks = [item for item in prs if item["class"] == "FORK_SAFETY_TEST_PR"]
    if forks and (forks[0].get("merged") or not forks[0].get("post_visibility")):
        raise PolicyError("fork safety PR must be post-visibility and unmerged")
    incidents = [item for item in prs if item["class"] == "INCIDENT_RECOVERY_PR"]
    if any(not item.get("explicitly_authorized") for item in incidents):
        raise PolicyError("incident recovery PR lacks explicit authorization")
    promotion = next(item for item in prs if item["class"] == "PROMOTION_INTEGRATION_PR")
    merge_sha = promotion.get("merge_sha")
    if not isinstance(merge_sha, str) or len(merge_sha) != 40:
        raise PolicyError("promotion merge SHA is missing or invalid")
    return merge_sha


def validate_required_checks(checks: dict[str, str]) -> None:
    """Require the exact frozen check set, all successful."""
    required = set(load_invariant_manifest()["required_check_contexts"])
    if set(checks) != required:
        missing = required - set(checks)
        extra = set(checks) - required
        raise PolicyError(
            f"required check mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    failed = sorted(name for name, status in checks.items() if status != "success")
    if failed:
        raise PolicyError(f"required checks are not successful: {', '.join(failed)}")


def validate_surface_inventory(surfaces: dict[str, dict[str, Any]]) -> None:
    """Fail closed for unknown, unsupported, incomplete, or wrong-state surfaces."""
    manifest = load_invariant_manifest()
    capabilities = manifest["github_surface_capabilities"]
    required_states = manifest["required_surface_states"]
    for name, expected in required_states.items():
        item = surfaces.get(name)
        if item is None:
            raise PolicyError(f"required GitHub surface is missing: {name}")
        capability = item.get("capability")
        if capability not in capabilities:
            raise PolicyError(f"unknown capability class for {name}")
        if capability == "unsupported" or not item.get("evidence_complete"):
            raise PolicyError(f"GitHub surface cannot be verified: {name}")
        if item.get("state") != expected:
            raise PolicyError(f"GitHub surface state mismatch: {name}")
    unknown = set(surfaces) - set(required_states)
    if unknown:
        raise PolicyError(f"unapproved GitHub surfaces: {', '.join(sorted(unknown))}")


def guard_publication_operation(operation: str) -> None:
    """Block every operation excluded from the local-only RC0 scope."""
    prohibited = set(load_invariant_manifest()["prohibited_publication_operations"])
    if operation in prohibited:
        raise PolicyError(f"publication operation is outside RC0: {operation}")
    raise PolicyError(f"operation is not allowlisted for local RC0: {operation}")
