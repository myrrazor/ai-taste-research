# NanoTaste Agent Sprints

This is the build plan for turning NanoTaste from a scoring harness into a small taste-aware agent. Each sprint maps to one agent part.

## Sprint 1: TasteRouter

Goal: route a task to the right taste domain and load only the taste files that matter.

Tickets:

- `NT-001`: Normalize domain aliases such as `design`, `copy`, `naming`, and `python`.
- `NT-002`: Discover `TASTE.md` by walking upward from the current directory.
- `NT-003`: Load optional `taste/<domain>.md` files after the global taste file.
- `NT-004`: Return a `TasteContext` with domain, rules, profile hash, and source paths.
- `NT-005`: Test global-only, domain-specific, and no-taste cases.

Done when: callers can resolve taste context without knowing file layout.

## Sprint 2: Generator

Goal: produce candidate outputs for calibration while keeping the generator swappable.

Tickets:

- `NT-006`: Define a `CandidateGenerator` interface.
- `NT-007`: Keep the deterministic local generator as the default.
- `NT-008`: Make generated candidates useful for human review, not just meta-instructions.
- `NT-009`: Keep LLM-backed generation out of the first pass.
- `NT-010`: Test generated candidate count, prompt cleanup, and domain-specific wording.

Done when: the agent can generate 2-4 candidates without binding the project to a model provider.

## Sprint 3: TasteCritic

Goal: score candidates against taste and explain the selected winner.

Tickets:

- `NT-011`: Score forbidden moves as strong negative signals.
- `NT-012`: Score positive taste rules while skipping negative anchors.
- `NT-013`: Return selected, rejected, all scores, and taste hash.
- `NT-014`: Keep reasons short enough to inspect in a review sheet or JSON record.
- `NT-015`: Test specific taste versus generic style-guide behavior.

Done when: the critic picks the better candidate in hand-built aesthetic, writing, product, and code scenarios.

## Sprint 4: TasteUpdater

Goal: turn human edits into pending taste updates without mutating `TASTE.md`.

Tickets:

- `NT-016`: Compare before/after text and extract representative changes.
- `NT-017`: Write pending markdown proposals under a review directory.
- `NT-018`: Keep `TASTE.md` unchanged unless a human applies the proposal.
- `NT-019`: Include domain and calibration example text in each proposal.
- `NT-020`: Test that proposal files are written and taste files are not mutated.

Done when: user edits produce clear pending proposals and no automatic preference drift.

## Sprint 5: Calibration Workflow

Goal: make manual human picking easy and measurable.

Tickets:

- `NT-021`: Add a starter prompt set with 10 prompts per domain.
- `NT-022`: Add `nanotaste calibrate prepare` to generate candidates and hidden NanoTaste picks.
- `NT-023`: Render a bias-resistant human review sheet with candidate IDs only.
- `NT-024`: Create a `human_picks.json` template for later manual labels.
- `NT-025`: Add `nanotaste calibrate evaluate` for match rate and per-domain reporting.
- `NT-026`: Test prepare/evaluate with partial and complete human labels.

Done when: a human can fill one file later and get a clear accuracy report.

## Stage Gate

Do not fork Hermes Agent until NanoTaste reaches a meaningful match rate on a calibration set with real external candidates. The generated starter set is only a smoke test for workflow and UX. The first threshold is 65-70% agreement with human picks on externally generated candidates. If it misses badly, improve the taste schema or scorer before adding a larger agent framework.
