# Changelog

## Unreleased

- `lib/snapshot.sh` `snapshot_field` now encodes string values via `python3`'s `json` module when available, covering the full RFC 8259 control range (`U+0000`–`U+001F` plus `\\` and `\"`); a manual fallback covering the named C0 controls is used when `python3` is unavailable. `snapshot_error` now routes its message through the same encoder so error JSON is consistent with snapshot JSON.
- `lib/snapshot.sh` `snapshot_end` now bounds invalid-UTF-8 failures to the offending value: each string is tried with strict UTF-8 decode and, on failure, re-decoded with `errors="replace"` so its bad bytes become U+FFFD. Sibling string fields keep full encoder semantics, snapshot output remains valid UTF-8 and valid JSON, and the helper no longer silently downgrades the whole snapshot to manual fallback when one value contains invalid bytes.

## v1.2 (2026-05-14)

### TL;DR
- `agent-do` is now a stronger default agent layer. It helps agents fetch fresh docs, handle auth, work GitHub PRs, coordinate with other agents, and send status updates.
- For current docs, the main command is now `agent-do context retrieve "<question>" --fresh --max-tokens 8000`.
- Local skills now show `local skill - no versioning` instead of looking like broken web docs.
- The public repo is cleaner. Local notes and non-release material belong under `.dev/`.

### Added
- Fresh docs support in `agent-do context`, including refresh, stale checks, HTML docs, local docs serving, source version checks, and last-good fallback when the network fails.
- GitHub PR work commands in `agent-do gh`, including inbox, awaiting review, diffs, review threads, checks, audits, replies, approvals, merge work, checkout, ready, and draft.
- Auth flow support in `agent-do auth`, with encrypted auth bundles, browser import, SSO, TOTP, email codes, SMS codes, recovery codes, passkeys, and checkpoint advance.
- Secure credential support in `agent-do creds`, plus registry metadata so tools can say which secrets they need.
- Agent coordination in `agent-do coord`, with focus, claims, needs, published outputs, presence, and interrupt checks.
- Notification support in `agent-do notify`, with SMS, email, Slack, Messenger, local pipes, rules, templates, groups, cooldowns, and delivery history.
- Harness and hook observability in `agent-do harness`, with telemetry, evidence bundles, manifest checks, and nudge outcome tracking.
- New tool families for Resend, hardware, meetings, email, SMS, and repo-local specs.
- `+live(...)` approval support for direct visible-machine actions.

### Changed
- Docs prompts now route agents toward `agent-do context retrieve ... --fresh` instead of weak generic search hints.
- The README is now a front door for agents, with detailed tool workflows moved to docs.
- Browser sessions are isolated per agent by default so parallel agents do not overwrite each other's saved state.
- Browser session import now carries more state, including cookies, localStorage, sessionStorage, and IndexedDB where possible.
- Auth flows can keep working in a real visible browser when a site blocks headless login.
- Email lookup now uses Apple Mail's local index for faster message and mailbox search.
- Structured dispatch now ignores unregistered `agent-*` binaries on `PATH`.
- `agent-do --health` now reports credential readiness from tool metadata.
- `agent-do macos` and `agent-do screen` now require explicit live approval for direct control actions.
- Public release files were cleaned so generated files, local handoffs, and private working notes stay out of the repo.

### Fixed
- Render service lookup by name works again.
- DPT scoring now checks the right agent-scoped browser socket before scoring.
- GitHub awaiting-review output no longer reports bad `[null]` reviewers.
- Browser `get text|html|value|attr` now sends the right protocol actions.
- Namecheap DNS writes no longer crash after a successful add.

## v1.1 (2026-04-11)

### Added
- `agent-do suggest "<task>"`, `agent-do suggest --project`, and `agent-do find <keyword>` for non-LLM discovery on top of shared registry routing metadata.
- `agent-do nudges stats|recent|clear` for local hook telemetry under `~/.agent-do/telemetry/`.
- Shared `routing` metadata in `registry.yaml` for the first high-value tool set, including discover keywords, raw CLI equivalents, readiness hints, and project signals.

### Changed
- SessionStart hook context is now project-aware and can recommend likely tools for the current repo instead of only a static key-tool list.
- Prompt-submit and PreToolUse hooks now use shared registry routing metadata for more exact hard nudges and concrete replacement commands.
- Offline matching now consumes shared registry routing metadata before falling back to legacy regex patterns.
- Natural-language cache memory is now project-scoped and weighted by route success/failure instead of treating all prior matches equally.

## v1 (2026-04-10)

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

## v0.9 (2026-03-17)

### Added
- **agent-context**: Curated docs and context for AI agents (tool #76), 22 commands:
  - `fetch <url>`: fetch markdown from any URL
  - `fetch-llms <domain>`: fetch llms.txt / llms-full.txt from any domain
  - `fetch-repo <owner/repo>`: fetch docs from GitHub via gh CLI
  - `scan-local`: index project context files (CLAUDE.md, .cursorrules, etc.)
  - `scan-skills`: index ~/.claude/skills/ as searchable context
  - `search <query>`: FTS5 BM25 search with keyword expansion, trust-tier boosting, feedback weighting
  - `get <id>`: retrieve cached doc with annotations, incremental fetch (--file, --full)
  - `list`: list all indexed packages with trust badges
  - `budget <tokens> <query>`: token-aware greedy knapsack context assembly
  - `inject --max-tokens N`: structured context blob for spawned agents
  - `annotate <id> <note>`: persistent notes displayed inline on future gets
  - `feedback <id> up|down`: ratings that influence search ranking
  - `build <dir>`: validate and package private content with registry.json
  - `cache list|clear|pin|stats`: full cache management with pinning
  - `sources` / `add-source` / `remove-source`: multi-source config management
  - `status` / `init`: storage management
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

## v0.8 (2026-02-27)

### Added
- **agent-zpc**: Structured project memory for AI coding agents (tool #75), 13 commands:
  - `learn`: capture validated lessons with tags (writes to `lessons.jsonl`)
  - `decide`: log decisions with rationale, confidence, bias detection (writes to `decisions.jsonl`)
  - `decide-batch`: batch-log decisions from planning phase via stdin or file (pipe-delimited)
  - `harvest`: consolidation scan with format health, pattern drafting, auto-write for 5+ lesson tags
  - `query`: search by tag, date, text, or type (lessons/decisions/all)
  - `patterns`: view established patterns, score effectiveness
  - `promote`: promote lessons to team (git-tracked) or global scope with dedup
  - `inject`: emit agent context blob for spawned agents (baseline counts for self-report grounding)
  - `init`: initialize `.zpc/` with stack auto-detection and platform-specific instructions
  - `status`: memory snapshot with health check (human + JSON output)
  - `checkpoint`: swarm phase boundary with memory inventory, agent compliance, format health, consolidation gaps
  - `review`: post-sprint lesson extraction from git history, draft lessons/decisions from commits
  - `profile`: view/update project profile, auto-detect stack
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

## v0.7 (2026-02-06)

### Added
- **agent-sessions**: AI coding session history search with FTS5 full-text search
- **agent-supabase**: Data access (REST queries, SQL via agent-db bridge)
- **install.sh**: Idempotent installer with Claude Code hooks distribution
- Claude Code hook trinity: SessionStart, UserPromptSubmit, PreToolUse

### Changed
- Tool count: 68 → 72
- Full repo audit: fix stale counts, symlink references, agent-gui→agent-macos renames

---

## v0.6 (2026-01-28)

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

## v0.5 (2026-01-15)

### Added
- Initial public structure with 60+ tools
- Structured API mode (`agent-do <tool> <command>`)
- Natural language mode (`agent-do -n "intent"`)
- Offline pattern matching (`agent-do --offline "intent"`)
- 3-tier fallback: SQLite cache → Jaccard fuzzy → Claude API
- Gold standard tools: browse, db, excel, unbrowse
