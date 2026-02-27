#!/bin/bash
# SessionStart hook: Add agent-do to PATH, inject tooling reminder,
# load always-active skills, detect frontend projects
#
# Auto-detects agent-do location (no hardcoded paths):
#   1. `which agent-do` (already in PATH)
#   2. ~/.local/bin/agent-do symlink (install.sh creates this)
#   3. ~/.agent-do/install-path breadcrumb file

INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd // ""')

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

# --- Load always-active skill: artful-claude ---
SKILL_FILE="$HOME/.claude/skills/artful-claude/SKILL.md"
if [ -f "$SKILL_FILE" ]; then
    SKILL_CONTENT=$(cat "$SKILL_FILE")
    CONTEXT="$CONTEXT

---

## ALWAYS-ACTIVE SKILL: artful-claude (MANDATORY)

The following skill governs ALL output — terminal, files, docs, conversation. Apply on every turn without exception.

$SKILL_CONTENT"
fi

# --- Detect frontend project → inject design toolkit ---
IS_FRONTEND=false

if [ -n "$CWD" ]; then
    # Check root package.json for frontend frameworks
    if [ -f "$CWD/package.json" ]; then
        if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$CWD/package.json" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi

    # Check monorepo subdirs (apps/*, packages/*)
    if [ "$IS_FRONTEND" = false ]; then
        for subdir in "$CWD"/apps/*/package.json "$CWD"/packages/*/package.json; do
            [ -f "$subdir" ] || continue
            if grep -qE '"(react|next|vue|nuxt|svelte|astro|angular|remix|gatsby|solid-js)"' "$subdir" 2>/dev/null; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for frontend file extensions in src/ or app/
    if [ "$IS_FRONTEND" = false ]; then
        for dir in "$CWD/src" "$CWD/app" "$CWD/apps"; do
            [ -d "$dir" ] || continue
            if find "$dir" -maxdepth 4 -name '*.tsx' -o -name '*.jsx' -o -name '*.vue' -o -name '*.svelte' 2>/dev/null | head -1 | grep -q .; then
                IS_FRONTEND=true
                break
            fi
        done
    fi

    # Check for Flutter/Dart (also has UI)
    if [ "$IS_FRONTEND" = false ] && [ -f "$CWD/pubspec.yaml" ]; then
        if grep -q 'flutter' "$CWD/pubspec.yaml" 2>/dev/null; then
            IS_FRONTEND=true
        fi
    fi
fi

if [ "$IS_FRONTEND" = true ]; then
    CONTEXT="$CONTEXT

---

## FRONTEND PROJECT DETECTED — Design Toolkit Active

This is a frontend project. When doing ANY visual/UI work, you MUST:

### 1. Load Design Skills
Read and apply these skills for all UI work:
- \`~/.claude/skills/artful-ux/SKILL.md\` — layout, hierarchy, interaction, spacing, anti-patterns
- \`~/.claude/skills/artful-colors/SKILL.md\` — color perception, palette, cultural context
- \`~/.claude/skills/artful-typography/SKILL.md\` — typeface selection, hierarchy, responsive type

### 2. Use Browser Verification (MANDATORY)
Never edit UI code without visual verification:
\`\`\`
agent-do browse open <dev-url>
agent-do browse screenshot /tmp/before.png   # visual truth — view with Read tool
agent-do browse snapshot -i                  # structural inventory
\`\`\`

Workflow: baseline screenshot → code → reload → screenshot → Quick-5 → fix → confirm.

### 3. Score with DPT
After visual changes, score the result:
\`\`\`
agent-do dpt score /tmp/after.png            # 0-100 with per-layer breakdown
\`\`\`

Screenshots for evaluation. Snapshots for inventory. Both, in that order."
fi

# --- Detect ZPC project → mention memory ---
if [ -n "$CWD" ] && [ -d "$CWD/.zpc" ]; then
    CONTEXT="$CONTEXT

---

## ZPC Memory Available

This project has ZPC memory at \`.zpc/\`. At session start:
\`\`\`
agent-do zpc status      # Memory health + counts
agent-do zpc patterns    # Established conventions — read before coding
\`\`\`
Log lessons and decisions as you work. Run \`agent-do zpc harvest\` after significant work."
fi

ESCAPED=$(echo "$CONTEXT" | jq -Rs .)
echo "{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":$ESCAPED}}"
exit 0
