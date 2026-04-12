# agent-do

<p align="center">
  <img src="assets/agent-do-logo.jpg" alt="agent-do logo" width="720" />
</p>

<p align="center"><strong>The outer harness for AI coding agents.</strong></p>

Claude Code, Cursor, and similar agents are strong inside a codebase. They read files, write code, run tests, and reason well. The hard part begins at the edge: browsers, simulators, databases, cloud platforms, design review, project memory, issue tracking, and the rest of the world outside the repo.

`agent-do` is the outer harness. It gives the inner agent one durable contract for acting in that world.

```bash
agent-do <tool> <command> [args...]
```

That is the center of gravity. Around it, `agent-do` adds discovery, nudging, health checks, bootstrap flows, secure credential resolution, auth-state orchestration, repo-local spec management, and natural-language routing. The result is simple to remember, easy to enforce through hooks, and broad enough to cover 84 tools.

## Why It Exists

Most agents know how to improvise. That is useful until it is not.

When an agent falls back to raw CLIs, custom curl calls, ad hoc Playwright scripts, or fragile shell glue, the session gets harder to understand, harder to repeat, and harder to improve. `agent-do` narrows that surface. It gives the agent a cleaner path:

- one command shape
- one registry
- one place for setup and readiness
- one discovery layer when the right tool is not obvious
- one hook surface for hard nudges without hard blocking

This is not a replacement for the inner agent. It is the structure around the inner agent that makes better behavior easier to choose.

## The Shape Of The System

The best `agent-do` tools share the same operational rhythm:

```text
Connect → Snapshot → Interact → Verify → Save
```

Snapshot is the hinge. An agent cannot reason well about a browser page, a database schema, or an iOS screen if it cannot see the current state in a structured way. Mature tools in this repo are designed around that need.

```bash
agent-do db connect mydb
agent-do db snapshot
agent-do db query "SELECT * FROM orders LIMIT 10"
agent-do db sample orders 5
agent-do db disconnect
```

Some tools are deep systems. Some are thinner wrappers. All of them aim at the same outer contract.

## Core Commands

When you already know the tool:

```bash
agent-do <tool> <command> [args...]
```

When you know the goal but not the tool:

```bash
agent-do suggest "deploy this service"
agent-do suggest --project
agent-do find playwright
```

When you want setup and readiness:

```bash
agent-do --health
agent-do bootstrap --recommend
agent-do bootstrap
agent-do nudges stats
```

When a tool needs secrets:

```bash
agent-do creds required render
agent-do creds store RENDER_API_KEY --stdin
agent-do creds check --tool render
```

When a site needs authenticated state:

```bash
agent-do auth init github
agent-do auth ensure github
agent-do auth validate github
```

When the repo needs durable behavior specs and change artifacts:

```bash
agent-do spec init
agent-do spec new add-oauth-device-flow --spec auth
agent-do spec status --change add-oauth-device-flow
```

When a human wants natural language routing:

```bash
agent-do -n "take an iOS screenshot"
agent-do --offline "deploy this on vercel"
agent-do --how "check render logs"
```

## Standout Tools

### `browse`

An AI-first Playwright surface with snapshot-driven interaction, reference IDs, headed login handoff, and API capture.

```bash
agent-do browse open https://app.example.com
agent-do browse snapshot -i
agent-do browse fill @e3 "admin"
agent-do browse click @e7
agent-do browse wait --stable
```

For sites with SSO or MFA:

```bash
agent-do browse login https://app.example.com
agent-do browse login done --save mysite
agent-do browse session load mysite
```

For turning a browsing session into a reusable curl skill:

```bash
agent-do browse capture start
agent-do browse capture stop myapi
agent-do browse api myapi get_users
```

For exact values hidden behind copy buttons instead of visible page text:

```bash
agent-do browse click @e12
agent-do browse clipboard read
```

### `zpc`

Structured project memory for lessons, decisions, patterns, and checkpointing.

```bash
agent-do zpc init
agent-do zpc learn "deploying" "missing env var" "added .env.example" "always ship env templates" --tags "deploy,env"
agent-do zpc decide "Which DB?" --options "postgres,sqlite" --chosen postgres --rationale "team expertise" --confidence 0.9
agent-do zpc harvest --auto
```

### `dpt`

Design Perception Tensor. A screenshot-in, critique-out visual quality tool with 72 rules across 5 perception layers.

```bash
agent-do browse screenshot /tmp/ui.png
agent-do dpt score /tmp/ui.png
```

### `context`

A searchable knowledge library for docs, repos, `llms.txt`, local skills, notes, and budget-aware assembly.

```bash
agent-do context fetch-llms stripe.com
agent-do context fetch-repo vercel/next.js docs/
agent-do context search "payments api"
agent-do context budget 4000 "react hooks"
agent-do context annotate stripe-llms "Use idempotency keys"
```

### `auth`

Site-level authentication orchestration over saved browser sessions, browser import, and secure credentials.

```bash
agent-do auth init github
agent-do auth ensure github
agent-do auth status github
agent-do auth validate github
```

### `resend`

Exact Resend domain records and verification state without UI truncation.

```bash
agent-do resend records example.com
agent-do resend status example.com
agent-do resend dns-check example.com
agent-do resend verify example.com
```

### `manna`

Git-backed issue coordination with claims and dependency blocking for agent work.

```bash
agent-do manna create "Add auth" "JWT with refresh tokens"
agent-do manna claim mn-a1b2c3
agent-do manna done mn-a1b2c3
```

### `spec`

Agent-facing, repo-local intended-behavior specs and change packages that stay visible in git.

```bash
agent-do spec init
agent-do spec new add-oauth-device-flow --spec auth
agent-do spec list --changes
agent-do spec show add-oauth-device-flow --type change
agent-do spec status --change add-oauth-device-flow
```

## Tool Surface

There are 84 tools today. A few are deep subsystems. Many are focused adapters. Together they cover most of the operational edges an AI coding agent runs into.

| Category | Tools | What They Do |
|----------|-------|--------------|
| Browser | `browse`, `unbrowse` | Browser automation, session capture, API extraction |
| Context | `context` | Docs ingestion, search, token budgeting, annotations |
| Credentials | `creds` | Secure secret storage and tool credential checks |
| Auth | `auth` | Site-level authenticated state orchestration and session reuse |
| Specification | `spec` | Repo-local intended behavior specs and change packages |
| Memory | `zpc` | Lessons, decisions, patterns, checkpointing |
| Design | `dpt` | UI scoring and design critique |
| Tracking | `manna` | Git-backed issue tracking and coordination |
| Mobile | `ios`, `android` | Simulator and emulator control |
| Desktop | `macos`, `tui`, `screen`, `ide` | GUI and terminal UI automation |
| Data | `db`, `excel`, `sheets`, `pdf`, `pdf2md` | Databases, spreadsheets, PDF flows |
| Communication | `slack`, `discord`, `email`, `sms`, `teams`, `zoom`, `meet`, `voice`, `resend` | Messaging, email delivery, and meeting surfaces |
| Productivity | `calendar`, `notion`, `linear`, `figma`, `jupyter`, `lab`, `colab` | Product and workflow tools |
| Infrastructure | `docker`, `k8s`, `cloud`, `gcp`, `ci`, `vm`, `network`, `dns`, `ssh`, `render`, `vercel`, `supabase`, `cloudflare`, `clerk`, `okta`, `namecheap` | Infra, cloud, auth, deployment |
| Creative | `image`, `video`, `audio`, `3d`, `cad`, `latex` | Media and document generation |
| Security | `burp`, `wireshark`, `ghidra` | Security and reverse-engineering tools |
| Hardware | `serial`, `midi`, `homekit`, `bluetooth`, `usb`, `printer` | Device control |
| AI / Meta | `prompt`, `eval`, `memory`, `learn`, `swarm`, `agent`, `repl` | Agent support and orchestration |
| Dev Tools | `git`, `api`, `tail`, `logs`, `sessions` | Git, HTTP, logs, session history |
| Utilities | `clipboard`, `ocr`, `vision`, `metrics`, `debug` | System utility surfaces |

Use `agent-do --list` for the full catalog. Use `agent-do <tool> --help` for any specific tool.

## Discovery, Nudges, And Routing

`agent-do` now has a dedicated discoverability layer. This matters because the right tool is often present before the agent knows its name.

### Discovery

```bash
agent-do suggest "deploy this on vercel"
agent-do suggest --project
agent-do find ios simulator
```

`suggest --project` inspects the current repo and ranks likely tools from local signals such as `vercel.json`, `playwright`, `ios/`, `.zpc/`, docs, and framework manifests.

### Nudges

When Claude Code hooks are installed:

- SessionStart injects project-aware tool guidance
- UserPromptSubmit suggests likely `agent-do` tools from shared routing metadata
- PreToolUse emits hard nudges when Claude reaches for raw commands that already have an `agent-do` equivalent

Those nudges are non-blocking by default. They are meant to bend behavior, not break flow.

```bash
agent-do nudges stats
agent-do nudges recent
```

### Natural Language Routing

`agent-do -n` routes through project-aware route memory first, then fuzzy matching, then the Claude API. `agent-do --offline` uses shared routing metadata plus legacy pattern matching, with no API key required.

The structured API remains the primary path. Natural language is the convenience layer around it.

## Installation

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
```

The installer can:

- symlink `agent-do` into `PATH`
- copy Claude Code hooks into place
- install Python dependencies
- optionally build the Node and Rust components that need it

See [INTEGRATION.md](INTEGRATION.md) for the hook model and Claude Code wiring.

## First Run

The safe first-run sequence is:

```bash
agent-do --health
agent-do bootstrap --recommend
agent-do bootstrap
```

`bootstrap` initializes the stateful pieces that actually need setup:

- `context` in `~/.agent-do/context/`
- `zpc` in `.zpc/` when the repo uses ZPC
- `manna` in `.manna/` when the repo uses Manna

If the SessionStart hook is installed, Claude asks once at session start when bootstrap work is pending.

## Credentials

API-oriented tools can now resolve secrets from either:

- environment variables
- the OS secure credential store through `agent-do creds`

Preferred flow:

```bash
agent-do creds required namecheap
agent-do creds store NAMECHEAP_API_USER --stdin
agent-do creds store NAMECHEAP_API_KEY --stdin
agent-do creds check --tool namecheap
```

For token-based tools:

```bash
agent-do creds store RENDER_API_KEY --stdin
agent-do creds store VERCEL_ACCESS_TOKEN --stdin
agent-do creds store SUPABASE_ACCESS_TOKEN --stdin
```

Once stored, `agent-do` preloads those secrets before executing the matching tool, including natural-language routed runs.

## Architecture

At runtime, the system is intentionally plain:

```text
agent-do <tool> <command>
        │
        ▼
tools/agent-<name>
```

The richer layers sit beside that core:

- `registry.yaml` defines the catalog, examples, and shared routing metadata
- `tools/agent-creds` and `lib/creds-helper.sh` resolve secrets from env vars or the secure store
- `bin/intent-router` handles natural-language routing
- `bin/pattern-matcher` handles offline matching
- `bin/suggest` and `bin/nudges` handle discovery and local telemetry
- `bin/bootstrap` and `bin/health` handle setup and readiness
- `lib/cache.py` stores project-aware route memory
- `hooks/` gives Claude Code a way to prefer `agent-do` without forcing block mode

That architecture is simple on purpose. The point is not to hide the tool surface. The point is to make it consistent.

## Prerequisites

- Python 3.10+
- `anthropic` and `pyyaml`
- Node.js 18+ for `browse` and `unbrowse`
- Rust for `manna`
- `tmux` for `tui`

## Environment

```bash
AGENT_DO_HOME         # Config and state directory, default: ~/.agent-do
ANTHROPIC_API_KEY     # Required for natural-language mode
RENDER_API_KEY        # Render, or store with: agent-do creds store RENDER_API_KEY --stdin
VERCEL_ACCESS_TOKEN   # Vercel, or store with: agent-do creds store VERCEL_ACCESS_TOKEN --stdin
SUPABASE_ACCESS_TOKEN # Supabase, or store with: agent-do creds store SUPABASE_ACCESS_TOKEN --stdin
GCP_SERVICE_ACCOUNT   # Google Cloud
```

## Adding Tools

`agent-do` resolves tools from three places:

```bash
tools/agent-<name>/agent-<name>
tools/agent-<name>
agent-<name> in $PATH
```

To add a tool:

1. Create the executable.
2. Add it to `registry.yaml`.
3. Add `routing` metadata if the tool should participate in discovery, hooks, or offline matching.

Shared helpers such as `lib/snapshot.sh` and `lib/json-output.sh` let bash tools expose structured output and `--json` support with less repeated code.

## License

MIT
