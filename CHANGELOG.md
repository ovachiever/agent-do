# Changelog

## Unreleased

### Added
- `agent-do gh` for GitHub repository, pull request, review, and merge work-state across accessible repos, with `inbox`, `awaiting`, `prs`, `pr`, `diff`, `threads`, `checks`, `review`, `approve`, `request-changes`, `comment`, `merge`, `ready`, and `draft` commands.
- Optional Sonnet 4.6 adaptive-thinking command selection for `agent-do suggest`, grounded in registry candidates with deterministic fallback and `--ai auto|on|off`.
- `agent-do notify` as a root-level notification contract over `sms`, `email`, `slack`, `messenger`, and local `pipe`, backed by `bin/notify` and `lib/notify.py` instead of another registry tool.
- Rule-driven notification emission through `agent-do notify set-rule` and `agent-do notify emit`, with exact fact matching, message templates, fingerprints, and cooldown-aware delivery state.
- `agent-do notify delete-rule` and `agent-do notify reset-state` for rule cleanup and cooldown-state hygiene.
- Built-in notify rule templates with `agent-do notify templates`, `show-template`, and `apply-template` for common cases like failed builds, failed deploys, stalled jobs, and approval requests.
- Recipient groups for `agent-do notify`, so direct sends and event rules can target aliases like `ops` without duplicating recipients across rules.
- Append-only notify delivery history with `agent-do notify history`, including filters for provider, recipient/group, rule, event, and success.
- Prompt-router completion nudge for fuzzy status/continue prompts, so long-running sessions refresh the stop condition instead of drifting into optional polish by default.
- `agent-do auth` for site-level authentication orchestration over saved browser sessions, browser import, and secure credentials.
- `agent-do creds` for secure secret storage, inspection, export, and per-tool credential checks.
- `agent-do spec` for repo-local canonical specs and active change packages under `agent-do-spec/`.
- `agent-do resend` for exact Resend domain records, verification state, and public DNS checks without relying on UI text.
- `agent-do hardware` as a family-level surface over serial, bluetooth, USB, printer, and MIDI commands, with a combined hardware snapshot and delegated subdomain commands.
- `agent-do meetings` as a family-level meeting surface over Zoom, Google Meet, and Microsoft Teams, with provider snapshots, auto-detected join routing, active-provider controls, and explicit passthroughs.
- `agent-do coord` as a project-local state-and-interrupt broker for parallel agents, with presence leases, focus declarations, advisory claims, dependency tracking, published artifacts, and derived contention/dependency/novelty interrupts.
- interrupt-aware coord nudges at session start and prompt time, so agents only get coordination context when a real interrupt exists or when active peers exist and the current agent has not declared focus yet.
- Internal `lib/live/` runtime substrate for explicit local-machine control approval, leases, and rerun hints behind the new `agent-do +live(...) ...` execution modifier.
- `lib/creds-helper.sh` as a shared secure-store backend for macOS Keychain, Linux Secret Service, and a Windows DPAPI-backed per-user store.
- Registry-level `credentials` metadata so tools can declare which secret env vars they need.
- Browser clipboard commands through `agent-do browse clipboard read|copy|paste` for copy-first extraction flows.
- `agent-do email latest|wait|code|link` for inbox polling, verification code extraction, and magic-link extraction.
- `agent-do sms snapshot|latest|wait|code|link` for message polling, verification code extraction, and link extraction.
- `agent-do auth probe` for classifying the live auth checkpoint branch and optional frontmost macOS dialog state.
- `agent-do auth advance` for executing one safe checkpoint step, then returning the updated auth branch state.
- `lib/snapshot.sh` honors `AGENT_DO_SNAPSHOT_COMPACT=1` to emit single-line JSON instead of pretty-printed output, for piping to jq, log lines, or other tools that prefer one document per line.

### Changed
- UserPromptSubmit coord nudges now stay quiet for ordinary work prompts and only inject coord context for explicit coordination requests or blocking coord interrupts.
- UserPromptSubmit no longer suggests `agent-do context search` just because a prompt asks to edit local docs, README, or changelog files.
- Python dependency floor for `anthropic` is now `>=0.97.0` so Sonnet 4.6 adaptive-thinking request fields are supported.
- Session-start bootstrap handling now uses a native macOS prompt in the global Claude/Codex hook path instead of relying on the model to remember to ask in conversation.
- `agent-do email` discovery now uses Apple Mail's local Envelope Index for account, mailbox, and message lookup, so large live mailboxes no longer block on AppleScript enumeration timeouts.
- `agent-do email` now exposes `search`, `get --id`, and `mailboxes` on top of a unified structured query path, with explicit `metadata_only` message states and scoped unread counts that distinguish all-mailbox totals from inbox-only unread totals.
- `agent-do` now recognizes `+live` and `+live(...)` as runtime modifiers before normal tool dispatch, so explicit local-control approval can live at the call site without introducing a wrapper tool in the registry.
- `agent-do auth` now supports `--strategy live-browser-control`, which keeps the agent in the visible real browser under `+live(...)` approval and runs the same checkpoint model on top of the existing `macos` and `screen` control surfaces instead of importing back into Playwright.
- Saved authenticated state is now a first-class outer-harness concern instead of an implicit split between `creds` and `browse`, with encrypted auth bundles stored under `~/.agent-do/auth/`.
- `agent-do auth` now uses provider-aware GitHub and Google login adapters for `site-creds`, with TOTP secrets resolved through `agent-do creds` when those flows require one-time codes.
- `agent-do auth init --provider github|google` now creates SSO-first site profiles, and `provider-refresh` can reuse upstream provider auth to complete cross-site sign-in.
- `agent-do auth` can now continue mailbox-driven login flows through `agent-do email` when a site profile declares an email code or magic-link challenge.
- `provider-refresh` now handles provider account choosers and consent checkpoints, and stores those checkpoint selectors in auth session metadata for later inspection.
- `agent-do auth` can now continue SMS-driven login flows through `agent-do sms`, and it correlates email/SMS challenges against a pre-login mailbox baseline so stale unread messages are ignored.
- `agent-do auth` now surfaces passkey or security-key checkpoints as explicit action-required states instead of flattening them into a later validation failure.
- `agent-do auth` now surfaces device-approval, consent, chooser, and CAPTCHA checkpoints as structured states, and `status`/`instructions` preserve that checkpoint context instead of dropping back to a generic configured state.
- `agent-do auth ensure` now stores pre-login email/SMS baselines in session metadata so later checkpoint retries can ignore stale unread challenges, and `advance` can safely continue chooser, consent, mailbox, TOTP, passkey-dialog, and passive device-approval branches.
- `agent-do auth advance` now prefers visible in-browser alternate auth methods like “Try another way” on passkey or device-approval branches before falling back to dialog clicks or passive waiting.
- `agent-do auth` now understands provider recovery-code branches, can consume the next unused backup code from secure storage for GitHub and Google flows, and records consumed codes locally so they are treated as finite credentials instead of endlessly replayed secrets.
- `agent-do auth ensure --strategy interactive` now opens a real system browser for human-visible or anti-bot login flows, then polls browser import and persists the imported state back into encrypted auth storage when validation succeeds or when the imported page lands on a live checkpoint branch that `probe` and `advance` can continue.
- Provider-backed site profiles now inherit upstream GitHub or Google TOTP and backup-code config for live checkpoint handling, and alternate-method selection prefers visible branches that match available credentials instead of clicking the first generic fallback.
- `agent-do browse session import-browser` now supports Comet directly, and Comet is the default real-browser import source for auth/browser-import flows instead of Atlas.
- `agent-do browse session import-browser` now imports Chromium localStorage and sessionStorage alongside cookies when those stores are available, so imported sessions can carry more than cookie state alone.
- `agent-do browse` session save/login-transfer/storage-export paths now request Playwright storage state with IndexedDB enabled, and `session import-browser` now includes best-effort Chromium IndexedDB for stores that can be losslessly serialized into Playwright’s native format.
- `agent-do browse` now auto-derives its daemon session from the current agent/thread identity when `--session` and `AGENT_BROWSER_SESSION` are absent, so multiple agents stop colliding on the shared implicit `default` browser daemon.
- Non-default `agent-do browse` daemons now fork writes away from existing shared saved-session names by default, so `session save <name>` or `login done --save <name>` stop silently overwriting a shared base unless `--shared` is used.
- `agent-do render logs` now uses Render's `/v1/logs` API with `ownerId` and `resource` filters, supports real log-query flags, and no longer treats `logs --help` as a missing service lookup.
- Structured tool dispatch now ignores unregistered `agent-*` binaries on `PATH`, so third-party commands cannot shadow built-in intents unless the tool name is explicitly registered in `registry.yaml`.
- Structured execution and natural-language execution now preload declared tool secrets from env vars or secure storage before invoking the target tool.
- `agent-do --health` now reports credential readiness from the same registry metadata instead of relying only on a small hardcoded env-var list.
- Discovery metadata now covers `agent-do spec`, including prompt matching for change proposals and repo-local spec work.
- Docs and smoke tests now cover the new credential workflow.
- `agent-do namecheap dns-add` and `dns-update` now reject suspicious masked values, verify exact Namecheap read-back by default, and can optionally confirm public DNS answers.
- `agent-do macos` and `agent-do screen` now require explicit `+live(...)` approval, or a matching active live lease, before performing direct visible-machine control actions like click, type, scroll, focus, open, or dialog clicks.

### Fixed
- `agent-do gh` now distinguishes strict GitHub review requests from broader awaiting-review PRs, and it normalizes direct `gh pr view` reviewer objects instead of reporting `[null]`.
- `agent-do browse get text|html|value|attr` now emits the correct browser protocol actions instead of invalid discriminator values.
- `agent-do namecheap dns-add` no longer crashes after successful writes because of the bare `host` reference in its success path.
- `agent-do render` commands now resolve services by name again; `resolve_service` was querying an invalid `name[]=` filter that the Render API rejects as "not a valid field," so every name-based lookup fell through to the not-found branch and only `srv-xxx` IDs worked.

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
