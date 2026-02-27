#!/bin/bash
# SessionStart hook: Add agent-do to PATH and inject tooling reminder
# Part of the agent-do hook trinity
#
# Auto-detects agent-do location (no hardcoded paths):
#   1. `which agent-do` (already in PATH)
#   2. ~/.local/bin/agent-do symlink (install.sh creates this)
#   3. ~/.agent-do/install-path breadcrumb file
#
# Uses `readlink` (not `readlink -f`) for macOS compatibility since
# the symlink from install.sh is single-level.

INPUT=$(cat)

# --- Resolve agent-do location ---
AGENT_DO_DIR=""

# 1. Already in PATH?
if command -v agent-do &>/dev/null; then
    RESOLVED=$(readlink "$(command -v agent-do)" 2>/dev/null || command -v agent-do)
    AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
fi

# 2. Check ~/.local/bin symlink
if [ -z "$AGENT_DO_DIR" ] && [ -L "$HOME/.local/bin/agent-do" ]; then
    RESOLVED=$(readlink "$HOME/.local/bin/agent-do" 2>/dev/null)
    if [ -n "$RESOLVED" ] && [ -x "$RESOLVED" ]; then
        AGENT_DO_DIR="$(cd "$(dirname "$RESOLVED")" 2>/dev/null && pwd)"
    fi
fi

# 3. Check breadcrumb file
if [ -z "$AGENT_DO_DIR" ] && [ -f "$HOME/.agent-do/install-path" ]; then
    BREADCRUMB=$(cat "$HOME/.agent-do/install-path" 2>/dev/null)
    if [ -n "$BREADCRUMB" ] && [ -x "$BREADCRUMB/agent-do" ]; then
        AGENT_DO_DIR="$BREADCRUMB"
    fi
fi

# --- Add to PATH if found ---
if [ -n "$AGENT_DO_DIR" ] && [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH=\"$AGENT_DO_DIR:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# --- Inject tooling reminder ---
CONTEXT="## TOOLING REMINDER - agent-do

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.), CHECK if agent-do has a tool:

\`\`\`
agent-do \"natural language description of what you want\"
agent-do --how \"...\"     # Explain without executing
agent-do --raw <tool> ... # Direct tool access
\`\`\`

Discovery: agent-do --list (all tools) | agent-do <tool> --help (per-tool)

KEY TOOLS:
- vercel: Vercel operations (NOT vercel CLI or curl to api.vercel.com)
- render: Render.com operations (NOT curl to api.render.com)
- supabase: Supabase operations (NOT supabase CLI or curl to supabase.co)
- browse: Browser automation (NOT playwright, puppeteer, or selenium)
- ios: iOS Simulator (NOT xcrun simctl)
- android: Android Emulator (NOT adb directly)
- macos: macOS desktop automation (NOT osascript)
- gcp: Google Cloud Platform (NOT gcloud CLI or curl to googleapis.com)
- tui: Terminal UI automation (NOT raw expect/tmux)
- db: Database queries (NOT psql/mysql directly)
- docker/k8s/cloud/ssh: Infrastructure tools
- zpc: Structured project memory (NOT manual JSONL writes)

Prefer agent-do over raw CLI commands when a tool exists.
Use agent-do <tool> --help to see available commands."

ESCAPED=$(echo "$CONTEXT" | jq -Rs .)
echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$ESCAPED}}"
exit 0
