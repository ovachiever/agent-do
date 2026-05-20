#!/bin/bash
# install.sh — Idempotent installer for agent-do + Claude Code (+ optional Codex) hooks
#
# What it does:
#   1. Symlinks agent-do into ~/.local/bin (adds to PATH)
#   2. Writes breadcrumb at ~/.agent-do/install-path
#   3. Copies Claude Code hooks to ~/.claude/hooks/
#   4. Optional: Codex hooks to ~/.codex/hooks/ (--codex or auto-detected)
#   5. Installs Python dependencies
#   6. Optional: npm install for browse/unbrowse
#   7. Optional: cargo build for manna
#   8. Runs agent-do --health
#   9. Prints Claude settings.json snippet (doesn't auto-modify)
#  10. Prints Codex hooks.json snippet if Codex install ran
#  11. Prints CLAUDE.md snippet for projects
#
# Usage:
#   ./install.sh              # Install (auto-installs Codex hooks if ~/.codex/ exists)
#   ./install.sh --codex      # Force Codex install even without ~/.codex/
#   ./install.sh --no-codex   # Skip Codex install even when ~/.codex/ exists
#   ./install.sh --uninstall  # Remove symlink + hooks (both Claude and Codex)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYMLINK_DIR="$HOME/.local/bin"
SYMLINK_PATH="$SYMLINK_DIR/agent-do"
AGENT_DO_HOME="${AGENT_DO_HOME:-$HOME/.agent-do}"
CLAUDE_HOOKS_DIR="$HOME/.claude/hooks"
CODEX_HOOKS_DIR="$HOME/.codex/hooks"
HOOKS_DIR="$REPO_DIR/hooks"
CODEX_HOOKS_SRC="$HOOKS_DIR/codex"

# Decide whether to install Codex hooks. Default: auto (yes if ~/.codex/ exists).
INSTALL_CODEX="auto"
for arg in "$@"; do
    case "$arg" in
        --codex)    INSTALL_CODEX="yes" ;;
        --no-codex) INSTALL_CODEX="no"  ;;
    esac
done

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

    # Remove Claude hooks that agent-do installs (only those, not personal hooks)
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

    # Remove Codex hooks that agent-do installs (only those, not personal hooks)
    local codex_hooks=(
        "agent-do-session-start.py"
        "agent-do-prompt-router.py"
        "agent-do-pretooluse-check.py"
        "stop-quality-gate.sh"
        "stop-quality-gate.py"
    )
    for hook in "${codex_hooks[@]}"; do
        if [ -f "$CODEX_HOOKS_DIR/$hook" ]; then
            rm "$CODEX_HOOKS_DIR/$hook"
            info "Removed Codex hook $CODEX_HOOKS_DIR/$hook"
        fi
    done

    echo ""
    warn "Remember to remove the agent-do hooks from ~/.claude/settings.json"
    warn "and ~/.codex/hooks.json. Search for 'agent-do' in the hooks sections."
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

# 3. Install hooks (wrapper-based, so `git pull` updates flow through)
#
# Installed hooks are thin wrappers that delegate to the canonical files
# under `<repo>/hooks/`. This means:
#   - `git pull` on the repo immediately changes hook behavior on the next
#     event. No re-install needed unless the wrapper itself changes (rare).
#   - Hooks that import from `<repo>/lib/` work correctly because the wrapper
#     resolves the repo root and sets sys.path before delegating.
#   - The wrappers themselves are version-tagged so re-running install.sh
#     refreshes them when the wrapper format changes.
#
# The canonical hook files stay in `hooks/` (Claude defaults) and
# `hooks/codex/` (Codex-specific variants). install.sh writes the
# corresponding wrapper at the installed path.

WRAPPER_VERSION="2"
# v2: hooks restructured into hooks/claude/ + hooks/codex/ symmetric dirs.
#     Auto-commit removed from the bundle (it's git automation, not agent-do).

install_py_wrapper() {
    local repo_hook_rel="$1"  # e.g. "hooks/agent-do-prompt-router.py"
    local installed="$2"      # e.g. "$CLAUDE_HOOKS_DIR/agent-do-prompt-router.py"
    local hook_name
    hook_name=$(basename "$installed")
    cat > "$installed" <<WRAPPER
#!/usr/bin/env python3
# agent-do hook wrapper v$WRAPPER_VERSION (managed by install.sh; do not edit).
# Delegates to the canonical hook under the agent-do repo so that future
# \`git pull\` updates flow through without re-running install.sh.
import os
import runpy
import sys
from pathlib import Path


def _resolve_repo():
    env_root = os.environ.get("AGENT_DO_REPO")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.is_dir():
            return candidate
    breadcrumb = Path.home() / ".agent-do" / "install-path"
    if breadcrumb.is_file():
        try:
            candidate = Path(breadcrumb.read_text().strip()).expanduser()
            if candidate.is_dir():
                return candidate
        except OSError:
            pass
    return None


def main():
    repo = _resolve_repo()
    if repo is None:
        sys.stderr.write(
            "[$hook_name wrapper] could not resolve agent-do repo; "
            "set AGENT_DO_REPO or run install.sh\\n"
        )
        return
    hook = repo / "$repo_hook_rel"
    if not hook.is_file():
        sys.stderr.write(f"[$hook_name wrapper] canonical hook missing: {hook}\\n")
        return
    sys.path.insert(0, str(repo / "lib"))
    runpy.run_path(str(hook), run_name="__main__")


if __name__ == "__main__":
    main()
WRAPPER
    chmod +x "$installed"
}

install_sh_wrapper() {
    local repo_hook_rel="$1"
    local installed="$2"
    local hook_name
    hook_name=$(basename "$installed")
    cat > "$installed" <<WRAPPER
#!/usr/bin/env bash
# agent-do hook wrapper v$WRAPPER_VERSION (managed by install.sh; do not edit).
# Delegates to the canonical hook under the agent-do repo so that future
# \`git pull\` updates flow through without re-running install.sh.
set -uo pipefail
repo="\${AGENT_DO_REPO:-\$(cat "\$HOME/.agent-do/install-path" 2>/dev/null)}"
if [ -z "\$repo" ] || [ ! -d "\$repo" ]; then
    echo "[$hook_name wrapper] could not resolve agent-do repo; set AGENT_DO_REPO or run install.sh" >&2
    exit 0
fi
canonical="\$repo/$repo_hook_rel"
if [ ! -x "\$canonical" ]; then
    echo "[$hook_name wrapper] canonical hook missing or not executable: \$canonical" >&2
    exit 0
fi
exec "\$canonical" "\$@"
WRAPPER
    chmod +x "$installed"
}

step "Installing Claude Code hooks (wrapper-based)"
mkdir -p "$CLAUDE_HOOKS_DIR"

# Map: installed-name | source-relative-to-repo | wrapper-kind
#
# Scope: only hooks that nudge agents toward agent-do tools, manage agent-do
# state, or implement agent-do conventions ship here. Personal productivity
# hooks (screenshot shorthand, prompt annotation, git auto-commit, generic
# OS notifications) belong in your dotfiles, not in the agent-do repo.
CLAUDE_HOOK_SPECS=(
    "agent-do-session-start.sh|hooks/claude/agent-do-session-start.sh|sh"
    "agent-do-prompt-router.py|hooks/claude/agent-do-prompt-router.py|py"
    "agent-do-pretooluse-check.py|hooks/claude/agent-do-pretooluse-check.py|py"
)
for spec in "${CLAUDE_HOOK_SPECS[@]}"; do
    IFS='|' read -r name rel kind <<< "$spec"
    src="$REPO_DIR/$rel"
    dst="$CLAUDE_HOOKS_DIR/$name"
    if [ ! -f "$src" ]; then
        err "Hook source not found: $src"
        continue
    fi
    case "$kind" in
        py) install_py_wrapper "$rel" "$dst" ;;
        sh) install_sh_wrapper "$rel" "$dst" ;;
    esac
    info "Installed Claude wrapper: $name → $rel"
done

# 3b. Optional: Codex hooks (also wrapper-based, same upgrade model)
should_install_codex="no"
case "$INSTALL_CODEX" in
    yes)  should_install_codex="yes" ;;
    auto) [ -d "$HOME/.codex" ] && should_install_codex="yes" ;;
esac

if [ "$should_install_codex" = "yes" ]; then
    step "Installing Codex hooks (wrapper-based)"
    mkdir -p "$CODEX_HOOKS_DIR"

    CODEX_HOOK_SPECS=(
        "agent-do-session-start.py|hooks/codex/agent-do-session-start.py|py"
        "agent-do-prompt-router.py|hooks/codex/agent-do-prompt-router.py|py"
        "agent-do-pretooluse-check.py|hooks/codex/agent-do-pretooluse-check.py|py"
        "stop-quality-gate.sh|hooks/codex/stop-quality-gate.sh|sh"
        "stop-quality-gate.py|hooks/codex/stop-quality-gate.py|py"
    )
    for spec in "${CODEX_HOOK_SPECS[@]}"; do
        IFS='|' read -r name rel kind <<< "$spec"
        src="$REPO_DIR/$rel"
        dst="$CODEX_HOOKS_DIR/$name"
        if [ ! -f "$src" ]; then
            err "Codex hook source not found: $src"
            continue
        fi
        case "$kind" in
            py) install_py_wrapper "$rel" "$dst" ;;
            sh) install_sh_wrapper "$rel" "$dst" ;;
        esac
        info "Installed Codex wrapper: $name → $rel"
    done

    info "Codex registration template: $CODEX_HOOKS_SRC/hooks.json.example"
    info "Merge into ~/.codex/hooks.json (see snippet at the end of this run)"
else
    info "Skipped Codex install (use --codex to force, or install ~/.codex/ first)"
fi

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
    ],
  }
}
SETTINGS_JSON
echo ""
echo "Note: agent-do does not register a Stop hook. If you want auto-commit,"
echo "DPT scoring at turn end, or other Stop-time behavior, register your"
echo "own scripts in settings.json under Stop. agent-do scopes itself to"
echo "agent-first tooling nudges and project bootstrap."
echo ""

# 8b. Print Codex hooks.json snippet if Codex install ran
if [ "$should_install_codex" = "yes" ]; then
    step "Codex hooks.json configuration"
    echo ""
    echo "Codex now supports hookSpecificOutput.additionalContext on PreToolUse"
    echo "(May 2026 release). The wrappers in ~/.codex/hooks/ runpy-pass-through to"
    echo "this repo's hooks, so updates flow through automatically."
    echo ""
    echo "Merge the following into ~/.codex/hooks.json (full template is at"
    echo "$CODEX_HOOKS_SRC/hooks.json.example):"
    echo ""
    cat "$CODEX_HOOKS_SRC/hooks.json.example"
    echo ""
fi

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
agent-do --list                       # List all 80 tools
agent-do <tool> --help                # Per-tool help
```

Key tools: vercel, render, supabase, gcp, browse, ios, android, macos, tui, db,
docker, k8s, cloud, ssh, excel, slack, image, video, audio, zpc
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
