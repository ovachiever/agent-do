---
workflow: 2
manna: mn-cf4d8d
track: mn-b7a0cc
source: independent review of mn-59f1e4, 2026-10-30; .dev/mn-59f1e4-review/fixture-ybbcr21k/review-results.txt
base_commit: ed20b7344e7d50fd4d442f1b34489668625c4ba6
scope: 'Corrective: mn-59f1e4 failed independent acceptance — bind acceptance to the exact submission, verified release only, atomic lifecycle transitions with authority rechecked under the lock, action-vs-info nudge semantics, evidence-based current state'
inputs:
- independent review of mn-59f1e4, 2026-10-30; .dev/mn-59f1e4-review/fixture-ybbcr21k/review-results.txt
binding: sha256:24bd0ddecaa1bc47e23c26da55ddac8d89780d4807eae8837c318ab3d1daa890
---

# Handoff: Corrective: mn-59f1e4 failed independent acceptance — bind acceptance to the exact submission, verified release only, atomic lifecycle transitions with authority rechecked under the lock, action-vs-info nudge semantics, evidence-based current state

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-cf4d8d
```

## Scope

Corrective: mn-59f1e4 failed independent acceptance — bind acceptance to the exact submission, verified release only, atomic lifecycle transitions with authority rechecked under the lock, action-vs-info nudge semantics, evidence-based current state

## Inputs

- independent review of mn-59f1e4, 2026-10-30; .dev/mn-59f1e4-review/fixture-ybbcr21k/review-results.txt

## Work order

Corrective item for mn-59f1e4 (independent review 2026-10-30, fixture under .dev/mn-59f1e4-review/). Findings: (1) acceptance survived a changed submission: submit A → accept → correct → submit B → closable; bind each acceptance to the exact submission it reviewed and refuse closure until B's checks are accepted. (2) managed release treated coord 'stale' as death; only verified dead/stopped or an established, validated isolated checkout may release; unknown/old lease never seats a second writer. (3) attempt advancement, claim release and audit must be one locked transaction with grant validity, scope, expected owner and attempt revalidated inside it; cover revocation races, concurrent release/claim, interrupted writes, abandonment. (4) nudge semantics: informational drops are notices, action drops stay visible after ack (read, not finished) and remind at work boundaries until resolved; hook identity fix is mn-812cd9 (not duplicated here). (5) assess/doctor report observations with their source and time, label recorded claims as recorded, keep unknown explicit; doctor separates command availability, hook registration and verified end-to-end behaviour (--probe). Per the no-reopen rule this item cites mn-59f1e4 and stays open until the independent review accepts it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-cf4d8d`.
4. Commit with `Manna: mn-cf4d8d` and run `agent-do manna done mn-cf4d8d` only after the work is verified.

## Submission for independent review (2026-10-30, session claude-35dfcfc4870d4899)

Status: SUBMITTED. This item stays open until the independent review accepts it. The hook-identity half of finding 4 is mn-812cd9 (its own commit and closure); nothing here duplicates it.

### Finding 1: acceptance bound to the exact submission

`Submission.id` (`sub-<12 hex>`, minted on every `submit`), `Acceptance.submission` (the key the verdict was given on). `ManagedRecord::accepted_checks` counts an acceptance only for the same attempt, the pinned target, and the submission currently on the record; a pre-binding acceptance that names no submission never counts. `accept` refuses a submission in `correction_requested`. `assess` lists `superseded_acceptances` with the reason. Regression: integration M4 reproduces the reviewer's sequence (submit A → accept → correct → submit B) and proves neither worker nor coordinator can close B until B is accepted; unit tests `acceptance_binds_to_the_exact_submission`, `an_acceptance_that_names_no_submission_never_counts`.

### Finding 2: stale presence is not death

`managed release` reads coord with stale peers included (`peers --all`), and releases a held claim only on `dead`/`stopped` (`verified_gone`) or a validated `--isolated-checkout`: an existing directory, inside a git working tree, whose canonical toplevel differs from this checkout's; the toplevel is recorded as `isolation_toplevel`. `--worker-stopped` is removed. Integration M2 shows a stale lease on a live process refusing, an unknown peer refusing, a nonexistent path and this checkout refusing, a real `git worktree` succeeding, and a coord-verified `stop` releasing without isolation. `manna` now also matches coord's twelve-character `session-` labels, so a worker pinned through `AGENT_DO_COORD_SESSION` is found.

### Finding 3: atomic transitions, authority rechecked under the lock

New store primitives `release_claim_with` (sidecar pending phase + audit → row claim release → sidecar released marker, one lock) and `complete_issue_on_acceptance_with` (precondition → row write → audit, one lock). `coordinator_mutation` reloads grants and re-derives authority against the reloaded row for require/correct/accept; `close_managed`'s precondition re-derives authority, checks expected owner and attempt, blockers and digest under the lock; `abandon` on a managed item is the same two-phase transaction. `Release.claim_release` records `pending`/`released`; `release_interrupted` blocks every mutation and `assess` names the resume command; the coordinator's next `managed release` completes it without advancing the attempt again. Test seams: `MANNA_MANAGED_FAULT=after_release_pending` (exit after the pending phase), `MANNA_MANAGED_PAUSE_BEFORE_LOCK=<s>` (hold between preview and lock). Integration M5 covers the interrupted release and its resumption, a grant revoked under the lock after the accept's preview (refused with "no longer holds coordinator authority"), three rounds of concurrent release/claim with a coherent board each time, and worker abandonment; unit test `an_interrupted_release_blocks_until_resumed`.

### Finding 4: nudge semantics

Drops carry `kind`: `info` (default; a delivery; interrupt kind `notice`, never a router blocker; leaves a reader's interrupts on that reader's ack) and `action` (`drop add --action`; an obligation; interrupt kind `dependency`; stays listed after ack, `new: false`, `acknowledged: true`, summary names the resolve command; the router reminds at work-start prompts; resolved or superseded entries stop). A drop that answers a declared need stays a dependency. The generic doorbell is untouched. Tests: `test_coord_v2.test_drop_lifecycle` (action vs info, escalation by re-add), `test_v11_routing` identity scenario. Hook identity: mn-812cd9.

### Finding 5: evidence-based current state

`assess` reports `claimant` as `{status, source, observed_at, matched_agent, verified_gone, note}`, `integration_target.pinned_reference_now`/`pinned_reference_moved`, `superseded_acceptances`, and an `observations` block naming the git and coord reads' source and time and marking sidecar content as recorded claims. `managed doctor` separates `commands` (binary capability; coord `drop ack`/`resolve`/`--action`), `hooks` (registration only, with a note that registration is not firing), and `verified` (`ran: false` unless `--probe`); `live` is `null` without a probe and `true` only when the probe passed. `--probe` runs manna-core, agent-coord and the prompt-router hook in a throwaway fixture.

### Receipts (executed, not compiled-only)

- `cargo test --quiet --manifest-path tools/agent-manna/Cargo.toml`: 192 passed (lib), 52 passed (bin), 0 failed.
- `bash tools/agent-manna/test/integration.sh` (PATH=.venv/bin first): 508 passed, 0 failed. Managed sections M1–M5 all pass (M2 release semantics, M4 acceptance binding, M5 atomicity/races).
- `python3 tests/test_coord_v2.py`, `tests/test_coord.py`, `tests/test_v11_routing.py`, `tests/test_session_start_reads.py`, `tests/test_manna_estate.py`, `tests/test_manna_serve.py`: passed.
- `agent-do harness contracts validate`: 103/103, Errors 0, Warnings 0, Gate PASS. `contracts drift`: declared-but-unimplemented 0. `tests/test_contracts_gate.py`, `tests/test_contracts_drift.py`: passed. `bin/gen-tools-doc --check`: clean.
- `agent-do manna managed doctor --probe --json` on this machine: `live: true`, `verified.passed: true`; without `--probe`: `live: null`, verdict "not verified".
- Root `./test.sh`: see the line appended below.

### Environment notes, separated from product checks

- `tests/test_live.py` (`live runtime tests` in `./test.sh`) fails on this machine with `macOS frameworks not available` under the repo venv Python; it fails identically on the untouched tree and is unrelated.
- PATH `python3` (Homebrew 3.15) lacks PyYAML; every receipt above was taken with the repo venv first on PATH.
- Root `./test.sh` (PATH=.venv/bin first): 128 passed, 1 failed; the failure is `live runtime tests` (`tests/test_live.py`, `macOS frameworks not available`), identical on the untouched tree and unrelated to this item. Every other section, including the Manna integration suite inside it, passed.

## Pass 2: the three reproduced closure defects (2026-10-30, session claude-35dfcfc4870d4899)

Status: SUBMITTED again. The item stays open until the independent review accepts it.

### P1: approval could attach to a submission the coordinator never reviewed

`accept` now requires `--submission <id>` and `--attempt <n>` (both printed by `assess` as `submission_key` and `attempt`) and, under the lock after the record is reloaded, refuses when the current submission key or the attempt differs from what the caller reviewed. The reviewer's exact sequence is integration test M4b: acceptance for A started and held before the lock with `MANNA_MANAGED_PAUSE_BEFORE_LOCK`, B submitted meanwhile, acceptance resumed → exit 1, "you reviewed submission sub-…", nothing accepted, B not closable; the wrong attempt and the superseded submission are refused; naming B lands. The doctor probe passes the submission id and attempt it got from `submit --json`.

### P1: `done --assessment` could ignore a blocking assessment

The token now carries its verdict and conditions: `assess:v2:<requested sha|->:<pinned reference now|->:<hex>` only when closable, `blocked:v2:<hex>` otherwise (`managed::assessment_token`, `parse_assessment_token`, `closable_hex`). `done --assessment` refuses a `blocked:` token and any old or malformed format outright, and for a closable token recomputes under the lock: the pinned reference must still point where it pointed, a requested target must still be the pinned commit and resolve, and the row and acceptance state must reproduce the hex. Integration M4c is the reviewer's sequence: accept at the branch head, advance the branch, `assess --target <branch>` → `blocked:v2`, `done` with it → exit 2 "a blocked assessment never authorizes a close"; the earlier closable token → exit 2 "points at … now"; an old `assess:<hex>` token → exit 2; a fresh assessment under the current conditions closes. Unit tests `a_blocked_assessment_token_never_parses_as_closable`, `a_closable_token_binds_its_conditions`.

### P2: an audit failure still permitted a successful mutation

Every managed mutation is now a recoverable transaction (`managed::Intent`, `ManagedStore::run_transaction`): the intent (the record after, the grants after when they change, the audit line with a `txn` id) is written to `.manna/managed-intent.json` before the sidecar and the audit writes; after both land it is retired. A failure after the intent is durable returns a non-zero "transaction … did not complete" and leaves the item refusing every mutation (require, submit, correct, accept, release, abandon, done) and `assess` reporting `incomplete_transactions` with `next_action: manna managed recover <id>`. `manna managed recover <id>` (operator, a coordinator whose grant covers the item, or the session that started the transaction, matched by label and proof) applies the recorded outcome idempotently: the audit line is appended only if no line with that `txn` exists. The close's audit is a transaction too: its intent is durable before the row changes, so an unwritable audit leaves the close durable, reported as pending, and recoverable. Integration M6 makes `.manna/lifecycle.jsonl` unwritable (chmod 000): the acceptance fails and names the transaction, assess blocks and names recover, a second accept, a submit and a done are refused, a stranger cannot recover, the coordinator recovers, the audit line lands exactly once, the acceptance stands once, no intent remains; then the same for the close audit.

### Integration-suite discrepancy (the reviewer's early failure in Test 1b)

The reviewer's run (`.dev/mn-59f1e4-review/corrective-integration.log`, 13:15:59, after commits 1bb76c9/aab9ca7 at 13:04) failed in `Test 1b: kill-mid-init recovery`: the rerun `init` refused with ".handoff already contains non-workflow files", so `federation.yaml` was never written and the suite aborted (`set -e` on `git hash-object` of the missing file). That refusal comes from `workflow::validate_new_handoff_root`, which accepts an empty `.handoff` or exactly one entry, `README.md`; it fires only when a second entry exists in the fresh fixture's `.handoff`. On this machine the test passed in every full run (four runs today, now 539/539) and in three standalone reproductions of the kill-and-rerun sequence; every leftover crash fixture under `$TMPDIR` (eight of them) holds a lone `README.md`. I could not reproduce the second entry and do not know what wrote it. What would verify: `ls -la .handoff` in the reviewer's crash fixture (`CRASH_INIT_DIR` is a `mktemp -d` the suite never removes, so it still exists under their `TMPDIR`), or a rerun on their side with that listing captured when it fails. Nothing in this pass touches `init`, the handoff scaffold, or Test 1b.

### Receipts (executed)

- `cargo test --quiet --manifest-path tools/agent-manna/Cargo.toml`: 194 passed (lib), 52 passed (bin), 0 failed.
- `bash tools/agent-manna/test/integration.sh` (PATH=.venv/bin first): 539 passed, 0 failed (M1–M6 all pass).
- `python3 tests/test_coord_v2.py`, `tests/test_coord.py`, `tests/test_v11_routing.py`, `tests/test_session_start_reads.py`, `tests/test_manna_estate.py`, `tests/test_manna_serve.py`: passed.
- `agent-do harness contracts validate`: 103/103, Errors 0, Warnings 0, Gate PASS. `contracts drift`: 0 failing. `tests/test_contracts_gate.py`, `tests/test_contracts_drift.py`: passed. `bin/gen-tools-doc --check`: clean.
- `agent-do manna managed doctor --probe --json`: `live: true`, probe passed.
- Root `./test.sh`: see the line appended below.
- Root `./test.sh` (PATH=.venv/bin first): 128 passed, 1 failed; the failure is `live runtime tests` (`tests/test_live.py`, `macOS frameworks not available`), identical on the untouched tree and unrelated. Every other section, including the Manna integration suite inside it, passed.

## Pass 3: the two remaining transaction findings (2026-10-30, session claude-35dfcfc4870d4899)

Status: SUBMITTED again. The item stays open until the independent review accepts it. That review confirmed the acceptance-binding and assessment fixes; this pass covers the two transaction findings it still reproduced.

### Finding: an incomplete close returned success

`done` on a managed item whose row write landed but whose close audit transaction did not exited 0 with a warning. It now fails with exit 2 (`EXIT_SYSTEM_ERROR`) and prints `success: false`, the error naming the close transaction, the durable row (`status: done`), the dependents it released, `authority`, `transaction`, and `next_action: agent-do manna managed recover <id>` (`main.rs` `IncompleteCloseData` via `output_failure`; `managed_cli::ManagedClose::incomplete`). Integration M6 (extended) is the reviewer's sequence: `.manna/lifecycle.jsonl` unwritable, `done` → exit 2, `success: false`, `status: done` reported, `show` confirms the row is done, `assess` reports one incomplete transaction with action `close` and names recover, recover lands the close audit line exactly once, no intent remains.

### Finding: board-level grant/revoke recovery did not work

`manna managed recover board` resolved `board` as an issue id and answered "Issue board not found", so a grant or revocation whose writes did not both land (`issue_id: board` in `.manna/managed-intent.json`) could never be finished. Now: `managed::BOARD_SCOPE`; `recover board` applies the recorded grants file and audit line idempotently (operator, or the session that started it; a coordinator is refused with exit 2 because its own authority is what the transaction decides). `ManagedStore::incomplete_transaction(id)` also answers for a pending board transaction, so every managed mutation (require, submit, correct, accept, release, abandon, done) and every further `coordinator grant`/`revoke` refuse naming `recover board`; a coordinator-only item `recover` waits on it too (the operator and the starting session do not). `assess` lists board transactions with `scope: board` and `next_action: operator: agent-do manna managed recover board`. New store methods `pending_intents_affecting`, `begin_transaction`, `finish_transaction`; fault seam `MANNA_MANAGED_FAULT=after_board_intent` (a revocation dies after its intent is durable, before the grants file or the audit is written). Integration M7 is the reviewer's sequence and its revoke counterpart: a second grant with an unwritable audit → exit 1 naming `recover board`, intent `board:grant`, grants file holds the grant (state landed, audit not); accept, submit, require, grant and revoke all refuse naming it; assess `1/board/False/operator: … recover board`; coordinator and stranger `recover board` → exit 2; item recover reports nothing pending on the item and the board transaction beside it; operator `recover board` → 1 recovered, the grant's audit line lands once, no intent remains, the acceptance then lands. Then a revocation killed through the seam (exit 70): the grants file still shows the grant live, the coordinator's `managed correct` is refused naming `recover board` (not the stale file), the operator recovers → revocation landed, audit line once, the coordinator holds no authority (exit 2). Unit tests: `a_pending_board_transaction_holds_every_item_and_names_board_recovery`, `recovering_the_board_lands_the_grants_and_the_audit_exactly_once`, `a_pending_revocation_whose_state_did_not_land_is_still_a_pending_revocation`.

### Integration-suite discrepancy: explained, filed separately

The reviewer's evidence (`.dev/mn-59f1e4-review/pass2-init-fixture-evidence.json`) shows the fresh fixture's `.handoff` holding `.README.md.87331.1793384159562101000.tmp` beside `README.md`. That is the temp `workflow::atomic_write` creates (`.{name}.{pid}.{nanos}.tmp`) before its rename or hard-link install, left behind when `init` is killed in that window; `workflow::validate_new_handoff_root` accepts only an empty `.handoff` or a lone `README.md`, so the rerun refuses and init recovery never completes. Filed as mn-bf448b (track mn-b7a0cc) with the fix shape and the regression tests it needs; nothing in this pass touches `init`. On this machine the full suite completed 572/572 once this pass; two earlier runs this pass aborted inside the new M7 test on test-harness mistakes (pty output capture, a serde-omitted field), not on product behaviour, and Test 1b passed in all three.

### Receipts (executed)

- Commit `36a3cb6` (`Manna: mn-cf4d8d`): source, tests, README, SCHEMA, ARCHITECTURE, CLAUDE.md, CHANGELOG, registry, docs/TOOLS.md.
- `cargo test --release` (tools/agent-manna): 197 passed (lib), 52 passed (bin), 0 failed.
- `bash tools/agent-manna/test/integration.sh` (PATH=.venv/bin first): 572 passed, 0 failed (M1–M7).
- `python3 tests/test_coord_v2.py`, `test_coord.py`, `test_v11_routing.py`, `test_session_start_reads.py`, `test_manna_estate.py`, `test_manna_serve.py`, `test_contracts_gate.py`, `test_contracts_drift.py`: passed.
- `agent-do harness contracts validate`: Gate PASS, Errors 0. `contracts drift`: 0 failing. `bin/gen-tools-doc --check`: clean.
- `agent-do manna managed doctor --probe --json`: `live: true`.
- Root `./test.sh` (PATH=.venv/bin first): 128 passed, 1 failed. The failure is `live runtime tests` (`tests/test_live.py:139`, expected the macOS live gate, got `macOS frameworks not available`): the same environment failure as pass 2, identical on the untouched tree. Every product check passed.
- `manna lint`: presentation drift only (numbered rename held on this live claim; `.handoff/README.md` index drift from another lane's uncommitted sync churn); no refusals.

## Pass 4: recovery authorized under the board lock (2026-11-02, session claude-35dfcfc4870d4899)

Status: SUBMITTED again. The item stays open until the independent review accepts it. That review passed 249 Rust tests and 572 integration checks on pass 3 and reproduced one remaining defect (`.dev/mn-59f1e4-review/pass3-0nw3470j/recovery-race-result.txt`): `cmd_recover` resolved coordinator authority from the grants file before taking the board lock, so a grant revoked while recovery waited for the lock still recovered (`"success":true` with `grant-295a3650d380`, revoked `2026-10-31T00:30:00Z`, and `Current authority: none` afterwards).

### Finding: recovery authorized before the lock

`managed_cli::cmd_recover` and `recover_board` now make every deciding check under the board lock against freshly loaded state (`MannaStore::with_locked_issue` for an item, `with_board_lock` for the board): the pending intents for the target, the board's own pending transaction, the grants file, and the row are all read inside the lock; `Authority::resolve` and the transaction-ownership check (`actor` and `actor_proof` equal to the caller's) run on those; and only then does recovery replay. The replay is `ManagedStore::recover_intents(&pending)`, which finishes exactly the list the lock-held look authorized and refuses a transaction that is no longer pending rather than replaying the caller's copy (`recover(id)` is now a thin wrapper over it). The outcome of the locked look is a `Recovery` enum (nothing pending / refused / finished) resolved after the lock drops into the same outputs as before: `note: no incomplete transaction` with `board`, exit 2 (`EXIT_NEEDS_AUTHORIZATION`) for a refusal, the recovered list with `managed` and `authority` on success. The refusal now reads "level under the lock: <level>; a grant that was live before the lock and is revoked now does not carry forward". Preserved: the operator recovers anything; the session that started a transaction recovers it with or without a grant; `recover board` stays operator-or-starter and refuses a coordinator. `pause_before_lock()` (the `MANNA_MANAGED_PAUSE_BEFORE_LOCK` seam) now also covers both recover paths. Nothing else changed: no new verb, no registry change, no schema change (`docs/TOOLS.md` and `registry.yaml` untouched).

### Regression tests for the exact sequence

Integration **M8** (22 checks) is the reviewer's race, synchronized on the grant read itself so the outcome never depends on scheduling: the worker's submission is left pending (audit unwritable, as in the reviewer's fixture); the grants file is replaced by a FIFO, so the fixture knows the moment recovery reads it, whatever recovery did first. A recovery that reads before its lock finds the lock free: the fixture takes it, serves the live grant, puts the revoked grant on disk under the lock, and lets go, and such a recovery recovers on obsolete permission (the pass-3 binary does exactly this: `read-before-lock`, exit 0, intent retired, audit written). A recovery that reads under its lock leaves the fixture refused the lock (`LOCK_NB`) and is served the revoked grant, the grants as they are at lock time. A fixture that holds the board lock from the start cannot expose this defect: `load_board_workflow` runs the federation transaction recovery under the board lock before anything managed is read, so the pass-3 binary stalls there and reads the grants only after the revocation (my first M8 draft passed on both binaries for that reason and was replaced). The test asserts the fixture saw `read-under-lock`, recovery exits 2 naming the authority as it stands under the lock; the sidecar, audit, and intent file are byte-identical before and after (one digest over all three); the transaction is still pending; no audit line was written; the revoked coordinator stays refused with the lock free; the operator recovers it (`1/<txn>/operator`), the audit line lands exactly once, no intent remains; a stranger is refused and the session that started the next pending transaction recovers it without a grant (`1/<txn>/owner`). Then the board-pending check under the lock: with a fresh grant, recovery holds before the lock (pause seam) while a revocation of that grant dies with its intent durable (`MANNA_MANAGED_FAULT=after_board_intent`, exit 70); recovery finds the board pending under the lock and is refused naming `recover board`, the item's transaction stays pending, no item audit line is written; the operator recovers the board, the coordinator holds nothing and stays refused, the starting session finishes the item's transaction. Unit test `recovery_replays_only_the_transactions_it_authorized` (managed.rs): two pending intents, replaying one finishes only that one, replaying its stale copy is refused with nothing doubled, the remaining one still recovers.

### Receipts (executed, pass 4)

- `cargo test --release` (tools/agent-manna): 198 passed (lib, one new), 52 passed (bin), 0 failed.
- Standalone probe of the race (`.dev`-free, scratch fixtures, both binaries): pass-3 binary `read-before-lock`, exit 0, intent retired, audit written, `success: true` with the revoked grant (the reviewer's result reproduced); this pass's binary `read-under-lock`, exit 2, sidecar/audit/intent byte-identical, intent still pending.
- The rewritten suite run in a detached worktree of `36a3cb6` (pass-3 source, its own build): 580 passed, 14 failed, every failure in M8 and nothing else (the seven under-lock checks of the revocation race, the operator-recovers check that the defect pre-empted, and the six checks of the board-pending race). Four of the seven old-source runs needed to reach M8 were spent on test-harness hardening (a `cat` over the retired intent file under `pipefail`, `recovered[0]` on an empty list, a missing `authority` key on the defective path) and on the separate init defect mn-bf448b, which killed two of them in Test 1b; none of those touched product code.
- `python3 tests/test_coord_v2.py`, `test_coord.py`, `test_v11_routing.py`, `test_session_start_reads.py`, `test_manna_estate.py`, `test_manna_serve.py`, `test_contracts_gate.py`, `test_contracts_drift.py`: passed.
- `agent-do harness contracts validate`: Gate PASS, Errors 0. `contracts drift`: 0 failing. `bin/gen-tools-doc --check`: clean (registry and docs/TOOLS.md unchanged).
- `agent-do manna managed doctor --probe --json`: `live: true`.
- Root `./test.sh` (PATH=.venv/bin first): 128 passed, 1 failed. The failure is `live runtime tests` (`tests/test_live.py:139`, expected the macOS live gate, got `macOS frameworks not available`, code 6): the same environment failure as passes 2 and 3, identical on the untouched tree. Inside it, `manna unit tests`, `manna integration tests`, and `manna release binary is current` passed.
- `bash tools/agent-manna/test/integration.sh` (PATH=.venv/bin first) on this pass's binary with the final test file: 594 passed, 0 failed (M1–M8; the 22 M8 checks included). Earlier full runs this pass: 594/0 twice more on the same source with earlier drafts of M8.
