---
workflow: 2
manna: mn-9b4359
track: mn-b7a0cc
source: 'Erik conversation 2026-11-03: optional track-level build assignment through existing Manna board claim flow'
base_commit: fb540b72ee5419796e1dc6549650dcb61a3996e6
scope: 'Manna: claimable tracks dispatch one agent through child items in dependency order'
inputs:
- 'Erik conversation 2026-11-03: optional track-level build assignment through existing Manna board claim flow'
binding: sha256:a6693e98340e4bfec8a7e931cdc7ab8edfe0e3a8ff5d0de565b79b61ce13634b
---

# Handoff: Manna: claimable tracks dispatch one agent through child items in dependency order

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9b4359
```

## Scope

Manna: claimable tracks dispatch one agent through child items in dependency order

## Inputs

- Erik conversation 2026-11-03: optional track-level build assignment through existing Manna board claim flow

## Work order

Make tracks usable as optional whole-track build assignments through Manna's existing board claim/launch flow. Erik selects either a track (one agent executes its children in dependency order) or individual child items (normal multi-agent execution). Command-click in Holy only navigates to the filtered Manna board; do not redesign it. This is a general agent-do feature, not a change to the example VMS Admin backlog.

Scope and implementation
1. Trace track creation, canonical handoff generation/sealing, board card/action eligibility, dispatch payload, CLI claim, and agent instructions. The Rust claim method already permits tracks; identify the real end-to-end gap rather than adding a second claim mechanism.
2. Automatically generate a canonical, sealed, dispatchable work order for new tracks using existing Manna pairing and ordering conventions. Preserve tracks as organizational containers when unclaimed. Provide a supported, idempotent way to supply missing handoffs for existing tracks, without stealing claims, changing dependencies, resetting status, or rewriting custom instructions.
3. Enable the existing board claim/launch flow for tracks. Reuse existing interfaces and contracts. Inspect Holy's consumer boundary if needed, but only change Holy if an actual separate restriction is demonstrated; record any required counterpart explicitly. No new command-click behavior or mode selector.
4. The dispatched agent claims the track, reads current children and dependencies from the canonical board, then claims eligible children individually and follows each child's sealed work order. Dependencies govern readiness; existing priority breaks ties deterministically. Refresh board state between children. Do not embed a copied progress ledger in the track handoff.
5. Continue through eligible children without Erik relaying a prompt per lane. Respect existing child claims, external prerequisites, review/acceptance requirements and scoped permissions. Do not bypass a refused claim. If one child is unavailable, select another eligible child; if none is eligible, record the precise blocker and continuation state using existing lifecycle conventions. Never mistake submitted implementation for accepted completion.
6. Track ownership does not claim/reserve every child, block independent child dispatch, confer coordinator authority, or authorize merging/deployment. Concurrent agents may claim children normally; existing atomic child claims prevent duplicate ownership. Releasing or transferring track responsibility preserves all child work and claims. A successor reconstructs progress from current board truth.
7. Close a track only when its required children and track-level acceptance conditions are satisfied. Decide and document empty-track, newly added child, removed/moved child, cycle/missing-dependency, and all-children-owned behavior without introducing a new scheduling service. Never silently expand authorized scope when children change.

Acceptance and tests
- Create a track with a dependency chain; exercise the actual board dispatch backend and inspect the complete generated assignment. Verify normal claim/launch eligibility, canonical pair and seal, and ordered child instructions, not just Issue::claim in isolation.
- Cover existing tracks missing handoffs and idempotent repair; preserve custom handoffs and existing ownership.
- Cover completed children, two eligible children with deterministic priority, child claimed elsewhere, external blockers, no eligible work, and a successor resuming track ownership.
- Demonstrate independent child dispatch still works with the parent unclaimed and claimed, and competing child claims do not both succeed.
- Test premature track completion refusal and any scope-change policy implemented. Reuse existing lifecycle and acceptance semantics; test ordinary and managed children where applicable.
- Run owning Rust, board/serve, workflow and integration tests as appropriate; validate registry contracts and regenerated docs if command surfaces change. Update Manna documentation with the user-facing flow and explicit limits. No claim that an idle/closed worker wakes automatically.

Delivery and boundaries
One implementation lane, with independent review before acceptance. Return SUBMITTED with exact commits, executed receipts, and any remaining end-to-end host gate; do not self-close. Commit owned paths with this item's Manna trailer and reseal. Preserve concurrent MI/Coord work and foreign board edits. No scheduler, automatic worker spawning, new dashboard, new dependencies, broad refactor, live worker injection, application launch/install, push, PR, or pilot activation. Managed Integration and Holy wake support are not prerequisites for this bounded feature. Filing authorizes preparation of this work order only, not starting implementation in this session.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9b4359`.
4. Commit with `Manna: mn-9b4359` and run `agent-do manna done mn-9b4359` only after the work is verified.

## Delivery receipts (2026-11-04, worker claude-a6751ebc0cba4493, SUBMITTED for independent review)

Status: implementation, tests and documentation delivered; not self-closed. Independent review pending (the reviewer closes).

Code commit: `8e786891bd74cf422e9c04ed2d1a301ce2eed652` (`Manna: mn-9b4359`).

### The end-to-end gap, as traced (step 1)

- `tools/agent-manna/src/store.rs` `validate_strict_row_shapes` refused any track carrying `prompt` or `handoff_digest`, so a track could never pair on a strict board.
- `tools/agent-manna/src/main.rs` `cmd_create` paired only items and refused `--prompt` on non-items; `cmd_claim` let a track through with no work order and no binding check; `cmd_done` closed a track over open items on every path.
- `tools/agent-manna/src/workflow.rs` `paired_items`/`planned_items` were item-only, so no track entered `handoff-order.yaml` or the generated index.
- `tools/agent-manna/src/state.rs` derived every track as `effective: track`, so none reached `next`; the serve launch pointer (`next[0]`) and Holy's dispatch refusal (which needs `effective == ready`, `prompt`, `handoff_digest`, `handoff_exists`) never saw one.
- Holy: `macos/Sources/HolyGhostty/Board/HolyMannaBoardWorker.swift` `HolyMannaWorkerDispatch.refusal` additionally guards `item.kind == "item"`. A separate, demonstrated restriction; recorded here, not changed from this lane.

### What landed

- `tools/agent-manna/src/track.rs` (new): `pairable`, `is_paired`, `is_dispatchable_track`; `track_children` (eligible items by dependency, then handoff priority, then age, then id; `next`; `held`; `waiting` with `missing` and `cycle`; `decisions`; `dreams`; `added_since_claim`; `stall`); `track_close_refusal`.
- `store.rs`: a track carries both pair fields or neither; the close gate runs under the lock in `finish_issue_unlocked` on every close path (owner, evidence, operator, acceptance); strict delete archives paired tracks.
- `workflow.rs`: paired rows are items plus paired tracks; `generated_track_body` (the dispatch protocol, same five required sections, no ledger); Create/Attach/Rebind/Detach/Delete transaction shapes keyed on pairable kinds; `adopt_handoff`; `regenerate_handoff`; `handoff_order_ids`; orphan detector admits track handoffs.
- `state.rs`: paired tracks follow the item lifecycle (`ready` while an item is claimable or every item is done, `waiting` otherwise, `active`, `done`); `children` on every track row; unpaired tracks keep `effective: track`.
- `main.rs`: `create` pairs tracks; `claim` refuses an unpaired track (exit 2, remedy named) and validates a paired one like an item; `done` pre-checks the track gate (exit 2); `handoff seal` admits paired tracks; new `handoff attach <track-id>` (idempotent, adopts an existing document, owner-only on a claimed track); `update` arms keyed on (paired before, pairable after), item <-> track regenerates the document, dream -> track pairs; `delete`; `show` children; lint and sprawl filters; `reconcile --fix` landed_open cure refuses to close a track over open items.
- `tools/agent-manna/serve/board.py`: the estate summary mirrors the paired-track lifecycle, including the waits rule.
- `registry.yaml` (create, claim, done, handoff, show descriptions; one example) and `docs/TOOLS.md` regenerated; `tools/agent-manna/README.md` (sections for create, claim, done, show, `handoff seal`/`attach`, and "Tracks as whole-track build assignments" with explicit limits); `tools/agent-manna/SCHEMA.md`; `ARCHITECTURE.md`; `CLAUDE.md` (Track dispatch convention); `CHANGELOG.md`.

### Policies decided and documented (step 7)

- Empty track: `effective: waiting`; `done` refuses (nothing was finished; delete it or give it items).
- Newly added child: eligible under its own sealed work order, listed under `children.added_since_claim`; the protocol has the agent name the change of scope before claiming it.
- Removed or moved child: leaves `children`; its row, claim and work order are untouched; one the agent already holds stays its own.
- Cycle or missing dependency: `waiting` with `cycle`/`missing` flags, named in `stall`; the track derives `waiting`; `manna block` itself does not refuse a cycle.
- All children owned elsewhere: `held` with owners, named in `stall`; the track derives `waiting`, so the launch pointer never proposes it.
- Track ownership reserves no item, blocks no independent worker, confers no authority; a refused child claim is final for that child.

zpc: decisions dec-94ce98 (attach as the explicit per-track opt-in), dec-981372 (ready only while dispatchable), dec-a0fc09 (close gate on every path); lessons les-23c955, les-be815f, les-776505, les-2cbc90.

### Executed validation (all exit 0 unless stated)

- `cargo test --release` (tools/agent-manna): 204 + 52 passed, 0 failed, including `track::tests` (5).
- `bash tools/agent-manna/test/integration.sh` (venv Python on PATH): 735 passed, 0 failed. New section T1–T13: a track with a dependency chain through the real derivation (`state --json`: ready, in `next`, `handoff_exists`, priority slot, `children.next`, grouping preserved, the three dispatch fields complete); ordered eligibility and priority moves; claim through the ordinary gate and premature-close refusal (exit 2, nothing written); the dispatched agent working children one claim at a time with a child claimed elsewhere, an external blocker, and refresh; six concurrent claims on one child with one winner, independent child dispatch with the parent claimed and unclaimed; successor resumption, added-since-claim and moved-out children; close only when every item is done; an unpaired existing track (container, claim refused with the remedy, lint silent, attach generates, second attach `changed: false`, binding stable, empty track waits and cannot close, then ready and claimable once it has an item; attach refuses an item); adoption of a custom document byte for byte and refusal of an invalid one; attach on a claimed legacy track (stranger refused, holder succeeds, claim, claim time, status and child dependencies preserved); cycles and deleted dependencies named; dream -> track -> item conversion regenerating the document; reconcile reports no orphan, pairing or sprawl finding; a managed child submitted but unaccepted holds the track open until the lead accepts and closes it.
- `python3 tests/test_manna_serve.py`: 57 OK (6 new `TrackDispatchTests`; `derive()` runs the real `manna-core state --json`). `python3 tests/test_manna_estate.py`: 6 OK.
- `agent-do harness contracts validate`: Gate PASS, 0 errors, 0 warnings. `contracts drift`: 0 failing. `bin/gen-tools-doc --check`: in sync. `tests/test_contracts_gate.py`, `test_contracts_drift.py`, `test_routing_contracts.py`: passed.
- rustfmt: every touched file clean; three pre-existing non-clean files (`managed.rs`, `managed_cli.rs`, `reconcile.rs`) deliberately left untouched.
- Everything above was executed; nothing is build-only. Not run: the full `./test.sh` (focused suites per the lane rules). No app launches, installs, screenshots, pushes or pull requests.

### Remaining acceptance and host gates

- Independent review of this submission; this worker does not self-close.
- Holy counterpart (not a prerequisite for the agent-do feature; `manna serve`'s launch pointer needs nothing): admit `kind == "track"` in `HolyMannaWorkerDispatch.refusal` (`holy-ghostty/macos/Sources/HolyGhostty/Board/HolyMannaBoardWorker.swift`, the `guard item.kind == "item"` line) when `effective == "ready"` and the pair fields are present. The brief text already fits a track because the track handoff carries the protocol and the close rule.
- Older `manna-core` binaries (other worktrees) refuse a strict board that holds a paired track; rebuild them before pairing a track on a shared board. No track on any board gains a handoff until someone runs `create --type track` or `handoff attach`.
- SessionEnd `reconcile --fix` (mn-4e7229): with this trailer commit on the branch, another session's end may close this in_progress item mechanically. That would be the cure, not acceptance.
- `.manna/issues.jsonl` carries this claim and the seal digest in the working tree beside other lanes' uncommitted rows; left for the operator's board commit.
