---
workflow: 2
manna: mn-cf4d8d
track: mn-b7a0cc
source: independent review of mn-59f1e4, 2026-10-30; .dev/mn-59f1e4-review/fixture-ybbcr21k/review-results.txt
base_commit: ed20b7344e7d50fd4d442f1b34489668625c4ba6
scope: 'Corrective: mn-59f1e4 failed independent acceptance — bind acceptance to the exact submission, verified release only, atomic lifecycle transitions with authority rechecked under the lock, action-vs-info nudge semantics, evidence-based current state'
inputs:
- independent review of mn-59f1e4, 2026-10-30; .dev/mn-59f1e4-review/fixture-ybbcr21k/review-results.txt
binding: sha256:94a9f339e38b98ad620aa8044db68c33a53ffbf1e3a0d925ded46fac73282049
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
