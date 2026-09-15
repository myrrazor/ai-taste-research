# Repository Rules

This document records the repository settings that should be enabled in GitHub.
It is source-controlled because GitHub repository rules are not fully visible in
the code diff.

## Branch Flow

- Work happens on one feature branch per sprint or logical concern.
- Pull requests target `main`.
- No automatic merge, tag, publish, or release from CI.

## Required Checks Before Merge

Protect `main` with required status checks:

- `ubuntu-latest / Python 3.11`
- `ubuntu-latest / Python 3.12`
- `ubuntu-latest / Python 3.13`
- `ubuntu-latest / Python 3.14`
- `windows-latest / Python 3.14`
- `macos-latest / Python 3.14`
- `Canonical artifact`
- `Artifact smoke`
- `CodeQL / python`
- `CodeQL / actions`
- `Dependency Review`

OpenSSF Scorecard should run on schedule or manually, but it is diagnostic
only. Do not treat it as a replacement for required CI, CodeQL, review, or
pinned actions.

## Pull Request Rules

- Require at least one approving review.
- Require CODEOWNERS review for every path (`* @myrrazor @MerlinTailor`).
- Require branches to be up to date before merge.
- Dismiss stale approvals when protected files change.
- Block force pushes and branch deletion on `main`.
- Code owners (`@myrrazor`, `@MerlinTailor`) may bypass review requirements to merge.
- Outside contributors need a code-owner approval plus one other approval.
- Exactly one implementation integration PR and one promotion integration PR define
  release provenance. A fork-safety PR is post-visibility and stays unmerged.

## GitHub Actions Policy

- Default workflow permissions: `contents: read`.
- Job permissions should be narrower when possible and elevated only when a job
  needs it, such as CodeQL `security-events: write`.
- Third-party actions must be pinned to full commit SHAs.
- `pull_request_target` is forbidden unless a documented security review
  explains why untrusted fork code cannot affect privileged execution.
- Release credentials must not be available to untrusted fork PRs.

## Repository Security Settings

Enable:

- secret scanning;
- push protection;
- dependency graph (required for the Dependency Review check to inspect diffs;
  until it is enabled the workflow stays present but cannot fail closed);
- Dependabot vulnerability alerts (alerts only; no version-update PRs);
- CodeQL code scanning;
- branch rules or rulesets for `main`.
- private vulnerability reporting with an owner-performed signed route test.

Document any setting that cannot be enabled because of account or plan limits.

## Dependency Updates

Do not enable Dependabot version-update PRs. Runtime NanoTaste stays
dependency-free; the four pinned tools in `requirements-dev.txt` and the
SHA-pinned GitHub Actions are updated only in a reviewed change. Vulnerability
alerts can stay on without opening pull requests.
