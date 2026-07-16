# Security Policy

NanoTaste is a local research harness. It is not a sandbox and should not be
used to execute untrusted code.

## Supported Versions

Security fixes target the current `main` branch until formal releases begin.
The package currently supports Python 3.11 and newer.

## Reporting A Vulnerability

The private vulnerability-reporting route has not yet completed its required
owner-performed signed test. Do not make this repository public or solicit reports until
that route is operationally verified and this section names the verified route.

Do not include private taste files, prompts, candidate text, API keys, credentials, or
security-contact message bodies in an issue or repository artifact.

If a public report is necessary, reduce it to a minimal reproduction that does
not expose private calibration data.

## Current Security Boundary

The Sprint 1 threat model lives in `docs/THREAT_MODEL.md`. In short:

- hostile local files and symlinks are in scope;
- malicious candidate/model text is in scope;
- interrupted writes are in scope;
- fully compromised user/root accounts are out of scope;
- NanoTaste does not sandbox model output or generated code.

## Repository Settings To Enable

The repository should enable these GitHub settings before accepting outside
contributions:

- secret scanning and push protection;
- Dependabot alerts;
- dependency graph;
- CodeQL code scanning alerts;
- branch/ruleset protection described in `docs/REPOSITORY_RULES.md`.
- a tested private vulnerability-reporting route.

## CI And Supply Chain

- GitHub Actions workflows use minimal permissions and full commit SHA pins.
- `pull_request_target` is not used.
- Release credentials must never be available to untrusted fork PRs.
- OpenSSF Scorecard is diagnostic only; it does not replace branch rules,
  CodeQL, reviews, or pinned actions.
