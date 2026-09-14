# First-run setup walkthrough

This is output from a real `nanotaste setup --yes` run against a machine that
had Cursor and Claude Code session files, plus the example like/unlike files
from this repository.

```text
$ nanotaste setup --yes

Coding agents and history sources

Source             Present   Files  Detail
------------------------------------------------------------------------
Cursor             yes           1  1 likely session files
Claude Code        yes           1  1 likely session files
OpenAI Codex       no            0  not detected on this machine
Continue           no            0  not detected on this machine
Aider              no            0  not detected on this machine
Windsurf           no            0  not detected on this machine
Cline              no            0  not detected on this machine
Gemini CLI         no            0  not detected on this machine
Zed                no            0  not detected on this machine
OpenHands          no            0  not detected on this machine
Amazon Q           no            0  not detected on this machine
GitHub Copilot     no            0  not detected on this machine
Git history        no            0  no .git directory in this workspace
NanoTaste records  yes           0  0 local NanoTaste files

Present now: cursor, claude-code, nanotaste

Workspace config: .nanotaste/config.json
Taste file: TASTE.md
Integrated: cursor, claude-code, nanotaste
Reports: weekly
First report: .nanotaste/reports/latest.md

Next:
  nanotaste serve               # local studio for hierarchy, seeds, and harvest
  nanotaste seed --url URL      # seed from a personal site or note
  nanotaste harvest             # pull sessions and refresh overlays
  nanotaste schedule --every weekly --install
```

Without `--yes`, setup asks:

1. whether to integrate every present coding agent;
2. which domains to keep in the index;
3. how often to pull sessions and refresh taste (`manual`, `daily`, `weekly`, `monthly`);
4. whether to run the first harvest immediately;
5. whether to seed a personal site, file, or note now.

`--yes` accepts the defaults. Add `--seed-url`, `--seed-file`, or `--seed-text`
when you want the first overlay without the prompt.
