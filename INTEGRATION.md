# Claude Code And Codex Integration

agent-do ships hooks that teach coding agents to prefer `agent-do` tools over raw CLI commands. The hooks use a nudge approach: they add context reminders but do not block commands by default.

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
- **Prompts for project bootstrap when needed** with a native macOS dialog at session start when project-local setup like `zpc` or `manna` is missing

SessionStart is not a chat surface, but the current hook can trigger a native macOS bootstrap dialog directly when bootstrap work is pending. If bootstrap is not pending, it falls back to context injection only.

Path auto-detection chain (no hardcoded paths):
1. `which agent-do` (already in PATH)
2. `~/.local/bin/agent-do` (symlink from `install.sh`)
3. `~/.agent-do/install-path` (breadcrumb file)

### Layer 2: UserPromptSubmit: Prompt Routing

**File:** `hooks/agent-do-prompt-router.py`

Analyzes every user prompt and suggests relevant agent-do tools only when the match is strong enough to be useful. When `ANTHROPIC_API_KEY` is available, the hook can use Sonnet 4.6 adaptive thinking over the compact full `agent-do` catalog. The model chooses from real registered tools and returns concise, exact commands; weak matches stay silent.

Prompt-time coordination is targeted. UserPromptSubmit emits `Coord Focus Required` context when active peers exist, the current agent has no focus, and the prompt is starting workspace work. The reminder is non-blocking because blocking hooks stop the agent turn instead of letting the model satisfy the requirement.

The deterministic fallback stays conservative: completion/status prompts still get completion-check context, design-quality prompts still get the DPT path, and generic tool suggestions stay silent instead of guessing.

AI prompt routing receives the catalog, not a deterministic shortlist. This keeps the hook from duplicating local matcher effort before the model has decided which tool, if any, is worth surfacing.

Use `AGENT_DO_HOOK_AI=off` for deterministic-only hook behavior, `auto` for best effort, or `on` to require the AI path.

### Layer 3: PreToolUse: Command Interception

**Claude file:** `hooks/agent-do-pretooluse-check.py`

**Codex file:** `hooks/agent-do-pretooluse-codex.py`

Watches every `Bash` tool call. When an agent tries to run a raw command that has an agent-do equivalent (e.g., `xcrun simctl`, `vercel deploy`, `kubectl`), it injects a hard nudge with the closest native replacement command and any relevant setup hint where the host supports that output.

**Claude nudge mode (default):** Adds `additionalContext`. Claude sees the reminder but the command still runs.

**Codex compatibility mode:** Runs the same shared PreToolUse check and records the same telemetry, but suppresses stdout because Codex rejects `additionalContext` for PreToolUse.

Examples:
- `npx playwright test` → `agent-do browse ...` + browser-install hint when relevant
- `xcrun simctl io booted screenshot` → `agent-do ios screenshot`
- `psql ...` → `agent-do db ...`

**Block mode (opt-in, Claude only):** Change `additionalContext` to `permissionDecision: "deny"` in the hook output to block raw commands entirely. Use this carefully; blocking stops the current agent turn.

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

For Codex PreToolUse, point the Bash matcher at the tracked compatibility wrapper:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/agent-do/hooks/agent-do-pretooluse-codex.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

## CLAUDE.md Integration

Add this to your project's `CLAUDE.md` so Claude knows about agent-do even without hooks:

```markdown
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

    agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
    agent-do -n "what you want"           # Natural language (humans)
    agent-do suggest "task"               # likely tool/command for a task
    agent-do suggest "task" --ai on        # require Sonnet-backed command selection
    agent-do suggest --project            # likely tools for this repo
    agent-do find <keyword>               # keyword search across tools
    agent-do creds check --tool <tool>    # check declared tool credentials
    agent-do creds store <ENV_VAR> --stdin # store a secret in the secure store
    agent-do spec list                    # list repo-local specs and changes
    agent-do spec status --change <id>    # inspect one change package
    agent-do --health                     # Dependency readiness
    agent-do bootstrap --recommend        # Detect pending project setup
    agent-do nudges stats                 # summary of hook nudges on this machine
    agent-do --list                       # List all 88 tools
    agent-do <tool> --help                # Per-tool help

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio, git, gh, ci, zpc
```

## Nudge vs Block Mode

By default, hooks use **nudge mode** where the host supports it: they add context reminders but do not prevent commands from running. This is still the recommended approach because:

- Claude learns the pattern over a session (the reminder accumulates)
- No false positives blocking legitimate commands
- Users can override when agent-do isn't appropriate

The difference in `v1.1` is that the nudges are now more exact:
- prompt-time suggestions are AI-ranked from the full registered catalog and only surface concrete `agent-do <tool> <command>` paths when confidence is high
- PreToolUse nudges can point at the closest raw-command replacement
- SessionStart can suggest likely tools for the current repo instead of a generic static list
- local telemetry is available through `agent-do nudges stats|recent`

To switch Claude PreToolUse to **block mode**, edit `hooks/agent-do-pretooluse-check.py` and change the output from `additionalContext` to `permissionDecision: "deny"`. Do not use block mode for coord focus reminders; those need to be seen by the agent so it can set focus and continue.

## Architecture

```
Coding Agent Session
    │
    ├─ SessionStart ──→ agent-do-session-start.sh
    │   └─ Adds agent-do to PATH + injects project-aware tool reminder
    │
    ├─ UserPromptSubmit ──→ agent-do-prompt-router.py
    │   └─ AI-ranks the full catalog and emits only exact high-confidence suggestions
    │
    └─ PreToolUse (Bash) ──→ agent-do-pretooluse-check.py        # Claude
        └─ agent-do-pretooluse-codex.py                         # Codex
```

All three hooks work independently. You can install any subset.

## Uninstalling

```bash
./install.sh --uninstall
```

This removes the symlink, breadcrumb, and hook files. You'll need to manually remove the hook entries from `~/.claude/settings.json`.
