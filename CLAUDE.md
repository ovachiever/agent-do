# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

agent-do is a universal automation CLI for AI agents with 84 specialized tools. Two modes:
- **Structured API** (AI/scripts): `agent-do <tool> <command> [args...]` (instant, no LLM)
- **Natural Language** (humans): `agent-do -n "what you want"` (LLM-routed via Claude)

## Commands

```bash
./test.sh                              # Run all tests
./agent-do --list                      # List available tools
./agent-do suggest "task"              # Recommend a likely tool/command
./agent-do suggest --project           # Recommend likely tools for this repo
./agent-do find playwright             # Search tools by keyword
./agent-do creds check --tool render   # Check a tool's declared credentials
./agent-do creds required namecheap    # Show which secrets a tool expects
./agent-do auth ensure github          # Reuse saved auth or import browser cookies/storage
./agent-do auth ensure cloudflare --strategy interactive --timeout 300  # Use the visible system browser, then import authenticated state
./agent-do resend status example.com   # Check Resend domain DNS/verification state
./agent-do spec init                   # Initialize repo-local spec storage
./agent-do spec status --change id     # Check one change package
./agent-do nudges stats                # Local nudge telemetry summary
./agent-do <tool> --help               # Tool-specific help
./agent-do --status                    # Active sessions and state
./agent-do --health                    # Check tool dependencies
./agent-do bootstrap --recommend       # Detect pending context/zpc/manna setup
./agent-do bootstrap                   # Initialize pending project setup
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
cd tools/agent-browse && npm test
cd tools/agent-browse && npm run test:protocol

# agent-unbrowse (Node.js)
cd tools/agent-unbrowse && npm install

# agent-context (Bash + Python)
bash tools/agent-context/test/integration.sh
```

## Architecture

### Routing Flow

The main `agent-do` script (bash) decides mode based on first argument:

1. **Structured API**: `agent-do ios screenshot` → `is_tool()` matches → `exec_tool()` dispatches to `tools/agent-ios`
2. **Natural Language** (`-n` flag): 3-tier fallback chain:
   - `lib/cache.py:check_cache()`: project-aware exact route memory (`~/.agent-do/cache/patterns.db`)
   - `lib/cache.py:fuzzy_match()`: Jaccard similarity weighted by project scope and past route success
   - `bin/intent-router`: Claude API call
3. **Offline** (`--offline`): `bin/pattern-matcher` (regex patterns + keyword matching, no LLM)

### Exit Codes (natural language mode)
- `0` = success
- `1` = error
- `2` = needs clarification (orchestrator should ask follow-up, then retry with `--context`)

### Tool Resolution

Tools live in `tools/agent-*`. The dispatcher checks (in order):
1. `tools/agent-<name>/agent-<name>` (directory with nested executable)
2. `tools/agent-<name>` (standalone executable)
3. `agent-<name>` in `$PATH`

Most tools are standalone bash scripts. Some are directory-based with Python or Node.js backends.

### Key Components

```
agent-do                    # Main entry (bash): mode selection + tool dispatch
├── bin/
│   ├── intent-router       # LLM router (Python): cache, fuzzy, Claude API
│   ├── pattern-matcher     # Offline router (Python): regex + keyword matching
│   ├── suggest             # Discovery CLI: task/project to likely tools/commands
│   ├── nudges              # Local telemetry summary for hook nudges
│   ├── health              # Tool dependency checker (bash)
│   └── status              # Session status display (bash + inline Python)
├── lib/
│   ├── state.py            # Session state CRUD (~/.agent-do/state.yaml)
│   ├── registry.py         # Tool registry loader (merges user/bundled/plugin registries)
│   ├── cache.py            # Project-aware route memory + fuzzy matching
│   ├── telemetry.py        # JSONL telemetry for nudges/suggestions
│   ├── snapshot.sh         # Shared JSON snapshot helpers for tools
│   ├── json-output.sh      # Shared --json flag and structured output for tools
│   └── capture/            # Shared capture pipeline (used by browse + unbrowse)
│       ├── capture.js      # CaptureSession: request/response correlation
│       ├── filter.js       # filterEntries: removes static assets, CDN, deduplicates
│       ├── auth.js         # extractAuth: identifies auth patterns in captured traffic
│       └── generator.js    # generateSkill: writes skill package to ~/.agent-do/skills/
├── tools/agent-*           # 84 tools (standalone scripts + directory-based tools)
└── registry.yaml           # Master tool catalog: tool descriptions, commands, examples
```

### Registry Loading Order (registry.py)

Registries merge in reverse priority order (higher-priority wins):
1. `~/.agent-do/registry.yaml` (user overrides, highest priority)
2. `./registry.yaml` (bundled)
3. `~/.agent-do/plugins/*.yaml` (plugin extensions)

### Session State

`lib/state.py` manages `~/.agent-do/state.yaml`, tracking active TUI/REPL/iOS/Android/Docker/SSH/Tail sessions. The intent router includes state in LLM context so "my python session" resolves correctly.

### Key Bundled Tools

| Tool | Tech | Notes |
|------|------|-------|
| `agent-browse/` | Node.js (Playwright) | Headless browser, @ref element selection, daemon.js lifecycle. `login <url>` opens headed browser for SSO/MFA, `login done` transfers auth to headless. `session save/load` persists and restores full auth state, and `session import-browser` now imports cookies plus Chromium localStorage/sessionStorage when available. `capture start/stop` records API traffic, `api` replays captured skills. |
| `agent-auth` | Python | Site-level auth orchestrator over encrypted auth bundles, browser import, and secure credentials. Profiles live under `~/.agent-do/auth/`; `ensure` tries saved-session, browser-import, provider-refresh, then site-creds where configured. GitHub/Google profiles have provider-aware login handling, TOTP resolution through `agent-do creds`, recovery-code consumption from backup-code pools in secure storage, cross-site SSO reuse, account-chooser/consent checkpoint handling, mailbox-driven email or SMS continuation via `agent-do email` and `agent-do sms`, explicit passkey/security-key and device-approval action-required states, a `probe` command for classifying the live checkpoint branch plus frontmost macOS dialog state, and `advance` for executing one safe checkpoint step, preferring in-browser alternate methods before out-of-band waits when available. |
| `agent-email` | Bash + Python | Email sending plus inbox querying. `snapshot`, `latest`, `wait`, `code`, and `link` support mailbox-driven auth workflows, with macOS Mail.app live queries and fixture-backed testing. |
| `agent-sms` | Bash + Python | SMS sending plus message querying. `snapshot`, `latest`, `wait`, `code`, and `link` support phone-driven auth workflows, with macOS Messages.app live queries and fixture-backed testing. |
| `agent-unbrowse/` | Node.js (Playwright) | Standalone API traffic capture → reusable curl-based skills. Launches its own headed browser. 2 files: `daemon.js` + `protocol.js`. Capture pipeline shared via `lib/capture/`. |
| `agent-manna/` | Rust | Git-backed issue tracking with session claims. Build with `cargo build --release`. |
| `agent-db/` | Bash + Python | Database client (PostgreSQL, MySQL, SQLite). Connection management, queries, schema inspection. |
| `agent-excel/` | Bash + Python | Excel workbook automation via openpyxl. Read/write cells, formulas, sheets, export. |
| `agent-macos/` | Bash + Python | Desktop GUI automation via macOS accessibility APIs. Click, type, UI tree inspection. |
| `agent-screen/` | Bash + Python | Vision-based screen perception. Multi-display capture, OCR, element detection, mouse/keyboard control. |
| `agent-vision/` | Bash + Python | Visual perception with YOLO object detection, OCR, face detection, motion detection. |
| `agent-render` | Bash + curl | Render.com service management via REST API. Requires `RENDER_API_KEY`. |
| `agent-vercel` | Bash + curl | Vercel project/deployment management via REST API. Requires `VERCEL_ACCESS_TOKEN`. Optional `--team <id>`. |
| `agent-supabase` | Bash + curl | Supabase project management + data access. REST API queries (no password) and SQL via agent-db bridge. Requires `SUPABASE_ACCESS_TOKEN`. |
| `agent-gcp` | Bash + curl | Google Cloud Platform management via REST API + Console automation. Projects, APIs, secrets, service accounts, OAuth credential creation. |
| `agent-cloudflare` | Bash + curl | Cloudflare management: zones, analytics (GraphQL), DNS records, Workers, Pages, R2, firewall events. 23 commands. Requires `CLOUDFLARE_API_TOKEN`. |
| `agent-clerk` | Bash + curl | Clerk authentication platform: users, organizations, sessions, OAuth apps, enterprise SSO (SAML/OIDC), JWT templates, roles/permissions. 55 commands. Requires `CLERK_SECRET_KEY`. |
| `agent-okta` | Bash + curl | Okta tenant management: applications (OIDC/SAML), SSO configuration, users, groups, auth servers, system logs. 34 commands. Requires `OKTA_API_TOKEN` + `OKTA_DOMAIN`. |
| `agent-namecheap` | Bash + curl | Namecheap domain and DNS management. Safe GET→merge→SET writes with suspicious-value rejection, exact provider read-back verification, and optional public DNS checks. Requires `NAMECHEAP_API_USER` + `NAMECHEAP_API_KEY`. |
| `agent-resend` | Python | Resend domain management and DNS verification. Exact DKIM/SPF record retrieval, verification triggering, and public DNS comparison without UI truncation. Requires `RESEND_API_KEY`. |
| `agent-dpt` | Bash + Python | Design Perception Tensor: visual quality scoring across 5 perception layers (72 rules, 0-100 score). |
| `agent-context/` | Bash + Python | **Knowledge library.** Fetches external reference docs (URLs, llms.txt, GitHub repos, local skills). SQLite FTS5 index with BM25 + trust-tier ranking. Token-budgeted retrieval (knapsack). Annotations, feedback-influenced scoring. 22 commands. Storage: `~/.agent-do/context/` (global, per-user). |
| `agent-zpc/` | Bash + Python | **Experience journal.** Structured lessons (context/problem/solution/takeaway), architectural decisions (options/chosen/rationale/confidence), pattern consolidation via harvest. Git history review, swarm checkpoints, lesson promotion (local → team → global). Storage: `.zpc/` (per-project). Sources `lib/json-output.sh` + `lib/snapshot.sh`. |
| `agent-pdf2md` | Bash | PDF-to-Markdown converter. Auto-detects tabular vs prose PDFs. Uses `pdftotext -layout` for tables, `markitdown` for prose. |
| `agent-tail` | Bash | Wraps dev commands, captures output to log files for AI agents. Multi-service, timestamped sessions, `latest` symlink. |
| `agent-sessions` | Bash + Python | AI coding session history search. FTS5 full-text search across transcripts and summaries. |

Other tools are standalone bash scripts.

### Framework Libraries

| Library | Purpose |
|---------|---------|
| `lib/snapshot.sh` | JSON snapshot helpers: `snapshot_begin`, `snapshot_field`, `snapshot_end` |
| `lib/json-output.sh` | `--json` flag support: `json_success`, `json_error`, `json_result`, `json_list` |
| `lib/retry.sh` | Shared error recovery: `api_request()` with per-error-class retry (429→backoff, 401→refresh, 5xx→backoff), `with_retry()` for generic commands, `stall_detect()` for streaming. Persistent mode for CI/CD. |
| `lib/capture/` | Shared capture pipeline: `CaptureSession` (request/response correlation), `filterEntries` (noise removal), `extractAuth` (auth detection), `generateSkill` (skill package writer). Used by both `agent-browse` and `agent-unbrowse`. |
| `bin/health` | Per-tool dependency checking with status levels (OK, WARN, CONF, MISS) |

### Tool Concurrency Classification

Every tool in `registry.yaml` declares a `concurrency` field:

| Value | Meaning | Parallelism |
|-------|---------|-------------|
| `read` | All commands are read-only queries | Safe to run in parallel with any tool |
| `write` | Has state-mutating commands | Must run serially |
| `mixed` | Some commands read, some write | Orchestrator checks per-command |

22 read-only tools (context, ocr, vision, metrics, etc.) can run concurrently. 16 write tools (render, vercel, namecheap, manna, etc.) must run serially. 42 mixed tools require per-command classification. When spawning parallel agents, assign read-only tools freely; gate write tools behind sequential execution.

### Universal Tool Pattern

All tools follow: **Connect → Snapshot → Interact → Verify → Save**

## Adding Tools

1. Create executable at `tools/agent-<name>` (must support `--help` flag)
2. Add entry to `registry.yaml` with `description`, `capabilities`, `commands`, `examples`
   - add `routing` metadata for discovery keywords, raw CLI equivalents, readiness hints, and project signals when the tool should participate in `suggest`, prompt nudges, or PreToolUse hard nudges
3. `--list` auto-discovers tools via filesystem scan of `tools/agent-*`

## Dependencies

- **Python 3.10+**: `anthropic>=0.18.0`, `pyyaml>=6.0`
- **agent-browse**: Node.js with `playwright-core`, `ws`, `zod`
- **agent-unbrowse**: Node.js with `playwright-core`, `zod`
- **agent-manna**: Rust with clap, serde, serde_yaml, chrono, sha2, fs2
- **System**: tmux (for agent-tui), Xcode CLI Tools (for agent-ios)

## Environment

- `AGENT_DO_HOME`: Config/state directory (default: `~/.agent-do`)
- `ANTHROPIC_API_KEY`: Required for natural language mode and `--dry-run`/`--how`
- `MANNA_SESSION_ID`: Override session ID for agent-manna
- `RENDER_API_KEY`: API key for agent-render (Render.com), or store with `agent-do creds store RENDER_API_KEY --stdin`
- `VERCEL_ACCESS_TOKEN`: API token for agent-vercel (Vercel), or store with `agent-do creds store VERCEL_ACCESS_TOKEN --stdin`
- `SUPABASE_ACCESS_TOKEN`: API token for agent-supabase (Supabase), or store with `agent-do creds store SUPABASE_ACCESS_TOKEN --stdin`
- `GCP_SERVICE_ACCOUNT`: Path to service account JSON key for agent-gcp
- `GCP_ACCESS_TOKEN`: Bearer token for agent-gcp (alternative to service account)
- `GCP_PROJECT`: Default GCP project ID for agent-gcp
- `CLOUDFLARE_API_TOKEN`: API token for agent-cloudflare (recommended, scoped)
- `CLOUDFLARE_ACCOUNT_ID`: Account ID for agent-cloudflare (Workers, Pages, R2)
- `CLERK_SECRET_KEY`: Secret key for agent-clerk (Clerk, sk_test_... or sk_live_...)
- `OKTA_API_TOKEN`: SSWS API token for agent-okta (Okta)
- `OKTA_DOMAIN`: Okta domain for agent-okta (e.g., versova.okta.com)
- `NAMECHEAP_API_USER`: API username for agent-namecheap
- `NAMECHEAP_API_KEY`: API key for agent-namecheap
- `NAMECHEAP_CLIENT_IP`: Whitelisted IP for agent-namecheap (auto-detected if not set)
- `RESEND_API_KEY`: API key for agent-resend (Resend), or store with `agent-do creds store RESEND_API_KEY --stdin`

Prefer `agent-do creds` for secret material when possible. The dispatcher, intent router, and health checker resolve declared tool secrets from the secure store automatically.
