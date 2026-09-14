# AI Taste Research

Research tooling for testing whether a structured taste file changes how an agent selects and critiques generated outputs.

[![License: MIT](https://img.shields.io/badge/License-MIT-111111.svg)](LICENSE)

This is a pre-alpha research repo, not a preference model or a finished agent. It explores a narrow question: can explicit taste rules make output selection easier to inspect and test? **NanoTaste** is the first harness—a small, local Python CLI that loads `TASTE.md`, compares candidate outputs, explains a deterministic choice, and records the run.

`v0.1.0-rc0` can now also discover local coding agents on first run, harvest opted-in session history, let you pick or drop in examples you prefer, and write taste reports on demand or on a schedule. That harvest is lexical pattern extraction. NanoTaste has not demonstrated human preference alignment.

## Install, then set it up

NanoTaste requires Python 3.11 or newer. It is not on PyPI; install it from a clone of this repository.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
```

The installer cannot safely scan your home directory during `pip install`. The first command after install does that:

```bash
nanotaste setup
```

Non-interactive install, integrate every present source, and run the first harvest:

```bash
nanotaste setup --yes
```

Setup:

1. looks for Cursor, Claude Code, Codex, Continue, Aider, Windsurf, Cline, Gemini CLI, Zed, OpenHands, Amazon Q, GitHub Copilot, git history, and existing NanoTaste records;
2. offers to integrate every present source immediately;
3. writes `TASTE.md` if you do not already have one;
4. asks how often reports should be generated (`manual`, `daily`, `weekly`, or `monthly`);
5. optionally harvests history, extracts taste-rule proposals, and writes the first report.

Captured output from a real `--yes` run is in [`examples/setup-walkthrough.md`](examples/setup-walkthrough.md):

```text
Source             Present   Files  Detail
------------------------------------------------------------------------
Cursor             yes           1  1 likely session files
Claude Code        yes           1  1 likely session files
...
Integrated: cursor, claude-code, nanotaste
Reports: weekly
First report: .nanotaste/reports/latest.md
```

## The everyday loop

```bash
nanotaste harvest              # pull sessions, learn signals, write a report
nanotaste like PATH            # drop in something you prefer
nanotaste unlike PATH          # drop in something to avoid
nanotaste pick --candidate A --candidate B
nanotaste prefer --like good.md --unlike bad.md
nanotaste report               # generate a report now
nanotaste report --if-due      # honor the schedule
nanotaste schedule --every weekly
```

`harvest` is the automated run: ingest opted-in history, extract lexical signals, and refresh `.nanotaste/reports/latest.md`. It redacts tokens, emails, and home-path usernames before storing excerpts. It does not rewrite `TASTE.md` unless you pass `nanotaste learn --apply` after review.

### Drop in a like or unlike

These files live in the repo so you can try the loop immediately:

- [`examples/likes/concrete-release-note.md`](examples/likes/concrete-release-note.md)
- [`examples/unlikes/generic-ai-prose.md`](examples/unlikes/generic-ai-prose.md)
- [`examples/sessions/cursor-sample.jsonl`](examples/sessions/cursor-sample.jsonl)

```text
$ nanotaste like examples/likes/concrete-release-note.md
Stored like: .nanotaste/likes/concrete-release-note.md

$ nanotaste unlike examples/unlikes/generic-ai-prose.md
Stored unlike: .nanotaste/unlikes/generic-ai-prose.md

$ nanotaste pick --prompt "Write a launch note" \
    --candidate "Run three concrete drafts and record the decision." \
    --candidate "This seamlessly empowers teams." \
    --choose 1
Preferred candidate #1
Run three concrete drafts and record the decision.
```

### Reports, manual or scheduled

```text
$ nanotaste schedule --every weekly
Report frequency: weekly
Crontab snippet: .nanotaste/schedule.cron
```

The snippet is:

```cron
15 9 * * 1 cd /path/to/your/project && nanotaste harvest --if-due
```

A real report from that loop is checked in at [`examples/reports/sample-taste-report.md`](examples/reports/sample-taste-report.md). The matching learned proposal is [`examples/learned/proposal.example.md`](examples/learned/proposal.example.md).

```text
$ nanotaste harvest
Harvested 23 session excerpts
Learned proposal: .nanotaste/learned/proposal.md
Report: .nanotaste/reports/latest.md

$ nanotaste status
Workspace: ~/projects/my-app
Taste file: ~/projects/my-app/TASTE.md
Integrated sources: cursor, claude-code, nanotaste
Report frequency: weekly
Report due now: no
```

## How the critic works

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

That score is not a probability, confidence value, or measure of quality. The critic does not understand intent, train a preference model, or recognize a good paraphrase unless the words happen to match. Its job is to provide an inspectable baseline that a later experiment can beat.

A normal run prints the selected candidate and its score reasons, then appends a JSONL record containing the prompt, normalized domain, taste-file hash, selected candidate, rejected candidates, and their reasons. Pass `--no-record` when you do not want the local record. Edits can also become pending taste-update proposals, but NanoTaste never rewrites `TASTE.md` automatically.

## Compare two drafts

Create `TASTE.md` in your working directory, or use the public template in [`examples/TASTE.example.md`](examples/TASTE.example.md):

```markdown
# TASTE.md

## Principles

### writing
- Prefer concrete drafts and visible decisions.

## Forbidden Moves

### writing
- "seamlessly"
```

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

`nanotaste --help` also lists `compare`, `propose-update`, and the calibration commands.

## Claim boundaries

RC0 demonstrates workflow mechanics only:

- it loads markdown taste rules and routes domain-specific sections;
- it generates synthetic candidates or accepts caller-supplied ones;
- it applies a deterministic lexical score and records reasons;
- it discovers local coding-agent paths and ingests opted-in history as redacted excerpts;
- it prepares manual calibration packets, likes, picks, and taste reports; and
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
