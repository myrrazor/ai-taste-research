# AI Taste Research v0.1.0-rc0

RC0 is the first public candidate for AI Taste Research. It packages NanoTaste as a small, local harness for inspecting whether explicit markdown taste rules change a deterministic candidate-selection workflow. This is pre-alpha research tooling, and the limits below are part of the release—not fine print.

## What RC0 contains

- A Python 3.11+ package with the `nanotaste` CLI and no runtime dependencies.
- Markdown `TASTE.md` parsing with general and domain-specific rules.
- A deterministic, model-free generator for local smoke tests.
- A lexical baseline critic that selects a candidate and records score reasons.
- Caller-supplied candidate comparison, JSONL run records, manual calibration packets, and approval-gated taste-update proposals.
- Local RC0 contracts and validators for canonical evidence, artifacts, governance, privacy checks, and fail-closed finalization.
- MIT licensing, contributor/security guidance, pinned CI workflows, and a 134-test local suite.

## Claim boundary

NanoTaste demonstrates workflow mechanics. It has not demonstrated human preference alignment, does not learn or train a preference model, and has not calibrated its lexical critic against held-out human judgments. Scores are deterministic heuristic totals, not probabilities, confidence values, or uncertainty estimates.

The built-in candidates and starter prompts are synthetic smoke-test material, not research-grade evaluation data. The current calibration bundle does not physically separate reviewer and private data. Upward `TASTE.md` discovery can read from a parent wrapper unless the caller supplies an explicit path. Local test output is not hosted CI evidence, and historical model-review records are advisory.

[`docs/RC0_CLAIMS.md`](docs/RC0_CLAIMS.md) is the authoritative claim lock.

## Known gaps

- No external replay set, blind review, held-out human labels, or validated preference study exists yet.
- The deterministic critic relies on literal phrases and word overlap; it does not understand semantics or paraphrases.
- NanoTaste is not published to PyPI, and RC0 has no standalone binaries or installer.
- Hermes Agent, OpenClaw, deployment, and any broader agent integration remain deferred.
- Hosted CI and security evidence cannot exist until the repository is pushed and the configured workflows run against the exact release commit.
- The last full-history privacy scan reported five policy matches in historical blobs. The release gate still requires an owner-authorized disposition before any public push or tag.
- Owner trust-anchor, CODEOWNER binding, and signed security-contact evidence remain separate gate work; this preparation does not fabricate them.

## Release shape

The chosen tag is `v0.1.0-rc0`, marked as a GitHub prerelease. The Python package version is the PEP 440 equivalent, `0.1.0rc0`. Distribution is repository/GitHub-release only for RC0; install from a clone as shown in the README.
