# agent-do Engineering Guide

This file is the operating guide for agents working in this repository.

## Scope

Applies to `agent-do/`.

## Source Of Truth

1. Running code and checked-in files in this project
2. Local manifests and lockfiles
3. Local README, deployment files, and nearest scoped `AGENTS.md` files
4. Historic notes only when they still match the code

## Current Repo Signals

- Root manifests: `requirements.txt`.
- Inferred stack signals: Python, Bash, Node.js, Rust.
- Allowed external helper reference: `agent-do` when browser, mobile, desktop, or GUI automation is actually required.

## Top-Level Layout

- `assets/`: images and visual assets
- `bin/`: core routing, discovery, and bootstrap scripts
- `hooks/`: Claude Code integration hooks
- `lib/`: shared library code (Python, Bash, Node.js)
- `tests/`: test scripts
- `tools/`: 102 tools (standalone scripts + directory-based tools)
- `agent-do`: main entry point (bash)
- `registry.yaml`: master tool catalog
- `models.yaml`: model roles and capability records for agent-do's own internal LLM calls
- `install.sh`: idempotent installer
- `test.sh`: root test runner (smoke tests, tool suites, contracts gate and drift check)
- `ARCHITECTURE.md`: routing flow and component map
- `CHANGELOG.md`: release history
- `CLAUDE.md`: Claude Code project instructions
- `CONTRIBUTING.md`: contribution guidelines
- `docs/INTEGRATION.md`: Claude Code hook wiring
- `LICENSE`: MIT license
- `README.md`: public-facing documentation
- `SECURITY.md`: vulnerability reporting policy
- `docs/TOOLS.md`: tool catalog reference

## Working Rules

- Keep this file factual and current-state. Do not turn it into a roadmap or target architecture document.
- Keep unrelated non-engineering language out of this file.
- Use the nearest scoped `AGENTS.md` before changing a deeper package, app, or subsystem.
- Prefer small, local changes and validate through the manifest that owns the touched code.
- Every registry tool declares a `contracts:` block mapping each command verb to the five beats (Connect → Snapshot → Interact → Verify → Save), with `attributes:` flags (`destructive`, `long_running`, `polymorphic`, `composite`, `sensitive`, `passthrough`, `own_state`) for verbs a single beat cannot express. Draft with `agent-do harness contracts propose --tool <name>`; validate with `agent-do harness contracts validate`. The gate runs in `./test.sh` and CI, enforces full coverage (no tool may merge without a block), and requires zero warnings. Companion subcommands: `contracts surface` (machine-readable safety buckets for parallel scheduling), `contracts drift` (registry promises vs each tool's `--help`), and `contracts audit` (bounded behavioral probe of the read surface).

## Work Tracking

- The manna board (`.manna/`) is the single backlog and tracked `.handoff/` is the single work-order root. `agent-do bootstrap` installs both for every detected project. Board grammar and this project's vocabulary live in `CLAUDE.md` under "Manna Board Conventions": every issue is a track, an item on a track, or a dream; typed fields are set through the manna CLI, never by editing `.manna/issues.jsonl`.
- Commits that advance an item cite it with a `Manna: mn-xxxxxx` trailer.
- Items and handoffs pair automatically: `manna create` writes the initial work order and its board pointer, and the handoff carries the exact claim command. `.manna/handoff-order.yaml` owns priority; `manna sync` transactionally derives dense `.handoff/<NN>[b<MM>]-<mn-id>-<slug>.md` names and the generated index. `claim` fails closed when the pair is broken. `manna reconcile` verifies both directions, reports presentation drift, and flags shadow roots as `workflow_sprawl`.
- Identity is host-anchored and authenticated: Claude and Cursor persist a stable host session id, Codex supplies its opaque thread id, and Manna derives the proof under a machine-local key. `AGENT_DO_COORD_SESSION` anchors coordination separately. There is no transient-pid fallback, the visible owner label is not a credential, and scripted lanes export both `MANNA_SESSION_ID` and secret `MANNA_SESSION_TOKEN` explicitly.
- Reconcile is the drift net: `manna lint` enforces board grammar and reports canonical board files absent from the Git index as `workflow_tracking` with `git-tracked: no`; `manna reconcile [--fix]` detects landed-but-open items, dead-session claims, blocker desync, stale dreams, dangling track edges, and doc references to nonexistent issues. The SessionEnd hook runs it advisorily and writes `.manna/drift.yaml`, which the next SessionStart surfaces as a greeting.

## Validation

```bash
./test.sh                                      # Root smoke tests
cd tools/agent-browse && npm test              # Browser tool tests
cd tools/agent-manna && cargo test             # Issue tracker unit tests
bash tools/agent-context/test/integration.sh   # Context tool integration tests
bash tools/agent-manna/test/integration.sh     # Manna integration tests
```
