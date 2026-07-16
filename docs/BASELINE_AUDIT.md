# Sprint 0 Baseline Audit

> Historical Sprint 0 snapshot. This is not current RC0 release evidence. Commands and
> model-review excerpts below describe the state observed at the recorded commit only.

Date: 2026-06-18

Sprint 0 scope: establish source truth, add minimal CI, prove the package can build/install/run from a clean wheel, and document discrepancies before any security/schema/storage rewrites.

## Executive Summary

- Branch used for Sprint 0: `chore/sprint-0-baseline-ci`.
- Baseline commit: `99001300639fe36b8ee0066499d9cea7542f44ef`.
- Starting state was not clean. The prior NanoTaste implementation existed as uncommitted work on `feat/nanotaste-harness`; Sprint 0 records that state instead of rewriting it.
- Existing source tests pass locally with `PYTHONPATH=src`: 39 tests, 0 failures.
- Installed-wheel smoke tests pass locally for all current CLI command families.
- Minimal CI workflow was added for current tests, wheel build/install, and CLI smoke tests.
- CI has not run yet because there is no configured git remote in this checkout. Local build/install/smoke checks are recorded as the current proof until the branch is pushed elsewhere and GitHub Actions can execute.
- No security, schema, storage, or research-workflow behavior was changed in Sprint 0.

## Repository State

Command:

```bash
git status --short --branch
```

Result at Sprint 0 start after creating the Sprint 0 branch:

```text
## chore/sprint-0-baseline-ci
 M .gitignore
 M README.md
?? data/
?? docs/
?? examples/
?? pyproject.toml
?? src/
?? tests/
```

Note: this is the start snapshot before adding `.github/workflows/ci.yml`, `docs/BASELINE_AUDIT.md`, `docs/SPRINT_0_HANDOFF.md`, and `docs/reviews/sprint0_opus_review.md`.

Tracked files at baseline commit:

```text
.gitignore
LICENSE
README.md
```

Working-tree file inventory at audit time, excluding `.git` and local virtualenvs:

```text
./.gitignore
./LICENSE
./README.md
./data/calibration/starter_prompts.json
./docs/AGENT_SPRINTS.md
./examples/TASTE.example.md
./pyproject.toml
./src/nanotaste/__init__.py
./src/nanotaste/agent.py
./src/nanotaste/calibration.py
./src/nanotaste/cli.py
./src/nanotaste/discovery.py
./src/nanotaste/domains.py
./src/nanotaste/generator.py
./src/nanotaste/records.py
./src/nanotaste/schema.py
./src/nanotaste/scoring.py
./src/nanotaste/update.py
./tests/test_agent.py
./tests/test_calibration.py
./tests/test_cli_and_updates.py
./tests/test_generator.py
./tests/test_schema.py
./tests/test_scoring.py
```

## Platform and Python

Commands:

```bash
python3 --version
python3 -c 'import sys, platform; print(sys.executable); print(platform.platform()); print(platform.machine())'
```

Result:

```text
Python 3.9.6
/Library/Developer/CommandLineTools/usr/bin/python3
macOS-26.5.1-arm64-arm-64bit
arm64
```

Sprint plan target: Python `>=3.11`. Local baseline remains Python 3.9.6 until Sprint 2 raises the package baseline and CI matrix.

## Local Test Baseline

Command:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Result:

```text
.......................................
----------------------------------------------------------------------
Ran 39 tests in 0.027s

OK
```

Meaning:

- The current tests require `PYTHONPATH=src` when running from source without installing the package.
- This matches the prior implementation report's 39-test claim.

## Source CLI Baseline

Command without source path:

```bash
python3 -m nanotaste.cli --help
```

Result:

```text
/Library/Developer/CommandLineTools/usr/bin/python3: Error while finding module specification for 'nanotaste.cli' (ModuleNotFoundError: No module named 'nanotaste')
```

Interpretation:

- Expected for an uninstalled `src/` layout project.
- Tests and source CLI commands currently need `PYTHONPATH=src`.

Command with source path:

```bash
PYTHONPATH=src python3 -m nanotaste.cli --help
```

Result:

```text
usage: nanotaste [-h] {run,compare,propose-update,calibrate} ...
```

Source smoke commands also succeeded for:

- `run --domain design --prompt ... --no-record --json`
- `compare --domain writing --prompt ... --candidates ... --no-record --json`

## Build and Installed-Wheel Baseline

Build setup:

```bash
python3 -m venv .venv/sprint0-build
.venv/sprint0-build/bin/python -m pip install --upgrade pip build
.venv/sprint0-build/bin/python -m build
python3 -m venv .venv/sprint0-install
.venv/sprint0-install/bin/python -m pip install --upgrade pip
.venv/sprint0-install/bin/python -m pip install dist/*.whl
```

Result:

- `python -m build` succeeded.
- Wheel install succeeded.
- Installed `nanotaste` CLI was available.
- Build emitted a setuptools deprecation warning: `project.license` as a TOML table is deprecated and should become an SPDX string before the 2027-02-18 setuptools deadline.

Installed-wheel smoke commands that succeeded:

```bash
nanotaste --help
nanotaste run --domain design --prompt "Design a landing page for a coffee subscription" --taste-file examples/TASTE.example.md --no-record --json
nanotaste compare --domain writing --prompt "Write a launch note" --taste-file examples/TASTE.example.md --candidates <two local files> --no-record --json
nanotaste propose-update --domain writing --before <file> --after <file> --output-dir <ignored scratch dir> --json
nanotaste calibrate prepare --taste-file examples/TASTE.example.md --prompt-set data/calibration/starter_prompts.json --output-dir <ignored scratch dir> --json
nanotaste calibrate evaluate --run <run file> --picks <picks file> --output <evaluation.md> --json
```

Important smoke-test note:

- Smoke commands that resolve taste use `--taste-file examples/TASTE.example.md` to avoid reading wrapper-level private `TASTE.md` through upward discovery.
- `propose-update` does not accept `--taste-file` and does not resolve taste; it is safe in this smoke path because it only reads the explicit before/after files.

## Minimal CI Added

File:

```text
.github/workflows/ci.yml
```

The workflow:

- uses `permissions: contents: read`;
- pins `actions/checkout` to `34e114876b0b11c390a56381ad16ebd13914f8d5`;
- pins `actions/setup-python` to `a26af69be951a213d495a4c3e4e4022e16d87065`;
- runs the current unittest suite with `PYTHONPATH=src`;
- builds source and wheel distributions;
- installs the built wheel into a venv;
- smoke-tests `help`, `run`, `compare`, `propose-update`, `calibrate prepare`, and `calibrate evaluate`.

This is intentionally minimal. Expanded matrices, Ruff, type checking, coverage, CodeQL, Dependabot, Scorecard, CODEOWNERS, and repository rules belong to later authorized sprints.

CI proof status:

- Workflow definition exists locally.
- GitHub Actions has not executed this workflow.
- A green CI run is pending until the baseline scaffold and Sprint 0 artifacts are committed, pushed, and opened as a PR by the approved release flow.

## Source-vs-Report Discrepancies

Compared to `PROJECT_IMPLEMENTATION_REPORT.md` and the engineering audit:

- The report describes the NanoTaste implementation as project files; source truth shows those implementation files are currently untracked work, not committed project history.
- The report says the branch was `feat/nanotaste-harness`; Sprint 0 now runs on `chore/sprint-0-baseline-ci`.
- The report says `TEST_STDOUT.log` is current proof; source truth showed it as a stale local artifact during the initial Sprint 0 audit. It was removed before committing the baseline and should not return as a source proof mechanism.
- The attached audit's statement that no `LICENSE` was listed is outdated for this checkout: `LICENSE` exists and is MIT.
- The audit's warning that `python -m build` was not available in the local system Python is accurate before creating a build venv.
- The audit's warning about Python 3.9 is accurate: local baseline is Python 3.9.6 while the remediation target is Python 3.11+.
- The audit's concern that wrapper/private taste can influence runs is relevant: default upward discovery can read parent wrapper taste files unless callers pass `--taste-file` or run from a bounded root. Sprint 1 must address project-boundary and discovery policy.

## Packaging Metadata Observations

- Project name: `ai-taste-research`.
- Version: `0.1.0`.
- CLI entry point: `nanotaste = "nanotaste.cli:main"`.
- Current `requires-python`: `>=3.9`.
- Current license metadata uses a TOML table and emits a setuptools deprecation warning.
- No explicit `[build-system]` table exists; the build relies on default setuptools behavior.

## Known Risks Carried Forward

- Current working tree started dirty because the NanoTaste scaffold was not committed.
- There is no configured git remote, so a real GitHub Actions run cannot be produced from this checkout. Before any public PR/release, push this branch to a remote and verify a green CI run.
- `TEST_STDOUT.log` is still present as an untracked file from prior work.
- Default discovery can walk into wrapper-level private taste files.
- The current scorer remains lexical and unvalidated.
- Calibration still uses synthetic candidates unless external candidates are provided.
- Review/private calibration artifacts are not physically separated yet.
- There is no typed profile schema, versioned record schema, or threat model yet.
- There is no expanded CI matrix, linting, type checking, coverage, CodeQL, Dependabot, or release governance yet.

## Sprint 0 Exit Criteria

- Baseline audit written: complete.
- Minimal CI workflow added: complete.
- Minimal CI executed by GitHub Actions: blocked locally by missing git remote; pending before PR/release.
- Current tests run locally: complete.
- Wheel build/install verified locally: complete.
- Installed CLI smoke verified locally: complete.
- No behavior changes beyond CI/docs: complete.
- Opus review gate: complete; review found no blockers, but required this audit to distinguish local verification from unexecuted CI and to make the committed-baseline requirement explicit.

## Opus 4.8 Review Summary

Review command used pinned model `claude-opus-4-8` through Claude Code `2.1.181`.

Review verdict:

- No `BLOCKER` findings.
- Two `HIGH` findings about CI proof being overclaimed before an actual GitHub Actions run.
- Three `MEDIUM` findings about committed-baseline prerequisites, Python version support gap, and handoff risk coverage.
- Three `LOW` findings about `TEST_STDOUT.log`, smoke-test rationale wording, and `git diff --check` not covering untracked files.

Sprint 0 remediation applied after review:

- Reworded audit and handoff to distinguish locally verified build/install/smoke from CI-verified proof.
- Added an explicit Sprint 1 prerequisite that the baseline scaffold and Sprint 0 artifacts need a decided commit/branch strategy and green CI run before security work starts.
- Expanded handoff risks so Sprint 1 does not miss known research/security/schema gaps.
- A second Opus pass found no blocker, high, or medium findings and accepted Sprint 0 for human handoff with CI execution still pending.
- The stale root `TEST_STDOUT.log` artifact was removed before baseline commit.
