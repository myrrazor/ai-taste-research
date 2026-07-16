# Sprint 0 Handoff

> Historical handoff. It is retained for provenance and does not establish current
> hosted CI, release readiness, or independent-review status.

Date: 2026-06-18

Branch: `chore/sprint-0-baseline-ci`

## What Changed

- Added `docs/BASELINE_AUDIT.md`.
- Added `.github/workflows/ci.yml`.
- Added this handoff document.

No NanoTaste runtime, schema, storage, security, calibration, or scoring behavior was intentionally changed in Sprint 0.

## Commands Run

```bash
git status --short --branch
git rev-parse HEAD
git branch --show-current
git ls-files
find . -path './.git' -prune -o -path './.venv' -prune -o -type f -print | sort
python3 --version
python3 -c 'import sys, platform; print(sys.executable); print(platform.platform()); print(platform.machine())'
PYTHONPATH=src python3 -m unittest discover -s tests
python3 -m nanotaste.cli --help
PYTHONPATH=src python3 -m nanotaste.cli --help
PYTHONPATH=src python3 -m nanotaste.cli run --domain design --prompt 'Design a landing page for a coffee subscription' --no-record --json
PYTHONPATH=src python3 -m nanotaste.cli compare --domain writing --prompt 'Write a launch note' --candidates <two candidate files> --no-record --json
python3 -m venv .venv/sprint0-build
.venv/sprint0-build/bin/python -m pip install --upgrade pip build
.venv/sprint0-build/bin/python -m build
python3 -m venv .venv/sprint0-install
.venv/sprint0-install/bin/python -m pip install --upgrade pip
.venv/sprint0-install/bin/python -m pip install dist/*.whl
.venv/sprint0-install/bin/nanotaste --help
.venv/sprint0-install/bin/nanotaste run --domain design --prompt 'Design a landing page for a coffee subscription' --no-record --json
.venv/sprint0-install/bin/nanotaste compare --domain writing --prompt 'Write a launch note' --taste-file examples/TASTE.example.md --candidates <two files> --no-record --json
.venv/sprint0-install/bin/nanotaste propose-update --domain writing --before <file> --after <file> --output-dir <ignored scratch dir> --json
.venv/sprint0-install/bin/nanotaste calibrate prepare --taste-file examples/TASTE.example.md --prompt-set data/calibration/starter_prompts.json --output-dir <ignored scratch dir> --json
.venv/sprint0-install/bin/nanotaste calibrate evaluate --run <run file> --picks <picks file> --output <evaluation.md> --json
git ls-remote https://github.com/actions/checkout.git refs/tags/v4
git ls-remote https://github.com/actions/setup-python.git refs/tags/v5
```

## Results

- Local unittest suite: 39 tests passing.
- System-source CLI without `PYTHONPATH`: fails as expected for uninstalled `src/` layout.
- Source CLI with `PYTHONPATH=src`: passes help/run/compare smoke.
- Local wheel build: succeeds.
- Local wheel install: succeeds.
- Installed CLI smoke: passes all current command families.
- Minimal CI workflow added with pinned checkout/setup-python action SHAs.
- GitHub Actions CI run: blocked locally by missing git remote. The workflow cannot prove anything until this branch is pushed through the approved PR flow.

## End-of-Sprint Git State

Final command:

```bash
git status --short --branch
```

Final result:

```text
## chore/sprint-0-baseline-ci
 M .gitignore
 M README.md
?? .github/
?? data/
?? docs/
?? examples/
?? pyproject.toml
?? src/
?? tests/
```

Sprint 0 files added in this pass:

```text
.github/workflows/ci.yml
docs/BASELINE_AUDIT.md
docs/SPRINT_0_HANDOFF.md
docs/reviews/sprint0_opus_review.md
```

Important: this was the pre-commit dirty state. The stale root `TEST_STDOUT.log` artifact was removed before baseline commit so it is not part of the committed scaffold.

## Open Risks for Next Authorization

- Sprint 1 should not begin until this handoff and `docs/BASELINE_AUDIT.md` are reviewed.
- A real GitHub Actions run is still pending because this checkout has no configured git remote. Before public PR/release, push to a remote and verify a green run.
- The existing NanoTaste implementation started as uncommitted dirty work and is committed locally as the baseline before Sprint 1 implementation.
- Sprint 1 must start with a threat-model decision document before security implementation.
- Default upward discovery can read wrapper-level private taste files.
- Python baseline is still `>=3.9`; raising to `>=3.11` belongs to Sprint 2.
- The build warns that `project.license` as a TOML table is deprecated.
- CI is minimal only; expanded release/security controls are intentionally deferred.
- The scorer is lexical and unvalidated.
- Calibration still uses synthetic candidates unless external candidates are supplied.
- Review/private calibration artifacts are not physically separated yet.
- Typed profile schemas and versioned record schemas do not exist yet.
- `TEST_STDOUT.log` was removed before the baseline commit and must not return as a source proof mechanism.

## Sprint 0 Review Gate

Claude Code Opus 4.8 review should evaluate:

- whether the baseline audit captures enough source truth;
- whether minimal CI actually proves tests/build/install/CLI smoke;
- whether Sprint 0 accidentally changed behavior;
- whether the dirty-start limitation is documented clearly;
- whether any Sprint 1 blocker is missing from the handoff.

Review result:

- Model: `claude-opus-4-8`.
- Claude Code: `2.1.181`.
- First-pass verdict: no blockers; changes requested on evidence wording.
- Main remediation: this handoff now states that CI is defined but not yet executed. In this checkout, green GitHub CI is blocked by missing remote, so local CI-equivalent verification is the Sprint 1 starting point.
- Second-pass verdict: acceptable for human handoff with CI execution still pending.
