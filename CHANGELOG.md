# Changelog

## Unreleased

### Added
- `agent-do auth` for site-level authentication orchestration over saved browser sessions, browser import, and secure credentials.
- `agent-do creds` for secure secret storage, inspection, export, and per-tool credential checks.
- `agent-do spec` for repo-local canonical specs and active change packages under `agent-do-spec/`.
- `agent-do resend` for exact Resend domain records, verification state, and public DNS checks without relying on UI text.
- `lib/creds-helper.sh` as a shared secure-store backend for macOS Keychain, Linux Secret Service, and a Windows DPAPI-backed per-user store.
- Registry-level `credentials` metadata so tools can declare which secret env vars they need.
- Browser clipboard commands through `agent-do browse clipboard read|copy|paste` for copy-first extraction flows.

### Changed
- Saved authenticated state is now a first-class outer-harness concern instead of an implicit split between `creds` and `browse`, with encrypted auth bundles stored under `~/.agent-do/auth/`.
- `agent-do auth` now uses provider-aware GitHub and Google login adapters for `site-creds`, with TOTP secrets resolved through `agent-do creds` when those flows require one-time codes.
- `agent-do auth init --provider github|google` now creates SSO-first site profiles, and `provider-refresh` can reuse upstream provider auth to complete cross-site sign-in.
- Structured execution and natural-language execution now preload declared tool secrets from env vars or secure storage before invoking the target tool.
- `agent-do --health` now reports credential readiness from the same registry metadata instead of relying only on a small hardcoded env-var list.
- Discovery metadata now covers `agent-do spec`, including prompt matching for change proposals and repo-local spec work.
- Docs and smoke tests now cover the new credential workflow.
- `agent-do namecheap dns-add` and `dns-update` now reject suspicious masked values, verify exact Namecheap read-back by default, and can optionally confirm public DNS answers.

### Fixed
- `agent-do browse get text|html|value|attr` now emits the correct browser protocol actions instead of invalid discriminator values.
- `agent-do namecheap dns-add` no longer crashes after successful writes because of the bare `host` reference in its success path.

## v1.1 — 2026-04-11

### Added
- `agent-do suggest "<task>"`, `agent-do suggest --project`, and `agent-do find <keyword>` for non-LLM discovery on top of shared registry routing metadata.
- `agent-do nudges stats|recent|clear` for local hook telemetry under `~/.agent-do/telemetry/`.
- Shared `routing` metadata in `registry.yaml` for the first high-value tool set, including discover keywords, raw CLI equivalents, readiness hints, and project signals.

### Changed
- SessionStart hook context is now project-aware and can recommend likely tools for the current repo instead of only a static key-tool list.
- Prompt-submit and PreToolUse hooks now use shared registry routing metadata for more exact hard nudges and concrete replacement commands.
- Offline matching now consumes shared registry routing metadata before falling back to legacy regex patterns.
- Natural-language cache memory is now project-scoped and weighted by route success/failure instead of treating all prior matches equally.

## v1 — 2026-04-10

### Fixed
- Natural-language routing now resolves directory-backed tools correctly instead of trying to execute tool directories directly.
- `agent-do --health` is now a real top-level command rather than an installer-only expectation.
- Offline routing preserves arguments correctly and surfaces clarification questions instead of failing silently.
- Stale `gui` routing no longer leaks into current `macos` flows.
- Missing `PyYAML` on common paths now produces actionable errors instead of Python tracebacks.
- `agent-context` source management now works without `PyYAML`, including the previously failing `sources` fallback path.
- `agent-dpt` is now repo-local instead of depending on an absolute symlink outside the repository.
- `agent-manna` health checks and binary resolution now match the actual `manna-core` build output.

### Added
- `agent-do bootstrap` for idempotent project setup of stateful tools.
- Session-start bootstrap detection that tells Claude to ask once when a project needs `context`, `zpc`, or `manna` initialization.
- Runnable browse tests via `vitest` in `tools/agent-browse`.
- Repo-local DPT source, install script, wrapper binaries, and documentation.

### Changed
- README, integration docs, architecture docs, and project CLAUDE guidance now document `--health`, bootstrap, and current first-run verification.
- Root smoke tests now validate bootstrap behavior in addition to direct, offline, and health-check flows.
- Claude Code hook guidance now reflects the real non-interactive SessionStart model: hooks inject context, Claude asks in conversation.

### Validation
- `./test.sh`
- `bash tools/agent-context/test/integration.sh`
- `cd tools/agent-browse && npm test`
- `bash tools/agent-manna/test/integration.sh`

## v0.9 — 2026-03-17

### Added
- **agent-context**: Curated docs and context for AI agents (tool #76), 22 commands:
  - `fetch <url>` — Fetch markdown from any URL
  - `fetch-llms <domain>` — Fetch llms.txt / llms-full.txt from any domain
  - `fetch-repo <owner/repo>` — Fetch docs from GitHub via gh CLI
  - `scan-local` — Index project context files (CLAUDE.md, .cursorrules, etc.)
  - `scan-skills` — Index ~/.claude/skills/ as searchable context
  - `search <query>` — FTS5 BM25 search with keyword expansion, trust-tier boosting, feedback weighting
  - `get <id>` — Retrieve cached doc with annotations, incremental fetch (--file, --full)
  - `list` — List all indexed packages with trust badges
  - `budget <tokens> <query>` — Token-aware greedy knapsack context assembly
  - `inject --max-tokens N` — Structured context blob for spawned agents
  - `annotate <id> <note>` — Persistent notes displayed inline on future gets
  - `feedback <id> up|down` — Ratings that influence search ranking
  - `build <dir>` — Validate and package private content with registry.json
  - `cache list|clear|pin|stats` — Full cache management with pinning
  - `sources` / `add-source` / `remove-source` — Multi-source config management
  - `status` / `init` — Storage management
  - Full `--json` support via `lib/json-output.sh` + `lib/snapshot.sh`
  - SQLite FTS5 index with 50-entry keyword expansion table
  - Trust tiers: official, maintainer, community, local
  - 31 integration tests (tools/agent-context/test/integration.sh)
- Registry entry for context in `registry.yaml` (22 commands, 8 examples)
- Exceeds Context Hub (chub): any-source fetching, token budgets, skills indexing, no Node.js dependency

### Changed
- Tool count: 75 → 76 across all documentation
- Updated README, CLAUDE.md, ARCHITECTURE.md, PLAN.md, TOOL_AUDIT.md, INTEGRATION.md, CHANGELOG.md, install.sh

---

## v0.8 — 2026-02-27

### Added
- **agent-zpc**: Structured project memory for AI coding agents (tool #75), 13 commands:
  - `learn` — Capture validated lessons with tags → `lessons.jsonl`
  - `decide` — Log decisions with rationale, confidence, bias detection → `decisions.jsonl`
  - `decide-batch` — Batch-log decisions from planning phase via stdin or file (pipe-delimited)
  - `harvest` — Consolidation scan: format health, pattern drafting, auto-write for 5+ lesson tags
  - `query` — Search by tag, date, text, or type (lessons/decisions/all)
  - `patterns` — View established patterns, score effectiveness
  - `promote` — Promote lessons to team (git-tracked) or global scope with dedup
  - `inject` — Emit agent context blob for spawned agents (baseline counts for self-report grounding)
  - `init` — Initialize `.zpc/` with stack auto-detection and platform-specific instructions
  - `status` — Memory snapshot with health check (human + JSON output)
  - `checkpoint` — Swarm phase boundary: memory inventory, agent compliance, format health, consolidation gaps
  - `review` — Post-sprint lesson extraction: analyze git history, draft lessons/decisions from commits
  - `profile` — View/update project profile, auto-detect stack
  - 4 platform templates: Claude Code, Cursor, Codex, Generic
  - Full `--json` support via `lib/json-output.sh` + `lib/snapshot.sh`
  - Per-project memory (`.zpc/`) + global memory (`~/.agent-do/zpc/`)
  - Team scope (`.zpc/team/`) for git-tracked shared memory
- Registry entry for zpc in `registry.yaml` (13 commands, 10 examples)
- zpc patterns in prompt router hook
- zpc in PreToolUse skip patterns
- zpc in SessionStart key tools list
- zpc entry in runtime index and catalog
- Frontend/design intent detection in prompt router (two-stage: UI keywords + action keywords)
- Frontend project detection at session start (monorepo-aware: apps/\*, packages/\*)
- ZPC project detection at session start (.zpc/ directory → memory reminder)

### Changed
- Tool count: 74 → 75 across all documentation
- Updated README, CLAUDE.md, AGENTS.md, ARCHITECTURE.md, PLAN.md, TOOL_AUDIT.md, INTEGRATION.md, install.sh
- Session-start hook: auto-detects agent-do location (3-tier fallback), no hardcoded paths
- Session-start hook: added macos, gcp, zpc to key tools list
- Prompt router: tightened iOS/Android patterns to prevent false positives (bare "ios" no longer matches)
- Prompt router: added design toolkit injection for frontend/visual prompts

---

## v0.7 — 2026-02-06

### Added
- **agent-sessions**: AI coding session history search with FTS5 full-text search
- **agent-supabase**: Data access (REST queries, SQL via agent-db bridge)
- **install.sh**: Idempotent installer with Claude Code hooks distribution
- Claude Code hook trinity: SessionStart, UserPromptSubmit, PreToolUse

### Changed
- Tool count: 68 → 72
- Full repo audit: fix stale counts, symlink references, agent-gui→agent-macos renames

---

## v0.6 — 2026-01-28

### Added
- **agent-gcp**: Google Cloud Platform management (projects, APIs, secrets, service accounts, OAuth)
- **agent-render**: Render.com service management via REST API
- **agent-vercel**: Vercel project/deployment management via REST API
- **agent-dpt**: Design Perception Tensor (72 rules, 0-100 visual quality score)
- **agent-pdf2md**: PDF-to-Markdown converter with tabular/prose auto-detection
- **agent-tail**: Dev command wrapper with log capture for AI agents
- **agent-vision**: Visual perception CLI (YOLO, OCR, face detection, Vision LLM)
- **agent-screen**: Multi-display vision (24fps capture, OCR, element detection)

### Changed
- P0-P3 tool audit: 20 tools upgraded with snapshot commands
- lib/snapshot.sh and lib/json-output.sh shared framework libraries
- bin/health dependency checker

---

## v0.5 — 2026-01-15

### Added
- Initial public structure with 60+ tools
- Structured API mode (`agent-do <tool> <command>`)
- Natural language mode (`agent-do -n "intent"`)
- Offline pattern matching (`agent-do --offline "intent"`)
- 3-tier fallback: SQLite cache → Jaccard fuzzy → Claude API
- Gold standard tools: browse, db, excel, unbrowse
