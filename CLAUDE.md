# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

agent-do is a universal automation CLI framework for agentic AI harnesses with 60+ specialized tools. It provides:
- **Structured API** (AI/scripts): `agent-do <tool> <command> [args...]` - instant, no LLM
- **Natural Language** (humans): `agent-do -n "what you want"` - LLM-routed via Claude

## Commands

```bash
# Run tests
./test.sh

# List available tools
./agent-do --list

# Tool help
./agent-do <tool> --help

# Status (active sessions, simulator state, etc.)
./agent-do --status

# Offline pattern matching (no API key needed)
./agent-do --offline "intent"

# Dry run (shows what would execute)
./agent-do --dry-run "intent"
```

### Tool-Specific

```bash
# agent-manna (Rust)
cd tools/agent-manna && cargo build --release
cd tools/agent-manna && cargo test

# agent-browse (Node.js)
cd tools/agent-browse && npm install
```

## Architecture

```
agent-do                    # Main entry (bash) - routes to tools or LLM
├── bin/
│   ├── intent-router       # Claude-powered NLP → structured command (Python)
│   ├── pattern-matcher     # Offline fallback router (Python)
│   └── status              # Session status display
├── lib/
│   ├── state.py            # Session state (~/.agent-do/state.yaml)
│   ├── registry.py         # Tool registry loader
│   └── cache.py            # Pattern cache (SQLite)
├── tools/agent-*           # 60+ automation tools
└── registry.yaml           # Master tool catalog (1000+ lines)
```

### Routing Flow

1. **Structured API**: `agent-do ios screenshot` → direct tool execution
2. **Natural Language**: `agent-do -n "screenshot iOS"` →
   - Pattern cache (learned mappings)
   - Pattern matcher (offline keywords)
   - Intent router (Claude API)
   → tool execution

### Key Tools

| Tool | Tech | Purpose |
|------|------|---------|
| `agent-browse/` | Node.js/Playwright | Headless browser with @ref selection |
| `agent-ios` | Bash | iOS Simulator control |
| `agent-tui` | Bash/tmux | Terminal app automation |
| `agent-db/` | Bash | Database exploration |
| `agent-excel/` | Bash | Spreadsheet automation |
| `agent-manna/` | Rust | Git-backed issue tracking |
| `agent-macos/` | Bash | macOS GUI automation |

### Universal Pattern

All tools follow: **Connect → Snapshot → Interact → Verify → Save**

```bash
agent-do browse open https://example.com   # Connect
agent-do browse snapshot -i                 # Snapshot (get @refs)
agent-do browse click @e3                   # Interact
agent-do browse wait --stable              # Verify
```

### @ref-Based Selection

Browser and GUI tools use semantic element references from snapshots:
```bash
agent-do browse snapshot -i    # Returns @e1, @e2, etc.
agent-do browse click @e7      # Not raw selectors
```

## Adding Tools

1. Create executable at `tools/agent-<name>`
2. Add entry to `registry.yaml` with description, commands, examples
3. Tool must support `--help` flag

## Environment

- `AGENT_DO_HOME`: Config directory (default: `~/.agent-do`)
- `ANTHROPIC_API_KEY`: Required for natural language mode
- `MANNA_SESSION_ID`: Override session ID for agent-manna

## Dependencies

**Root** (Python): `anthropic>=0.18.0`, `pyyaml>=6.0`

**agent-browse** (Node.js): `playwright-core`, `ws`, `zod`

**agent-manna** (Rust): clap, serde, serde_json, serde_yaml, chrono, sha2, fs2

## Key Files

- `AGENTS.md`: Detailed tool reference with workflows
- `ARCHITECTURE.md`: Integration patterns for AI harnesses
- `registry.yaml`: Tool catalog with capabilities and examples
- `PLAN.md`: Vision and milestones
