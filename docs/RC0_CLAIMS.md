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
- The security boundary is the local-file threat model in `docs/THREAT_MODEL.md`.

## Claims We Do Not Make

- NanoTaste has not demonstrated human preference alignment.
- It does not learn or train a preference model.
- The lexical critic has not been calibrated against held-out human judgments.
- A score or score margin is not a probability, confidence, or uncertainty estimate.
- Starter prompts and synthetic candidates are not research-grade evaluation data.
- The current calibration bundle does not physically separate reviewer and private data.
- Upward taste-file discovery is part of the privacy boundary and can read a parent
  wrapper's taste file unless the caller supplies an explicit file.
- Local test output is not hosted CI evidence.
- Historical model-review records are advisory snapshots, not proof of correctness.

## Deferred Work

External replay candidates, blind review, held-out human labels, validated preference
claims, Hermes Agent, OpenClaw, public visibility, tags, GitHub releases, PyPI, and
deployment are outside RC0.

Any public summary, release note, package metadata, or repository description must stay
within this claim lock until new evidence is separately reviewed.
