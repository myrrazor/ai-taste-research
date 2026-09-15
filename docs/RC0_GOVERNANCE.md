# RC0 Governance Bootstrap

RC0 requires CODEOWNERS governance on both integration pull-request bases before either
pull request is opened or relied on. The local implementation validates this state but
does not create commits, move refs, push branches, or configure GitHub.

The frozen recipe is part of `src/nanotaste/rc0/rc0_invariants.json`:

- branch: `chore/rc0-governance-bootstrap`
- parent: `99001300639fe36b8ee0066499d9cea7542f44ef`
- only changed path: `.github/CODEOWNERS`
- mode: `100644`
- encoding and line endings: UTF-8, LF, final newline
- content owner: `@myrrazor`
- required bases: `testing` and `main`

Before execution, the owner must establish and verify the trust anchor, bind
`@myrrazor` to its immutable GitHub identity and qualifying access, sign the governance
binding, and separately authorize each ref mutation. Plan approval and this local recipe
do not authorize those actions.
