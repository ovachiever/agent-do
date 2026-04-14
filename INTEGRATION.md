# Claude Code Integration

agent-do ships 3 hooks that teach Claude Code to prefer `agent-do` tools over raw CLI commands. The hooks use a nudge approach: they add context reminders but never block commands.

## Quick Setup

```bash
./install.sh
```

The installer:
1. Symlinks `agent-do` into `~/.local/bin`
2. Copies hooks to `~/.claude/hooks/`
3. Installs Python dependencies
4. Prints a `settings.json` snippet you merge manually

## The 3-Layer Hook System

### Layer 1: SessionStart: PATH + Context Injection

**File:** `hooks/agent-do-session-start.sh`

Runs once per Claude Code session. Two jobs:
- **Adds agent-do to PATH** via `CLAUDE_ENV_FILE` so all `Bash` tool calls can find it
- **Injects a tooling reminder** into Claude's context with the `agent-do` pattern and project-scoped likely tools
- **Prompts for project bootstrap when needed** by telling Claude to ask once on the first reply if project-local setup like `zpc` or `manna` is missing

SessionStart itself is not an interactive prompt surface. The hook can add context, but the actual yes/no question must be asked by Claude in the normal conversation flow.

Path auto-detection chain (no hardcoded paths):
1. `which agent-do` (already in PATH)
2. `~/.local/bin/agent-do` (symlink from `install.sh`)
3. `~/.agent-do/install-path` (breadcrumb file)

### Layer 2: UserPromptSubmit: Prompt Routing

**File:** `hooks/agent-do-prompt-router.py`

Analyzes every user prompt and suggests relevant agent-do tools. It now uses shared routing metadata from `registry.yaml`, so prompt nudges, PreToolUse nudges, and offline matching can converge on the same native suggestions instead of drifting.

It still has broad fallback coverage across these categories:

| Category | Trigger Examples |
|----------|-----------------|
| ios | "screenshot the simulator", "tap on the button in iOS" |
| android | "android emulator", "adb shell" |
| macos | "click the button in Finder", "desktop automation" |
| gcp | "GCP project", "google cloud", "oauth credentials" |
| tui | "interactive terminal", "run vim" |
| browser | "open website", "web scraping", "playwright" |
| db | "database query", "SQL command" |
| k8s | "kubernetes", "kubectl", "pods" |
| docker | "docker container", "docker compose" |
| slack | "post to slack", "slack message" |
| email | "send email", "inbox" |
| image | "resize image", "convert png" |
| video | "convert video", "ffmpeg video" |
| audio | "transcribe audio", "whisper" |
| calendar | "create event", "schedule meeting" |
| cloud | "aws s3", "gcloud", "azure" |
| vercel | "vercel deploy", "vercel project" |
| render | "render.com", "render service" |
| supabase | "supabase project", "supabase database" |

### Layer 3: PreToolUse: Command Interception

**File:** `hooks/agent-do-pretooluse-check.py`

Watches every `Bash` tool call. When Claude tries to run a raw command that has an agent-do equivalent (e.g., `xcrun simctl`, `vercel deploy`, `kubectl`), it injects a hard nudge with the closest native replacement command and any relevant setup hint.

**Nudge mode (default):** Adds `additionalContext`. Claude sees the reminder but the command still runs.

Examples:
- `npx playwright test` → `agent-do browse ...` + browser-install hint when relevant
- `xcrun simctl io booted screenshot` → `agent-do ios screenshot`
- `psql ...` → `agent-do db ...`

**Block mode (opt-in):** Change `additionalContext` to `permissionDecision: "deny"` in the hook output to block raw commands entirely. See the comment at the top of the hook file.

Intercepted commands include:
- `vercel`, `npx vercel`, `curl api.vercel.com`
- `supabase`, `npx supabase`, `curl supabase.co`
- `render services`, `curl api.render.com`
- `xcrun simctl`, `simctl`
- `adb shell/install/logcat`
- `osascript`, `automator`
- `docker ps/logs/exec/compose`
- `kubectl`, `ssh user@host`, `psql`, `mysql`
- `aws s3/ec2/lambda`, `gcloud`, `az vm/storage`
- ImageMagick, ffmpeg (image/video/audio)

Safe commands are skipped (git, npm, python, basic shell tools, localhost curl, etc.).

## Registering Hooks in settings.json

Claude Code hooks must be registered in `~/.claude/settings.json`. They are NOT auto-discovered.

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-session-start.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-prompt-router.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-pretooluse-check.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

If you already have hooks in `settings.json`, merge the agent-do entries into the existing arrays for each event.

## CLAUDE.md Integration

Add this to your project's `CLAUDE.md` so Claude knows about agent-do even without hooks:

```markdown
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

    agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
    agent-do -n "what you want"           # Natural language (humans)
    agent-do suggest "task"               # likely tool/command for a task
    agent-do suggest --project            # likely tools for this repo
    agent-do find <keyword>               # keyword search across tools
    agent-do creds check --tool <tool>    # check declared tool credentials
    agent-do creds store <ENV_VAR> --stdin # store a secret in the secure store
    agent-do spec list                    # list repo-local specs and changes
    agent-do spec status --change <id>    # inspect one change package
    agent-do --health                     # Dependency readiness
    agent-do bootstrap --recommend        # Detect pending project setup
    agent-do nudges stats                 # summary of hook nudges on this machine
    agent-do --list                       # List all 84 tools
    agent-do <tool> --help                # Per-tool help

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio, zpc
```

## Nudge vs Block Mode

By default, all hooks use **nudge mode**: they add context reminders but never prevent Claude from running commands. This is still the recommended approach because:

- Claude learns the pattern over a session (the reminder accumulates)
- No false positives blocking legitimate commands
- Users can override when agent-do isn't appropriate

The difference in `v1.1` is that the nudges are now more exact:
- prompt-time suggestions can name a concrete `agent-do <tool> <command>`
- PreToolUse nudges can point at the closest raw-command replacement
- SessionStart can suggest likely tools for the current repo instead of a generic static list
- local telemetry is available through `agent-do nudges stats|recent`

To switch to **block mode**, edit `hooks/agent-do-pretooluse-check.py` and change the output from `additionalContext` to `permissionDecision: "deny"`. See the docstring at the top of that file.

## Architecture

```
Claude Code Session
    │
    ├─ SessionStart ──→ agent-do-session-start.sh
    │   └─ Adds agent-do to PATH + injects project-aware tool reminder
    │
    ├─ UserPromptSubmit ──→ agent-do-prompt-router.py
    │   └─ Suggests agent-do tools from shared routing metadata + fallbacks
    │
    └─ PreToolUse (Bash) ──→ agent-do-pretooluse-check.py
        └─ Hard-nudges when raw CLI commands have agent-do equivalents
```

All three hooks work independently. You can install any subset.

## Uninstalling

```bash
./install.sh --uninstall
```

This removes the symlink, breadcrumb, and hook files. You'll need to manually remove the hook entries from `~/.claude/settings.json`.
