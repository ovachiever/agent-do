# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

agent-do is a universal automation CLI framework for agentic AI harnesses with 60+ specialized tools. Two modes:
- **Structured API** (AI/scripts): `agent-do <tool> <command> [args...]` — instant, no LLM
- **Natural Language** (humans): `agent-do -n "what you want"` — LLM-routed via Claude

## Commands

```bash
./test.sh                              # Run all tests (bash-based, checks help/status/offline/pattern-matcher)
./agent-do --list                      # List available tools
./agent-do <tool> --help               # Tool-specific help
./agent-do --status                    # Active sessions and state
./agent-do --offline "intent"          # Offline pattern matching (no API key)
./agent-do --dry-run "intent"          # Show what would execute (uses LLM)
```

### Tool-Specific Build/Test

```bash
# agent-manna (Rust)
cd tools/agent-manna && cargo build --release
cd tools/agent-manna && cargo test

# agent-browse (Node.js)
cd tools/agent-browse && npm install
cd tools/agent-browse && node browser.test.js   # or protocol.test.js

# agent-unbrowse (Node.js)
cd tools/agent-unbrowse && npm install
```

## Architecture

### Routing Flow (the critical path)

The main `agent-do` script (bash) decides the mode based on first argument:

1. **Structured API**: `agent-do ios screenshot` → `is_tool()` matches → `exec_tool()` dispatches to `tools/agent-ios`
2. **Natural Language** (`-n` flag): goes through a 3-tier fallback chain:
   - `lib/cache.py:check_cache()` — SQLite pattern cache (`~/.agent-do/cache/patterns.db`)
   - `lib/cache.py:fuzzy_match()` — Jaccard similarity against cached intents (threshold 0.6)
   - `bin/intent-router` — Claude API call (currently uses `claude-opus-4-5-20251101`)
3. **Offline** (`--offline`): `bin/pattern-matcher` — regex patterns + keyword matching against registry, no LLM

### Exit codes for natural language mode
- `0` = success
- `1` = error
- `2` = needs clarification (orchestrator should ask follow-up, then retry with `--context`)

### Tool Resolution

Tools live in `tools/agent-*`. The dispatcher checks (in order):
1. `tools/agent-<name>/agent-<name>` (directory with nested executable, e.g. agent-browse)
2. `tools/agent-<name>` (standalone executable)
3. `agent-<name>` in `$PATH`

Most tools are **symlinks** to `../../agent-CLIs/agent-<name>/agent-<name>` (sibling repo).

### Key Components

```
agent-do                    # Main entry (bash) — mode selection + tool dispatch
├── bin/
│   ├── intent-router       # LLM router (Python) — cache → fuzzy → Claude API
│   ├── pattern-matcher     # Offline router (Python) — regex + keyword matching
│   └── status              # Session status display (bash + inline Python)
├── lib/
│   ├── state.py            # Session state CRUD (~/.agent-do/state.yaml)
│   ├── registry.py         # Tool registry loader (merges user/bundled/plugin registries)
│   └── cache.py            # SQLite pattern cache + fuzzy matching
├── tools/agent-*           # 60+ tools (mostly symlinks, some bundled)
└── registry.yaml           # Master tool catalog — tool descriptions, commands, examples
```

### Registry Loading Order (registry.py)

Registries are loaded in reverse priority order so higher-priority sources win:
1. `~/.agent-do/registry.yaml` (user overrides, highest priority)
2. `./registry.yaml` (bundled)
3. `~/.agent-do/plugins/*.yaml` (plugin extensions)

### Session State

`lib/state.py` manages `~/.agent-do/state.yaml` — tracks active TUI/REPL/iOS/Android/Docker/SSH sessions. The intent router includes this state in LLM context so "my python session" resolves correctly.

### Key Tools (bundled in this repo)

| Tool | Tech | Notes |
|------|------|-------|
| `agent-browse/` | Node.js (Playwright) | Headless browser, @ref element selection, daemon.js manages browser lifecycle. Also has `capture start/stop` for API skill generation and `api` subcommand for replaying captured skills. |
| `agent-unbrowse/` | Node.js (Playwright) | Standalone API traffic capture → reusable curl-based skills. Launches its own headed browser for manual browsing. Shares filter/auth/generator pipeline with browse. |
| `agent-manna/` | Rust | Git-backed issue tracking with session claims, build with `cargo build --release` |

Other tools (`agent-ios`, `agent-tui`, `agent-db`, etc.) are bash scripts symlinked from sibling `agent-CLIs` repo.

### Universal Tool Pattern

All tools follow: **Connect → Snapshot → Interact → Verify → Save**

### @ref-Based Selection

Browser/GUI tools use semantic element references from snapshots:
```bash
agent-do browse snapshot -i    # Returns @e1, @e2, etc.
agent-do browse click @e7      # Use @refs, not raw selectors
```

## Adding Tools

1. Create executable at `tools/agent-<name>` (must support `--help` flag)
2. Add entry to `registry.yaml` with `description`, `capabilities`, `commands`, `examples`
3. The `--list` command auto-discovers tools via filesystem scan of `tools/agent-*`

## Environment

- `AGENT_DO_HOME`: Config/state directory (default: `~/.agent-do`)
- `ANTHROPIC_API_KEY`: Required for natural language mode and `--dry-run`/`--how`
- `MANNA_SESSION_ID`: Override session ID for agent-manna

## Dependencies

- **Python 3.10+**: `anthropic>=0.18.0`, `pyyaml>=6.0`
- **agent-browse**: Node.js with `playwright-core`, `ws`, `zod`
- **agent-unbrowse**: Node.js with `playwright-core`, `zod`
- **agent-manna**: Rust with clap, serde, serde_yaml, chrono, sha2, fs2
- **System**: tmux (for agent-tui), Xcode CLI Tools (for agent-ios)

## Key Files

- `AGENTS.md`: Detailed tool reference with full command workflows
- `ARCHITECTURE.md`: Integration patterns for different AI harnesses (Factory, Claude Code, OpenCode, Cursor, etc.)
- `registry.yaml`: Complete tool catalog (60 tools, ~1000 lines)
- `PLAN.md`: Vision, milestones, and implementation status
