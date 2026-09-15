# RC0 Claim Lock

NanoTaste `0.1.0` is a pre-alpha local experiment harness. The release claim is
limited to workflow mechanics: it can load a markdown taste profile, generate or
accept candidates, apply a deterministic lexical score, and prepare manual
calibration records.

## Claims We Make

- The package is a small, dependency-free Python CLI for local experiments.
- The current critic is deterministic and lexical.
- The built-in generator is synthetic and model-free.
- The starter prompt set exercises the calibration workflow.
- Taste updates are proposals and are not applied automatically.
- Local setup can discover coding-agent install paths and ingest opted-in
  history as redacted lexical excerpts.
- Learned rules are word-overlap proposals, not a trained preference model.
- First-run setup can install a taste-file hierarchy, prompt for a harvest
  schedule, and seed overlays from operator-supplied URLs, files, images, or
  notes. Scheduled harvest writes `taste/learned/` overlays; seeded category
  files are not rewritten unless the operator applies a proposal.
- The local studio is a localhost viewer and editor for that hierarchy. It is
  not a hosted product and is separate from the static marketing site.
- The security boundary is the local-file threat model in `docs/THREAT_MODEL.md`.

## Claims We Do Not Make

- NanoTaste has not demonstrated human preference alignment.
- It does not learn or train a preference model.
- The lexical critic has not been calibrated against held-out human judgments.
- A score or score margin is not a probability, confidence, or uncertainty estimate.
- Starter prompts and synthetic candidates are not research-grade evaluation data.
- A `calibrate evaluate` agreement rate is computed against synthetic generator drafts
  unless a prompt set supplies candidates; it is a workflow smoke test, not evidence of
  taste alignment, and is not an accuracy result.
- The critic's inflection matching is a fixed suffix table and its echo guard only
  defeats trivial keyword stuffing; neither is language understanding.
- Record redaction covers a fixed list of credential shapes and is not a secret scanner.
- The current calibration bundle does not physically separate reviewer and private data.
- Upward taste-file discovery is part of the privacy boundary and can read a parent
  wrapper's taste file unless the caller supplies an explicit file. NanoTaste prints a
  stderr note when that happens and fails when no taste file exists at all.
- Local test output is not hosted CI evidence.
- Historical model-review records are advisory snapshots, not proof of correctness.

## Deferred Work

External replay candidates, blind review, held-out human labels, validated preference
claims, Hermes Agent, OpenClaw, public visibility, tags, GitHub releases, PyPI, and
deployment are outside RC0.

Any public summary, release note, package metadata, or repository description must stay
within this claim lock until new evidence is separately reviewed.
