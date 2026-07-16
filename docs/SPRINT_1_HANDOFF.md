# Sprint 1 Handoff - Threat Model and Security Hardening

> Historical handoff. It is retained for provenance and does not establish current
> hosted CI, release readiness, or independent-review status.

Branch: `fix/sprint-1-security-hardening`
Base commit: `a11e780`
Reviewed implementation commit: `0c7d20fba38f4af1a21a7f3f03b42ce935312318`
Remote/PR status: no git remote is configured in this checkout, so no push or PR was created.
Wrapper/private docs: not modified.

## Commit Log

- `ccdef3f docs: add Sprint 1 threat model (#0)`
- `fbd6c34 security: harden NanoTaste local file IO [SHARED] (#0)`
- `0c7d20f fix: remediate Sprint 1 review findings (#0)`

## What Changed

Sprint 1 started with `docs/THREAT_MODEL.md` before implementation. It defines the security boundary for the local research harness: hostile repo files/symlinks, malicious candidate/model text, interrupted writes, dependency/action compromise risk, and second local account risk are in scope. Fully compromised user/root, sandboxing, malicious filesystems, and concurrent writers are out of scope.

The implementation adds `src/nanotaste/security.py` as the shared IO and display-safety layer. It now owns:

- domain identifier validation;
- byte-size constants;
- strict UTF-8 file reading;
- regular-file checks;
- resolved-root containment checks;
- same-directory atomic text writes;
- JSONL append checks;
- terminal-only escaping for display-manipulation characters.

Domain input is now validated in `src/nanotaste/domains.py` before it can be used as a path component. Built-in aliases still normalize first, so `design` maps to `aesthetic` and `python` maps to `code`. Path-like or control-character domains are rejected.

Taste discovery in `src/nanotaste/discovery.py` now resolves existing files through the safety layer. Auto-discovered taste files must stay under their approved root. Explicit `--taste-file` may point outside the project as an operator choice, but its companion `taste/<domain>.md` must stay under the companion `taste/` directory. Explicit `--taste-dir` domain files must stay inside that directory.

Taste parsing in `src/nanotaste/schema.py` now reads files with strict UTF-8 and the 256 KiB taste-file cap. It enforces the 2,000-rule cap both per file and after merging multiple taste files.

Agent calls in `src/nanotaste/agent.py` now enforce prompt size, candidate size, and candidate count before generation/scoring.

Calibration in `src/nanotaste/calibration.py` now validates prompt-set file size, item count, prompt size, candidate count, candidate size, calibration-run file size, and human-picks file size. Calibration run, review, pick-template, evaluation markdown, and evaluation JSON writes are atomic.

Run records in `src/nanotaste/records.py` now route through checked JSONL append logic. Records reject symlink targets and lines over 4 MiB.

Taste update proposals in `src/nanotaste/update.py` now enforce before/after input size and use atomic writes.

CLI behavior in `src/nanotaste/cli.py` now catches expected input errors for `run`, `compare`, `propose-update`, and calibration commands. Human-readable candidate output and diagnostics are rendered with `safe_for_terminal`. JSON output is not display-sanitized; it remains machine JSON and round-trips decoded text faithfully. Calibration errors now go to stderr, including in `--json` mode.

## Limits Implemented

- Taste markdown file: 256 KiB.
- Total parsed taste rules: 2,000.
- Prompt-set JSON file: 1 MiB.
- Calibration run JSON file: 4 MiB.
- Human-picks JSON file: 1 MiB.
- Candidate input file: 512 KiB.
- Prompt text: 20 KiB.
- Candidate text: 100 KiB.
- Prompt-set items: 500.
- Candidates per prompt item: 26.
- CLI generated candidate count: 26.
- JSONL record line: 4 MiB.
- Proposed update before/after text: 512 KiB each.

## Tests Added Or Updated

New file: `tests/test_security.py`.

It covers:

- domain alias normalization still works;
- path-like/control-character domains are rejected;
- auto-discovered `taste/<domain>.md` symlink escape is rejected;
- explicit taste-file companion domain symlink escape is rejected;
- explicit `--taste-dir` domain symlink escape is rejected;
- invalid UTF-8 taste files are rejected;
- merged taste profiles enforce the total rule cap;
- oversize taste file, prompt-set, calibration run, and human-picks files are rejected;
- oversize prompt-set candidate text is rejected;
- CLI compare rejects oversize candidate files;
- CLI run rejects oversize prompts;
- atomic writes reject symlink targets without mutating the real target;
- JSONL record appends reject symlink targets;
- oversized JSONL records are rejected;
- terminal rendering neutralizes ANSI/OSC, C1, BIDI, line separator, and paragraph separator controls;
- non-JSON CLI output escapes candidate display controls;
- JSON CLI output preserves decoded candidate text;
- JSONL run records preserve decoded candidate text on disk;
- invalid UTF-8 candidate files are rejected by the CLI.

Updated file: `tests/test_cli_and_updates.py`.

It now asserts calibration input errors are written to stderr. It adds a JSON-mode calibration error test proving stdout stays empty while stderr receives the diagnostic.

Existing calibration pick-validation tests in `tests/test_calibration.py` already covered invalid winner labels, duplicate picks, and unknown item IDs.

## Verification Run

Local source verification:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Result:

```text
Ran 58 tests in 0.076s
OK
```

Whitespace/diff verification:

```bash
git diff --check HEAD
```

Result: passed with no output.

Package build verification used a repo-local throwaway venv:

```bash
.venv-sprint1-build/bin/python -m build
```

Result: built `ai_taste_research-0.1.0.tar.gz` and `ai_taste_research-0.1.0-py3-none-any.whl`.

Known build warning: setuptools warns that the current `project.license` TOML table is deprecated and should become an SPDX string before 2027-02-18. This predates Sprint 1 behavior and did not block the build.

Installed-wheel smoke verification used a clean repo-local venv:

```bash
.venv-sprint1-smoke/bin/python -m pip install dist/ai_taste_research-0.1.0-py3-none-any.whl
.venv-sprint1-smoke/bin/nanotaste --help
.venv-sprint1-smoke/bin/nanotaste run --domain design --prompt "Design a pricing page" --no-record --json
.venv-sprint1-smoke/bin/nanotaste run --domain ../secret --prompt "Design a pricing page" --no-record
.venv-sprint1-smoke/bin/nanotaste compare --domain writing --candidates README.md LICENSE --no-record --json
.venv-sprint1-smoke/bin/nanotaste propose-update --domain writing --before README.md --after LICENSE --output-dir .nanotaste/sprint1-updates --json
.venv-sprint1-smoke/bin/nanotaste calibrate prepare --prompt-set data/calibration/starter_prompts.json --output-dir .nanotaste/sprint1-calibration --json
.venv-sprint1-smoke/bin/nanotaste calibrate evaluate --run .nanotaste/sprint1-calibration/starter_run.json --picks .nanotaste/sprint1-calibration/human_picks.json --output .nanotaste/sprint1-calibration/evaluation.md --json
```

Result: all smoke commands behaved as expected. The invalid-domain command returned exit code 1 with a clean input error. Build and smoke artifacts were removed after verification.

## Opus Review

Review record: `docs/reviews/sprint1_opus_review.md`.

First pass found no blockers or highs, two mediums, and four lows. Remediation fixed the two mediums and three of the lows directly; the remaining low-severity items are recorded below.

Second pass on `claude-opus-4-8` reported:

- `BLOCKER`: none.
- `HIGH`: none.
- `MEDIUM`: none.
- Verdict: accept with follow-up.

## Remaining Follow-Ups

These are advisory and do not block Sprint 1 completion:

- `records.py` serializes a payload twice for JSONL append. This is harmless but inefficient for large records.
- CLI handlers catch broad `ValueError` as user-facing input errors. That is useful for current safety errors but could hide an internal `ValueError` bug.
- `append_jsonl_record` rejects an existing symlink before opening, but append is not an atomic no-follow open on every OS. This remains within the documented non-concurrent, local threat boundary.
- Terminal escaping is not intended to be reversible. A literal backslash in input can make escaped display text ambiguous, which is acceptable for human display.

## Final Diff

Complete diff range after this handoff commit:

```bash
git diff a11e780..HEAD
```

Diff stat command:

```bash
git diff --stat a11e780..HEAD
```

## Stop Point

Sprint 1 is complete locally and ready for human review. Sprint 2 remains unauthorized until Sprint 1 is reviewed and accepted.
