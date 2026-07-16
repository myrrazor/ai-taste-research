# Repository Rules

This document records the repository settings that should be enabled in GitHub.
It is source-controlled because GitHub repository rules are not fully visible in
the code diff.

## Branch Flow

- Work happens on one feature branch per sprint or logical concern.
- Pull requests target `testing`.
- Only the owner promotes `testing` to `main`.
- No automatic merge, tag, publish, or release from CI.

## Required Checks Before Merge

Protect `testing` and `main` with required status checks:

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
- Require CODEOWNERS review for `.github/workflows/`, `.github/dependabot.yml`,
  and `.github/CODEOWNERS`.
- Require branches to be up to date before merge.
- Dismiss stale approvals when protected files change.
- Block force pushes and branch deletion on `testing` and `main`.
- Do not configure bypass actors. Incident recovery still uses a reviewed, separately
  authorized pull request.
- The PR author and bound CODEOWNER reviewer must be distinct identities.
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
- dependency graph;
- Dependabot alerts;
- CodeQL code scanning;
- branch rules or rulesets for `testing` and `main`.
- private vulnerability reporting with an owner-performed signed route test.

Keep repository visibility private through RC0 review. Tags, releases, packages,
deployments, environments, Pages, publication secrets, self-hosted runners, and
publication workflows must remain absent.

Document any setting that cannot be enabled because of account or plan limits.

## Dependency Updates

Dependabot is configured for:

- pip dependencies in `requirements-dev.txt`;
- GitHub Actions workflow references.

Dependency PRs should run the same required checks as normal code PRs.
