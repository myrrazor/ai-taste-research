# Sprint 0 Opus Review

> Historical advisory transcript. This file records the invocation and reported output;
> it is not current RC0 proof and must not substitute for deterministic or hosted checks.

Date: 2026-06-18

Model: `claude-opus-4-8`

Claude Code version: `2.1.181`

Repository commit reviewed: `99001300639fe36b8ee0066499d9cea7542f44ef`

Branch: `chore/sprint-0-baseline-ci`

Important limitation: the worktree was not clean because the NanoTaste scaffold and Sprint 0 artifacts were uncommitted local work. The review treated that dirty start as a documented limitation and focused on whether Sprint 0 overclaimed proof.

## Review Prompt

```text
You are reviewing Sprint 0 of NanoTaste remediation. This is advisory evidence, not proof.

Model gate requirements:
- Use rubric severities: BLOCKER, HIGH, MEDIUM, LOW.
- Findings must include file/line evidence and a reproduction case for BLOCKER.
- Review only Sprint 0 concerns: baseline audit, minimal CI, wheel install/smoke coverage, and handoff quality.
- Do not propose or perform code edits.
- Treat the worktree dirty-start as a known limitation; judge whether it is clearly documented, not whether it is ideal.
- Check that no NanoTaste runtime/security/schema/storage behavior changed intentionally in Sprint 0.
- Check whether minimal CI proves: existing tests, wheel build, wheel install, and current CLI command smoke tests.
- Check whether the baseline audit captures source truth, packaging observations, discrepancies, and forward risks.
- Check whether any Sprint 1 blocker is missing from the handoff.

Context:
- Repository: `<repository-root>`
- Branch: chore/sprint-0-baseline-ci
- Commit: 99001300639fe36b8ee0066499d9cea7542f44ef
- Claude Code version recorded by Codex: 2.1.181 (Claude Code)
- Sprint 0 created/changed files of interest: .github/workflows/ci.yml, docs/BASELINE_AUDIT.md, docs/SPRINT_0_HANDOFF.md.
- Existing dirty implementation files are intentionally not reviewed as Sprint 0 implementation changes except where they affect baseline claims.

Allowed commands if useful:
- git status --short --branch
- git diff --check
- PYTHONPATH=src python3 -m unittest discover -s tests

Return:
1. Summary verdict.
2. Findings grouped by BLOCKER/HIGH/MEDIUM/LOW.
3. Required remediations before Sprint 0 handoff can be accepted.
```

## Review Output

```text
Summary verdict: Changes requested - not yet acceptable for handoff. No BLOCKER, two HIGH.

The documentation is honest and the CI definition is well-formed: it covers all four required proofs (existing tests, wheel build, wheel install, CLI smoke across every command family), pins action SHAs, and uses least-privilege permissions: contents: read. The calibrate prepare -> evaluate chain is logically sound. Sprint 0 changed no runtime/security/schema/storage source; it added only ci.yml and two docs.

The problem is evidence, not design: the entire Sprint 0 deliverable and the scaffold it depends on are uncommitted working-tree state. The CI has therefore never executed, and the handoff presents it as a delivered, working artifact. The gate question "does minimal CI prove tests/build/install/smoke" currently answers no because zero runs exist.

BLOCKER:
None.

HIGH:
H1 - CI is claimed as a delivered exit criterion but has never run; the "CI proves X" gate is unestablished.
H2 - Exit criteria overclaim "complete" for items that are only locally verified.

MEDIUM:
M1 - Sprint 1 is missing its true entry blocker: committing the baseline scaffold.
M2 - CI exercises only Python 3.11, but the package declares requires-python >=3.9.
M3 - Handoff risk list is a narrower subset of the audit's carried risks.

LOW:
L1 - TEST_STDOUT.log is a stray untracked artifact at repo root.
L2 - Audit safety claim is imprecise for propose-update because propose-update accepts no taste-file and reads no taste.
L3 - git diff --check only covered tracked-modified files; whitespace/EOL of untracked files was not fully represented by that command.

Required remediations:
1. Commit and prove: decide commit strategy for the baseline scaffold plus Sprint 0 artifacts, commit them, push, and let ci.yml execute. Until one green run exists, CI exit criterion stays pending.
2. Re-label exit criteria/results to distinguish locally verified from CI-verified.
3. Add "commit the baseline scaffold" as an explicit Sprint 1 entry prerequisite.
```

## Remediation Applied

- Updated `docs/BASELINE_AUDIT.md` to distinguish local verification from unexecuted CI.
- Updated `docs/SPRINT_0_HANDOFF.md` to make committed baseline plus green CI run a Sprint 1 prerequisite.
- Expanded handoff risks to include lexical scorer, synthetic candidates, non-separated review/private artifacts, missing typed profile schema, missing versioned record schema, and the untracked `TEST_STDOUT.log` artifact.
- Removed the stale untracked root `TEST_STDOUT.log` artifact before baseline commit.

## Follow-Up Review Output

```text
Summary verdict: Acceptable for human handoff.

All six prior findings were remediated. CI is now consistently described as defined but never executed, local verification is separated from CI proof, and Sprint 1 requires a committed baseline plus green CI before security work starts.

Remaining findings:
- LOW-1: The captured git status snapshot predates adding .github/. This is technically truthful but should be clarified.
- LOW-2: requires-python >=3.9 remains asserted but untested in CI. This is disclosed and deferred to Sprint 2.

Handoff acceptability:
Yes, acceptable for human handoff with CI execution still pending. The dirty-start and unexecuted-CI limitations are stated plainly and carried forward as Sprint 1 entry prerequisites.
```
