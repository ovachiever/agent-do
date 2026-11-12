---
workflow: 2
manna: mn-88d1ac
track: mn-b7a0cc
source: 'Erik conversation 2026-11-03: background Holy worker notification, no GUI focus takeover; standalone agent-do'
base_commit: 7096b00c4668e3a51d1d39a5a8e1d84a2b061aaa
scope: 'Coord: standalone delivery contract for host-driven worker wakeups'
inputs:
- 'Erik conversation 2026-11-03: background Holy worker notification, no GUI focus takeover; standalone agent-do'
binding: sha256:8d10bad02ec922d5df001de5e045ca39114cf972fc9975060052a55a46eeee5b
---

# Handoff: Coord: standalone delivery contract for host-driven worker wakeups

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-88d1ac
```

## Scope

Coord: standalone delivery contract for host-driven worker wakeups

## Inputs

- Erik conversation 2026-11-03: background Holy worker notification, no GUI focus takeover; standalone agent-do

## Work order

Outcome
Keep agent-do independently usable while allowing Holy or another host to observe pending assignment actions, request a generic wakeup and record transport outcomes without claiming acknowledgment. This item supplies the reusable contract; its Holy counterpart owns lifecycle readiness, terminal transport and human UI.

Scope
Inspect current Coord targeting, revision/ack/resolve lifecycle, bells and existing structured reads before choosing additions. Extend existing coord commands/contracts rather than add a competing mailbox, status daemon or agent-do dependency on Holy. Agree the minimal contract with the Holy work order before either side hard-codes it.
Expose durable outstanding-action records with canonical board/item/claim generation/managed attempt/work-order revision, exact resolved recipient, drop ID/revision, and explicit unavailable/ambiguous/stale outcomes. Preserve info/action semantics and role/broadcast behavior. Default automatic wake demand is actionable unresolved work needing attention, not every informational update or unresolved-but-already-acknowledged obligation. New revisions may require fresh attention.
Define host-neutral notification request and outcome receipts with deduplication identity and evidence. Distinguish recorded, pending readiness, notification requested/submitted/unknown/failed, recipient acknowledged and resolved. Transport receipts never count as recipient ack, confer approval, or complete an assignment. A reconnect or timeout must not justify blind resubmission. Retain history and make unknown explicit. Multiple host consumers must not independently duplicate one wake demand; define ownership/claiming or another concrete deduplication mechanism.
Revalidate targeting and assignment freshness at dispatch/receipt boundaries. Reassignment, ambiguous identities, changed approval revision and stale attempts must not forward authorization. Host adapter can be absent: Coord continues to function normally, with delivery pending and ordinary hooks still usable. No generic GUI or tmux control implementation belongs in this item.

Acceptance
Real CLI tests in isolated boards cover two competing consumers, duplicate/replayed receipts, crash/restart, unknown transport outcome, reassignment after enqueue, changed revision, unavailable/ambiguous recipient, acknowledged action suppression, new action/revision, and unchanged standalone use with no Holy. Demonstrate recorded/submitted is never acknowledged. Validate docs, registry contracts and relevant Coord/hook suites. Provide an exact small wire/CLI contract and fixtures that the Holy implementation can consume. Implementation can run in parallel after contract agreement; cross-product acceptance waits for both sides.

Boundaries and return
This is a work order, not authorization to inject into live sessions or install an app. No mouse/keyboard GUI automation, focus changes, window/tab selection, terminal resurrection, session kill, permission-dialog answering, pushes, PRs or deployment. Preserve concurrent changes and existing sessions. No paid credential retrieval or metered API work without the separately required explicit provider/purpose/spend approval; no per-notification confirmation ceremony in the product design. Use isolated synthetic fixtures first. Verify independent acceptance evidence for mn-5cdd6e (source correction 7096b00), not merely its done status. Return SUBMITTED with exact source commits, executed test receipts and remaining installed/live gates; do not self-close.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-88d1ac`.
4. Commit with `Manna: mn-88d1ac`, return SUBMITTED for independent review and leave reviewer closure pending.

## Cross-repository counterpart

mn-702ea1 on holy-ghostty. Cross-board relations are advisory, not automatic claim blockers. Agree the contract first; implementation may proceed in parallel in isolated workspaces. Integration acceptance requires both sides and verified targeting-correction acceptance.

## Return (2026-11-03, session-8d880bb0c2dc / claude-8d880bb0c2dc4127): SUBMITTED for independent review

Source commit: `be27371f0388b0ed67575329617e6327f3e03613` on branch `mn-88d1ac-coord-wake` (worktree
`/Users/erik/Custom-Coding/agent-do-mn-88d1ac-coord-wake`), one commit ahead of main at 9776e7d.
History: first committed as 1dd4a9f on 7096b00 because the primary checkout held another live
writer's uncommitted edits (mn-e6e1a8) to tools/agent-coord, tests/test_coord_v2.py,
CHANGELOG.md, registry.yaml and docs/TOOLS.md; after mn-e6e1a8 landed (e408409, board 9776e7d)
the branch was rebased onto main, resolving one conflict hunk in each of tools/agent-coord
(their stale-remedy summary block plus this lane's wake detail), registry.yaml (their STALE
wording plus this lane's `drop wake` clause), CHANGELOG.md (both bullets) and docs/TOOLS.md
(regenerated), and every check below was rerun on the rebased tree. Integration onto main is
`git merge --ff-only mn-88d1ac-coord-wake` from the primary checkout once its working tree is
clean for registry.yaml and docs/TOOLS.md (the mn-54fe40 lane holds uncommitted edits there
at the time of writing). Not pushed; no PR.

### What shipped

- `coord drops --wake` (contract `coord-wake/1`): wake demands open action drops raise,
  actionable first (unresolved, unacknowledged at the current revision, one exact live
  recipient, assignment not stale) with the pinned assignment (board, item, claimant,
  claim proof, claimed_at, managed attempt, work-order digest) and the recipient's harness
  facts; held ones with the reason (informational, broadcast, pending, ambiguous, stale,
  acknowledged); each with its notification state.
- `coord drop wake <id> [--revision n] [--after <rid> --evidence]`: a host claims a demand
  under its own coord identity; presence is the lease (one live consumer per demand; dead
  holders lapse and are superseded; a restart is the same consumer).
- `coord drop wake <id> --request <rid> --waiting <reason>` and
  `--outcome submitted|unknown|failed|released --evidence <text>`: transport receipts.
  Replays are duplicate and change nothing; a different state is a correction with history;
  unknown blocks every further request until established; submitted is followed only by the
  recipient's ack or an explicit `--after` request. No receipt moves the delivery stage,
  writes an ack, extends an approval or touches the claim.
- Contract doc `docs/COORD-WAKE.md`; fixtures `tests/fixtures/coord-wake/` (19 real CLI
  payloads from `tests/gen_coord_wake_fixtures.py`); `docs/INTEGRATION.md` section;
  registry capabilities/commands/examples; CHANGELOG entry; TOOLS.md regenerated.

### Executed receipts (all in the worktree, isolated boards, synthetic sessions, AI routing off)

| Check | Result |
|---|---|
| `python3 tests/test_coord_v2.py` (21 scenarios incl. `test_wake_contract`, `test_wake_fixtures`) | coord v2 tests passed on the rebased tree (exit 0; receipt full-coord-v2-rebased.log); also passed at 1dd4a9f (2m57s; full-coord-v2-final.log) |
| focused `test_wake_contract` + `test_wake_fixtures` on the rebased tree | passed (33.7s; focused-wake-rebased.log) |
| gates and the nine adjacent suites rerun on the rebased tree (`gates-rebased.log`, `*-rebased.log`) | all exit 0: contracts validate PASS (0 errors, 0 warnings), contracts drift 0 failing, gen-tools-doc --check in sync, coord v1, routing, install specs, contracts drift tests, routing contracts, hook store resolution, global hooks nonblocking, hook outcome telemetry, prompt hook AI |
| focused `test_wake_contract` + `test_wake_fixtures` | passed (35.3s; receipts focused-wake-3.log) |
| `python3 tests/test_coord.py` | coord tests passed |
| `python3 tests/test_v11_routing.py` | v1.1 routing tests passed |
| `python3 tests/test_install_specs.py` | OK |
| `tests/test_contracts_drift.py`, `test_routing_contracts.py`, `test_hook_store_resolution.py`, `test_global_hooks_nonblocking.py`, `test_hook_outcome_telemetry.py`, `test_prompt_hook_ai.py` | all passed |
| `agent-do harness contracts validate` | Gate PASS, 103 declared, 0 errors, 0 warnings |
| `agent-do harness contracts drift` | 0 declared-but-unimplemented |
| `bin/gen-tools-doc --check` | in sync |
| `tests/gen_coord_wake_fixtures.py` | wrote 19 fixtures (22.9s) |
| baseline `python3 tests/test_coord_v2.py` at 7096b00 before any edit | coord v2 tests passed (3m17s) |

Receipt logs: `.dev/mn-88d1ac/receipts/` in the primary checkout (copied from the session scratchpad); the return report is `.dev/mn-88d1ac/return.md` and the focused runner `.dev/mn-88d1ac/run_wake_tests.py`.

Acceptance scenarios covered by `test_wake_contract`, through the real CLI and the
prompt-router and doorbell hooks: standalone with no host (A), recipient cannot wake itself
(B), two competing consumers and duplicate requests (C), pending readiness and replayed
waiting (D), submitted never acknowledges and replayed receipts (E), acknowledged-action
suppression (F), new revision as a fresh demand with history (G), unknown blocks every
consumer until established (H), crash/restart with lapse and supersession plus a dead
holder's unknown (I), changed revision while held (J), reassignment after enqueue (K),
unavailable and ambiguous recipients (L), direct action drops (M).

### mn-5cdd6e acceptance evidence, verified (not just its done status)

`.dev/mn-ed4353-review/acceptance-mn-5cdd6e.md`: independent reviewer
claude-07c1f9c7eb7a4627 accepted 7096b00 on 2026-11-03 with executed suites (coord v2,
routing, coord v1), a baseline discrimination run against 0342d6b (both new regressions
fail there), and four reviewer probes (P1 same-worker reclaim, P2 legitimate restart,
P3 role/broadcast/need-key, P4 item closed). The non-blocking finding it filed is
mn-e6e1a8, in progress by another worker during this lane.

### Remaining gates (not this lane's to close)

- Independent review of `be27371f0388b0ed67575329617e6327f3e03613`, then `git merge --ff-only mn-88d1ac-coord-wake`
  from a primary checkout whose registry.yaml and docs/TOOLS.md are clean (mn-54fe40's uncommitted edits sit there now).
- Holy counterpart mn-702ea1 consumes `docs/COORD-WAKE.md` and the fixtures; cross-product
  acceptance (one action wakes exactly its intended ready worker) waits for both sides.
- Live/installed acceptance needs the separately authorized test session; none was run here.
- Board filing: this handoff's seal and `.manna/issues.jsonl` live in the primary checkout
  alongside preexisting foreign board edits and are not swept into the source commit.
- Filed during this lane: mn-dd9be1 (coord classifies a live session dead when its anchor
  pid was transient; observed on session-3f2a6552e3b9).

## Return 2 (2026-11-03, session-8d880bb0c2dc / claude-8d880bb0c2dc4127): crash-window correction, RESUBMITTED for independent review

The independent review (`.dev/independent-integration-review/review.md`) found that a host
which claimed a wake request, submitted input and died before recording the outcome left no
receipt, and coord read the missing receipt as a lapsed lease, so a second host could claim
and send again; the crash test expected that reclamation. Corrected in the lane worktree.

Source commits on `mn-88d1ac-coord-wake`, rebased onto main 47929e1 (two ahead, not pushed,
no PR): `ff111ac` (the contract; be27371 rebased, CHANGELOG.md the only conflict, both bullets
kept, TOOLS.md regenerated) and `882291a193048bd70521e70aa0f4a36a8b587568` (the fix).

What changed: a request is a reservation (reclaimable when its holder lapses; nothing can have
been sent) until the holder writes `drop wake <id> --request <rid> --dispatching <evidence>`
immediately before it touches the transport. Coord revalidates the demand at that boundary
(same demand id, still actionable, else refused with "do not send", nothing written), pins
the recipient incarnation it saw, journals `wake_dispatch`. After the mark a dead holder's
request reads `unknown` (`notification.unknown.how: lapsed after dispatch-started`,
`lapsed.reclaimable: false`); nobody may request, supersede, release or dispatch on its
behalf until a live consumer records `--outcome submitted|failed` on that same request with
transport evidence. `--waiting` and `--outcome released` are refused after dispatch-started.
Request identity and fencing unchanged; transport receipts still never acknowledge. The
contract (`docs/COORD-WAKE.md`) tabulates the three crash windows, states the host's
deduplication and reconciliation obligations, and promises no exactly-once terminal input.
Fixtures: 31 (12 new) in `tests/fixtures/coord-wake/`.

Executed receipts (logs in `.dev/mn-88d1ac/receipts/`; all runs executed, none compile-only):

| Check | Result |
|---|---|
| `python3 tests/test_coord_v2.py` (full, 21 scenarios) on the corrected tree | passed, 3m49s (full-coord-v2-fix.log) |
| focused `test_wake_contract` + `test_wake_fixtures` at 882291a | passed, 48.5s (focused-wake-882291a.log) |
| nine adjacent suites (coord v1, routing, install specs, contracts drift, routing contracts, hook store, global hooks nonblocking, hook telemetry, prompt hook AI) | all exit 0 (adjacent-fix.log) |
| `tests/test_git_integration.py` (main's new suite, combined check after the rebase) | passed, 54s (git-integration-fix.log) |
| `harness contracts validate` / `contracts drift` / `gen-tools-doc --check` | Gate PASS 0/0; 0 failing; in sync (gates-fix.log) |
| `tests/gen_coord_wake_fixtures.py` | wrote 31 fixtures, 19.8s |
| `.dev/mn-88d1ac/probe_crash_window.py` (the reviewer's sequence, real CLI) on pre-fix ff111ac | DEFECT REPRODUCED: B superseded A, would send again (probe-prefix-ff111ac.log) |
| same probe on 882291a | FENCED: demand `unknown`, B refused exit 2 (probe-corrected-882291a.log) |

New regressions: part I is the crash before dispatch (reclaimable), N the crash after
dispatch-started before sending, O the crash after sending before the receipt, P dispatch
revalidation (moved revision, acknowledged drop, text form), K the stale-at-dispatch refusal.

Remaining gates: independent re-review of 882291a, then `git merge --ff-only
mn-88d1ac-coord-wake` from a clean primary (other lanes' board files are uncommitted there
now); Holy mn-702ea1 adopts `--dispatching` before every send (pointer left on its coord
board); authorized live acceptance (none run; no live worker woken); board filing stays
uncommitted beside foreign edits; item stays `in_progress`, not self-closed. Full return:
`.dev/mn-88d1ac/return-2-correction.md`.
