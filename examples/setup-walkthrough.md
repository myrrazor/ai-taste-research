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
  nanotaste like PATH          # drop in something you prefer
  nanotaste unlike PATH        # drop in something to avoid
  nanotaste pick --candidate A --candidate B
  nanotaste harvest            # pull sessions and refresh the report
  nanotaste report --if-due    # honor the report schedule
```

Without `--yes`, setup asks whether to integrate every present source, which
domains to keep, how often to write reports, and whether to run the first
harvest immediately.
