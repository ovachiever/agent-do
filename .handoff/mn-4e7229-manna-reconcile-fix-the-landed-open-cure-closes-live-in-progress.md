---
workflow: 2
manna: mn-4e7229
track: mn-b7a0cc
source: 'mn-54fe40 round three, 2026-11-03: discriminating fixture after the board closed the item under an active claimant'
base_commit: fb540b72ee5419796e1dc6549650dcb61a3996e6
scope: 'manna reconcile --fix: the landed_open cure closes live in_progress items because its liveness guard cannot match a hook-pinned Claude session'
inputs:
- 'mn-54fe40 round three, 2026-11-03: discriminating fixture after the board closed the item under an active claimant'
binding: sha256:710c636ed06d0745be3578aa12f4ef0afddfe4361a7a2efea782909b759472e3
---

# Handoff: manna reconcile --fix: the landed_open cure closes live in_progress items because its liveness guard cannot match a hook-pinned Claude session

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-4e7229
```

## Scope

manna reconcile --fix: the landed_open cure closes live in_progress items because its liveness guard cannot match a hook-pinned Claude session

## Inputs

- mn-54fe40 round three, 2026-11-03: discriminating fixture after the board closed the item under an active claimant

## Work order

Reproduced 2026-11-03 in an isolated fixture against the current manna build (scratchpad probe_guard_matrix.py, four variants): an in_progress item with a landed `Manna:` trailer commit, claimed by a session whose coord record is active (touched seconds earlier, anchor process alive), is closed and its claim released by `manna reconcile --fix` whenever the claimant's manna label and coord agent id do not fit the guard's derivation. coord_status_for_owner (tools/agent-manna/src/main.rs) looks the label up as-is, then as `session-` plus the first 16 alphanumerics of the label; coord names a session `session-` plus the first 12 hex of the session uuid, and the Claude hooks pin the manna label as `claude-` plus the first 16 hex. So `claude-31022d9c53c942eb` is looked up as `session-claude31022d9c53` while coord reports `session-31022d9c53c9`: no match, the guard passes, the cure closes ("closed on landed evidence; orphaned claim ... released"). A plain label (`owner-plain` / `session-ownerplain`) matches and is refused ("claiming session owner-plain is active; not closing over live work"). Every SessionEnd hook runs `manna reconcile --fix --write-drift` (hooks/claude/agent-do-coord-stop.sh), so a live lane holding an in_progress item that already has a trailer commit on the branch is closed by the next session that ends in the repository. This closed mn-54fe40 at 2026-11-04T03:00:51Z (drift.yaml: session 8d880bb0-c2dc-4127-9e57-f6e5789b72eb) while its claimant was active and mid-lane, twelve minutes before that lane sealed its round-three receipts; the handoff says SUBMITTED and the row says done. Fix direction: match the owner by the coord record's bound manna proof (equal to claim_token_hash) or its bound manna label, never by re-deriving an id from the label; refuse to close while any live coord record is bound to the claim; add the four-variant fixture as a regression. Do not reopen mn-54fe40 (nothing reopens); its follow-up item carries the pending acceptance.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-4e7229`.
4. Commit with `Manna: mn-4e7229` and run `agent-do manna done mn-4e7229` only after the work is verified.

## Delivery receipts (2026-11-04, worker claude-833d4f4ab80a40cc, closed on evidence)

### Root cause, reproduced

- `coord_status_for_owner` (tools/agent-manna/src/main.rs) looked a claimant up as-is, then as `session-` plus the label's first sixteen alphanumerics. coord names a hook-pinned session `session-` plus the first twelve hex of the session uuid; manna labels it `claude-` plus the first sixteen hex. `claude-31022d9c53c942eb` became `session-claude31022d9c53` against coord's `session-31022d9c53c9`: no match, the miss read as the orphan wedge, the cure closed. Reproduced again before the fix through the new fixture's four live variants (each closed on the old binary; each refused on the new one).
- A second lifecycle matcher in `managed_cli.rs` (`coord_peer_for_owner`) found the same pairing by a hex-tail prefix compare, a stranger-matching heuristic in the path that authorizes `managed release`. `manna state` (`state.rs` `matching_peer`) still uses a hex-tail resemblance for display only; left as is (dec-cc956f).
- coord already stored the exact facts (`manna.session`, `manna.proof`, bound by `touch` asking `manna identity` in the worker's own process) but `peers --json` did not render them, so manna had nothing exact to compare.

### What landed (ec30858, `Manna: mn-4e7229`)

- `tools/agent-coord`: every `peers --json` row carries `manna` (session, proof, bound_at, source, operator; null until the session's own shell has bound it); text output shows `manna:<label>`; help updated.
- `tools/agent-manna/src/liveness.rs` (new, lib): `CoordPeer`, `parse_peers`, `peers_bound_to_claim` (Proof, then Label, then AgentId; exact facts only), `is_live` (anything coord has not classified dead, stopped, or stale), `live_bound`, `all_gone`, `statuses_by_agent`; four unit tests including the raw-uuid and `session-claude...` non-matches.
- `main.rs`: `coord_peers`/`coord_peers_all` return records; `check_dead_claims` matches by binding and reports dead only when every bound record is gone; `landed_open_close_blocked(issue, peers)` blocks on any live bound record and names it with how it matched; `apply_reconcile_fixes` reads coord once and skips a `dead_claim` for a row the close already released (no stale second release); unit tests rewritten around the hook pairing, idle, dead/stopped, twins, absence, unclaimed, and coord down.
- `managed_cli.rs`: `liveness_for(owner, claim_proof)` by binding (a live bound record speaks for the claim; `verified_gone` only when every bound record is dead or stopped); `hex_tail`/`coord_peer_for_owner` removed; `assess` and `managed release` pass the row's proof.
- `tests/test_manna_reconcile_liveness.py` (new; registered in test.sh after the release build): four live variants refused (underscore label with and without `--write-drift`, plain label, the real hook pairing with no MANNA pins), plus two controls (anchor died: `dead_claim` names the bound record and `--fix` closes on the evidence without a second release; a claimant coord never saw still closes).
- `tests/test_coord_v2.py`: peers carry the binding in JSON and text. `tools/agent-manna/test/integration.sh` M2: the worker's touch runs with its Manna identity, as a worker's shell does, and asserts the bound label on the record.
- Docs: ARCHITECTURE.md (reconcile `dead_claim` and the `--fix` paragraph now describe the orphan cure and its guard), CLAUDE.md (ownership-gate sentence; coord row), CHANGELOG.md, registry.yaml and regenerated docs/TOOLS.md (peers description).

### Policies decided

- Match by exact facts only; nothing is derived from a label (dec-44cde7). A bound record blocks the cure unless coord classified it dead, stopped, or stale: idle counts as live, since an aged lease on a process coord could not call dead is a lane that has not touched coord lately. The old guard let idle pass; same defect class.
- Absence from coord still closes: the orphan wedge is a claimant coord no longer sees. Known limit: a lane whose shell never ran any coord command has an unbound record and is treated as absent; today every live Claude record on this machine is bound (7 of 7 in agents.json), the prompt hook nags until focus is set, and `coord touch` binds.
- mn-54fe40 is not reopened; its acceptance rides mn-cbc990.

### Executed validation (venv Python on PATH; all exit 0 unless stated)

- `cargo build --release` (tools/agent-manna): clean, no warnings. `cargo test`: 208 + 52 passed, 0 failed.
- `python3 tests/test_manna_reconcile_liveness.py`: 6 scenarios passed, run before and after the rustfmt pass on the final binary.
- `bash tools/agent-manna/test/integration.sh`: 736 passed, 0 failed (735 before plus the bound-label assertion). Without the venv the same run shows 9 environment failures (`yaml` missing under Homebrew python3); 4 of those were the M2 liveness cases until the test bound the worker the way a worker's shell does.
- `python3 tests/test_coord_v2.py`: passed. `tests/test_coord.py`: passed. `tests/test_git_integration.py`: 21/21 passed. `tests/test_manna_serve.py`: 57 OK. `tests/test_manna_estate.py`: 6 OK.
- `agent-do harness contracts validate`: 0 errors. `contracts drift`: 0 failing. `tests/test_contracts_gate.py`, `test_contracts_drift.py`, `test_routing_contracts.py`: passed. `bin/gen-tools-doc --check`: in sync.
- rustfmt: liveness.rs clean; main.rs's own hunks formatted; managed_cli.rs's pre-existing non-clean state left byte-identical to the edit.
- Everything above was executed; nothing is build-only. Not run: the full `./test.sh`. No app launches, installs, screenshots, pushes, or pull requests.
- zpc: les-bf9334 (lesson), dec-44cde7 and dec-cc956f (decisions).

### Remaining acceptance

- None named by the work order; closed on evidence per the closing rule (trailer commit ec30858 touches source). No live or visual pass applies to this CLI change; the executed fixture is the acceptance.
- `.manna/issues.jsonl` carries this claim, seal, and close in the working tree beside other lanes' uncommitted rows; left for the operator's board commit, as the lanes before did.
