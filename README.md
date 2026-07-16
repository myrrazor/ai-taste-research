# AI Taste Research

Research tooling for testing whether a structured taste file changes how an agent selects and critiques generated outputs.

[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](LICENSE)

This is a pre-alpha research repo, not a preference model or a finished agent. It explores a narrow question: can explicit taste rules make output selection easier to inspect and test? **NanoTaste** is the first harness—a small, local Python CLI that loads `TASTE.md`, compares candidate outputs, explains a deterministic choice, and records the run.

## How it works

`TASTE.md` is ordinary markdown with sections for anchors, principles, tradeoffs, forbidden moves, calibration examples, and update policy. Rules can be general or scoped to a domain such as writing, product, aesthetic, or code. NanoTaste searches upward from the working directory for the file, or you can pass one explicitly with `--taste-file`.

```text
TASTE.md + task domain
          |
          v
   load relevant rules       candidate outputs
          |                         |
          +------------+------------+
                       v
             deterministic critic
                       |
          +------------+-------------+
          v                          v
 selected text + reasons     .nanotaste/runs.jsonl
```

You can supply candidates from another model or tool. If you do not, NanoTaste's built-in generator creates two to four deterministic, synthetic drafts for local smoke tests. It does not call a model.

The critic is deliberately simple:

- each matching forbidden rule subtracts 3 points;
- eligible word overlap with a positive rule adds 1 or 2 points for that rule, with positive matches capped at 6 points total;
- a number, amount, percentage, day, or time unit adds 1 concrete-detail point;
- sharing an eligible word with the prompt adds 1 stays-on-brief point; and
- a tie goes to the earlier candidate.

Eligible words are four or more characters after a small stop-word filter. The same inputs produce the same score and selection.

That score is not a probability, confidence value, or measure of quality. The critic does not understand intent, learn from feedback, or recognize a good paraphrase unless the words happen to match. Its job is to provide an inspectable baseline that a later experiment can beat.

A normal run prints the selected candidate and its score reasons, then appends a JSONL record containing the prompt, normalized domain, taste-file hash, selected candidate, rejected candidates, and their reasons. Pass `--no-record` when you do not want the local record. Edits can also become pending taste-update proposals, but NanoTaste never rewrites `TASTE.md` automatically.

## Try it

NanoTaste requires Python 3.11 or newer. It is not on PyPI; install it from a clone of this repository.

With [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.11
uv pip install .
. .venv/bin/activate
```

Or with `pip` (replace `python3.12` with any Python 3.11+ executable you have):

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

Create `TASTE.md` in your working directory:

```markdown
# TASTE.md

## Principles

### writing
- Prefer concrete drafts and visible decisions.

## Forbidden Moves

### writing
- "seamlessly"
```

Now compare two drafts:

```bash
nanotaste run \
  --taste-file TASTE.md \
  --domain writing \
  --prompt "Write a release note for NanoTaste" \
  --candidate "NanoTaste helps teams seamlessly compare outputs." \
  --candidate "Run NanoTaste on three concrete drafts and record the decision."
```

Output from an actual run:

```text
Selected candidate #1 (score 3)
- +2 matches taste: concrete, drafts
- +1 stays on brief

Run NanoTaste on three concrete drafts and record the decision.
```

The second draft wins because it overlaps with two words in the positive writing rule and stays on the prompt. The first draft is penalized for the literal forbidden phrase. That is the whole claim: the file changed this deterministic lexical comparison. It does not show that NanoTaste agrees with a person.

The full public template is [`examples/TASTE.example.md`](examples/TASTE.example.md). Run `nanotaste --help` to see the candidate-file, calibration, and update-proposal commands.

## Claim boundaries

RC0 demonstrates workflow mechanics only:

- it loads markdown taste rules and routes domain-specific sections;
- it generates synthetic candidates or accepts caller-supplied ones;
- it applies a deterministic lexical score and records reasons;
- it prepares manual calibration packets; and
- it writes proposed taste updates for later human review.

What remains unproven matters more:

- NanoTaste has not demonstrated human preference alignment.
- It does not learn or train a preference model.
- The critic has not been calibrated against held-out human judgments.
- Starter prompts and synthetic candidates are not research-grade evaluation data.
- Scores and score margins are not probabilities, confidence, or uncertainty estimates.
- The current calibration bundle does not physically separate reviewer and private data.
- Upward discovery can read a parent directory's taste file unless you pass an explicit file.
- Local tests are not hosted CI evidence, and historical model reviews are advisory snapshots.

The authoritative boundary is [`docs/RC0_CLAIMS.md`](docs/RC0_CLAIMS.md). Any broader result needs new evidence and a separate review.

## Status

`v0.1.0-rc0` is a pre-alpha, repository-only release candidate. NanoTaste runs locally on Python 3.11+ and has no runtime dependencies. It is not published to PyPI. External replay candidates, blind review, held-out human labels, validated preference claims, Hermes Agent, and OpenClaw remain future work.

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Keep issues, examples, and experiment data public-safe: no personal taste files, private prompts, secrets, or strategy notes.

## License

MIT — see [`LICENSE`](LICENSE).

Repository: [github.com/myrrazor/ai-taste-research](https://github.com/myrrazor/ai-taste-research)
