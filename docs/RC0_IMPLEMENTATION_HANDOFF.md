# RC0 Local Implementation Handoff

Date: 2026-07-11

This handoff covers the authorized local-only portion of RC0. It does not claim that RC0
release readiness, repository integration, hosted evidence, or publication is complete.

## 1. Repository State

- Source baseline: `chore/sprint-2-release-foundation` at
  `dd6212481ec9148f40e27c886693ed2b81cc1a0a`.
- Implementation branch: `chore/rc0-release-evidence`.
- Last implementation commit before the final handoff update:
  `97f9dba0b9f483e2298edcd24559cbacda863fa1`.
- No remote is configured. No push, PR, review, merge, tag, release, package
  publication, deployment, visibility change, or repository-setting mutation occurred.
- Wrapper documents, private taste files, private calibration material, and strategy
  documents were not modified.

Atomic commits:

1. `fa9b3be` - freeze RC0 evidence contracts.
2. `a6c074c` - lock RC0 claims and reconcile historical documents.
3. `ddd7249` - fan out one canonical package in CI.
4. `2c9b5e1` - implement the local RC0 control plane.
5. `0da4006` - freeze the governance bootstrap.
6. `3a100e6` - scope worktree privacy scanning to release inputs.
7. `dff39e6` - validate direct evidence directories.
8. `9b80904` - document RC0 operations and the external stop gate.
9. `2bb20f2` - add the initial Prompt 6 handoff.
10. `97f9dba` - remediate the integrated GStack checklist findings.

## 2. Ticket Status

| Ticket | Status | Evidence or stop reason |
|---|---|---|
| `RC0-001` | Complete locally | Strict contracts, canonical JSON, frozen invariant manifest, digest binding, tests |
| `RC0-002A` | Complete locally | Claim lock and historical-document banners |
| `RC0-003` | Complete locally/configured | Canonical wheel/sdist manifest, CI fan-out, local build/install/smoke; hosted run pending |
| `RC0-004` | Complete locally | Preflight, signatures, bindings, authorizations, ledger, policy, privacy, review, finalization |
| `RC0-001B` | Validator complete; execution blocked | Trust anchor, immutable owner identity, signed governance binding, and ref mutations require owner evidence |
| `RC0-005A` | Blocked at owner gate | Security-contact route has no owner-performed signed test |
| `RC0-004A` | Scanner complete; gate fails | Worktree clean; reachable history has five policy matches requiring disposition |
| `RC0-004B` onward | Not started | Separate owner authorization and successful preceding gates are absent |
| `PUB-001` | Prohibited in RC0 | Public visibility and fork test are separately authorized post-RC0 operations |

## 3. Features and Behaviors

- Canonical UTF-8 JSON uses NFC strings, sorted keys, compact separators, preserved
  array order, integer counts, and rejects floating-point values.
- Twenty-three approved evidence schemas reject unknown top-level and payload fields.
- Every record carries its schema, attempt, producer version, timestamp, invariant
  digest, explicit extensions object, and detached SHA-256 record digest.
- The candidate packet records every schema version, algorithm version, and caller tool
  version. It accepts criteria A-E only.
- The frozen invariant manifest records all four PR classes, exact integration
  cardinality, actor/reviewer separation, required checks, capability classes,
  publication prohibitions, governance recipe, and plan/review digests.
- Package artifacts have a versioned manifest containing source SHA, exact byte sizes,
  SHA-256 digests, invariant digest, algorithm version, and explicit
  `SDIST_VERIFIED` state.
- Resource bindings are reusable identity/state evidence and are never consumed by
  validation.
- Operation authorizations permit exactly one action and are consumed atomically with
  a durable `STARTED` ledger event.
- Ledger events are hash-chained. Broken chains, duplicate consumption, concurrent
  writers, stale locks, missing starts, duplicate terminal events, and replay fail.
- Unresolved `STARTED` and explicit `OUTCOME_UNKNOWN` map only to
  `OUTCOME_UNKNOWN_PRIVATE`, with no retry and no path into review or publication.
- Review derivation is A-E, candidate, explicit verdict, then F. F cannot be caller
  supplied or interpreted through truthiness.
- Finalization is F, aggregate candidate, payload, detached digest, transition
  preflight, transition record, then terminal pointer. No state or self-digest appears
  in the payload being authenticated.
- Terminal persistence writes and verifies the transition record before atomically
  updating the state pointer. Recovery completes only the exact recorded transition.
- Repository policy rejects a third integration PR, self-approval, wrong reviewer,
  stale checks, unknown/unsupported surfaces, incomplete evidence, and every local RC0
  publication operation.
- The privacy scanner covers tracked and unignored release inputs plus every reachable
  Git blob without echoing matched secret text.
- OpenSSH signature verification uses an argument vector and message stdin, never a
  shell command. No trust anchor was invented or accepted during local implementation.

## 4. Important Implementation Details

- The invariant digest is
  `1eac0ce7fa11e3156b168841d5ce46204173929e4b9863e4bde99abef68f2b6f`.
- The sanitized execution-preflight record was written outside Git and verified with
  digest `d5447debd05f3fc133b7afaab0f3cff5b840fa550e603e606aa8329e13d18676`.
- That preflight records local-only PASS, 94% observed capacity remaining, 90%
  projected remaining, a 5% reserve floor, Claude disabled, GStack read-only, no
  remotes, and no external authorization.
- Evidence files use mode `0600`, same-directory temporary files, file fsync, atomic
  replacement, directory fsync, and immediate-file/directory symlink rejection.
- The macOS `/var` to `/private/var` system alias is allowed because only the evidence
  file and its direct output directory define the output-symlink policy.
- A lock collision or stale lock is not automatically removed. It requires explicit
  reconciliation.
- Governance validation is read-only. It verifies the approved parent, only changed
  path, Git mode, exact bytes, exact digest, and exact CODEOWNERS on each base ref.
- The CI graph builds one wheel and one sdist on Linux/Python 3.14, uploads them for 14
  days, downloads the same bytes into six smoke jobs, and exposes stable `Canonical
  artifact` and `Artifact smoke` check names.

## 5. Architecture and Data Model

New package: `nanotaste.rc0`.

- `canonical.py`: normalized canonical JSON and content digest.
- `contracts.py`: strict schema registry and sealed records.
- `invariants.py` and `rc0_invariants.json`: frozen policy anchor.
- `artifacts.py`: canonical package manifest creation and verification.
- `storage.py`: atomic JSON persistence and exclusive locks.
- `control.py`: graph, binding, authorization, ledger, and uncertainty controls.
- `signatures.py`: OpenSSH verification adapter.
- `preflight.py`: controlling-artifact, reserve, delegation, and local/external gate.
- `governance.py`: deterministic bootstrap and base-CODEOWNERS validation.
- `policy.py`: PR topology, check, GitHub surface, and publication policy.
- `privacy.py`: release-tree and full-history scanner.
- `finalization.py`: candidate, verdict, F, aggregate, payload, digest, transition, and
  recovery flow.

Records are JSON objects rather than a database schema. Private evidence remains outside
Git. Public source contains only contracts, validators, tests, and sanitized summaries.

## 6. Database Migrations

None. NanoTaste has no database and RC0 adds no migration system.

## 7. Security Work

- Full-SHA action pins retained; upload/download actions are also full-SHA pinned.
- Every checkout disables persisted credentials.
- Workflow permissions remain read-only except CodeQL's documented analysis needs.
- No `pull_request_target`, release credentials, publication action, `id-token: write`,
  `packages: write`, or `contents: write` was added.
- Unknown schema fields and unsupported versions fail closed.
- Resource identity and mutation permission are separate object types.
- Replay, expiry, wrong actor/action/target/payload/binding, stale state, graph cycles,
  corruption, crash ambiguity, self-approval, stale check names, and unsupported GitHub
  capabilities have negative tests.
- Terminal display/storage behavior from Sprint 1 remains unchanged.
- Current tracked/unignored worktree privacy scan: zero findings.
- Reachable-history privacy scan: five findings. Two historical Sprint 0 blobs contain a
  workstation path; three RC0 implementation blobs contain scanner/test fixture strings.
  The gate remains failed because no exception or history rewrite was authorized.

## 8. Tests Added or Modified

- `test_rc0_contracts.py`: 16 canonicalization, schema, extension, version, digest, and
  invariant tests.
- `test_rc0_artifacts.py`: 6 artifact count, hash, mutation, sdist-state, unknown-field,
  and canonical-write tests.
- `test_rc0_controls.py`: 31 storage, symlink, lock, binding, authorization, replay,
  ledger, graph, PR, check, capability, publication, review, digest, crash, recovery,
  and uncertainty tests.
- `test_rc0_preflight_privacy.py`: 11 reserve, delegation, state, source, authorization,
  signature, worktree, deleted-history, and no-secret-echo tests.
- `test_rc0_governance.py`: 5 exact content, line-ending, recipe, commit, base, and
  extra-path tests.
- `test_rc0_repository_policy.py`: 5 release-tree, action-pin, permission, required
  check, security/release claim, and claim-lock tests.
- Existing 58 NanoTaste tests remain unchanged and passing.
- Total: 133 tests.

## 9. Validation Commands

Executed:

```text
PYTHONPATH=src python3.14 -m unittest discover -s tests
ruff check src tests
mypy
python3.14 -m compileall -q src tests
ruby YAML parsing for all workflows and Dependabot
full-SHA, checkout-credential, permission, and pull_request_target policy checks
git diff --check
two isolated Git-archive package builds with SOURCE_DATE_EPOCH
artifact manifest create and verify
clean wheel install and complete CLI smoke
sdist build, wheel-from-sdist build, install, and CLI help smoke
tracked/unignored worktree privacy scan
full reachable-history privacy scan
current-tree private-key/token pattern scan
```

`TEST_STDOUT.log` captures the final 133-test run. It is local proof only and does not
replace hosted, commit-bound CI evidence.

## 10. Validation Results

- Unit/integration tests: 133 passed on Python 3.14.6.
- Ruff 0.15.18: passed.
- Strict mypy 2.1.0: passed across 25 source files using Python 3.12.13.
- Compileall: passed.
- YAML parse: passed for all workflows and Dependabot.
- Workflow policy checks: passed.
- Diff/whitespace checks: passed.
- Canonical wheel: 50,103 bytes,
  `886bafe77d2ed03ca3c6b41dc7b38fbbbdaa8107f4cdbfc076a0880bf2b5b249`.
- Verified sdist: 56,552 bytes,
  `cbe1fb711025b41200d71a689182d5d84d9234bc54c7e6b2511cdbcf2478686c`.
- Wheel reproducibility across two isolated builds: passed, identical digest.
- Sdist reproducibility across two local builds: not achieved; the sdist is explicitly
  install-verified, which is the approved RC0 state.
- Wheel install: passed with no runtime dependencies.
- Sdist install: passed using the already installed setuptools build backend because
  network access was unavailable.
- Installed CLI smoke: `--help`, `run`, `compare`, `propose-update`, `calibrate prepare`,
  and `calibrate evaluate` passed.
- Coverage 7.14.1: not rerun locally because the pinned package was not installed and
  network access was unavailable. Hosted CI remains configured to enforce 85%.
- Database migration, browser accessibility, UI, and performance checks: not applicable.
- Hosted CI/security checks: not run because no external mutation or remote exists.

## 11. GStack Review

The GStack review skill and its critical/security checklists were read and applied. A
read-only external Codex-backed pre-implementation review was attempted, but the sandbox
could not resolve the model endpoint. It made no repository changes. The local checklist
identified schema drift, self-digest cycles, authorization-consumption timing, and
unavailable-hosted-evidence overclaiming as the primary risks; each has deterministic
negative tests.

The integrated read-only GStack attempt against the exact branch diff was also
interrupted by endpoint DNS failure and produced no model findings. The manual GStack
critical/security pass found four actionable issues:

1. Ledger `STARTED` needed to validate binding freshness and reject reused nonces and
   operation IDs.
2. Derivation, final payload, and transition construction needed stronger source-record
   digest binding.
3. Delegation activity needed to be computed from its expiry, not accepted as a boolean.
4. Directory fsync and release-symlink behavior needed explicit cross-platform handling.

Commit `97f9dba` fixed all four and added negative tests. The follow-up 133-test, Ruff,
mypy, build, install, smoke, and policy passes succeeded. This is still not represented
as an independent model verdict.

## 12. Opus Review

Claude Code was explicitly disabled for this run. No Opus review was invoked or claimed.
The approved override requires GStack at review boundaries. Historical Opus transcripts
are now labeled advisory and historical.

## 13. Documentation

- Added `RC0_CLAIMS.md`, `RC0_GOVERNANCE.md`, `RC0_OPERATIONS.md`, and this handoff.
- Updated README, changelog, security policy, release process, repository rules, and all
  Sprint 0-2 historical handoffs/review records.
- Security documentation now states that the private reporting route is unverified.
- Repository rules now require canonical artifact checks, zero bypass, actor/reviewer
  separation, exact two-PR release provenance, and private RC0 state.

## 14. Deviations

- Work stopped before owner trust-anchor establishment as required by the authorization
  boundary; subsequent tickets were not simulated.
- The planned hosted evidence, repository settings, PR topology, CodeQL, Dependency
  Review, and Scorecard evidence cannot exist without prohibited external actions.
- The pre/post GStack model-backed process was attempted but network-blocked. A local
  checklist review and deterministic tests were used, but not represented as an
  independent model verdict.
- Local coverage was not rerun because the pinned tool could not be obtained offline.
- Sdist repeat builds were not byte-identical. The sdist was built once as the canonical
  candidate and install-verified, matching `SDIST_VERIFIED` rather than a reproducible-
  sdist claim.

## 15. Assumptions and Decisions

- Runtime remains dependency-free; no production dependency was introduced.
- Integer percentages are used in evidence to avoid canonical floating-point ambiguity.
- Arrays preserve order because PR, graph, and evidence order can be meaningful.
- Unknown fields fail instead of being ignored; future data belongs under `extensions`.
- Direct evidence-file and directory symlinks are forbidden; macOS system path aliases
  above the chosen evidence directory are outside that check.
- Stale locks are never auto-deleted because liveness cannot prove mutation outcome.
- Current history matches are blockers even when some appear to be test fixtures; no
  silent exception was added.
- Exact GitHub identity, contact route, repository ID, and settings were not guessed.

## 16. Uncertainties and Residual Risks

- Signature verification has unit-tested process boundaries but no owner trust anchor or
  real signed fixture yet.
- Filesystem atomicity depends on local `fsync` and `os.replace` semantics. Network and
  unsupported filesystems fail outside the promised boundary.
- The action ledger supports one local writer and fail-closed lock collisions, not
  distributed concurrency.
- Hosted action SHAs are static-policy checked but could not be refreshed from upstream
  in this network-restricted run.
- GitHub capability and security-state validators use synthetic fixtures until an
  authenticated, bound repository exists.
- The current branch has no hosted OS/Python matrix evidence.

## 17. Known Limitations and Deferred Work

- Owner trust anchor and immutable CODEOWNER binding.
- Signed security-contact test.
- Authorized history disposition.
- Repository creation/selection and identity binding.
- Governance base initialization and GitHub rulesets/settings.
- Two integration PRs and distinct approval/merge authorizations.
- Hosted CI, CodeQL, Dependency Review, Scorecard, and artifact bindings.
- GitHub disclosure-surface inventory.
- Exact private release-boundary GStack verdict and A-F finalization.
- Visibility, fork test, tags, release, PyPI, deployment, external replay candidates,
  blind review, human-label study, Hermes Agent, and OpenClaw.

## 18. Acceptance Criteria

| Criterion | Local result | RC0 result |
|---|---|---|
| A: claim lock | PASS for source wording | BLOCKED by unsigned contact test/content freeze |
| B: integration | Validators PASS | BLOCKED; no authorized repository or PR operations |
| C: hosted verification | Workflow configured | BLOCKED; no hosted runs or bindings |
| D: security posture | Policy/tests PASS | BLOCKED; no bound identity or observed GitHub state |
| E: artifact/privacy | Local wheel/sdist PASS; worktree clean | FAIL; reachable history has five matches and hosted artifact evidence is absent |
| F: exact review | Derivation tested | BLOCKED; exact private boundary review cannot run yet |

The two approval P2 notes are satisfied locally:

1. Every schema, algorithm, and tool version is frozen and included in candidate/final
   packets.
2. The invariant manifest digest is mandatory for dependent evidence; any change
   invalidates validation. Terminal transition persistence has all four requested crash
   tests and exact-transition recovery.

## 19. Independent Review Focus

The independent reviewer should inspect:

1. Canonicalization and self-digest exclusion in `canonical.py`, `contracts.py`, and
   `finalization.py`.
2. Invariant completeness and the hard-coded digest relationship.
3. Atomic consumption timing and crash mapping in `control.py` and `storage.py`.
4. Whether `OUTCOME_UNKNOWN_PRIVATE` is isolated from every review/publication path.
5. Terminal record-before-pointer ordering and competing-transition rejection.
6. CI artifact fan-out, sdist handling, required check names, permissions, and pins.
7. The five reachable-history findings and the required non-destructive disposition.
8. The owner trust/contact gates and absence of implied external authorization.

## 20. Final Assessment

The authorized local implementation slice is complete and deterministically tested. RC0
as a repository-integration and hosted-release-evidence sprint is not complete. It is
stopped at the required owner gate with no external side effects.

The next valid action is an owner decision that supplies a verified trust anchor,
immutable CODEOWNER binding, signed security-contact result, and an authorized
non-destructive disposition for the five reachable-history findings. Only after those
objects validate may governance/ref/repository operations receive separate one-use
authorizations.

## Final Review Addendum

- Model-backed GStack status: attempted twice, network-blocked, no verdict.
- Manual GStack checklist findings: four actionable, all fixed in `97f9dba`.
- Follow-up deterministic result: 133 tests, Ruff, mypy, YAML, workflow policy, wheel
  reproducibility, artifact verification, wheel/sdist installation, and CLI smoke pass.
- Unresolved P0/P1 code findings: none identified by the completed local review.
- Release gate remains blocked by owner evidence, hosted evidence, exact independent
  review, and full-history privacy disposition.
