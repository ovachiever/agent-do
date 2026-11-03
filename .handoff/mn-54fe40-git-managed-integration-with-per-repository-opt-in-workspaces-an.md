---
workflow: 2
manna: mn-54fe40
track: mn-b7a0cc
source: 'Erik conversation 2026-11-03: Managed Integration, reusable agent-do capability with one-repository pilot'
base_commit: 4227aed0a551631cf4acecb03b1b839565777862
scope: 'Git: Managed Integration with per-repository opt-in workspaces and durable automatic landing'
inputs:
- 'Erik conversation 2026-11-03: Managed Integration, reusable agent-do capability with one-repository pilot'
binding: sha256:de47caf42efa015c76d67366f6e38da5a7d089ad53d40bef6f78163900ced0ed
---

# Handoff: Git: Managed Integration with per-repository opt-in workspaces and durable automatic landing

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-54fe40
```

## Scope

Git: Managed Integration with per-repository opt-in workspaces and durable automatic landing

## Inputs

- Erik conversation 2026-11-03: Managed Integration, reusable agent-do capability with one-repository pilot

## Work order

Outcome
Build reusable Managed Integration in agent-do, primarily extending agent-do git, using Manna for assignment/submission/acceptance and Coord for targeted obligations. Erik dispatches work normally; work remains discoverable and ready submissions integrate without manual branch shepherding. One owner delivers the complete path with internal checkpoints, not separate planning lanes.

Scope
1. Per-repository opt-in configuration. Missing/disabled configuration preserves existing workflow; invalid configuration refuses managed operations. Disable stops new dispatch and automatic landing but retains status, recovery, pending submissions and worktrees. Use approved canonical configuration, never a worker branch policy as integration authority. Final command/schema names follow existing patterns and applicable approval rules.
2. Register one workspace/branch per assignment attempt, with canonical repository/board identity, source base, exact worker binding and recovery metadata. Replacement sessions inherit work. Resolve canonical Manna access explicitly: worktrees currently have divergent board copies. Do not merge worker board copies into canonical state.
3. Durable submission queue pins source commit, submission ID, attempt and verification evidence. A commit saves progress; submission requests integration; done records closure. Do not auto-land every commit or hide merging inside done.
4. One integrator per repository builds a candidate against current target and validates that exact combined result. Advance only against the unchanged tested base; otherwise rebuild/revalidate. Preserve dirty primary checkouts and other checked-out worktrees. Define safe Git ref/index/worktree handling before implementing landing. Record original submission and integrated SHA provenance.
5. Recover crashes idempotently, including after Git advances but before queue/board receipt completes. Preserve original refs and pending work. Fail closed on stale acceptance, revoked authority, changed configuration and inconsistent state. No duplicate landing or false clean success.
6. Route conflicts/check failures through assignment-targeted action drops; unavailable workers remain explicitly pending for authorized reassignment. Keep coherent status: building, queued, integrating, landed or blocked, with evidence and reason. Reuse existing CLI/board surfaces.
7. Same deliberate-commit/snapshot workflow across Codex and Claude. Document enforcement boundaries honestly: local hooks alone do not prevent arbitrary filesystem/ref writes. Do not rewrite machine-wide runtime policies without explicit adoption authority. Separate workspaces do not isolate shared databases, ports, build caches or installed applications; identify required resource isolation.

Delivery checkpoints
A. Inspect current git, managed lifecycle and targeting implementation (including 0342d6b), applicable AGENTS, manifests and contracts. Confirm targeting acceptance status; do not silently treat source presence as reviewed. Produce a compact code-backed design covering canonical board, transaction recovery, config trust, main checkout safety and integration authority. Surface consequential unresolved decisions before coding; avoid a separate planning program.
B. Implement general capability and deterministic isolated CLI fixtures. Reuse existing validation commands, no new dashboard or scheduled AI supervisor. Execute meaningful tests for opt-in/off/invalid config, canonical board across worktrees, two competing submissions, stale base, conflicts, failed checks, dirty target checkout, worker disappearance/replacement, authority/config change, and interruption before/after ref update. Verify replay does not duplicate integration and branches remain recoverable.
C. After independent review and explicit repository/authority selection, enable a bounded live pilot in one repository with two real assignments. Show automatic integration without Erik switching branches or relaying messages, and demonstrate recovery. Broader rollout is configuration, not a repository-specific rewrite. Local fixture success is not live-pilot completion.

Boundaries
Creating this item authorizes implementation preparation, not live activation or automatic main updates. Obtain explicit approval for the selected pilot repository and local integration authority before enabling it. No push, PR, deployment, app installation, bulk branch migration/cleanup, automatic branch/worktree deletion, automatic idle-session revival, or estate-wide rollout. Preserve foreign edits. No paid-service credential access or metered jobs without explicit provider/service, purpose and maximum total spend approval including retries. Prefer deterministic queue automation; no paid review loop.

Acceptance and return
Commit coherent verified implementation with this item trailer, document commands/config/contracts and executed receipts. Return SUBMITTED for independent review; do not self-certify acceptance. Report implementation, independent acceptance and live activation separately. If pilot authorization is pending, state that plainly rather than declare the complete goal achieved. Keep all pending work discoverable with an owner or explicit disposition; do not promise every branch must merge. Retain snapshots as recovery material, not integration evidence.

Related work
mn-cf4d8d managed closure/recovery; mn-59f1e4 coordinator lifecycle; assignment targeting commit 0342d6b. Separate init defect mn-bf448b is not part of this assignment.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-54fe40`.
4. Commit with `Manna: mn-54fe40`, return SUBMITTED for independent review, and leave this item open. Independent acceptance and authorized live-pilot receipts are required before reviewer closure.

## Delivery receipts (2026-11-03, worker claude-ccc4d8f0e9ed4447, SUBMITTED for independent review)

Status: implementation and fixtures delivered (checkpoints A and B). Independent acceptance: not self-certified; pending the reviewer. Live pilot (checkpoint C): not activated; no repository has `agent-do.integration.enabled` set, and enabling one needs Erik's explicit choice of repository and local integration authority (`agent-do git integration enable ... --authorized-by <who>`).

Code commit: `90f49ca4db952c30d67265e35e5c38af8db4834f` (`Manna: mn-54fe40`).

### What landed

- `lib/git_integration.py` (new): the engine behind `agent-do git integration enable|disable|config|workspace add|workspace list|submit|run|recover|status`.
- `tools/agent-git`: the `integration` verb, help text, examples.
- `tests/test_git_integration.py` (new, registered in `test.sh`): eleven isolated estates with real boards, pinned identities and killable coord anchors.
- `tools/agent-manna/src/managed.rs`: defect found by the fixtures and fixed here: sidecar files (`managed.json`, `coordinators.json`, `managed-intent.json`) were written with `"version": 0` by the derived `Default` while the serde read default and coord's `_item_attempt` expect 1, so `coord drop add --for-item` refused every item on a freshly managed board ("cannot verify assignment attempt"). Manual `Default` impls with `SIDECAR_VERSION = 1`, `load_*` reads a 0 as 1 so the next save upgrades the file, regression test `a_fresh_sidecar_carries_version_one_and_a_zero_on_disk_reads_as_one`.
- `registry.yaml` (commands, contracts, capabilities, examples), `docs/TOOLS.md` (regenerated), `docs/MANAGED-INTEGRATION.md` (new: design, commands, lifecycle, enforcement boundaries, resource isolation, pilot procedure, receipts), `ARCHITECTURE.md` (section), `CHANGELOG.md`, `CLAUDE.md`.

### Design decisions (checkpoint A), recorded in zpc

- dec-17b5f2: policy lives in the common git dir's config (`[agent-do "integration"]`), never a tracked file; shared by every worktree (verified), unreachable from a branch.
- dec-c3de25: a landing is `git merge --ff-only` inside the checkout holding the target (git's own guard preserves non-overlapping dirty files and refuses overlaps; probed 2026-11-03) or a compare-and-swap `update-ref` when nothing holds it; never `update-ref` under a checkout (probe: phantom staged changes).
- dec-a7e7fe: every manna and coord call runs at the common git dir's checkout (coord's own `canonical_board_root` rule); manna's rooting and coord's per-git-dir store are unchanged (two live coord items); worker board copies are never written; board-owned paths in a submission are refused.
- pos-b008a0: write-ahead `intent.json` plus pinned `refs/integration/candidates/<entry>` lets recovery decide by `merge-base --is-ancestor`; falsifier is a duplicate landing or a lost candidate in the fixtures (none observed).
- Surfaced, not decided here: coord stores state per git dir, so a session whose hooks read a worktree store sees obligations through `integration status`, not the doorbell (documented); coord tolerating version-0 sidecars already on disk on other boards would need a coord change (manna now upgrades them on its next write).

### Executed validation (all exit 0 unless stated)

- `python3 tests/test_git_integration.py`: 11/11 scenarios, end to end in one run (opt-in off/enabled/invalid/disabled; canonical board from inside a worktree whose copy predates the claim; board paths refused; submit + fast-forward landing in the holder + receipts + info drop + replay no-op; competing submissions superseded and stale base rebuilt with both SHAs recorded; conflict blocks with files, one action drop, no duplicate on rerun, resubmission lands; failed checks with the log; dirty target checkout preserved / overlapping blocks and retries; interruption after intent and after ref update land exactly once, moved target voids and rebuilds; disabled retains, changed target and removed authority fail closed, reassignment and closure not forwarded; managed worker dies, coord-verified `managed release`, replacement inherits on attempt 2, lands, coordinator accepts at the integrated SHA and closes; one integrator per repository).
- `cargo test` (tools/agent-manna): 199 + 52 passed, 0 failed (includes the new regression).
- `bash tools/agent-manna/test/integration.sh` with the venv Python on PATH: 594 passed, 0 failed (an earlier run without the venv on PATH failed 4 YAML-parsing checks on `ModuleNotFoundError: yaml`, an environment fact, not a regression).
- `python3 tests/test_coord_v2.py`, `tests/test_manna_serve.py`, `tests/test_manna_estate.py` against the rebuilt binary: coord v2 tests passed; manna serve 51 tests OK; manna estate 6 tests OK.
- `agent-do harness contracts validate`: Gate PASS, 0 errors, 0 warnings. `agent-do harness contracts drift`: 0 failing. `bin/gen-tools-doc --check`: in sync. `tests/test_contracts_gate.py`, `test_contracts_drift.py`, `test_routing_contracts.py`, `test_bounds_gate.py`, `test_git_guardrails.py`, `test_index_generation.sh`: passed.
- Not run: the full `./test.sh` (focused suites only, per the lane rules); no app launches, installs, pushes or PRs.

### Remaining acceptance and open dispositions

- Independent review of this submission (the reviewer closes; this worker does not self-certify).
- Pilot authorization: repository and local integration authority named by Erik; then `enable`, two real assignments, one demonstrated recovery, per docs/MANAGED-INTEGRATION.md "Enabling a pilot".
- `.manna/issues.jsonl` carries this claim and the seal digest in the working tree beside other lanes' uncommitted rows; it is left for the operator's board commit rather than swept into this lane's commits.

## Delivery receipts, round two (2026-11-03, worker claude-ccc4d8f0e9ed4447, SUBMITTED for independent review)

Independent review (`.dev/independent-integration-review/review.md`, probes in `probe.py`/`probe.log`) reproduced three acceptance blockers against 90f49ca and named three source concerns. All are fixed in `ba76f34f4bf88c81e676d3e6d78cd599aae3a0da` (`Manna: mn-54fe40`). Status unchanged: implementation and fixtures delivered; independent acceptance pending the reviewer; live pilot (checkpoint C) not activated and not authorized.

### Dispositions

1. Policy changed while the checks ran (reproduced): fixed. The integrator compares the full policy digest after the checks (`lib/git_integration.py`, `Integrator.integrate`): a changed policy is adopted once and the candidate rebuilt and revalidated under it (both passes' check logs kept, `revalidations` recorded with both digests); a policy that moves again during that revalidation blocks `config_changed` (retryable). The reviewer's probe (check rewrites the check list to `false`) now revalidates under `false`, fails, blocks `checks_failed`, and the target does not move. Fixture `test_policy_changes_during_checks` (three sub-cases: rewritten to `false`; edited once, adopted and landed with equal tested and landing digests; moving twice, blocked then landed once settled).
2. Recovery bypassed the new policy (reproduced): fixed. The intent now records the tested policy digest, the worker binding, attempt, submission id, check results and tree verification (`Integrator.land`); `Integrator.recover` voids and requeues on a changed digest (or an intent that predates digests), voids and blocks on a moved assignment, and finishes the record (never a second landing) when the ref already moved, stating a policy change since the test in that record. Fixture `test_recovery_revalidates_policy_and_assignment` (four sub-cases: policy changed before the ref update; claim moved before the ref update; policy changed after the ref update; legacy intent).
3. Tested tree differed from the landed commit (reproduced): fixed. `Integrator.verify_candidate` runs after the checks: HEAD at the candidate and detached, index and tracked files identical by content (`git diff --cached --quiet`, `git diff --quiet`); a changed tree blocks `candidate_changed` (worker obligation) with `candidate-drift.patch`; the original candidate stays pinned; untracked build output is reported and allowed. Fixture `test_candidate_tree_integrity` (repaired, committed, staged, untracked).
4. Assignment freshness (source concern): fixed. `staleness` is re-read immediately before the ref update and in recovery before a re-landing. Fixture `test_assignment_rechecked_before_landing` (the check itself moves the claim; blocked `reassigned`, nothing landed). The remaining window is the instant between that read and the ref write; for managed items manna's `accept --submission --attempt` is the closing gate (documented).
5. Intent removed before queue, receipt, audit (source concern): fixed. `Integrator.complete` writes the queue row, then the receipt, the routing record, the audit line, and retires the intent last; a crash in the tail is finished by `recover` with one info drop and one audit line (`landed_tail_recovered`). Seam `AGENT_GIT_INTEGRATION_FAULT=after_landed_row`. Fixture `test_landing_tail_recovery`.
6. Candidate worktree adopted without ownership (source concern): fixed. The integrator writes `agent-do-integration-candidate` into the worktree's private git dir when it creates the tree (recorded in `candidate.json`); a detached worktree at the candidate path without the marker is refused (exit 1, `candidate_path` named) and left untouched. Fixture `test_candidate_ownership`.
7. Beyond the review's list, from the security note routed to this item (`.dev/mn-88d1ac/security-note-git-integration.md`, drop drp-d480dce9fbb4, stale for this revision): checks run the candidate's own scripts, so the integrator's identity (`MANNA_SESSION_*`, `MANNA_OPERATOR`, `CLAUDE_*`/`CODEX_*` ids, coord anchors) and every credential-shaped variable are withheld, `MANNA_OPERATOR=0` set, withheld names logged and values never. Fixture `test_check_environment`. Withholding, not sandboxing; the doc says so.
8. Found by the new fixtures and fixed with them: the candidate reset ran `checkout --detach` before `reset --hard`, so a tree a check had dirtied refused every later build; the reset now discards first.

### Executed validation (all exit 0 unless stated)

- `python3 tests/test_git_integration.py` (the registered command, one run): 18/18 scenarios, 98 s; the eleven round-one scenarios unchanged.
- The seven round-two scenarios against an archived copy of 47929e1 (`git archive`, same manna binary): every one exits 1. Six fail on the behavior the review reproduced (the reviewed engine lands: policy rewritten during checks; policy changed in recovery, `recovered: true`; repaired tree; foreign candidate tree; claim moved during checks; and the check sees the integrator's secrets, so the environment probe fails its checks). `test_landing_tail_recovery` fails there because the reviewed `complete` has no point where the row is durable while the intent exists (it removed the intent first), which is the defect.
- `agent-do harness contracts validate`: Gate PASS, 0 errors, 0 warnings. `agent-do harness contracts drift`: 0 failing. `bin/gen-tools-doc --check`: exit 0. `tests/test_git_guardrails.py`, `tests/test_contracts_gate.py`, `tests/test_bounds_gate.py` (41 tests): passed.
- Not run this round: the manna Rust suites and the coord suites (no change to `tools/agent-manna` or `tools/agent-coord` in this commit); the full `./test.sh`; no app launches, installs, pushes or PRs. The registry is unchanged (no new verbs).

### Remaining acceptance and open dispositions

- Independent review of this round (the reviewer closes; this worker does not self-certify). The reviewer's fixtures under `.dev/independent-integration-review/fixtures/` are untouched.
- Pilot authorization unchanged: repository and local integration authority named by Erik, then `enable`, two real assignments, one demonstrated recovery.
- `.manna/issues.jsonl` carries this claim and the new seal digest beside other lanes' uncommitted rows; left for the operator's board commit, as in round one.
- The wake-contract branch (mn-88d1ac, be27371) is not merged or rebased by this lane; main advanced by two more commits.
