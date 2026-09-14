# NanoTaste taste report

Generated: 2026-09-14T19:53:28+00:00

This report summarizes local setup, opted-in coding-agent history, and operator
likes. It is inspectable workflow evidence, not a claim that NanoTaste has
learned a preference model.

## Workspace

- Root: `~/projects/my-app`
- Taste file: `~/projects/my-app/TASTE.md` (present)
- Domains: general, writing, code, product, aesthetic
- Report frequency: `weekly`
- Next scheduled report: 2026-09-21T19:53:15+00:00
- Last ingest: 2026-09-14T19:53:28+00:00
- Last learn pass: 2026-09-14T19:53:28+00:00

## Coding agents

| Source | Present | Integrated | Session files | Detail |
|---|---|---|---:|---|
| Cursor | yes | on | 1 | 1 likely session files |
| Claude Code | yes | on | 1 | 1 likely session files |
| OpenAI Codex | no | off | 0 | not detected on this machine |
| Continue | no | off | 0 | not detected on this machine |
| Aider | no | off | 0 | not detected on this machine |
| Windsurf | no | off | 0 | not detected on this machine |
| Cline | no | off | 0 | not detected on this machine |
| Gemini CLI | no | off | 0 | not detected on this machine |
| Zed | no | off | 0 | not detected on this machine |
| OpenHands | no | off | 0 | not detected on this machine |
| Amazon Q | no | off | 0 | not detected on this machine |
| GitHub Copilot | no | off | 0 | not detected on this machine |
| Git history | no | off | 0 | no .git directory in this workspace |
| NanoTaste records | yes | on | 2 | 2 local NanoTaste files |

Enabled: cursor, claude-code, nanotaste

## Harvested history

- Session excerpts: 23
- Liked examples: 2
- Unliked examples: 2

## Learned signals

- Prefer inspectable work that keeps drafts obvious.
- Prefer inspectable work that keeps concrete obvious.
- Prefer inspectable work that keeps decision obvious.
- Prefer inspectable work that keeps record obvious.
- Prefer inspectable work that keeps filler obvious.
- Prefer inspectable work that keeps inspectable obvious.

### Forbidden-move candidates

- `seamlessly`
- `empower`
- `leverage`
- `cutting-edge`
- `in today's fast-paced world`
- `unlock their potential`
- `potential`
- `landscape`

## Operator likes

- concrete-release-note.md
- pick-0.md

## Operator unlikes

- generic-ai-prose.md
- pick-reject-0.md

## Recent NanoTaste runs

- No `nanotaste run` records yet.

## Keep steering this

```bash
nanotaste like examples/likes/concrete-release-note.md
nanotaste unlike examples/unlikes/generic-ai-prose.md
nanotaste pick --prompt "Write a launch note" --candidate "A" --candidate "B" --choose 1
nanotaste harvest
nanotaste report
nanotaste schedule --every weekly
```

## Automation snippet

```cron
# NanoTaste weekly harvest and taste report
15 9 * * 1 cd ~/projects/my-app && nanotaste harvest --if-due
```
