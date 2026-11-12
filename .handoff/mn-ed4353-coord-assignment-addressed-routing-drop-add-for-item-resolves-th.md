---
workflow: 2
manna: mn-ed4353
track: mn-b7a0cc
source: zpc les-a56af7/les-c802a0/les-a7243a on versova-supply-intelligence; mn-cf4d8d acceptance .dev/mn-59f1e4-review/acceptance-dcb3eea.json
base_commit: 3beacb3052177213bef98b50ce29b9f9a72664f6
scope: 'coord: assignment-addressed routing — drop add --for-item resolves the worker from the board claim proof, honest delivery stages, scoped approval records, worker lookup by item'
inputs:
- zpc les-a56af7/les-c802a0/les-a7243a on versova-supply-intelligence; mn-cf4d8d acceptance .dev/mn-59f1e4-review/acceptance-dcb3eea.json
binding: sha256:eb41c78d7490f407e9f2ecc037c51a9cb6bfaba95a3a03d614fd9695a1108aca
---

# Handoff: coord: assignment-addressed routing — drop add --for-item resolves the worker from the board claim proof, honest delivery stages, scoped approval records, worker lookup by item

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-ed4353
```

## Scope

coord: assignment-addressed routing — drop add --for-item resolves the worker from the board claim proof, honest delivery stages, scoped approval records, worker lookup by item

## Inputs

- zpc les-a56af7/les-c802a0/les-a7243a on versova-supply-intelligence; mn-cf4d8d acceptance .dev/mn-59f1e4-review/acceptance-dcb3eea.json

## Work order

Follows the mn-261c29 incident on the versova-supply-intelligence board (2026-10-30): an approval was dropped to session-01a18d6ac8fd and to codex-01a18d6ac8fd7653, both guessed from the Manna claimant label, and the worker found it only as a file in its receipts folder (zpc les-a56af7, les-c802a0, les-a7243a). Linked to mn-cf4d8d (coordinator-owned closure, drop lifecycle, action-vs-info nudges; accepted 2026-11-02 at dcb3eea) and mn-812cd9 (hooks read coord under the shell's session id). Scope: (1) coord drop add <file> --for-item <mn-id> [--action] resolves the canonical board, the current claimant, the managed attempt where one exists, and the exact coord session, and shows the destination with its provenance; (2) identities bind explicitly: the Manna claimant's claim_token_hash equals the proof manna identity derives in the worker's own process, and coord records that proof on the worker's record at touch; resolution is exact equality among live records, never a label, a prefix, or a first match, and two different harness sessions carrying one proof refuse as ambiguous; (3) an unknown direct --for destination is refused; roles and any still broadcast; a drop whose worker cannot be reached stays visibly pending and is never forwarded to a replacement claimant or a revised work order; (4) delivery stages are reported as recorded, recipient resolved, bell queued, acknowledged, completed; a ledger write or a queued bell is never acknowledgment; the owner keeps seeing unacknowledged action drops; (5) approval records carry item, work-order digest, allowed actions, exclusions and the human source, and routing confers no authority; (6) coord worker <mn-id> shows the exact session, the board assignment versus the declared focus title, liveness evidence and open obligations. Out of scope: idle-worker resumption, terminal retirement, mn-bf448b, pushes and PRs.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-ed4353`.
4. Commit with `Manna: mn-ed4353` and run `agent-do manna done mn-ed4353` only after the work is verified.

## Implementation (2026-11-02, session claude-35dfcfc4870d4899, SUBMITTED for independent review)

Status: SUBMITTED. The item stays `in_progress` under this session's claim until the independent reviewer accepts it. No push, no PR, no live approval relay, no bulk cleanup; mn-bf448b untouched.

### The incident, as reproduced

On the versova-supply-intelligence board the approval for mn-261c29 was dropped twice: to `session-01a18d6ac8fd` (a shortened guess) and to `codex-01a18d6ac8fd7653` (the Manna claimant label). Neither name was a coord session: `.git/agent-do/coord/agents.json` there holds no record under either, and the lane's actual coord identity was never known to the coordinator. The drop ledger wrote both without complaint (`for_agent_id: null`), the bell had nobody to ring, and the worker found the approval only as a file in its own receipts folder (zpc les-a56af7, les-c802a0, les-a7243a). Root cause: coord labels (`session-<12 hex>` from a pinned session, `codex-<raw thread id>` from the thread env) and Manna labels (`claude-<16 hex>`, `codex-<16 hex>`) are different derivations of one harness id; nothing shared is visible in the label, and a prefix match between them is a guess. What is shared is the proof: the board's `claim_token_hash` is the digest `manna identity` derives under the machine-local key in the worker's own process.

### What changed

- `tools/agent-coord`
  - Binding: `register_self` asks the manna binary (`manna identity --json`, located beside the tool, under `~/.agent-do/install-path`, or on PATH) for this process's session label and proof and records them as `manna` on the agent record; `touch` and `whoami` refresh it, every other call retries until a proof is bound, and a process that cannot produce one (a hook without the session's env) keeps the earlier binding rather than erasing it. `whoami` and `touch` print it.
  - `drop add <path> --for-item <mn-id> [--action] [--allows … --excludes … --authorized-by …]`: reads the canonical board (`manna show --json` from the common git dir's checkout, so a worktree reads the primary board; `manna assess --json` for the managed attempt), refuses a done or unclaimed item, pins `for_item` (id, status, board, claimant, claim proof, claimed_at, attempt, work-order prompt and digest, observed_at, source), resolves the recipient as the one live record whose bound proof equals the row's (`_resolve_item_recipient`: unassigned / pending / ambiguous / resolved; records of one harness session, sharing `identity_raw`, are one recipient), refuses when the worker is this session, rings the exact recipient and records `bell_queued_at`, and prints the destination with its provenance. A re-add that re-pins a different claimant, attempt, or digest journals a `readdressed` history event. An approval needs all of `--allows`, `--excludes`, `--authorized-by`; it is recorded against the item and work-order digest, is an action, and states that routing confers no authority and that local implementation approval is not deployment approval.
  - Unknown direct destinations: `--for <name>` that is not a registered session or alias, a role (`builder|auditor|researcher|overseer`), or `any` is refused (exit 2) naming the live sessions and the `--for-item` remedy; nothing is written. Roles and `any` are unchanged broadcasts.
  - Targeting: `_drop_targets_me` matches an item drop by the resolved id (or a sibling record of the same harness session) or by proof equality; a label never matches. `drop ack` and `drop resolve` follow it.
  - Pending delivery: a worker's `touch` resolves item drops waiting on its proof (`_deliver_pending_item_drops`: `for_agent_id`, `recipient`, `recipient_resolved` history, one bell, `drop_deliver` journal line); a replacement claimant never matches (its proof differs).
  - Delivery stages: every drop view carries `delivery` (`stage`, `recorded`, `recipient` with presence, `bell`, `acknowledged` by the exact recipient at the current revision or the readers of a broadcast, `completed`, `stale`); `stale` is read from the board at view time: `reassigned`, `item closed`, `work-order revised`, or `unverified` with manna's answer. `drops` text lines show the stage and `item:<id> -> <session>`.
  - Interrupts: item drops are labelled "Drop/Action/Approval for the worker on <id>", carry the approval scope and any STALE reason; the owner's interrupts carry an `awaiting` notice (kind `notice`, never blocking) for each own open action drop not yet acknowledged or still pending/ambiguous.
  - `worker <mn-id>`: exact session with binding provenance (how, manna session, proof, bound_at, source) and harness anchor, liveness evidence (lease presence, `kill -0`/`ps lstart` verdict, pulse, observed_at), the board assignment beside the session's declared focus title with `focus_predates_claim`, manna's own claimant observation (labelled, evidence only), and open obligations with stages; `recipient_state` and reason when there is no exact session.
  - Help text, examples.
- `tools/agent-manna/src/main.rs`: `manna show <id> --json` (same payload as the YAML form). No other manna change; the claim path already stores the proof.
- `tests/test_coord_v2.py`: `test_assignment_targeting` (the incident through the real CLI, the prompt-router hook and the doorbell hook in a throwaway board: guessed ids refused and the ledger untouched; roles and `any` preserved; the scoped approval reaches the exact worker's hook with its scope and ack command and not a stranger's; the coordinator sees it unacknowledged, a stranger cannot ack, the worker acks, the coordinator observes it through `worker` and the awaiting notice leaves; an acknowledged action keeps reminding until resolved; an info drop to the item stays a notice; an unregistered claimant leaves the drop pending and its first `touch` discovers it; two live sessions with different anchors and one proof are ambiguous; abandon and re-claim marks the old drop STALE reassigned and the replacement never sees it; a resealed work order marks the approval STALE work-order revised and tells the worker; done and unclaimed items refuse; text renderings). `test_drops_and_history` now registers the builder before dropping to it, because writing a drop to a name nobody holds is the defect this item removes. `MANNA_SESSION_ID`/`MANNA_SESSION_TOKEN` are cleared from fixture environments.
- `registry.yaml` (drop, drops, new `worker`; contracts snapshot += worker; two examples), `docs/TOOLS.md` (regenerated), `ARCHITECTURE.md` (Coord v2: Assignment addressing), `CHANGELOG.md`, `CLAUDE.md` (coord row).

### Limitations (stated, not hidden)

- An unreachable worker is shown pending; there is no wakeup path for an idle or retired session (out of scope by ruling). The worker's next coord call delivers it.
- The binding is written by the worker's own process; a worker that never runs any coord command after this change has no binding and its drops stay pending with that reason.
- Staleness is a board read at view time (one `manna show --json` per item per command); an older manna binary without `show --json` reports `unverified` with its own message rather than guessing.
- A direct `--for` to a registered but dead/stopped session is still accepted (the session exists); its delivery view says so.
- `manna assess`'s own claimant liveness still uses its prefix match; it is reported in `worker` as `manna_observation`, labelled evidence, and never used for routing.

### Receipts (executed on the implementing machine, 2026-11-02 evening; logs under `.dev/mn-ed4353/`)

| Check | Result | Log |
|---|---|---|
| `python3 tests/test_coord_v2.py` (16 scenarios incl. `test_assignment_targeting`) | passed | `coord-v2-tests.log` |
| `python3 tests/test_v11_routing.py` (prompt-router and session-start hooks, hook identity) | passed | `v11-routing-tests.log` |
| `python3 tests/test_coord.py` (v1) | passed | `coord-v1-tests.log` |
| `cargo test --release` (manna, after `show --json`) | 198 + 52 passed, 0 failed | `cargo-test.log` |
| `bash tools/agent-manna/test/integration.sh` (M1 to M8) | 594 passed, 0 failed | `manna-integration.log` |
| `agent-do harness contracts validate` | Gate PASS, 0 errors, 0 warnings | `contracts-validate.log` |
| `agent-do harness contracts drift` | 0 declared-but-unimplemented | (stdout) |
| `bin/gen-tools-doc --check` | in sync | (stdout) |
| `agent-do manna managed doctor --probe` (installed coord + prompt-router through the real binaries) | `live: true`, no failed step | (stdout) |
| `bash .dev/mn-ed4353/repro.sh` (standalone replay of the incident for the reviewer) | every check ok, exit 0 | `repro-run.log` |
| `./test.sh` (root: smoke, python suites, contracts gate, tools-doc check) on the final code | 128 passed, 1 failed | `root-test.log` |

Environment failure, separated from the passed checks: the one root failure is `tests/test_live.py`, which reports "macOS frameworks not available" (exit 6) on this machine; it fails the same way on the untouched tree and was the same single failure in passes 2 to 4 of mn-cf4d8d. No check that this item touches is in it.

Reviewer entry points: `bash .dev/mn-ed4353/repro.sh` (throwaway board, prints each stage, exit 0 when every expectation holds); `python3 tests/test_coord_v2.py` (the full scenario); `agent-do coord worker <mn-id>` and `agent-do coord drop add <path> --for-item <mn-id>` on any board.

