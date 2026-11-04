---
workflow: 2
manna: mn-880173
track: mn-b7a0cc
source: Independent review of ec30858 / mn-4e7229; .dev/liveness-review/review.md
base_commit: 1ec68d9a044e5465a44459592ec40e98afdf53c2
scope: 'Manna: stale or unbound living claimants must not be auto-closed by reconcile'
inputs:
- Independent review of ec30858 / mn-4e7229; .dev/liveness-review/review.md
binding: sha256:e53e08e7b695134df61b7a562c701533173c90df8f2caf2140622961244caa92
---

# Handoff: Manna: stale or unbound living claimants must not be auto-closed by reconcile

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-880173
```

## Scope

Manna: stale or unbound living claimants must not be auto-closed by reconcile

## Inputs

- Independent review of ec30858 / mn-4e7229; .dev/liveness-review/review.md

## Work order

# Independent review of ec30858

Result: original identity-matching correction verified; automatic-closure safety remains incomplete. Six existing real-CLI fixture scenarios passed independently (tests.log). No live board repaired, no production source edit, no pilot activation.

Additional isolated CLI probes in probe.py and probe-three-days.log:
- A correctly proof-bound Claude claimant has an actually living fixture process. Only its fixture presence timestamps are aged three days (inside the seven-day pruning window, beyond the two-day idle window). coord peers --all reports stale. Another session runs reconcile --fix --write-drift. Parent item becomes done and unclaimed on trailer evidence while the process remains alive before and after. Fixture item mn-00998f under fixtures3/aged_live/repo.
- A living claimant with no Coord binding also becomes done and unclaimed. Fixture item mn-c6885b under fixtures3/unbound_live/repo. This matches the documented limit, but still violates the user-visible guarantee that cleanup does not close live work.
- Control: a two-hour-old bound record reads idle and correctly remains in_progress (probe.log).

The fixture uses real Manna and Coord CLI paths; only timestamps in the throwaway Coord store are seeded to model elapsed time. No real session presence was aged or stopped. Initial setup used a timestamp outside the prune window and could not find the record; that setup error is not counted as a product result. Corrected probe uses three days and observes stale explicitly.

Code: main.rs coord_peers uses peers without --all, so a stale live record is omitted and the landed_open guard sees absence. liveness.rs is_live excludes stale and all_gone treats stale as gone even though tools/agent-coord classify_presence permits stale on a verified living process. managed_cli.rs correctly documents stale as an aged lease and separately requires dead/stopped for verified_gone. Preserve that managed-release distinction.

Required correction: use complete presence evidence and do not treat stale, absent, unbound or malformed evidence as proof of death. Ambiguous identity must refuse destructive lifecycle repair. Dead-claim release requires positive dead/stopped evidence. Automatic reconcile, particularly SessionEnd, must not turn commit trailers into completion when acceptance remains outstanding. Preserve findings and actionable next steps instead of declaring work done from uncertainty. Add living stale and living unbound regression fixtures that must retain status and claim, alongside existing bound active/idle, transport unavailable, truly dead and managed-release tests. Coordinate with the track-close race correction in mn-9b4359; both touch reconcile.

No Rust or full integration/root suites rerun in this focused review. Independent approval of the MI implementation at 9fe3a44 stands; live pilot remains gated on safe lifecycle handling.

Delivery: implement a narrow correction, test real CLI paths in isolated fixtures, commit owned paths with this item trailer, reseal and return SUBMITTED for independent review; do not self-close. No push/PR or live board cleanup. Keep mn-4e7229 closed; this follow-up carries the remaining invariant.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-880173`.
4. Commit with `Manna: mn-880173` and run `agent-do manna done mn-880173` only after the work is verified.

## Delivery receipts (2026-11-04, worker claude-833d4f4ab80a40cc; SUBMITTED for independent review, not self-closed)

### Reproduced

- The review's two probes, replayed by the extended fixture against the pre-fix binary at 81c7f0e (built in a throwaway worktree): the four active claimants were refused (the ec30858 identity match holds), then the stale living claimant's item was closed on its trailer while its anchor process stayed alive, as `probe-three-days.log` recorded. The same fixture passes on 69af762.
- Code cause, confirmed in the source: `coord_peers()` took `peers --json`, which omits stale records; `is_live` excluded stale and `all_gone` counted stale as gone; the guard let absence through as the orphan wedge; and the SessionEnd hook ran the full `--fix` as whichever session happened to end, against its own comment and against ARCHITECTURE.md, docs/INTEGRATION.md and the manna README, which all already said it applied only the two safe repairs.

### What landed (69af762, `Manna: mn-880173`)

- `tools/agent-manna/src/liveness.rs`: `is_gone` (dead or stopped) is the only positive verdict and `all_gone` requires it of every bound record; `not_gone`; `claim_presence` rules once for every reader (gone, present, unseen, ambiguous); `parse_peers_strict` refuses a payload with a row it cannot read; seven unit tests.
- `main.rs`: `coord_peers()` removed; `coord_peers_all()` reads `peers --all --json` through the strict parser. `check_dead_claims` reports dead only on gone, reports an ambiguous identity as a `skipped` finding on the row, and releases nothing else. `landed_open_close_blocked` refuses present (active, idle, stale, unknown), unseen, ambiguous, and an unreadable or unreachable coord, each with the next step named (`manna done` in the claimant's own shell, or the operator after review). The unit guard test covers stale, a stale twin beside a dead one, absence, and the worn label.
- `hooks/claude/agent-do-coord-stop.sh`: the SessionEnd reconcile runs `--fix --only dead_claim,blocker_desync`; the wrapper in `~/.claude/hooks` delegates to this file, so the edit is deployed.
- `tests/test_manna_reconcile_liveness.py`: ten real-CLI scenarios: four active claimants refused; stale (the throwaway coord store's `last_seen` and `lease_expires_at` seeded three days back, process alive, `peers --all` says stale, default `peers` omits it), unbound (hook pairing, never ran a coord command), ambiguous (a second shell wearing the pinned label under another token; dead_claim reports `skipped` on the row) and absent (pinned lane coord never saw) each keep status and claim and exit nonzero; the positively dead orphan still closes under an explicit `--fix` with no second release; the hook's own call releases the dead claim, reopens the row, closes nothing, and leaves the landed finding in drift.yaml.
- `tests/test_manna_reconcile_track_gate.py` (mn-9b4359): the coord stand-in answers with the track owner dead and bound by its claim proof (`GATE_SHIM_PEERS`), so the race window it probes is still reached; the gate, the store refusal, and the three variants' assertions are unchanged.
- Docs: ARCHITECTURE.md (reconcile `dead_claim`, the `--fix` paragraph, the SessionEnd section), CLAUDE.md (ownership gate), docs/INTEGRATION.md (hook row, session identity), tools/agent-manna/README.md (reconcile by click), CHANGELOG.md.

### Policies decided

- Positive evidence only (dec-5a4590, supersedes the absence clause of dec-44cde7): dead or stopped is death; stale is an aged lease on a process coord could not call dead; absence is coord saying nothing. The orphan whose record coord pruned, or who never bound one, is closed by a hand with authority, never mechanically; its landed_open finding and next step stay in drift.yaml.
- The automatic path never closes (dec-8995b2): the hook names the two safe repairs with `--only`; an explicit `manna reconcile --fix` keeps the orphan close over a claimant coord positively verified gone, so the wedge still breaks by a deliberate hand.
- Ambiguous identity (the claimant's label or agent id under another proof, or its proof under another label) refuses every lifecycle repair and is reported as `skipped` on the row.
- A coord payload with an unreadable row is an unusable read: the cure and the dead_claim check refuse; the managed lifecycle's reader takes the same strict read and already treats an error as unknown. `assess`/`managed release` keep their distinction (`verified_gone` only on dead or stopped); managed_cli.rs is untouched.
- dead_claim release still runs from the hook on positive death, including for a landed in_progress row: the claim is released and the row reopens, nothing closes. On this board that means mn-88d1ac's claim (claimant dead per coord) is released by the next SessionEnd; mn-9b4359's claimant was dead at the start of this lane and is idle again now, so it is present and untouched.

### Known limit (for the reviewer)

- A positively dead claimant's landed item still closes under an explicit `manna reconcile --fix`, and the serve daemon's `apply` button (`serve.py`, `"fix"` action) runs that full `--fix` under the daemon's pinned identity; the README now says so. The board has no field for outstanding acceptance on an unmanaged item (SUBMITTED lives in handoff prose), so for that one case the choice is Erik's: `managed require` for review-gated items, a typed acceptance field, or narrowing the explicit cure as well. This lane changed neither the serve button nor the schema.

### Coordination with mn-9b4359

- 408b5e7 is untouched and this change builds on it. Drops drp-c7522019adf9 (reviewer codex-01a18d749b1170e3) and drp-1fc1ba6833ad (claimant session-a6751ebc0cba) name the fixture change; coord refused my claim on that file because the mn-9b4359 lane still holds it, so the edit is recorded here and in the drops.

### Executed validation (venv Python on PATH; everything executed, nothing build-only)

- `cargo build --release` clean; `cargo test --release` 213 + 55 passed on the formatted final source (liveness.rs rustfmt clean; main.rs formatted with managed_cli.rs restored byte-identical).
- `tests/test_manna_reconcile_liveness.py`: 10/10 on 69af762; against 81c7f0e it fails at the stale claimant (row done).
- `tests/test_manna_reconcile_track_gate.py` 3/3; `tools/agent-manna/test/integration.sh` 736 passed, 0 failed; `tests/test_coord.py` and `tests/test_coord_v2.py` passed; `tests/test_git_integration.py` passed; `tests/test_manna_serve.py` 57 OK; `tests/test_manna_estate.py` 6 OK; `agent-do harness contracts validate` 0 errors; `contracts drift` 0 failing.
- Read-only `manna reconcile --json` on this board with the new binary: mn-9b4359 reports landed_open only; mn-88d1ac reports dead_claim. No `--fix`, no `--write-drift`, no live board cleanup.
- Not run: the full `./test.sh`. No push, pull request, app launch, install, screenshot, or live session spawning.
- zpc: les-945171 (lesson); dec-8995b2, dec-5a4590 (decisions).

### Remaining acceptance

- SUBMITTED: in_progress under claude-833d4f4ab80a40cc, not self-closed per the work order. Review points: the positive-evidence rule and the unseen refusal; the hook narrowing; the known limit above; whether the hook's dead_claim release should also be withheld for landed rows.
- `.manna/issues.jsonl` carries this claim and seal in the working tree beside other lanes' uncommitted rows; left for the operator's board commit.

## Delivery receipts, round two (2026-11-04, worker claude-833d4f4ab80a40cc; SUBMITTED for independent review, not self-closed)

Erik's acceptance boundary after the independent liveness check passed all ten scenarios: make `landed_open` advisory in every reconcile path, explicit `--fix` and the serve Apply action included; a trailer identifies work, it does not approve completion; keep closure through explicit `manna done` and managed acceptance; preserve positive-death claim release and blocker repair; releasing ownership must not mark work accepted; no new schema, no mandatory managed conversion.

### What landed (dcbb6cf, `Manna: mn-880173`)

- `main.rs`: the landed_open cure is retired from `apply_reconcile_fixes`; the finding is advisory in every path. `--fix` keeps its two repairs: releasing a claim coord has positively verified gone (`dead_claim`; the row reopens under no claim) and clearing resolved blockers (`blocker_desync`). `--only` refuses an advisory kind by name through `FindingKind::repairable` (`reconcile.rs`), and `--only landed_open` names what closes an item. The liveness guard, the owner bypass and the coord read in the fix path are gone; `dead_claim_findings` is the pure classification over coord's complete records (gone, present, unseen, ambiguous as skipped). `liveness.rs` is unchanged from round one.
- `reconcile.rs`: the landed_open finding's next step says the trailer identifies the work and does not approve completion.
- `hooks/claude/agent-do-coord-stop.sh`: comment only; `--only dead_claim,blocker_desync` stays as the hook's explicit contract.
- `tests/test_manna_reconcile_liveness.py`, 12 real-CLI scenarios: the eight claimants reconcile cannot act on (four active; stale, unbound, ambiguous, absent) are left exactly as found (status and claim kept, nothing fixed, nothing failed, the landed finding reported); a dead worker's committed but unreviewed item stays unfinished through every cleanup entry point, each asserting claim released, row reopened, nothing done, the landed finding kept: the explicit `--fix`; the serve daemon's Apply action, run with the argv its `ACTIONS` table defines (imported from `serve.py`, never retyped) under a pinned daemon identity; the SessionEnd hook's own call. `--only landed_open` is refused by name. Explicit completion still works: the operator closes the reopened item with `manna done` (authority evidence) and a live claim-holder closes its own landed item.
- `tests/test_manna_reconcile_track_gate.py` (mn-9b4359): at the boundary reconcile closes no track (the dead track claim is released, the track reopens, the late item stays open under it); `--only landed_open` is refused; `manna done` refuses over the open item naming it and closes once every item is done. The store gate from 408b5e7 is untouched.
- `tools/agent-manna/test/integration.sh`: G5b asserts `--fix` closes nothing, `--only landed_open` is refused, the claim-holder's explicit `done` closes; the managed trailer test asserts `--fix` closes nothing, managed or not.
- Unit tests: landed_open advisory even for the verified owner (then the owner's `complete_issue` closes); a dead claim release reopens a landed row and never marks it done; `--only` refuses advisory kinds; reconcile never closes a track and `done` keeps the gate; dead_claim findings ruled by claim presence (gone, stale, stale twin, absence, ambiguous).
- Docs: ARCHITECTURE.md (landed_open, `--fix`, SessionEnd), CLAUDE.md (ownership gate), docs/INTEGRATION.md, tools/agent-manna/README.md (reconcile by click), CHANGELOG.md.
- Not changed: `serve.py` (its Apply argv now runs a `--fix` that cannot close), `managed_cli.rs`, the board schema; no managed conversion is required of anyone.

### Policies decided

- dec-29c1a6 (supersedes the "explicit `--fix` keeps the orphan close" half of dec-8995b2): no reconcile path transitions a row to done. A receipt identifies work; approval is an explicit act by someone with authority (les-65e6b0).
- Releasing ownership is not acceptance: a dead worker's landed row returns to open under no claim, its landed_open finding and next step stay in the report and in drift.yaml, and `manna done` (claim-holder, operator, or landed evidence) or managed acceptance closes it.
- The hook keeps `--only dead_claim,blocker_desync` as an explicit contract even though `landed_open` has no repair anywhere now; a misspelled kind is refused by name.

### Executed validation (venv Python on PATH; everything executed, nothing build-only)

- `cargo build --release` clean, no warnings; `cargo test --release` 213 + 54 passed on the formatted final source (liveness.rs and reconcile.rs rustfmt clean; main.rs formatted with managed_cli.rs restored byte-identical).
- `tests/test_manna_reconcile_liveness.py` 12/12 on dcbb6cf's binary. Against the round-one binary at 69af762 (built in a throwaway worktree) the same fixture fails at its first scenario: that binary still reported a refusal for a live claimant, which the fixture now treats as a failure, so the run stopped there; round one's executed fixture run at 69af762 is the recorded observation that the explicit `--fix` closed a dead worker's item ("--fix closed mn-fa54d2").
- `tests/test_manna_reconcile_track_gate.py` 4/4; `tools/agent-manna/test/integration.sh` 741 passed, 0 failed; `tests/test_coord.py`, `tests/test_coord_v2.py`, `tests/test_git_integration.py` passed; `tests/test_manna_serve.py` 57 OK; `tests/test_manna_estate.py` 6 OK; `agent-do harness contracts validate` 0 errors, 0 warnings; `contracts drift` 0 failing; `bash -n` on the hook.
- Not run: the full `./test.sh`. No push, pull request, app launch, install, screenshot, live board cleanup, or live session spawning.
- zpc: les-65e6b0 (lesson); dec-29c1a6 (decision).

### Remaining acceptance

- SUBMITTED: in_progress under claude-833d4f4ab80a40cc, not self-closed. Review points: the advisory rule in the explicit `--fix` and in serve's Apply argv; the dead-claim release reopening a landed row (ownership released, work not accepted); the refused `--only landed_open`; the track-gate fixture's new shape beside the untouched store gate.
- Live board consequence: the next SessionEnd or explicit `--fix` on this board releases mn-88d1ac's claim (claimant dead per coord) and reopens it; nothing closes. mn-9b4359's claimant is present again and is untouched.
- `.manna/issues.jsonl` carries this claim and both seals in the working tree beside other lanes' uncommitted rows; left for the operator's board commit.
