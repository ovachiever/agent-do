---
workflow: 2
manna: mn-dd9be1
track: mn-b7a0cc
source: 'mn-88d1ac session 2026-11-03: coord peers --all --json showed session-3f2a6552e3b9 dead with a fresh needs-user pulse; agents.json pid 31111 absent, pid_start empty'
base_commit: 9776e7d1dc08f601fa737f9eed91fdcccd1f99e9
scope: 'coord: a live session reads dead when its anchor pid was transient (empty pid_start)'
inputs:
- 'mn-88d1ac session 2026-11-03: coord peers --all --json showed session-3f2a6552e3b9 dead with a fresh needs-user pulse; agents.json pid 31111 absent, pid_start empty'
binding: sha256:28f02434737394d7090015c3595ca1f6266a3e423ffb586ea62996f9864ad59e
---

# Handoff: coord: a live session reads dead when its anchor pid was transient (empty pid_start)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-dd9be1
```

## Scope

coord: a live session reads dead when its anchor pid was transient (empty pid_start)

## Inputs

- mn-88d1ac session 2026-11-03: coord peers --all --json showed session-3f2a6552e3b9 dead with a fresh needs-user pulse; agents.json pid 31111 absent, pid_start empty

## Work order

Observed 2026-11-03 17:31Z on the agent-do board: session-3f2a6552e3b9 (the mn-e6e1a8 worker, a live Claude Code session whose pulse row showed needs-user seconds earlier and which was editing tools/agent-coord) was classified dead by coord peers. Its agents.json record carried pid 31111 with pid_start '' and that pid no longer existed, so process_liveness returned False and classify_presence returned dead. find_anchor_pid had anchored the identity to a process that was already gone or short-lived when ps lstart ran, and register_self kept that pid on every later touch.

Consequences: a dead verdict hides a live writer from peers --active-only, lets another session's claim or territory look uncontended, drops the session's bell (dead targets never ring), makes an item-addressed drop read pending instead of resolved, and under the coord-wake/1 contract (mn-88d1ac) would make a host consumer's held request lapse while the host is alive.

Fix direction: when pid_start is empty or the recorded pid is gone while the session's pulse row is fresh, do not call it dead; re-anchor on the next register_self (the pulse hook payload names the live harness session), or fall back to the lease plus pulse recency and say unverifiable. Add a regression that registers with a transient anchor pid and asserts the peer is not dead while its pulse is fresh. Evidence: .git/agent-do/coord/agents.json record for session-3f2a6552e3b9 at 17:40Z; coord peers --all --json output in the mn-88d1ac session report.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-dd9be1`.
4. Commit with `Manna: mn-dd9be1` and run `agent-do manna done mn-dd9be1` only after the work is verified.

## Delivery receipts (2026-11-04, worker claude-833d4f4ab80a40cc; SUBMITTED for independent review, not self-closed)

### Reproduced

- Live board, this lane: between tool calls its record read `pid 48897`, then `2478`, then `64096`, each with `pid_start ''` and each gone by the next read, while `coord whoami` from a foreground tool-call shell anchored to the `claude` runtime (pid 38445, started 09:54:14, `comm /opt/homebrew/bin/claude`). The writer between calls is the pulse hook (`hooks/claude/agent-do-pulse-record.sh`): it runs `coord pulse record --from-hook` in a subshell that is backgrounded and disowned, and exits first. `record_pulse` calls `register_self`, so the orphaned call rewrote the anchor. mn-880173's receipts hold the consequence: the mn-9b4359 lane's SessionEnd reconcile at 18:55:38Z read this lane dead (`session-833d4f4ab80a dead (bound by claim proof)`) and released its claim.
- Cause in code: `find_anchor_pid` walks `ps -axo pid,ppid,comm` from the coord process; an orphaned process's chain ends at pid 1 before any runtime name, so it fell back to `os.getsid(0)`, the hook shell, alive for milliseconds; `ps_lstart` of that pid returned nothing, `register_self` wrote pid and empty start unconditionally, and `process_liveness` read a missing pid as death, start time or not.
- Fixture reproduction (`tests/test_coord_anchor.py`): an orphaned `whoami` under a fresh identity reports `anchor: session-leader`, `anchor_verified: false`; with the old rule that record read dead from any other process.
- Board measurement before the change: 38 ended sessions carried a known start time and a gone pid (genuine death), nine live ones were anchored to long-lived shared processes (tmux, launchd) by the fallback, and the only empty-start record was this live lane.

### What landed (bff2e9b, `Manna: mn-dd9be1`)

- `tools/agent-coord`: `find_anchor` returns `(pid, kind)` with kinds `runtime`, `session-leader`, `parent`; `process_anchor` adds `explicit` for `AGENT_DO_COORD_PID` and records `anchor` and `anchor_verified` (durable kind with a known start time). `process_liveness` answers None for an unverified anchor or an empty start time and proves death only through a verified anchor (missing pid, or a start time that no longer matches). `register_self` never replaces a verified anchor with an unverified registration; the owning session's next foreground call repairs the record. `_tombstone_superseded` tombstones a pane's previous occupant only on a verified exit. `peers --json` rows carry `anchor` (kind, verified, liveness `alive`/`gone`/`unverifiable`); `peers` text marks `liveness:unverifiable`; `whoami` reports `anchor` and `anchor_verified`; help updated.
- `tests/test_coord_anchor.py` (registered in `test.sh`): a runtime process stands for the Claude Code process and runs the lane's shells as its children. Scenarios: the Claude case (foreground registration anchors to the runtime; an orphaned pulse registration refreshes presence and the pulse row but never downgrades the anchor; another session reads the lane active; the SessionEnd call `--fix --only dead_claim,blocker_desync --write-drift` and the full `--fix` both keep the lane's claim; the Manna binding is preserved; then the runtime ends, peers read dead with verdict `gone`, and the SessionEnd call releases the claim with nothing marked done); first contact from an orphan (unverified record reads active, idle after the lease, stale after the idle window, never dead; its claim survives the SessionEnd call; a foreground touch repairs the anchor to the runtime and binds the proof); process-reuse protection (explicit pin with a different start time reads dead); `stop` reads stopped; legacy records (gone pid with empty start reads idle and unverifiable; gone pid with a known start reads dead).
- Docs: CLAUDE.md (agent-coord row), ARCHITECTURE.md (identity anchoring and liveness classification), CHANGELOG.md.
- Not changed: the hooks (the fix is at the source, so every orphaned caller gets the same verdict), manna (`liveness.rs` reads coord's status as before; the new `anchor` field is extra data it ignores), the identity rules, the store layout (two new fields on the record).

### Policies decided

- dec-fa14fe: an anchor coord cannot verify is unknown, never death; the lease decides, and a weaker registration never overwrites a stronger one on the same identity. Interactive shells without a runtime ancestor (the `session-leader` fallback) therefore age out as stale and are pruned at the prune window instead of reading dead when the terminal closes; `stop` still retires them at once.
- Genuine detection preserved: a verified runtime that is gone reads dead; a pinned pid whose start time differs reads dead; `stop` reads stopped; legacy records with a known start time keep the process check. les-5f2425.

### Executed validation (venv Python on PATH; everything executed)

- `tests/test_coord_anchor.py`: six checks across five scenarios passed. `tests/test_coord.py` and `tests/test_coord_v2.py` passed. `tests/test_manna_reconcile_liveness.py` 12/12; `tests/test_manna_reconcile_track_gate.py` 4/4; `tests/test_git_integration.py` passed; `tests/test_manna_serve.py` 57 OK; `tools/agent-manna/test/integration.sh` 741 passed, 0 failed; `agent-do harness contracts validate` 0 errors, 0 warnings; `contracts drift` 0 failing.
- Live, after the change (the repo file is the deployed coord): this lane's record read `pid 38445`, `anchor runtime`, `anchor_verified true` after every pulse hook that fired during the rest of the lane, where before the change each pulse had rewritten it to an exited shell's pid.
- Not run: the full `./test.sh`. No live claim cleanup, installs, pushes, pull requests, or worker launches.
- zpc: les-5f2425 (lesson), dec-fa14fe (decision).

### Remaining acceptance

- SUBMITTED: in_progress under claude-833d4f4ab80a40cc, not self-closed. Review points: the anchor kinds and the verified rule; the no-downgrade rule in `register_self`; the pane tombstone now requiring a verified exit; the `session-leader` fallback for interactive shells reading by lease rather than dead; the `anchor` field on peers rows.
- Live records written before this change keep their shape until the owning session's next foreground coord call; ended sessions with a known start time still read dead, and the one empty-start record (this lane's) was repaired by its own `whoami`.
- `.manna/issues.jsonl` carries this claim and seal in the working tree beside other lanes' uncommitted rows; left for the operator's board commit.
