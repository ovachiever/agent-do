# Codex hook bundle for agent-do

This directory ships the Codex-specific install bundle that mirrors what
`install.sh` does for Claude Code. The wrappers here use `runpy.run_path` to
forward to the canonical hooks at `<repo>/hooks/`, so a single source of truth
serves both surfaces. Codex supports `hookSpecificOutput.additionalContext` on
PreToolUse as of the May 2026 hooks release; the same nudges Claude Code sees
flow through.

## Install

```bash
mkdir -p ~/.codex/hooks
cp hooks/codex/agent-do-prompt-router.py    ~/.codex/hooks/
cp hooks/codex/agent-do-pretooluse-check.py ~/.codex/hooks/
cp hooks/codex/auto-commit.sh               ~/.codex/hooks/
chmod +x ~/.codex/hooks/auto-commit.sh

# Register the hooks (merge with any existing ~/.codex/hooks.json entries)
cp hooks/codex/hooks.json.example ~/.codex/hooks.json
```

`install.sh --codex` does this automatically when `~/.codex/` is present.

## What each file does

| File | Role |
|---|---|
| `agent-do-prompt-router.py` | Thin wrapper. `runpy.run_path` forwards stdin/stdout to the repo's `hooks/agent-do-prompt-router.py`. Emits AI-classified routing nudges. |
| `agent-do-pretooluse-check.py` | Thin wrapper. Forwards to the repo's `hooks/agent-do-pretooluse-check.py`. Emits raw-command nudges when an `agent-do` tool exists for the same job. |
| `auto-commit.sh` | Stop-event auto-commit with **safe-commit pattern**: no `--no-verify`, retries once after pre-commit auto-fix, fails loudly with `.handoff/auto-commit-blocked-<session>.md` breadcrumb + macOS notification when pre-commit really blocks. Includes coord-focus / env-var scoping so it never commits the whole repo on accident. |
| `hooks.json.example` | The Codex hook registration template. Copy to `~/.codex/hooks.json` and merge with existing entries. |

## What's in this bundle

Only hooks that nudge agents toward agent-do tools, manage agent-do state, or
implement agent-do conventions ship here. Personal productivity hooks
(screenshot shorthand, prompt annotation, git auto-commit, generic OS
notifications) belong in your own dotfiles, not in this repo.

| File | Role |
|---|---|
| `agent-do-session-start.py` | Codex SessionStart: agent-do project context, tooling reminder, bootstrap dialog with macOS notification + log on completion. |
| `agent-do-prompt-router.py` | Codex UserPromptSubmit: AI-classified routing nudges toward agent-do tools. |
| `agent-do-pretooluse-check.py` | Codex PreToolUse: raw-command nudges (`agent-do api` instead of `from anthropic import` etc.). |
| `stop-quality-gate.sh` | Codex Stop: advisory DPT scoring of the current agent-do browse session, surfaced as additionalContext for the model. Does not block. |
| `stop-quality-gate.py` | DPT scoring helper called by `stop-quality-gate.sh`; uses `agent-do browse` and `agent-do dpt`. |
| `hooks.json.example` | The Codex hook registration template. Copy to `~/.codex/hooks.json` and merge with existing entries. |

## Repo resolution

The wrappers look for the repo in this order:

1. `AGENT_DO_REPO` environment variable
2. `~/.agent-do/install-path` breadcrumb (written by `install.sh`)
3. `~/Custom-Coding/agent-do` default fallback (edit the wrapper if your clone is elsewhere)

## Auto-commit safety

`auto-commit.sh` **respects pre-commit hooks**. It never uses `--no-verify`.
Flow:

1. Try a clean commit. If it succeeds, done.
2. If pre-commit hooks auto-fixed files in place (formatters, linters with
   `--fix`), re-stage and retry once.
3. If commit still fails, write `.handoff/auto-commit-blocked-<session>.md`
   with the pre-commit output and staged file list, fire a macOS notification
   (Basso sound), exit non-zero. The work stays staged; you recover by
   reviewing the breadcrumb and committing manually.

This is opt-in safety. The auto-commit habit stays; silent bypass goes.
