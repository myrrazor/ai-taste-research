# Changelog

## Unreleased

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
