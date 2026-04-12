# agent-do Architecture

## Overview

agent-do is a universal automation layer that works with any AI coding agent. It provides:

1. **Structured CLI API** — Direct tool invocation without LLM overhead
2. **Natural Language Mode** — LLM-routed for human users
3. **Discovery + nudge layer** — task suggestions, project-scoped tool ranking, and hook nudges
4. **Bootstrap + health flow** — explicit setup path for stateful tools and dependency checks
5. **80 specialized tools** — browser, iOS, database, spreadsheet, messaging, infrastructure, memory, and more

## Routing Flow

```
                          agent-do <arg>
                               │
               ┌───────────────┼───────────────┐
               │               │               │
         Structured API   Natural Language   Offline
         is_tool()?       -n / --natural     --offline
               │               │               │
               │         ┌─────┴─────┐    bin/pattern-matcher
               │         │  3-tier   │    (regex + keywords)
               │         │ fallback: │
               │         │ 1. cache  │
               │         │ 2. fuzzy  │
               │         │ 3. Claude │
               │         └─────┬─────┘
               └───────────────┼───────────────┘
                               │
                               ▼
                       tools/agent-<name>
```

### Mode Selection (agent-do main script)

The bash entry point checks the first argument:

| First Arg | Mode | Path |
|-----------|------|------|
| Known tool name | Structured API | `exec_tool()` → `tools/agent-<name>` |
| `suggest` / `find` / `nudges` | Discovery + telemetry | `bin/suggest`, `bin/nudges` |
| `bootstrap` | Project setup | `bin/bootstrap` |
| `-n` / `--natural` | Natural language | `bin/intent-router` (Claude API) |
| `--offline` | Offline NL | `bin/pattern-matcher` (regex) |
| `--dry-run` | Dry run | `bin/intent-router --dry-run` |
| `--how` | Explain | `bin/intent-router --explain` |

### Natural Language Fallback Chain

`bin/intent-router` tries three strategies in order:

1. **SQLite route memory** (`lib/cache.py:check_cache`) — exact match on normalized intent, preferring project-scoped history
2. **Weighted fuzzy match** (`lib/cache.py:fuzzy_match`) — Jaccard similarity ranked by project scope and past route success
3. **Claude API** — full LLM call with registry + session state in context

Successful routes are cached and then scored by later outcomes, so the router can prefer the route that actually works in the current repo. At 100 requests/day, LLM cost is still around ~$0.20/day, but cache quality improves over time.

### Offline Pattern Matching

`bin/pattern-matcher` now uses shared routing metadata from `registry.yaml` before falling back to legacy regex patterns. No API key needed. Handles common intents like "screenshot iOS", "list docker containers", and migrated discovery cases like "deploy this on vercel".

## Tool Resolution

Tools live in `tools/agent-*`. The dispatcher (`exec_tool()`) checks in order:

1. `tools/agent-<name>/agent-<name>` — directory with nested executable (e.g., agent-browse)
2. `tools/agent-<name>` — standalone executable
3. `agent-<name>` in `$PATH` — external tool

Most tools are standalone bash scripts. Some are directory-based with Python or Node.js backends.

## Key Components

```
agent-do                    # Main entry (bash) — mode selection + tool dispatch
├── bin/
│   ├── intent-router       # LLM router (Python) — 3-tier fallback
│   ├── pattern-matcher     # Offline router (Python) — shared registry routing + regex fallbacks
│   ├── suggest             # Discovery CLI — task/project → likely tools
│   ├── nudges              # Local telemetry summary for hook nudges
│   ├── bootstrap           # Stateful-tool bootstrap recommender/executor
│   ├── health              # Dependency checker (bash) — per-tool health status
│   └── status              # Session status display (bash + Python)
├── lib/
│   ├── state.py            # Session state CRUD (~/.agent-do/state.yaml)
│   ├── registry.py         # Registry loader + shared routing helpers
│   ├── cache.py            # Project-aware route memory + fuzzy matching
│   ├── telemetry.py        # JSONL telemetry for suggestions and hard nudges
│   ├── snapshot.sh         # Shared JSON snapshot helpers for bash tools
│   ├── json-output.sh      # Shared --json flag support for bash tools
│   └── capture/            # Shared capture pipeline (browse + unbrowse)
│       ├── capture.js      # CaptureSession — request/response correlation
│       ├── filter.js       # Traffic filtering (removes static, CDN, deduplicates)
│       ├── auth.js         # Auth extraction from captured headers/cookies
│       └── generator.js    # Skill package writer → ~/.agent-do/skills/<name>/
├── tools/agent-*           # 80 tools (standalone scripts + directory-based tools)
├── registry.yaml           # Master tool catalog
├── test.sh                 # Test suite
└── requirements.txt        # Python dependencies
```

### Registry (registry.yaml)

The master catalog defines all tools with:
- `description` — what the tool does
- `capabilities` — list of actions it supports
- `commands` — subcommands with descriptions
- `examples` — intent → command mappings (used by LLM router and pattern matcher)
- `routing` — optional discovery metadata: keywords, regexes, raw CLI equivalents, readiness hints, and project signals

### Registry Loading Order (lib/registry.py)

Registries merge in reverse priority (higher-priority wins):
1. `~/.agent-do/registry.yaml` — user overrides (highest priority)
2. `./registry.yaml` — bundled
3. `~/.agent-do/plugins/*.yaml` — plugin extensions

### Session State (lib/state.py)

Tracks active sessions in `~/.agent-do/state.yaml`:
- TUI/REPL sessions (ID, command, label)
- iOS/Android simulator state
- Docker containers
- SSH connections
- Tail sessions (dev server log capture)

The intent router includes state in LLM context so ambiguous references ("my python session", "the postgres container") resolve correctly.

### Framework Libraries

**`lib/snapshot.sh`** — JSON snapshot output for bash tools:
```bash
source lib/snapshot.sh
snapshot_begin "tool-name"
snapshot_field "key" "value"
snapshot_json_field "data" '{"nested": true}'
snapshot_end
# → {"tool": "tool-name", "timestamp": "...", "key": "value", "data": {"nested": true}}
```

**`lib/json-output.sh`** — `--json` flag support:
```bash
source lib/json-output.sh
parse_output_format "$@"    # Detects --json flag
json_success "result"       # {"success": true, "result": "..."}
json_error "message"        # {"success": false, "error": "..."}
json_result '{"key": "val"}' # Pass-through raw JSON
```

**`lib/retry.sh`** — Shared error recovery for API tools:
```bash
source lib/retry.sh
result=$(api_request GET "$url" -H "Authorization: Bearer $TOKEN")
# Automatic retry: 429→respect Retry-After, 5xx→exponential backoff, network→immediate retry
# with_retry 3 some_command   # Generic command retry
# AGENT_DO_PERSISTENT=1       # CI/CD mode: retry 429/5xx indefinitely
```

**`bin/health`** — Per-tool dependency checking:
- Verifies tool exists and `--help` works
- Checks tool-specific dependencies (node for browse, docker daemon, env vars for Slack/Notion)
- Reports: OK, WARN (missing dependency), CONF (needs env var), MISS (tool not found)

**`bin/bootstrap`** — Idempotent setup for stateful tools:
- Detects project-local signals in `CLAUDE.md`, `AGENTS.md`, and the repo root
- Initializes `context` globally and `zpc` / `manna` locally when the project actually uses them
- Powers the SessionStart bootstrap prompt injected by the Claude Code hook

**`bin/suggest`** — Discovery CLI:
- `agent-do suggest "<task>"` picks likely tools and concrete commands
- `agent-do suggest --project` ranks likely tools for the current repo
- `agent-do find <keyword>` searches the tool surface without an LLM call

**`bin/nudges`** — Local telemetry viewer:
- `agent-do nudges stats` summarizes prompt and PreToolUse nudges
- `agent-do nudges recent` shows recent local events from the live hook stack
- Uses JSONL under `~/.agent-do/telemetry/`

### Tool Concurrency Classification

Every tool in `registry.yaml` declares `concurrency: read|write|mixed`:
- **read** (22 tools): safe to run in parallel — context, ocr, vision, metrics, dpt, etc.
- **write** (16 tools): must run serially — render, vercel, namecheap, manna, docker, etc.
- **mixed** (42 tools): per-command — browse snapshot is read, browse click is write

Orchestrators use this to batch parallel tool calls safely: read-only tools run concurrently, write tools run serially, mixed tools require per-command inspection.

## Bundled Tools

Directory-based tools with complex backends:

| Tool | Tech Stack | Notes |
|------|-----------|-------|
| `tools/agent-browse/` | Node.js, Playwright | Headless browser with @ref element selection. `daemon.js` manages browser lifecycle. `login <url>` opens headed browser for SSO/MFA → `login done` transfers auth to headless. `session load` creates new context with saved cookies. API capture via `capture start/stop`, replay via `api` subcommand. |
| `tools/agent-unbrowse/` | Node.js, Playwright | Standalone API traffic capture. 2 files (`daemon.js`, `protocol.js`). Launches headed browser for manual browsing. Capture pipeline shared via `lib/capture/`. |
| `tools/agent-manna/` | Rust | Git-backed issue tracking. Session-based claims prevent multi-agent conflicts. |
| `tools/agent-db/` | Bash + Python | Database client (PostgreSQL, MySQL, SQLite). Connection management, queries, schema inspection. |
| `tools/agent-excel/` | Bash + Python | Excel workbook automation via openpyxl. Read/write cells, formulas, sheets, export. |
| `tools/agent-macos/` | Bash + Python | Desktop GUI automation via macOS accessibility APIs. Click, type, UI tree inspection. |
| `tools/agent-screen/` | Bash + Python | Vision-based screen perception. Multi-display capture, OCR, element detection. |
| `tools/agent-vision/` | Bash + Python | Visual perception with YOLO object detection, OCR, face detection. |
| `tools/agent-cloudflare` | Bash + curl | Cloudflare management — zones, analytics (GraphQL), DNS, Workers, Pages, R2, firewall events. 23 commands. |
| `tools/agent-clerk` | Bash + curl | Clerk auth platform — users, orgs, sessions, OAuth apps, enterprise SSO, JWT templates, roles. 55 commands. |
| `tools/agent-okta` | Bash + curl | Okta tenant management — OIDC/SAML apps, SSO config, users, groups, auth servers, system logs. 34 commands. |
| `tools/agent-namecheap` | Bash + curl | Namecheap domain and DNS management. XML API with safe GET→merge→SET for DNS writes. 16 commands. |
| `tools/agent-context/` | Bash + Python | **Knowledge library.** Fetches external docs (URLs, llms.txt, GitHub repos). SQLite FTS5 index, BM25 + trust-tier ranking, token-budgeted retrieval. Storage: `~/.agent-do/context/` (global). 22 commands. |
| `tools/agent-zpc/` | Bash + Python | **Experience journal.** Structured lessons, decisions, patterns. Harvest consolidation, git review, swarm checkpoints, promotion (local → team → global). Storage: `.zpc/` (per-project). Complementary to context: context = *what docs say*, zpc = *what we learned*. |

## Integration with AI Harnesses

agent-do works with any AI coding assistant that can execute shell commands:

| Harness | Integration | Config |
|---------|-------------|--------|
| Claude Code | CLAUDE.md instructions + hooks | `CLAUDE.md`, `.claude/hooks/` |
| Cursor | Rules file + shell commands | `.cursorrules` |
| Aider | Config file + shell access | `.aider.conf.yml` |
| Continue.dev | Context providers + shell | `.continue/config.json` |

### Integration Pattern

1. **Document the API** in the harness's instruction file (CLAUDE.md, .cursorrules, etc.)
2. **Enforce with hooks** when available (hard-nudge agent-do when raw commands detected)
3. **Create subagents/skills** for specialized workflows

### Hook Example (PreToolUse)

Block raw commands and suggest agent-do alternatives:

```python
AGENT_DO_PATTERNS = {
    r'\bxcrun\s+simctl\b': ('ios', 'Use agent-do ios instead'),
    r'\badb\s+(shell|install)': ('android', 'Use agent-do android instead'),
    r'\bosascript\b': ('macos', 'Use agent-do macos instead'),
    r'\bplaywright\b|\bpuppeteer\b': ('browse', 'Use agent-do browse instead'),
}
```

## Exit Codes

| Code | Meaning | When |
|------|---------|------|
| `0` | Success | Command executed successfully |
| `1` | Error | Tool error, missing dependency, invalid arguments |
| `2` | Needs clarification | Natural language mode — ambiguous intent |

Exit code 2 signals the orchestrator to ask a follow-up question and retry with `--context`.

## Design Principles

1. **Structured > Natural Language for AI** — AI agents should use `agent-do ios tap 200 400`, not `agent-do -n "tap the button"`. Natural language is a human convenience layer.

2. **Snapshot = AI Vision** — The `snapshot` command gives AI agents structured understanding of current state. Without it, agents are blind.

3. **Session = Memory** — Persistent sessions (database connections, browser state, TUI sessions) give agents context across commands.

4. **Tools are Composable** — Each tool is standalone, callable directly or via agent-do, with the same interface for AI and humans.
