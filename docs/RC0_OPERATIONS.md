# RC0 Local Control Operations

RC0 prepares NanoTaste `0.1.0` as a private pre-alpha research scaffold. The local
control tool validates evidence and computes decisions; it does not call GitHub or any
publication service.

## Frozen Control Boundary

`src/nanotaste/rc0/rc0_invariants.json` is the normative local manifest. Its digest is
hard-coded in the package, and every versioned record must reference that digest. The
manifest freezes:

- all evidence schema versions;
- canonical JSON, digest, ledger, review, transition, privacy, and tool versions;
- four PR classes and their cardinalities;
- exactly two merged integration PRs;
- distinct PR author and bound CODEOWNER reviewer;
- literal required-check context names;
- GitHub surface capability classes and required states;
- every prohibited publication operation;
- controlling plan and approval digests;
- the governance-bootstrap parent, path, mode, bases, and CODEOWNERS bytes.

Changing any invariant changes the manifest digest and invalidates dependent evidence.

## Binding and Authorization

A resource binding records immutable identity and observed state. Validation does not
consume it. It becomes unusable when its bound state changes, it expires, its trust
anchor is revoked, or its graph is inconsistent.

An operation authorization permits exactly one action by one actor against one bound
state. It has `max_uses: 1` and is consumed in the same atomic state update that makes
the ledger's `STARTED` event durable. Approval and merge are distinct actions and need
distinct authorizations. Plan approval cannot act as either object.

The owner trust anchor, immutable GitHub identity, signatures, and operation envelopes
remain private evidence outside Git.

## Crash and Recovery

Ledger events are hash-chained. An unresolved durable `STARTED` event or an explicit
`OUTCOME_UNKNOWN` maps immediately to `OUTCOME_UNKNOWN_PRIVATE`. The original attempt
cannot proceed to A-E, review, F, packet construction, release readiness, or publication.
Recovery requires a new owner decision, authorization, binding, and attempt.

Terminal finalization is acyclic:

```text
A-E -> candidate -> verdict -> F -> aggregate candidate -> packet payload
    -> detached digest -> transition preflight -> transition record -> state pointer
```

The transition record is persisted, flushed, reread, and verified before the state
pointer changes. A crash before the pointer update leaves the prior state intact;
recovery may complete only the exact durable transition. A competing transition fails.

## Repository and Surface Policy

The final private repository must have `main` as its default branch, exact CODEOWNERS on
both integration bases, active no-bypass rules on `testing` and `main`, read-only Actions
permissions, all frozen required checks, and the security features listed in
`docs/REPOSITORY_RULES.md`.

GitHub surfaces are classified as API-exportable, metadata-only, manual/UI-only, or
unsupported. Required evidence must be complete. An unknown or unsupported capability,
incomplete pagination, inaccessible state, unexpected surface, or state mismatch fails
closed.

## Rollback and Containment

- Never retry an operation after durable `STARTED` unless reconciliation proves a
  trustworthy terminal failure and a new authorization is issued.
- Never use a binding as permission or an authorization as identity evidence.
- Do not force-push, delete refs, delete a repository, delete hosted evidence, or change
  visibility automatically.
- Settings drift is corrected only under a new exact authorization.
- Unexpected visibility requires a separately authorized containment action.
- Any recovery invalidates affected bindings, candidate packets, reviews, final packets,
  and terminal transitions.

## Current Owner Gate

Local implementation stops before:

1. owner trust-anchor establishment;
2. immutable `@masterhit` identity and access binding;
3. signed governance approval and base-ref mutations;
4. owner-performed signed security-contact test;
5. full-history disposition;
6. repository creation, settings, pushes, PRs, approvals, merges, or hosted runs.

Public visibility, fork testing, tags, releases, PyPI, deployments, Hermes Agent, and
OpenClaw remain separate post-RC0 decisions.
