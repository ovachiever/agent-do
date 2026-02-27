#!/bin/bash
# install.sh — Idempotent installer for agent-do + Claude Code hooks
#
# What it does:
#   1. Symlinks agent-do into ~/.local/bin (adds to PATH)
#   2. Writes breadcrumb at ~/.agent-do/install-path
#   3. Copies 3 Claude Code hooks to ~/.claude/hooks/
#   4. Installs Python dependencies
#   5. Optional: npm install for browse/unbrowse
#   6. Optional: cargo build for manna
#   7. Runs agent-do --health
#   8. Prints settings.json snippet (doesn't auto-modify)
#   9. Prints CLAUDE.md snippet for projects
#
# Usage:
#   ./install.sh              # Install
#   ./install.sh --uninstall  # Remove symlink + hooks

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYMLINK_DIR="$HOME/.local/bin"
SYMLINK_PATH="$SYMLINK_DIR/agent-do"
AGENT_DO_HOME="${AGENT_DO_HOME:-$HOME/.agent-do}"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
HOOKS_DIR="$REPO_DIR/hooks"

# Colors (skip if not a terminal)
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    RED='\033[0;31m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' RED='' BLUE='' BOLD='' NC=''
fi

info()  { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*"; }
step()  { echo -e "\n${BOLD}${BLUE}→${NC} ${BOLD}$*${NC}"; }

# ─── Uninstall ───────────────────────────────────────────────────────────────

uninstall() {
    step "Uninstalling agent-do"

    # Remove symlink
    if [ -L "$SYMLINK_PATH" ]; then
        rm "$SYMLINK_PATH"
        info "Removed symlink $SYMLINK_PATH"
    else
        warn "No symlink at $SYMLINK_PATH"
    fi

    # Remove breadcrumb
    if [ -f "$AGENT_DO_HOME/install-path" ]; then
        rm "$AGENT_DO_HOME/install-path"
        info "Removed breadcrumb $AGENT_DO_HOME/install-path"
    fi

    # Remove hooks
    local hooks=(
        "agent-do-session-start.sh"
        "agent-do-prompt-router.py"
        "agent-do-pretooluse-check.py"
    )
    for hook in "${hooks[@]}"; do
        if [ -f "$CLAUDE_HOOKS_DIR/$hook" ]; then
            rm "$CLAUDE_HOOKS_DIR/$hook"
            info "Removed hook $CLAUDE_HOOKS_DIR/$hook"
        fi
    done

    echo ""
    warn "Remember to remove the agent-do hooks from ~/.claude/settings.json"
    warn "Search for 'agent-do' in the hooks section and remove those entries."
    echo ""
    info "Uninstall complete. Repo at $REPO_DIR is untouched."
    exit 0
}

if [ "${1:-}" = "--uninstall" ]; then
    uninstall
fi

# ─── Install ─────────────────────────────────────────────────────────────────

echo -e "${BOLD}agent-do installer${NC}"
echo "Repo: $REPO_DIR"
echo ""

# 1. Symlink into ~/.local/bin
step "Symlinking agent-do into PATH"
mkdir -p "$SYMLINK_DIR"
if [ -L "$SYMLINK_PATH" ]; then
    EXISTING=$(readlink "$SYMLINK_PATH" 2>/dev/null || true)
    if [ "$EXISTING" = "$REPO_DIR/agent-do" ]; then
        info "Symlink already correct: $SYMLINK_PATH → $REPO_DIR/agent-do"
    else
        ln -sf "$REPO_DIR/agent-do" "$SYMLINK_PATH"
        info "Updated symlink: $SYMLINK_PATH → $REPO_DIR/agent-do (was: $EXISTING)"
    fi
elif [ -e "$SYMLINK_PATH" ]; then
    err "$SYMLINK_PATH exists but is not a symlink — skipping (remove it manually)"
else
    ln -s "$REPO_DIR/agent-do" "$SYMLINK_PATH"
    info "Created symlink: $SYMLINK_PATH → $REPO_DIR/agent-do"
fi

# Check if ~/.local/bin is in PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$SYMLINK_DIR"; then
    warn "$SYMLINK_DIR is not in your PATH"
    warn "Add to your shell profile: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# 2. Write breadcrumb
step "Writing install-path breadcrumb"
mkdir -p "$AGENT_DO_HOME"
echo "$REPO_DIR" > "$AGENT_DO_HOME/install-path"
info "Wrote $AGENT_DO_HOME/install-path"

# 3. Copy hooks to ~/.claude/hooks/
step "Installing Claude Code hooks"
mkdir -p "$CLAUDE_HOOKS_DIR"

HOOK_FILES=(
    "agent-do-session-start.sh"
    "agent-do-prompt-router.py"
    "agent-do-pretooluse-check.py"
)
for hook in "${HOOK_FILES[@]}"; do
    src="$HOOKS_DIR/$hook"
    dst="$CLAUDE_HOOKS_DIR/$hook"
    if [ ! -f "$src" ]; then
        err "Hook source not found: $src"
        continue
    fi
    if [ -f "$dst" ] && diff -q "$src" "$dst" &>/dev/null; then
        info "Hook already up to date: $hook"
    else
        cp "$src" "$dst"
        chmod +x "$dst"
        info "Installed hook: $dst"
    fi
done

# 4. Python dependencies
step "Installing Python dependencies"
if command -v pip3 &>/dev/null; then
    pip3 install -r "$REPO_DIR/requirements.txt" --quiet 2>/dev/null && \
        info "Python dependencies installed" || \
        warn "pip install failed — try: pip3 install -r requirements.txt"
elif command -v pip &>/dev/null; then
    pip install -r "$REPO_DIR/requirements.txt" --quiet 2>/dev/null && \
        info "Python dependencies installed" || \
        warn "pip install failed — try: pip install -r requirements.txt"
else
    warn "pip not found — install Python deps manually: pip install -r requirements.txt"
fi

# 5. Optional: Node.js tools
step "Optional: Browser tools (agent-browse, agent-unbrowse)"
if command -v npm &>/dev/null; then
    read -rp "Install Node.js deps for browse/unbrowse? [y/N] " answer
    if [[ "$answer" =~ ^[Yy] ]]; then
        (cd "$REPO_DIR/tools/agent-browse" && npm install --quiet 2>/dev/null) && \
            info "agent-browse deps installed" || warn "agent-browse npm install failed"
        (cd "$REPO_DIR/tools/agent-unbrowse" && npm install --quiet 2>/dev/null) && \
            info "agent-unbrowse deps installed" || warn "agent-unbrowse npm install failed"
    else
        info "Skipped (run later: cd tools/agent-browse && npm install)"
    fi
else
    warn "npm not found — browser tools require Node.js 18+"
fi

# 6. Optional: Rust tool
step "Optional: Issue tracker (agent-manna)"
if command -v cargo &>/dev/null; then
    read -rp "Build agent-manna (Rust)? [y/N] " answer
    if [[ "$answer" =~ ^[Yy] ]]; then
        (cd "$REPO_DIR/tools/agent-manna" && cargo build --release --quiet 2>/dev/null) && \
            info "agent-manna built" || warn "cargo build failed"
    else
        info "Skipped (run later: cd tools/agent-manna && cargo build --release)"
    fi
else
    warn "cargo not found — agent-manna requires Rust"
fi

# 7. Health check
step "Running health check"
"$REPO_DIR/agent-do" --health 2>/dev/null || warn "Health check had issues (non-fatal)"

# 8. Print settings.json snippet
step "Claude Code settings.json configuration"
echo ""
echo "Add the following to ~/.claude/settings.json under the \"hooks\" key:"
echo "(If you already have hooks entries, merge these into the existing arrays)"
echo ""
cat << 'SETTINGS_JSON'
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
SETTINGS_JSON
echo ""

# 9. Print CLAUDE.md snippet
step "Project CLAUDE.md snippet"
echo ""
echo "Add the following to your project's CLAUDE.md to teach Claude about agent-do:"
echo ""
cat << 'CLAUDE_SNIPPET'
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

```bash
agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
agent-do -n "what you want"           # Natural language (humans)
agent-do --list                       # List all 74 tools
agent-do <tool> --help                # Per-tool help
```

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio
CLAUDE_SNIPPET
echo ""

# Done
echo -e "\n${BOLD}${GREEN}Installation complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Merge the settings.json snippet above into ~/.claude/settings.json"
echo "  2. Optionally add the CLAUDE.md snippet to your project"
echo "  3. Restart Claude Code to pick up the new hooks"
echo ""
echo "Verify: agent-do --list"
