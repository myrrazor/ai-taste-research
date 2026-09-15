# Security Policy

NanoTaste is a local research harness. It is not a sandbox and should not be
used to execute untrusted code.

## Supported Versions

Security fixes target the current `main` branch until formal releases begin.
The package currently supports Python 3.11 and newer.

## Reporting A Vulnerability

Use GitHub private vulnerability reporting:
https://github.com/myrrazor/ai-taste-research/security/advisories/new

Do not include private taste files, prompts, candidate text, API keys,
credentials, or full workspace dumps in a public issue.

If a public report is necessary, use a minimal title and reproduction that
does not expose private calibration data, then ask a maintainer for a
private channel.

## Current Security Boundary

The Sprint 1 threat model lives in `docs/THREAT_MODEL.md`. In short:

- hostile local files and symlinks are in scope;
- malicious candidate/model text is in scope;
- interrupted writes are in scope;
- fully compromised user/root accounts are out of scope;
- NanoTaste does not sandbox model output or generated code.

## CI And Supply Chain

- GitHub Actions workflows use minimal permissions and full commit SHA pins.
- `pull_request_target` is not used.
- Release credentials must never be available to untrusted fork PRs.
- OpenSSF Scorecard is diagnostic only; it does not replace branch rules,
  CodeQL, reviews, or pinned actions.
