---
workflow: 2
manna: mn-59f1e4
track: mn-b7a0cc
source: 'Erik conversation 2026-10-30: stale coord drops and coordinator closure; approved one complete agent assignment'
base_commit: c664a81c024fb9a46bc3957528f614679cb0a16c
scope: 'Coord/Manna: complete coordinator-owned handoff and closure without worker revival'
inputs:
- 'Erik conversation 2026-10-30: stale coord drops and coordinator closure; approved one complete agent assignment'
binding: sha256:c43ab158467efb3882a8b64a007dec0c42a2fc00a14b6b678c269629d23973ab
---

# Handoff: Coord/Manna: complete coordinator-owned handoff and closure without worker revival

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-59f1e4
```

## Scope

Coord/Manna: complete coordinator-owned handoff and closure without worker revival

## Inputs

- Erik conversation 2026-10-30: stale coord drops and coordinator closure; approved one complete agent assignment

## Work order

## Outcome
One agent owns and delivers the complete workflow: a worker submits, its original session becomes unavailable, the authorized coordinator verifies integration and acceptance and closes or releases the assignment without Erik resuming the worker. Resolved coordination notes stop resurfacing; reports and history remain inspectable. These are internal checkpoints of one delivery, not three separately dispatched tasks.

## Motivation and observed baseline (2026-10-30; reverify before editing)
Versova supply-intelligence reported nonexistent unmerged code from old coord drops. mn-8825b0 and mn-452827 remain in_progress under old worker claims despite integration commits appearing in the locally recorded origin/staging history. Their handoffs reserve integration/deployed acceptance for the coordinator; this item does NOT authorize closing those items without their receipts.
- tools/agent-coord add_drop/drops/interrupts: drops lack stable resolution lifecycle. mark-seen affects newness but does not suppress a drop. Agent pruning leaves drops behind. Hook prompt routing reads interrupts repeatedly.
- tools/agent-manna/src/main.rs cmd_done already permits foreign-claim closure on source-touching trailer evidence. collect_landed_trailers searches only the current HEAD's last 500 commits. A canonical board checkout on design/overhaul therefore sees different evidence from the integration branch. A trailer is not acceptance, and the current outside-.manna/.handoff path test is not proof of product completion.
- reconcile --fix can close landed orphaned claims. Managed acceptance must not be bypassed through this or another lifecycle entry point.
- Existing full architecture: /Users/erik/Custom-Coding/holy-ghostty/.handoff/HOLY-MANAGED-COLLABORATION-PROPOSAL-2026-10-13.md, especially result records and authority/recovery. Deliver a compatible bounded slice, not the full runtime overhaul.

## Complete scope
1. Drop lifecycle: stable IDs, acknowledgment distinct from resolution, audit actor/reason/evidence, retained history. Recipients acknowledge delivery; authorized coordinator resolves work. Resolved drops leave routine interrupts. Acknowledged unchanged informational drops do not repeat on every prompt. Meaningful updates can resurface; active contention remains visible. Preserve original timestamps and label historical reports as unverified current state. Define any/role recipient semantics; one reader must not silently hide a broadcast for everyone. Handle legacy drops compatibly without treating age, missing owner, or missing file as completion. Do not delete unresolved information.
2. Closure assessment: one read-only structured CLI path explains target revision, integration evidence, outstanding required acceptance, authority and exact next action. Explicitly pin the integration target SHA; distinguish current HEAD, local branches, remote-tracking refs and deployed revision. No silent checkout/fetch/deployment assumptions. Handle rewritten/cherry-picked integration through explicit evidence; trailers and patch matches alone never prove acceptance. Closure revalidates expected board/assignment/evidence state under locking and refuses stale assessment or incomplete acceptance. Scope enforcement consistently across done, reconcile and other mutation paths. Preserve documented unmanaged compatibility without making it an escape hatch for managed items.
3. Scoped coordinator authority: authenticated, explicit grant for bounded items/track scope, never self-elevated from an overseer label, pulse, claimed identity string, or shared worker secret. Coordinator can receive submission, request correction, accept and close, or release/cancel with reason. Submission is distinct from acceptance; remaining checks have a visible coordinator owner. Expected owner plus assignment revision/attempt prevent races and superseded worker completion. Establish old-worker stop or isolated checkout before replacement; unknown liveness is not death. Preserve files, result reports and audit history. Reuse existing Manna identity/transaction mechanisms and coord ledger; no separate shadow backlog or messaging system.
4. Wire the workflow through relevant hooks, CLI help, registry contracts, existing human-facing state consumers and docs. Provide a clear installed/runtime adoption check so source-only implementation is not reported as live. Include backward-compatible storage handling and recovery behavior; if migration impact is uncertain, present the concrete design before applying it to live boards.

## Acceptance
- Exercise the actual CLI production paths against isolated fixture repositories: worker claims and submits, source integrates on a different branch from the canonical board checkout, worker becomes unavailable, authorized coordinator records required acceptance and closes without resuming or impersonating worker. Related drops resolve, stop nudging across repeated turns and fresh sessions, and remain available in history. No human relay.
- Missing/failed acceptance blocks closure even with a source-touching trailer; receipt-only commits are not product acceptance. Unavailable/stale integration targets fail clearly.
- Unauthorized coordinator, wrong scope, changed assignment/target, concurrent close/reassign, and superseded worker cannot mutate the managed lifecycle. Unknown liveness never authorizes simultaneous writers.
- Legacy drops and unmanaged boards remain usable; role/any drop delivery is not lost; acknowledgment is not completion; changed records can resurface; contention stays visible. Lifecycle audit survives restart.
- Test all relevant closure paths, including reconcile, not only a new happy-path verb. Verify normal owner completion and dependency release still work.

## Validation and delivery
Read nearest AGENTS.md, current manifests, source and coord ownership before editing. Claim this item first; do not steal conflicting claims. Use narrow owned paths and isolated worktree if needed; canonical Manna lifecycle remains in primary checkout. Inspect related existing backlog items (mn-42501b report persistence, mn-fa98a3 closing-rule docs, mn-00160d stale-claim findings, mn-e593a1 reconcile review) and reuse relevant work without absorbing unrelated scope.
Run applicable coord suites, Manna cargo/unit and CLI integration tests, hook regression tests, registry contracts validate/drift and root test.sh per canonical setup. Add meaningful end-to-end and failure/race coverage. Report failed or unexecuted gates explicitly. Commit verified changes with this item's Manna trailer, update the sealed work order with exact receipts and adoption status, and close only when this work order is satisfied.

## Boundaries
No automatic terminal/process retirement, Holy UI redesign, durable execution service, cross-machine scheduler or full orchestration rewrite. No sweeping live-board cleanup, worker impersonation, editing issues.jsonl by hand, shared identity secrets, or bypassing required acceptance. No push, PR, deployment, destructive cleanup or live migrations without separately applicable authority. Preserve existing foreign dirt. This is one complete implementation assignment; do not stop after a plan or one of the three components.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-59f1e4`.
4. Commit with `Manna: mn-59f1e4` and run `agent-do manna done mn-59f1e4` only after the work is verified.

## Delivery (2026-10-30, session claude-35dfcfc4870d4899)

### What landed

- `tools/agent-coord`: drop lifecycle. Stable `drp-` ids, `revision`, `status`, per-reader `acks`, `history`; legacy drops normalized read-only (deterministic id, `legacy: true`, original timestamps, `owner_presence: unknown` for a pruned owner). New verbs `drop ack <id>`, `drop resolve <id> --reason [--evidence] [--for-everyone]`, `drop history <id>`, `drops --all`. Interrupts skip resolved drops and drops the reader acknowledged at the current revision; summaries carry the drop id, `reported <age>, not re-verified`, and the ack command. Journal lines carry `drop_id`. Nothing deletes a drop; cascade prune leaves them.
- `tools/agent-manna`: managed lifecycle. New lib module `src/managed.rs` (grants, records, audit, authority, closure rule, assessment digest; 6 unit tests) and binary module `src/managed_cli.rs`. Verbs: `identity`, `coordinator grant|revoke|list`, `managed require|correct|release|history|doctor`, `submit`, `accept`, `assess`, `done --assessment`. Sidecars `.manna/coordinators.json`, `.manna/managed.json`, `.manna/lifecycle.jsonl` under the board lock (`store.rs`: `complete_issue_on_acceptance`, `with_locked_issue`; `issue.rs`: `complete_on_acceptance`, `SessionIdentity::proof`). `done` on a managed item ignores trailer evidence; `reconcile --fix` refuses `dead_claim`/`landed_open` on managed items; `claim`/`abandon` write audit lines and `abandon` ends the attempt. `state.rs` adds a per-row `managed` summary; `workflow.rs` tracks and un-ignores the sidecars.
- Wiring: `registry.yaml` (commands, examples, capabilities, contracts), `docs/TOOLS.md` regenerated, hooks `agent-do-session-start.sh` and `agent-do-prompt-router.py` name the ack/resolve commands, `ARCHITECTURE.md`, `tools/agent-manna/README.md`, `SCHEMA.md`, `docs/INTEGRATION.md`, `CLAUDE.md`, `CHANGELOG.md`.

### Adoption status

`agent-do manna managed doctor` on this machine: `live: true` (answering binary `tools/agent-manna/target/release/manna-core` carries `managed_lifecycle`; installed `tools/agent-coord` carries `drop ack`/`drop resolve`; `agent-do-prompt-router.py` and `agent-do-session-start.sh` are registered in `~/.claude/settings.json`). Live demonstration on this repo's board: the five legacy drops addressed to `any` (corpus/design, apprenticeship, serve XSS note, zpc-trigger note, CHANGELOG fetch note) normalized to `drp-` ids and were acknowledged by this session only; `coord interrupts` dependency count went 5 → 0 for this reader, the records stay `open` for every other reader, and `drop history` shows the acknowledgment. No live board was migrated: sidecars are created only when a coordinator runs `managed require`.

### Verification receipts (executed, not compiled-only)

- `cargo test --quiet --manifest-path tools/agent-manna/Cargo.toml`: 189 passed (lib, includes 6 new `managed::tests`), 52 passed (bin), 0 failed.
- `bash tools/agent-manna/test/integration.sh`: 463 passed, 4 failed. The 4 failures (`done reports an empty release list...`, `done lists only the fully released dependent`, `only the unfinished blocker remains...`, `last blocker done lists the newly released dependent`) are pre-existing on the unmodified tree (`git stash` baseline: 407 passed, 4 failed) and come from the PATH `python3` (Homebrew 3.15) lacking PyYAML; they pass under the repo venv. The new section "Managed Lifecycle Tests" (M1 worker submits / source lands elsewhere / coordinator accepts and closes without the worker; M2 release, superseded worker, changed assignment; M3 unmanaged paths intact) is 56 checks, all passing, including reconcile `--fix` refusing a managed item with a landed trailer on HEAD, dependency release on the managed close, stale-assessment refusal, stranger/worker/impostor refusals, unavailable target, mismatched target, and operator grant through a pty.
- `python3 tests/test_coord_v2.py` (new `test_drop_lifecycle`: legacy normalization, stable ids, idempotent re-add, per-reader ack, suppression across repeated reads, revision resurfacing, authorized resolve with reason/evidence, silence for fresh sessions, `--all`/history retention, broadcast ack vs `--for-everyone`, reopen, contention still visible, nothing deleted): passed. `python3 tests/test_coord.py`: passed.
- Hooks: `python3 tests/test_v11_routing.py`, `tests/test_session_start_reads.py`: passed. `tests/test_manna_estate.py`, `tests/test_manna_serve.py` (venv python): OK.
- `agent-do harness contracts validate`: Tools 103, Declared 103, Errors 0, Warnings 0, Gate PASS. `agent-do harness contracts drift`: declared-but-unimplemented 0. `tests/test_contracts_gate.py`, `tests/test_contracts_drift.py`: passed. `bin/gen-tools-doc --check` clean after regeneration.
- Root `./test.sh` (PATH=.venv/bin first): see the receipt line appended below.

### Not done / boundaries kept

- mn-8825b0 and mn-452827 were not closed; this item does not authorize it and their receipts are not recorded. The path for them is now: coordinator `managed require` → worker (or operator) `submit` → `accept --target <integration ref>` → `done --assessment`.
- No push, PR, deployment, live migration, or sweep of existing drops/claims. The five legacy drops on this board were acknowledged for this reader only, not resolved.
- Known limits: `manna managed doctor` reads `~/.claude/settings.json` only (Codex hook registration is not checked); `assess --deployed` records a caller assertion, never an observation; coordinator grants are per board (no federation of grants).
- Root `./test.sh` (PATH=.venv/bin first): 128 passed, 1 failed. The failure is `live runtime tests` (`tests/test_live.py`: `macOS frameworks not available`, exit 1); it fails identically on the unmodified tree (`git stash` baseline exit 1) and is unrelated to this item. The manna integration suite inside it passed in full under the venv python.
- Known gap found at close: the Claude hooks run `coord` under a different coord identity than the shell (the prompt-router lists this shell's session as a peer), so a `drop ack` from the shell quiets the shell's `coord interrupts` but not the hook's nudge; `drop resolve` quiets both. Filed as a follow-up item on this board.
