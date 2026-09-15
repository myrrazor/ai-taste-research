from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

import nanotaste
from nanotaste.rc0.invariants import load_invariant_manifest
from nanotaste.rc0.privacy import require_clean, scan_worktree

ROOT = Path(__file__).parents[1]


class RepositoryPolicyTests(unittest.TestCase):
    def test_release_tree_has_no_private_pattern_matches(self) -> None:
        require_clean(scan_worktree(ROOT))

    def test_every_action_is_full_sha_pinned_and_checkout_is_credentialless(self) -> None:
        for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            text = workflow.read_text()
            for number, line in enumerate(text.splitlines(), start=1):
                if "uses:" not in line:
                    continue
                reference = line.rsplit("@", 1)[-1].strip()
                self.assertRegex(reference, r"^[0-9a-f]{40}$", f"{workflow}:{number}")
            if "actions/checkout@" in text:
                self.assertIn("persist-credentials: false", text, str(workflow))

    def test_dependabot_version_updates_are_not_configured(self) -> None:
        self.assertFalse((ROOT / ".github" / "dependabot.yml").exists())

    def test_workflows_have_no_privileged_or_publication_surface(self) -> None:
        workflow_text = "\n".join(
            path.read_text() for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))
        )
        for forbidden in (
            "pull_request_target",
            "id-token: write",
            "packages: write",
            "contents: write",
            "pypa/gh-action-pypi-publish",
            "softprops/action-gh-release",
        ):
            self.assertNotIn(forbidden, workflow_text)

    def test_literal_required_check_contexts_are_implemented(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        codeql = (ROOT / ".github" / "workflows" / "codeql.yml").read_text()
        dependency = (ROOT / ".github" / "workflows" / "dependency-review.yml").read_text()
        implemented = ci + codeql + dependency
        for check in load_invariant_manifest()["required_check_contexts"]:
            if check.endswith(("Python 3.11", "Python 3.12", "Python 3.13", "Python 3.14")):
                os_name, version = check.split(" / Python ")
                self.assertIn("name: ${{ matrix.os }} / Python ${{ matrix.python-version }}", ci)
                self.assertIn(f"os: {os_name}", ci, check)
                self.assertIn(f'python-version: "{version}"', ci, check)
            elif check.startswith("CodeQL / "):
                language = check.removeprefix("CodeQL / ")
                self.assertIn("name: CodeQL / ${{ matrix.language }}", codeql)
                self.assertRegex(codeql, rf"(?m)^\s+- {re.escape(language)}$")
            else:
                self.assertIn(check, implemented, check)

    def test_security_and_release_docs_do_not_claim_unverified_contact_or_release(self) -> None:
        security = (ROOT / "SECURITY.md").read_text()
        release = (ROOT / "docs" / "RELEASE.md").read_text()
        rules = (ROOT / "docs" / "REPOSITORY_RULES.md").read_text()
        self.assertIn("has not yet completed", security)
        self.assertIn("not ready for public visibility", release)
        self.assertNotIn("owner in an emergency", rules)
        self.assertIn("Do not configure bypass actors", rules)

    def test_claim_lock_names_lexical_and_unvalidated_boundary(self) -> None:
        claims = (ROOT / "docs" / "RC0_CLAIMS.md").read_text().lower()
        for phrase in ("deterministic and lexical", "has not demonstrated", "does not learn"):
            self.assertIn(phrase, claims)

    def test_rc0_public_metadata_and_docs_stay_aligned(self) -> None:
        repository_url = "https://github.com/myrrazor/ai-taste-research"
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
        readme = (ROOT / "README.md").read_text()
        release_notes = (ROOT / "RELEASE_NOTES_RC0.md").read_text()

        self.assertEqual(metadata["project"]["version"], "0.1.0rc0")
        self.assertEqual(metadata["project"]["version"], nanotaste.__version__)
        self.assertEqual(metadata["project"]["urls"]["Repository"], repository_url)
        self.assertIn(repository_url, readme)
        self.assertIn("v0.1.0-rc0", readme)
        self.assertIn("has not demonstrated human preference alignment", readme)
        self.assertIn("v0.1.0-rc0", release_notes)
        self.assertIn("not probabilities", release_notes)

    def test_readme_documents_the_real_cli_surface_and_calibration_limits(self) -> None:
        readme = (ROOT / "README.md").read_text()
        release_notes = (ROOT / "RELEASE_NOTES_RC0.md").read_text()
        for flag in ("--version", "--candidate-file", "--candidates", "--no-taste",
                     "--allow-outside-paths"):
            self.assertIn(flag, readme, flag)
        self.assertNotIn("candidate-file, calibration, and update-proposal commands", readme)
        for text in (readme, release_notes):
            self.assertIn("synthetic", text)
            self.assertIn("not evidence", text)


if __name__ == "__main__":
    unittest.main()
