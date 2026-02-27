# agent-do

75 tools that give AI agents structured access to everything outside the editor. Two modes, one interface.

```bash
agent-do <tool> <command> [args...]   # Structured API (AI/scripts — instant, no LLM)
agent-do -n "what you want"           # Natural language (humans — LLM-routed)
```

## The Tools That Change How Agents Work

Most of agent-do's 75 tools are solid wrappers — they give AI agents clean interfaces to Docker, Kubernetes, Slack, SSH, and dozens more. But a few tools do something no other framework offers.

### browse — AI-Native Browser

Headless Playwright browser with `@ref`-based element selection. Agents don't write CSS selectors or XPaths. They snapshot the page, get semantic references (`@e1`, `@e3`, `@e7`), and interact by reference.

```bash
agent-do browse open https://app.example.com
agent-do browse snapshot -i          # Interactive elements with @e1, @e2, @e3...
agent-do browse fill @e3 "admin"     # Fill by reference
agent-do browse click @e7            # Click by reference
agent-do browse wait --stable        # Wait for network + DOM to settle
```

The capture pipeline turns any browsing session into a reusable API skill:

```bash
agent-do browse capture start        # Record all XHR/fetch traffic
# ... click around, trigger API calls ...
agent-do browse capture stop myapi   # Filter → extract auth → generate curl skill
agent-do browse api myapi get_users  # Call via curl (~100x faster than browser)
```

One session of manual browsing produces a permanent, authenticated API client.

### zpc — Structured Project Memory

AI agents forget everything between sessions. ZPC fixes that. Lessons, decisions, and patterns persist in `.zpc/memory/` and compound over time.

```bash
agent-do zpc init                    # Initialize in any project
agent-do zpc learn "deploying" "missing env var" "added .env.example" "always ship env templates" --tags "deploy,env"
agent-do zpc decide "Which DB?" --options "postgres,sqlite" --chosen postgres --rationale "team expertise" --confidence 0.9
agent-do zpc harvest --auto          # Consolidate lessons into patterns
```

Format enforcement at the tool boundary — agents can't write malformed JSONL. The `inject` command feeds memory into spawned agents with baseline counts that ground self-reports against verifiable reality. The single change that moved multi-agent compliance from 0% to 100%.

```bash
agent-do zpc inject                  # Context blob for spawned agents
agent-do zpc status                  # Health check: lessons, decisions, patterns, gaps
agent-do zpc query --tag deploy      # Search across all memory
agent-do zpc promote --tag mypy --to team  # Share patterns via git-tracked team scope
```

### dpt — Design Perception Tensor

72 rules across 5 perception layers. Scores any UI screenshot 0–100 with specific, actionable findings.

```bash
agent-do browse screenshot /tmp/ui.png
agent-do dpt score /tmp/ui.png       # → 73/100 with per-layer breakdown
```

Five layers: Visual Hierarchy, Spacing & Rhythm, Color & Contrast, Typography, Interaction Affordances. Each rule fires or doesn't — no subjective "looks good." Agents use DPT to verify their own UI work before reporting done.

### unbrowse — API Capture → Curl Skills

Launch a headed browser, browse manually, stop the capture. Out comes a documented, authenticated curl-based API skill file.

```bash
agent-do unbrowse capture https://dashboard.example.com
# Browse around in the visible browser window...
agent-do unbrowse stop myservice     # → ~/.agent-do/skills/myservice/
agent-do unbrowse replay myservice get_users   # Call endpoint via curl
```

No API documentation needed. No auth token hunting. The skill file captures everything: endpoints, headers, auth tokens, request shapes. Works against any web application with an API.

### manna — Git-Backed Issue Tracking

Purpose-built for AI agent swarms. Claims prevent two agents from working the same issue. Dependencies block work automatically.

```bash
agent-do manna init
agent-do manna create "Add auth" "JWT with refresh tokens"   # → mn-a1b2c3
agent-do manna create "Add login UI" "Form with validation"  # → mn-d4e5f6
agent-do manna block mn-d4e5f6 mn-a1b2c3                     # Login blocked by auth
agent-do manna claim mn-a1b2c3       # Agent claims ownership
# ... work ...
agent-do manna done mn-a1b2c3        # → mn-d4e5f6 auto-unblocks
```

---

## All 75 Tools

| Category | Tools | What They Do |
|----------|-------|-------------|
| **Browser** | browse, unbrowse | Headless browser + @ref selection, API traffic capture → curl skills |
| **Memory** | zpc | Structured project memory — lessons, decisions, patterns, harvest, inject |
| **Design** | dpt | Visual quality scoring — 72 rules, 5 perception layers, 0–100 score |
| **Tracking** | manna | Git-backed issue tracking with claims and dependencies |
| **Mobile** | ios, android | Simulator/emulator control, screenshots, gestures |
| **Desktop** | macos, tui, screen, ide | GUI automation, terminal apps, multi-display vision |
| **Data** | db, excel, sheets, pdf, pdf2md | Database queries, spreadsheets, PDF conversion |
| **Communication** | slack, discord, email, sms, teams, zoom, meet, voice | Messaging and meetings |
| **Productivity** | calendar, notion, linear, figma, jupyter, lab, colab | App integrations |
| **Infrastructure** | docker, k8s, cloud, gcp, ci, vm, network, dns, ssh, render, vercel, supabase | Containers, clusters, cloud, PaaS |
| **Creative** | image, video, audio, 3d, cad, latex | Media processing |
| **Security** | burp, wireshark, ghidra | Security analysis |
| **Hardware** | serial, midi, homekit, bluetooth, usb, printer | Device control |
| **AI/Meta** | prompt, eval, memory, learn, swarm, agent, repl | Agent orchestration |
| **Dev Tools** | git, api, tail, logs, sessions | Git, HTTP testing, log capture, session history |
| **Utilities** | clipboard, ocr, vision, metrics, debug | System utilities |

Run `agent-do --list` for the full list. Run `agent-do <tool> --help` for any tool.

## The Universal Pattern

Every tool follows: **Connect → Snapshot → Interact → Verify → Save**

```bash
agent-do db connect mydb          # 1. Connect
agent-do db snapshot              # 2. See current state (schema, tables, types)
agent-do db query "SELECT ..."    # 3. Interact
agent-do db sample orders 5       # 4. Verify
agent-do db disconnect            # 5. Clean up
```

The **snapshot** step is the key insight. AI agents can't see a database schema, a browser page, or an iOS screen directly. Snapshot gives them structured understanding of the current state. Without it, agents are blind.

## Two Modes

```bash
# Structured API — instant, deterministic, no LLM. Use this in AI agents.
agent-do ios screenshot ~/screen.png
agent-do db query "SELECT count(*) FROM users"
agent-do zpc learn "ctx" "prob" "sol" "takeaway" --tags "tag"

# Natural language — LLM-routed. Use this as a human.
agent-do -n "screenshot my iPhone simulator"
agent-do -n "how many users do we have"
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
                            (75 executables)
```

Structured API calls bypass the LLM entirely — direct dispatch to the tool executable. Natural language routes through a 3-tier fallback: SQLite cache, Jaccard fuzzy match, then Claude API. Offline mode uses regex + keyword matching with no API key.

## Installation

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
```

The installer symlinks `agent-do` into PATH, copies Claude Code hooks, installs Python dependencies, and optionally builds the Node.js and Rust tools.

See [INTEGRATION.md](INTEGRATION.md) for Claude Code hook details (nudge vs block mode, manual setup).

### Prerequisites

- **Python 3.10+** with `anthropic` and `pyyaml`
- **Node.js 18+** (for browse and unbrowse)
- **Rust** (for agent-manna)
- **tmux** (for agent-tui)

### Environment Variables

```bash
AGENT_DO_HOME         # Config/state directory (default: ~/.agent-do)
ANTHROPIC_API_KEY     # Required for natural language mode
RENDER_API_KEY        # Render.com (agent-render)
VERCEL_ACCESS_TOKEN   # Vercel (agent-vercel)
SUPABASE_ACCESS_TOKEN # Supabase (agent-supabase)
GCP_SERVICE_ACCOUNT   # Google Cloud (agent-gcp)
```

## Adding Tools

```bash
tools/agent-<name>/agent-<name>   # Directory with nested executable
tools/agent-<name>                # Standalone executable
agent-<name> in $PATH             # External tool
```

Create an executable, add an entry to `registry.yaml`, and `--list` auto-discovers it. Shared libraries `lib/snapshot.sh` and `lib/json-output.sh` give every bash tool JSON output and `--json` flag support for free.

## License

MIT
