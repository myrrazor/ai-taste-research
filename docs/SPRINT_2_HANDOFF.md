# Sprint 2 Handoff - Expanded CI and Release Foundation

> Historical handoff. It is retained for provenance and does not establish current
> hosted CI, release readiness, or independent-review status.

Branch: `chore/sprint-2-release-foundation`
Base commit: `cd2c787e4449a2c956259580e50b1d8b44ca8ee2`
Reviewed implementation commit: `9abc74f89ff1166ac76d80cb95b245354dd4b022`
Remote/PR status: no git remote is configured in this checkout, so no push or PR was created.
Wrapper/private docs: not modified.

## Commit Log

- `47e858e chore: add Python 3.11 tooling [SHARED] [NEW DEP: build@1.5.0, coverage@7.14.1, mypy@2.1.0, ruff@0.15.18] (#0)`
- `29c9a6d chore: add CI and supply-chain workflows [SHARED] (#0)`
- `da37a5a docs: add release and security governance (#0)`
- `9abc74f fix: remediate Sprint 2 review findings [SHARED] [NEW DEP: setuptools>=77] (#0)`

## What Changed

Sprint 2 raises NanoTaste from a local-only scaffold to a repository with a release-foundation baseline. It does not publish, tag, push, or merge anything.

### Python And Tooling

`pyproject.toml` now:

- requires Python `>=3.11`;
- uses SPDX `license = "MIT"`;
- declares `[build-system]` with `setuptools>=77` and `setuptools.build_meta`;
- configures Ruff for Python 3.11 syntax and 100-character lines;
- configures strict mypy over `src`;
- configures coverage over `nanotaste` with branch coverage and `fail_under = 85`.

`requirements-dev.txt` pins the dev/CI tools:

- `build==1.5.0`
- `coverage==7.14.1`
- `mypy==2.1.0`
- `ruff==0.15.18`

The runtime package remains dependency-free.

Two source changes were needed for strict mypy:

- `src/nanotaste/discovery.py`: renamed the early-return `paths` variable to `discovered` to avoid a same-scope redefinition conflict with the later annotated `paths`.
- `src/nanotaste/cli.py`: added `cast(dict[str, Any], ...)` when printing the internally generated selected-candidate record.

### CI

`.github/workflows/ci.yml` now runs:

- Linux Python 3.11, 3.12, 3.13, and 3.14;
- Windows Python 3.14;
- macOS Python 3.14.

Each CI job:

- checks out with a full commit SHA-pinned action;
- installs pinned dev tooling;
- installs the package editable;
- runs `ruff check src tests`;
- runs strict `mypy`;
- runs coverage-backed unit tests and enforces the configured threshold;
- builds sdist and wheel;
- installs the wheel in a clean venv;
- smoke-tests the installed `nanotaste` CLI across `--help`, `run`, `compare`, `propose-update`, `calibrate prepare`, and `calibrate evaluate`.

### GitHub Security Workflows

Added `.github/workflows/codeql.yml`:

- analyzes Python;
- analyzes GitHub Actions workflows;
- uses only the CodeQL permissions it needs.

Added `.github/workflows/dependency-review.yml`:

- runs on pull requests;
- checks dependency diffs.

Added `.github/workflows/scorecard.yml`:

- runs OpenSSF Scorecard as diagnostic only;
- sets `publish_results: false`;
- uses read-only permissions.

All workflow `uses:` references are full 40-character commit SHAs. No workflow uses `pull_request_target`.

### Dependabot And Ownership

Added `.github/dependabot.yml` for:

- pip dependency updates in `/`;
- GitHub Actions updates.

Added `.github/CODEOWNERS` with coverage for:

- all files;
- `.github/workflows/`;
- `.github/dependabot.yml`;
- `.github/CODEOWNERS`.

Assumption: `@myrrazor` is the intended repository owner handle. If the GitHub repository uses a different owner/team, update CODEOWNERS before enabling required CODEOWNERS review.

### Release And Governance Docs

Added:

- `SECURITY.md`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `CHANGELOG.md`
- `docs/RELEASE.md`
- `docs/REPOSITORY_RULES.md`

These docs cover:

- Python 3.11+ support;
- local dev setup;
- required checks and branch/ruleset settings;
- secret scanning and push protection settings to enable;
- dependency graph and Dependabot alerts;
- no release credentials in untrusted PR workflows;
- no `pull_request_target`;
- preferred future release path using trusted publishing/OIDC and attestations when releases begin;
- OpenSSF Scorecard as diagnostic only.

## Action Pin Provenance

Action SHAs were resolved with `git ls-remote --tags` from the upstream repositories:

- `actions/checkout` v7.0.0: `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`
- `actions/setup-python` v6.2.0: `a309ff8b426b58ec0e2a45f0f869d46889d02405`
- `github/codeql-action` v4.36.2 peeled commit: `8aad20d150bbac5944a9f9d289da16a4b0d87c1e`
- `ossf/scorecard-action` v2.4.3 peeled commit: `4eaacf0543bb3f2c246792bd56e8cdeffafb205a`
- `actions/dependency-review-action` v5.0.0: `a1d282b36b6f3519aa1f3fc636f609c47dddb294`

## Verification

Local runtime available:

```text
Python 3.14.6
```

Local limitation:

- I verified on local Python 3.14.6.
- I did not download extra Python runtimes locally because the sprint constraint was to avoid changes outside the public repo.
- The CI matrix is configured to verify Python 3.11 through 3.14 on GitHub.

Commands run locally after remediation:

```bash
ruby -e 'require "yaml"; ARGV.each { |path| YAML.load_file(path); puts "ok #{path}" }' .github/workflows/*.yml .github/dependabot.yml
```

Result: all workflow/dependabot YAML files parsed.

```bash
python3.14 - <<'PY'
from pathlib import Path
bad = []
for path in Path('.github/workflows').glob('*.yml'):
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        if 'uses:' not in line:
            continue
        ref = line.split('@', 1)[1].strip() if '@' in line else ''
        ok = len(ref) == 40 and all(c in '0123456789abcdef' for c in ref)
        print(f'{path}:{lineno}: {ref} pinned={ok}')
        if not ok:
            bad.append(f'{path}:{lineno}')
if bad:
    raise SystemExit('unpinned actions: ' + ', '.join(bad))
PY
```

Result: all workflow actions were pinned to 40-character SHAs.

```bash
rg -n "pull_request_target" .github/workflows || true
```

Result: no workflow uses `pull_request_target`.

```bash
python3.14 -m venv .venv-sprint2-tools
PIP_NO_CACHE_DIR=1 .venv-sprint2-tools/bin/python -m pip install -r requirements-dev.txt
PIP_NO_CACHE_DIR=1 .venv-sprint2-tools/bin/python -m pip install -e .
.venv-sprint2-tools/bin/ruff check src tests
.venv-sprint2-tools/bin/mypy
.venv-sprint2-tools/bin/coverage erase
.venv-sprint2-tools/bin/coverage run -m unittest discover -s tests
.venv-sprint2-tools/bin/coverage report
```

Result:

```text
Ruff: All checks passed.
Mypy: Success: no issues found in 12 source files.
Tests: Ran 58 tests.
Coverage: 89%.
```

Build and wheel smoke:

```bash
.venv-sprint2-tools/bin/python -m build
python3.14 -m venv .venv-sprint2-smoke
PIP_NO_CACHE_DIR=1 .venv-sprint2-smoke/bin/python -m pip install dist/*.whl
.venv-sprint2-smoke/bin/nanotaste --help
.venv-sprint2-smoke/bin/nanotaste run --domain design --prompt "Design a landing page for a coffee subscription" --taste-file examples/TASTE.example.md --no-record --json
.venv-sprint2-smoke/bin/nanotaste compare --domain writing --prompt "Write a launch note" --taste-file examples/TASTE.example.md --candidates .nanotaste/sprint2-smoke/candidates/a.md .nanotaste/sprint2-smoke/candidates/b.md --no-record --json
.venv-sprint2-smoke/bin/nanotaste propose-update --domain writing --before .nanotaste/sprint2-smoke/before.md --after .nanotaste/sprint2-smoke/after.md --output-dir .nanotaste/sprint2-smoke/updates --json
.venv-sprint2-smoke/bin/nanotaste calibrate prepare --taste-file examples/TASTE.example.md --prompt-set data/calibration/starter_prompts.json --output-dir .nanotaste/sprint2-smoke/calibration --json
.venv-sprint2-smoke/bin/nanotaste calibrate evaluate --run .nanotaste/sprint2-smoke/calibration/starter_run.json --picks .nanotaste/sprint2-smoke/calibration/human_picks.json --output .nanotaste/sprint2-smoke/calibration/evaluation.md --json
```

Result:

- build created sdist and wheel;
- build isolation installed `setuptools>=77`;
- wheel metadata contained `License-Expression: MIT`;
- wheel metadata contained `Requires-Python: >=3.11`;
- clean wheel install succeeded;
- installed CLI smoke commands succeeded;
- JSON outputs parsed with `python3.14 -m json.tool`.

All generated artifacts and local venvs were removed after verification.

## Opus Review

Review record: `docs/reviews/sprint2_opus_review.md`.

First pass:

- `BLOCKER`: none.
- `HIGH`: none.
- `MEDIUM`: one docs mismatch for required CI check names.
- `LOW`: missing explicit `setuptools>=77` build backend, plus advisory pin-comment provenance.

Remediation:

- fixed required check names in `docs/REPOSITORY_RULES.md`;
- added `[build-system]` with `setuptools>=77`.

Second pass:

- `BLOCKER`: none.
- `HIGH`: none.
- `MEDIUM`: none.
- Verdict: accept.

Remaining low observations:

- `Dependency Review` as a required check depends on dependency graph support being enabled in GitHub settings. This is documented as a deployment precondition.
- CI and CodeQL run on both PRs and feature-branch pushes, so branch PR commits may run CI twice. This is cost-only and intentional enough for now.

## Assumptions

- Sprint 2 is stacked on Sprint 1 because Sprint 1 has not been merged into a remote branch in this checkout.
- `@myrrazor` is the correct CODEOWNERS handle unless the public GitHub repo uses a different org/team.
- Repository settings such as secret scanning, dependency graph, branch protection, and required checks cannot be enabled from this local source-only sprint; they are documented in source for the owner to apply.
- Python 3.14.6 local verification is acceptable as local evidence; GitHub CI is responsible for the full 3.11-3.14 matrix after a remote exists.
- No release publishing begins in Sprint 2.

## Stop Point

Sprint 2 is complete locally and ready for human review. Sprint 3 still requires approval of the revised identity/hash schema before implementation.
