from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from nanotaste.rc0.governance import (
    CODEOWNERS_BYTES,
    GovernanceError,
    governance_recipe,
    validate_base_codeowners,
    validate_codeowners_bytes,
    validate_governance_commit,
)


class GovernanceTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        )
        return result.stdout.decode().strip()

    def test_frozen_codeowners_file_matches_repository(self) -> None:
        root = Path(__file__).parents[1]
        data = subprocess.run(
            ["git", "show", "HEAD:.github/CODEOWNERS"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        validate_codeowners_bytes(data)
        self.assertEqual(data, CODEOWNERS_BYTES)

    def test_wrong_content_or_line_endings_fail(self) -> None:
        for data in (
            CODEOWNERS_BYTES.replace(b"@masterhit", b"@other", 1),
            CODEOWNERS_BYTES.replace(b"\n", b"\r\n"),
            CODEOWNERS_BYTES.rstrip(b"\n"),
        ):
            with self.subTest(data=data):
                with self.assertRaises(GovernanceError):
                    validate_codeowners_bytes(data)

    def test_recipe_contains_parent_path_mode_and_bases(self) -> None:
        recipe = governance_recipe()
        self.assertEqual(recipe["changed_paths"], [".github/CODEOWNERS"])
        self.assertEqual(recipe["codeowners_mode"], "100644")
        self.assertEqual(recipe["required_base_branches"], ["testing", "main"])

    def test_commit_and_base_validation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.email", "test@example.invalid")
            self.git(root, "config", "user.name", "NanoTaste Test")
            (root / "README.md").write_text("base\n")
            self.git(root, "add", "README.md")
            self.git(root, "commit", "-qm", "base")
            parent = self.git(root, "rev-parse", "HEAD")
            path = root / ".github" / "CODEOWNERS"
            path.parent.mkdir()
            path.write_bytes(CODEOWNERS_BYTES)
            self.git(root, "add", ".github/CODEOWNERS")
            self.git(root, "commit", "-qm", "governance")
            commit = self.git(root, "rev-parse", "HEAD")

            recipe = governance_recipe()
            original_parent = recipe["parent_commit"]
            # The validator deliberately binds to the approved parent. A synthetic repo
            # proves the remaining commit rules by temporarily patching only that value.
            from unittest.mock import patch

            synthetic = {**recipe, "parent_commit": parent}
            with patch("nanotaste.rc0.governance.governance_recipe", return_value=synthetic):
                validate_governance_commit(root, commit)
                validate_base_codeowners(root, commit)
            self.assertNotEqual(parent, original_parent)

    def test_extra_changed_path_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.email", "test@example.invalid")
            self.git(root, "config", "user.name", "NanoTaste Test")
            (root / "README.md").write_text("base\n")
            self.git(root, "add", "README.md")
            self.git(root, "commit", "-qm", "base")
            parent = self.git(root, "rev-parse", "HEAD")
            path = root / ".github" / "CODEOWNERS"
            path.parent.mkdir()
            path.write_bytes(CODEOWNERS_BYTES)
            (root / "extra.txt").write_text("not allowed\n")
            self.git(root, "add", ".")
            self.git(root, "commit", "-qm", "bad governance")
            commit = self.git(root, "rev-parse", "HEAD")
            synthetic = {**governance_recipe(), "parent_commit": parent}
            from unittest.mock import patch

            with patch("nanotaste.rc0.governance.governance_recipe", return_value=synthetic):
                with self.assertRaisesRegex(GovernanceError, "unapproved path"):
                    validate_governance_commit(root, commit)


if __name__ == "__main__":
    unittest.main()
