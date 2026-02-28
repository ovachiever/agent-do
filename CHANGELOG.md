# Changelog

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
