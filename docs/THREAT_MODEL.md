# NanoTaste Sprint 1 Threat Model

Sprint 1 hardens the existing local research harness. It does not turn
NanoTaste into a sandbox, a multi-user service, or a secure execution runtime.
The goal is narrower: hostile files and hostile text should not trick the CLI
into reading or overwriting surprising paths, corrupting records during normal
writes, or manipulating terminal output.

## Assets

- Private taste files and calibration material chosen by the local operator.
- Candidate text, prompts, run records, and proposed taste updates.
- Experiment provenance that should remain reproducible after interrupted
  writes.
- The user's terminal view of candidate/model output.

## In Scope

- A malicious cloned repository containing hostile `TASTE.md`, `taste/*.md`,
  prompt-set files, or symlinks.
- Malicious candidate or model output, including ANSI, OSC, C0/C1, and
  bidirectional-display control characters.
- Accidental corruption from interrupted full-file writes.
- A compromised dependency or GitHub Action as a supply-chain risk to be
  reduced by later CI/release controls, not fully solved in this sprint.
- A second untrusted local account trying to exploit predictable output paths
  or symlink clobbering where normal filesystem permissions allow interaction.

## Out of Scope

- A fully compromised user account.
- Root, administrator, or kernel-level compromise.
- Sandboxing generated code or model output.
- Defending against a malicious filesystem, broken OS atomicity guarantees, or
  network storage that does not honor local filesystem semantics.
- Concurrent writers intentionally sharing the same NanoTaste output files.

## Path And Symlink Policy

Input symlinks are allowed only when the resolved target stays inside the
approved root for that discovery path. For example, an auto-discovered
`taste/code.md` may be a symlink to another file under the same project root,
but not to `~/.ssh/config` or another external path.

Opted-in coding-agent discovery reads only source roots the operator enables
during `nanotaste setup`. Session ingest copies redacted excerpts into
`.nanotaste/sessions/` and never writes raw history into `TASTE.md`. Home-directory
roots are operator-selected; NanoTaste does not follow session-file symlinks
and skips common cache, plugin, and `node_modules` trees.

Explicit input overrides are treated as deliberate operator choices:

- `--taste-file` may point outside the project, but it must resolve to a
  regular file.
- Companion domain files discovered beside an explicit taste file must resolve
  under that explicit file's parent `taste/` directory.
- `--taste-dir` may be absolute or relative, but domain file discovery must stay
  inside that directory after symlink resolution.
- Candidate files, prompt-set files, calibration run files, and pick files must
  resolve to regular files.

Output targets must not be symlinks. NanoTaste writes to a temporary file in the
same directory, flushes it, and replaces the target. Output directories are
operator-selected. If a parent directory is itself a symlink, NanoTaste follows
it as the operator's chosen destination, but it still refuses to replace a
symlink target file.

Domain names are validated before being used as path components. Valid custom
domains must match:

```text
^[a-z][a-z0-9_-]{0,63}$
```

Built-in aliases such as `design` and `python` are normalized before this
validation. Path separators, dot-dot traversal, NUL bytes, control characters,
empty domains, and leading punctuation are rejected.

## Race Resistance

Linux and macOS:

- Full-file writes use same-directory temporary files plus `os.replace`, which
  gives atomic replacement on normal local filesystems.
- Existing symlink targets are rejected before replacement.
- Parent directory metadata is fsynced when the platform permits it.

Windows:

- Full-file writes use same-directory temporary files plus `os.replace`.
- Existing symlink targets are rejected before replacement.
- Directory fsync is best effort and may be unavailable.

JSONL run-record appends are not transactional across concurrent writers in
Sprint 1. NanoTaste supports one writer per record file. It does reject an
existing symlink at the record path before appending.

These controls reduce accidental corruption and simple symlink clobbering. They
do not guarantee protection against a fully compromised account racing file
checks and replacement calls.

## Size Limits

Limits are byte limits after UTF-8 encoding unless noted otherwise.

| Item | Limit |
|---|---:|
| Taste markdown file | 256 KiB |
| Total parsed taste rules | 2,000 |
| Prompt-set JSON file | 1 MiB |
| Calibration run JSON file | 4 MiB |
| Human-picks JSON file | 1 MiB |
| Candidate input file | 512 KiB |
| Prompt text | 20 KiB |
| Candidate text | 100 KiB |
| Prompt-set items | 500 |
| Candidates per prompt item | 26 |
| CLI generated candidate count | 26 |
| JSONL record line | 4 MiB |
| Proposed update input text | 512 KiB |

The first version favors small research packets over accepting arbitrary bulk
data. Larger studies should introduce explicit streaming/import contracts in a
later sprint.

## UTF-8 Policy

NanoTaste stores decoded text faithfully after strict UTF-8 decoding. Invalid
UTF-8 input is rejected with a user-facing input error. Candidate text, prompts,
and records are not mutated for storage simply because they contain terminal
control characters.

Terminal rendering is separate from storage. Human-readable CLI output escapes
display-manipulation characters before printing:

- ANSI escape and OSC introducers.
- C0 controls other than line feed and tab.
- C1 controls.
- Unicode bidirectional-display controls.
- Unicode line and paragraph separators.

JSON output remains machine-readable JSON only. Diagnostics go to stderr where
the existing command shape already does so; Sprint 4 will formalize the complete
JSON stdout contract and stable error envelopes.

## Dependency And Action Risk

Sprint 1 does not add dependencies. Later CI/release sprints must pin third
party GitHub Actions to full commit SHAs, use minimal permissions, and document
repository settings such as secret scanning and required checks. A compromised
dependency or action remains an acknowledged supply-chain risk until those
controls are complete.
