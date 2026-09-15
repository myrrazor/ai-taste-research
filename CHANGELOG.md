# Changelog

## Unreleased

Hostile-pass CLI/critic hardening plus first-run harvest, taste hierarchy, and
the local studio. NanoTaste stays a research harness with a lexical critic;
none of these changes add a preference model or make it a selection gate.

### Added

- First-run `nanotaste setup` that discovers local coding agents and can
  integrate every present source immediately.
- `nanotaste harvest` to pull opted-in session history, extract lexical taste
  signals, and write a report.
- Manual steering with `like`, `unlike`, `pick`, and `prefer`.
- Manual or scheduled reports via `nanotaste report` and `nanotaste schedule`.
- Example likes, unlikes, session excerpts, and a sample report in `examples/`.
- Seeded taste-file hierarchy: `TASTE.md` plus category files for writing,
  code, aesthetic, product, personal, brand, communication, and research.
- `nanotaste seed` for personal sites, files, images, and pasted notes.
- `nanotaste catalog` and a localhost studio (`nanotaste serve`) for hierarchy,
  tags, seeds, and harvest.
- First-run schedule prompt and optional seed URL/file/note before the first
  harvest. `schedule --install` can append the crontab snippet.
- Static marketing site in `website/`, separate from the local studio.
- `nanotaste --version` / `-V`, backed by `nanotaste.__version__` (tested against
  `pyproject.toml`).
- Descriptions for every command and flag in `--help`, plus a taste-discovery and
  input-file epilog on the commands that read files.
- `run --candidate-file PATH` (repeatable) to score file candidates alongside
  inline `--candidate` text; records list the files as `candidate_files`.
- `--no-taste` for an explicit no-rules baseline run.
- `--allow-outside-paths` to opt into reading candidate/edit files from outside
  the working directory.
- Secret redaction of JSONL run records (`nanotaste.redaction`): OpenAI/Anthropic
  `sk-` keys, GitHub, AWS, Slack, and Google tokens, JWTs, bearer tokens, PEM
  private keys, and `key = value` secret assignments become `[REDACTED-...]`.
- A stderr note when taste rules are discovered outside the working directory,
  and a tie disclosure in the readable result header.

### Changed

- Missing taste files are an error with a message that names the search path,
  instead of silently scoring against an empty profile.
- Candidate files and `propose-update` inputs must resolve inside the working
  directory (symlinks included) unless `--allow-outside-paths` is passed.
- Forbidden words of four or more letters also match simple inflections
  (`-s`, `-es`, `-ed`, `-ing`, `-ly`, `-ness`), so `"seamless"` catches
  `seamlessly`.
- Positive taste credit is capped at the candidate's count of eligible words not
  copied from the rules (echo guard), so trivial keyword stuffing no longer beats
  a concrete on-brief draft.
- `--taste-dir` is honored when `--taste-file` is also given (it used to be
  ignored).
- `examples/TASTE.example.md` forbids the generic filler phrases under `general`
  so the built-in generator's filler draft loses in every domain, including
  `--domain product`; the generator also strips leading `define`, `describe`,
  `choose`, and `explain` from prompts.
- README, release notes, and claim lock state plainly that calibration against
  synthetic drafts is a smoke test, not evidence of alignment.
- Frozen CODEOWNERS bytes, digest, and bound reviewer login now match the
  live CODEOWNERS file.

### Removed

- Weekly Dependabot version-update PRs. Dev-tool pins and action SHAs stay
  manual.

### Fixed

- RC0 preflight timestamp comparison no longer requires IANA tzdata, so
  Windows Python 3.14 CI can run without the `tzdata` package.
- Frozen CODEOWNERS bytes are read from `git show HEAD:.github/CODEOWNERS`
  so Windows autocrlf cannot fail the digest check.
- Dependency Review is allowed to error while the repository dependency
  graph setting is disabled.
- Local studio binds only to loopback, seed filenames stay in the seed
  directory, and seed URL fetches rebuild a validated http(s) URL and refuse
  redirects.
- `like` / `unlike` file paths are opened only after a trusted-root prefix
  check. CodeQL treats `Path(user).resolve()` as a path-injection sink, so
  preference examples no longer resolve the operator path before containment.
  Containment uses `os.path.realpath` so macOS `/var` aliases and Windows
  8.3 names still match the resolved workspace.

## 0.1.0-rc0 - 2026-07-16

RC0 prepares `0.1.0` as a pre-alpha research scaffold. It does not make a validated
preference-model claim, and package publication remains deferred.

### Added

- Sprint 2 CI matrix for Linux Python 3.11-3.14 plus Windows/macOS Python 3.14.
- Ruff linting, strict mypy type checking, source coverage, package build, clean
  wheel install, and CLI smoke tests in CI.
- CodeQL workflow for Python and GitHub Actions workflow analysis.
- Dependency Review workflow for pull-request dependency diffs.
- OpenSSF Scorecard diagnostic workflow.
- Dependabot updates for pip tooling and GitHub Actions.
- CODEOWNERS coverage for workflow and repository automation files.
- Security, contributing, code of conduct, release, and repository-rule docs.
- Strict RC0 evidence contracts and a frozen invariant manifest.
- An explicit claim lock separating implemented workflow mechanics from unvalidated
  preference research claims.
- A README-first quickstart with output captured from the documented example.
- RC0 release notes and canonical repository metadata.

### Changed

- Raised package support floor to Python 3.11.
- Switched package license metadata to SPDX `MIT`.

## Sprint 1

### Added

- Threat model for local NanoTaste security boundaries.
- Safe local IO helpers for domain validation, root containment, strict UTF-8,
  atomic writes, JSONL append checks, size limits, and terminal-safe display.
- Security tests for symlink escapes, invalid UTF-8, limits, and display-control
  escaping.

## Sprint 0

### Added

- Baseline audit and minimal CI scaffold.
- Package build/install/CLI smoke-test path.
