# agent-do

Universal automation CLI for AI agents. 74 tools, two modes, one interface.

## What is agent-do?

agent-do gives AI coding agents (Claude Code, Cursor, OpenCode, etc.) structured access to everything outside the editor: browsers, iOS simulators, databases, cloud platforms, spreadsheets, Slack, Docker, and 60+ more tools. Instead of writing fragile automation scripts, agents call `agent-do <tool> <command>` and get JSON responses they can reason about.

Two modes:
- **Structured API** (for AI/scripts): `agent-do <tool> <command> [args...]` — instant, no LLM
- **Natural language** (for humans): `agent-do -n "what you want"` — LLM-routed

## Quick Start

```bash
git clone https://github.com/your-org/agent-do.git
cd agent-do

# See what's available
./agent-do --list

# Use structured API (AI-optimized, no LLM needed)
./agent-do browse open https://example.com
./agent-do browse snapshot -i
./agent-do browse click @e3

# Use natural language (human-friendly, requires ANTHROPIC_API_KEY)
./agent-do -n "take a screenshot of the iOS simulator"
```

## Tools by Category

| Category | Tools | Examples |
|----------|-------|---------|
| **Browser** | browse, unbrowse | Headless browser, API traffic capture, curl skill generation |
| **Mobile** | ios, android | Simulator/emulator control, screenshots, gestures |
| **Desktop** | macos, tui, screen, ide | Desktop GUI automation, terminal apps, screen capture |
| **Data** | db, excel, sheets, pdf, pdf2md | Database queries, spreadsheet automation, PDF conversion |
| **Communication** | slack, discord, email, sms, teams, zoom, meet, voice | Messaging and meetings |
| **Productivity** | calendar, notion, linear, figma, jupyter, lab, colab | App integrations |
| **Infrastructure** | docker, k8s, cloud, gcp, ci, vm, network, dns, ssh, render, vercel, supabase | Containers, clusters, cloud platforms, PaaS management |
| **Creative** | image, video, audio, 3d, cad, latex | Media processing |
| **Security** | burp, wireshark, ghidra | Security analysis tools |
| **Hardware** | serial, midi, homekit, bluetooth, usb, printer | Device control |
| **AI/Meta** | prompt, eval, memory, learn, swarm, agent, repl | Agent orchestration |
| **Tracking** | manna | Git-backed issue tracking for AI agents |
| **Dev Tools** | git, api, tail, logs, sessions | Git operations, HTTP testing, log capture, log viewing, session history |
| **Design** | dpt | Design quality scoring (72 rules, 0-100 score) |
| **Utilities** | clipboard, ocr, vision, metrics, debug | System utilities |

74 tools total. Run `agent-do --list` for the full list with descriptions.

## Key Concepts

### Structured API vs Natural Language

AI agents should use the structured API for speed and reliability:

```bash
# Structured (instant, deterministic) — use this in AI agents
agent-do ios screenshot ~/screen.png
agent-do db query "SELECT count(*) FROM users"

# Natural language (LLM-routed) — use this as a human
agent-do -n "screenshot my iPhone simulator"
agent-do -n "how many users do we have"
```

### The Universal Pattern

All tools follow: **Connect → Snapshot → Interact → Verify → Save**

```bash
agent-do db connect mydb          # 1. Connect
agent-do db snapshot              # 2. See schema (tables, columns, types)
agent-do db query "SELECT ..."    # 3. Interact
agent-do db sample orders 5       # 4. Verify
agent-do db disconnect            # 5. Clean up
```

The **snapshot** step is critical — it gives AI agents structured visibility into the current state. Without it, agents are blind.

### @ref-Based Element Selection

Browser and GUI tools use semantic element references from snapshots:

```bash
agent-do browse open https://example.com
agent-do browse snapshot -i        # Returns elements with @e1, @e2, @e3...
agent-do browse click @e3          # Click by reference, not brittle selectors
agent-do browse fill @e5 "hello"
```

### Snapshot Commands

Every tool supports a `snapshot` command that returns JSON state for AI consumption:

```bash
agent-do docker snapshot       # Running containers, images, volumes
agent-do git snapshot          # Branch, status, recent commits
agent-do slack snapshot        # Channels, unread counts
agent-do ios snapshot          # Device state, running apps
```

## Architecture

```
                          agent-do "intent or tool"
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              Structured API   Natural Language   Offline
              (is_tool?)       (-n flag)          (--offline)
                    │               │               │
                    │         ┌─────┴─────┐    pattern-matcher
                    │         │ 3-tier    │    (regex + keywords)
                    │         │ fallback: │
                    │         │ 1. cache  │
                    │         │ 2. fuzzy  │
                    │         │ 3. LLM    │
                    │         └─────┬─────┘
                    └───────────────┼───────────────┘
                                    │
                                    ▼
                            tools/agent-<name>
                            (74 executables)
```

**Routing flow:**
1. **Structured API**: `agent-do ios screenshot` → `is_tool()` matches `ios` → dispatches to `tools/agent-ios`
2. **Natural language** (`-n`): SQLite cache → Jaccard fuzzy match → Claude API call
3. **Offline** (`--offline`): regex patterns + keyword matching, no API needed

## Installation

### Prerequisites

- **Python 3.10+** with `anthropic` and `pyyaml` (for natural language routing)
- **Node.js 18+** (for browse and unbrowse tools)
- **Rust** (to build agent-manna from source)
- **tmux** (for agent-tui)
- **Xcode CLI Tools** (for agent-ios on macOS)

### Setup

```bash
git clone https://github.com/your-org/agent-do.git
cd agent-do

# Python dependencies (for natural language mode)
pip install -r requirements.txt

# Browser tools
cd tools/agent-browse && npm install && cd ../..
cd tools/agent-unbrowse && npm install && cd ../..

# Issue tracker (Rust)
cd tools/agent-manna && cargo build --release && cd ../..

# Check what's ready
./agent-do --health
```

### Claude Code Integration

agent-do ships hooks that teach Claude Code to prefer `agent-do` tools over raw CLI commands:

```bash
./install.sh
```

This creates a PATH symlink, installs 3 Claude Code hooks (session start, prompt routing, command interception), and prints a `settings.json` snippet to register them.

See [INTEGRATION.md](INTEGRATION.md) for details on the hook system, nudge vs block mode, and manual setup.

### Environment Variables

```bash
AGENT_DO_HOME         # Config/state directory (default: ~/.agent-do)
ANTHROPIC_API_KEY     # Required for natural language mode and --dry-run/--how
RENDER_API_KEY        # API key for Render.com (agent-render)
VERCEL_ACCESS_TOKEN   # API token for Vercel (agent-vercel)
SUPABASE_ACCESS_TOKEN # API token for Supabase (agent-supabase)
GCP_SERVICE_ACCOUNT   # Path to service account JSON key (agent-gcp)
GCP_ACCESS_TOKEN      # Bearer token for Google Cloud (agent-gcp)
GCP_PROJECT           # Default GCP project ID (agent-gcp)
```

## Adding Tools

1. Create an executable at `tools/agent-<name>` (must support `--help` flag)
2. Add an entry to `registry.yaml` with description, capabilities, commands, and examples
3. The `--list` command auto-discovers tools via filesystem scan of `tools/agent-*`

Tools can be:
- A standalone executable: `tools/agent-myname`
- A directory with an executable inside: `tools/agent-myname/agent-myname`
- An executable found in `$PATH`

### Tool Resolution Order

1. `tools/agent-<name>/agent-<name>` (directory with nested executable)
2. `tools/agent-<name>` (standalone executable)
3. `agent-<name>` in `$PATH` (external)

## Framework Libraries

Shared libraries for building tools with consistent output:

| Library | Purpose | Usage |
|---------|---------|-------|
| `lib/snapshot.sh` | Structured JSON snapshot output | `source lib/snapshot.sh` then `snapshot_begin`, `snapshot_field`, `snapshot_end` |
| `lib/json-output.sh` | `--json` flag support and structured responses | `source lib/json-output.sh` then `json_success`, `json_error`, `json_result` |
| `bin/health` | Dependency health checking | `agent-do --health [tool...]` |

## Running Tests

```bash
./test.sh              # All tests (checks help, status, offline, pattern-matcher)
```

Tool-specific tests:

```bash
cd tools/agent-manna && cargo test
cd tools/agent-browse && node browser.test.js
```

## Project Structure

```
agent-do                    # Main entry point (bash)
├── bin/
│   ├── intent-router       # LLM router (Python): cache → fuzzy → Claude API
│   ├── pattern-matcher     # Offline router (Python): regex + keyword matching
│   ├── health              # Tool dependency checker (bash)
│   └── status              # Session status display (bash)
├── lib/
│   ├── state.py            # Session state CRUD (~/.agent-do/state.yaml)
│   ├── registry.py         # Tool registry loader (merges user/bundled/plugin)
│   ├── cache.py            # SQLite pattern cache + fuzzy matching
│   ├── snapshot.sh         # Shared JSON snapshot helpers for tools
│   └── json-output.sh      # Shared --json flag support for tools
├── tools/agent-*           # 74 tools (standalone scripts + directory-based tools)
├── registry.yaml           # Master tool catalog (~1000 lines)
├── test.sh                 # Test suite
└── requirements.txt        # Python dependencies
```

## License

MIT
