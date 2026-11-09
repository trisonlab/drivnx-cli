# drivnx-cli

One command that sets up the whole DrivnX workspace on your computer, and the guide to how the team works.

## Start here

**macOS / Linux**

```bash
curl -fsSL https://raw.githubusercontent.com/trisonlab/drivnx-cli/main/get.sh | sh
```

**Windows** (PowerShell)

```powershell
irm https://raw.githubusercontent.com/trisonlab/drivnx-cli/main/get.ps1 | iex
```

You only need **git** and **Python 3.10+** first. The command creates `~/DrivnX`, downloads this tool into it and runs
`drivnx install`, which takes care of the rest. Run it in a normal terminal, not inside Claude Code: it asks questions
and two secret keys.

Prefer to see each step? This does the same:

```bash
mkdir ~/DrivnX && cd ~/DrivnX
git clone https://github.com/trisonlab/drivnx-cli.git
python3 drivnx-cli/drivnx install          # Windows: py drivnx-cli\drivnx install
```

**Before you start**, the owner sends you three invites (GitHub org `trisonlab`, the Plane workspace `drivnx`, the
Pumble workspace `TrisonLab`) and, in a Pumble direct message, the two Pumble keys `drivnx install` asks for.

### What `drivnx install` does

1. **Tools:** checks git, Claude Code, the GitHub CLI, uv, npm and pnpm. Offers to install Claude Code, uv and pnpm
   with their official installers, tells you how to get the others, and logs you in to GitHub (`gh auth login`).
2. **Repos:** clones `drivnx-docs`, `drivnx-web` and `drivnx-landing` next to this one.
3. **Dependencies:** `uv sync` and `pnpm install` for drivnx-web, `npm ci` for drivnx-landing, all from the lockfiles.
4. **Claude Code:** connects it to Plane (tickets) and Pumble (team chat). Asks for the two Pumble keys, with hidden
   input.
5. **Team posts:** installs the notifier that posts your work to Pumble (see [Pumble](#pumble)).
6. **Daily report:** an hourly job (cron, or Task Scheduler on Windows) that posts your day at 23:00.
7. **The `drivnx` command:** puts it on your PATH.

Then it shows `drivnx status`. It's safe to run again any time: it only fixes what's missing.

### Last steps

1. **Restart Claude Code.**
2. **Sign in to Plane once:** in Claude Code type `/mcp`, pick *plane*, then *Authenticate*.
3. **Delete** the Pumble message with the keys.
4. **Check:** `drivnx status --online` shows everything ✔.

```
~/DrivnX/
├── drivnx-cli/       this repo: the drivnx command and this guide
├── drivnx-docs/      product docs (the Phase 1 direction is the source of truth) and the shared AI skill setup
├── drivnx-web/       the Phase 1 app
└── drivnx-landing/   the public website
```

Work inside a code repo (`cd ~/DrivnX/drivnx-web`, then `claude`) so Claude Code loads that repo's skills and rules.
Each repo's `CONTRIBUTING.md` explains its own workflow.

## Commands

| Command | What it does |
|---|---|
| `drivnx install` | Set up, or repair, everything above. `--skip-deps`, `--skip-mcp`, `--no-schedule` leave a step out |
| `drivnx status` | Health check: each repo's branch and changes, tools, Plane and Pumble, hooks, daily job, AI skills. `--online` also tests the connections |
| `drivnx update` | Pulls all four repos (fast-forward only; a repo with uncommitted changes is skipped) and refreshes the team posts |
| `drivnx report` | Previews today's daily report. `--post` posts it now |
| `drivnx skills sync` | Applies `drivnx-docs/ai-skills/baseline.txt` to every code repo (needs the `ai-skills` CLI) |

## How we work

| When | What | Where |
|---|---|---|
| Sunday to Saturday | One sprint = one Plane cycle in project DRIVN | Plane |
| Every day | Nothing to write: your work and PRs are posted for you | Pumble |
| Thursday | Mid-sprint check-in: blockers, open PRs, re-plan if needed | Google Meet |
| Saturday | Sprint review, retro, and plan the next sprint | Google Meet |

Before each meeting, ask Claude Code to *"post the Thursday check-in"* or *"post the Saturday review"*. It reads Plane
and GitHub and posts a summary to `#meetings`. After Saturday's meeting, close the cycle in Plane and open the next.

**A piece of work, start to finish:**

1. Pick a work item from the current cycle in Plane, assign it to yourself, move it to *In Progress*.
2. Branch as `feat/<plane-key>-short-name` (e.g. `feat/drivn-31-login-form`).
3. Open the PR with the Plane key at the start of the title (`DRIVN-31: Add the login form`). Its repo's PR channel
   gets it.
4. After review, squash-merge and move the item to *Done*.

Things you can ask Claude Code: *"Move DRIVN-31 to Done and say so in #meetings"*, *"What's still open in this
sprint?"*, *"Post the Thursday check-in"*.

## Pumble

| Channel | What lands there | Sent by |
|---|---|---|
| `#meetings` | Thursday check-in, Saturday review / retro / plan | Claude Code, when you ask |
| `#daily-report` | Each person's day: commits, PRs, Claude tasks, skills used. 23:00 Vietnam time | Automatic |
| `#dev-activity` | "Claude finished" after each Claude Code task that changed files or made commits | Automatic |
| `#pr-web`, `#pr-landing`, `#pr-docs` | PRs opened / reviewed / merged, pushes, issues, releases for that repo | Pumble GitHub app |
| `#general` | Everything else | You |

Your name and the report time come from `~/.config/drivnx/pumble.json`. Set `"activity": null` under `channels` there
to stop the per-task posts.

## Rules

- **Keys never go in a repo or a chat.** Don't paste them into Pumble channels or into Claude (transcripts are stored
  on disk). If one leaks, tell the owner, who regenerates it.
- **Pumble's free plan allows 3 apps:** GitHub, Google Calendar and Claude. Agree with the team before adding one.
- **Group calls aren't free on Pumble:** meetings are on Google Meet.
- **A new repo** gets its PR channel and `/github subscribe trisonlab/<repo>` there *before* its first PR; events from
  before the subscription are never posted.

## If something doesn't work

| Problem | Fix |
|---|---|
| `drivnx: command not found` | Open a new terminal. If it's still missing, add `~/.local/bin` to your PATH (install printed the line) |
| `drivnx status` shows a ✘ | Run `drivnx install` again |
| Claude has no `send_message` tool for Pumble | The Claude app is missing scopes: the owner adds them and reinstalls it. Then `claude mcp remove pumble -s user` and `drivnx install` with the new token |
| Nothing in `#dev-activity` or `#daily-report` | Read `~/.claude/hooks/pumble-notify.log`. "channel not found" means the Claude bot isn't in that channel |
| A PR event is missing | The channel isn't subscribed to that repo, or it's a comment (comments aren't part of the subscription) |
| A code repo says "requirements not found" | It's on an old branch from before the workspace layout: `drivnx update`, or merge `main` into your branch |

## For the owner

**Adding a teammate:** invite them to the GitHub org `trisonlab`, the Plane workspace `drivnx` (project DRIVN), the
Pumble workspace `TrisonLab` (channels above) and the Thursday and Saturday meetings. Then send them the Claude app's
App key and bot token in a Pumble direct message and this repo's link.

**The Pumble Claude app** (Workspace settings → Configure apps). User *and* bot scopes: `messages:read`,
`messages:write`, `files:write`, `messages:edit`, `messages:delete`, `channels:read`, `channels:list`,
`channels:write`, `users:list`, `user:read`, `workspace:read`, `reaction:read`, `reaction:write`. Without
`files:write` and `channels:list` the MCP server has no send or channel-list tools. The bot must be a member of
`#meetings`, `#daily-report` and `#dev-activity`.

**The Pumble GitHub app:** on GitHub, trisonlab → Settings → GitHub Apps → *pumble-github* → give it each repo, then run
`/github subscribe trisonlab/<repo>` in that repo's PR channel.

## What it changes on your computer

| Where | What |
|---|---|
| `~/DrivnX/` | The four repos |
| `~/.claude.json` | The Plane and Pumble MCP servers (via `claude mcp add`; the Pumble keys live here) |
| `~/.claude/settings.json` | Two hooks that run the notifier (a backup is kept as `settings.json.bak`) |
| `~/.claude/hooks/pumble-notify.py` | The notifier, copied from `notifier/` here |
| `~/.config/drivnx/pumble.json` | Your name, timezone, report time and channels (no secrets) |
| crontab / Task Scheduler | One hourly line / task, "DrivnX daily report" |
| `~/.local/bin/drivnx` | The command (a link to this repo's `drivnx`; `drivnx.cmd` on Windows) |

To remove it: delete those, plus `claude mcp remove plane -s user` and `claude mcp remove pumble -s user`.

## Working on drivnx-cli

`drivnx` and `notifier/pumble-notify.py` are single Python files using only the standard library, for Linux, macOS
and Windows. Every pull request runs `drivnx install` on all three (`.github/workflows/test.yml`). After changing the
notifier, run `drivnx update` to install your copy.
