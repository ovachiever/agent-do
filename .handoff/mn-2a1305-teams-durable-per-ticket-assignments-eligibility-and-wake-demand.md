---
workflow: 2
manna: mn-2a1305
track: mn-a2b986
source: Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
base_commit: 5229e77b91e408f7833fd646d021e4a0d427f294
scope: 'Teams: durable per-ticket assignments, eligibility and wake demands for a track run'
inputs:
- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
binding: sha256:79ac0323e41f4f2e4b1548b56cc0694e1383131a66d7ce21da88fbe34b8ce095
---

# Handoff: Teams: durable per-ticket assignments, eligibility and wake demands for a track run

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-2a1305
```

## Scope

Teams: durable per-ticket assignments, eligibility and wake demands for a track run

## Inputs

- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff

## Work order

Implement agent-do's standalone team run/assignment lifecycle using Manna's board as the only dependency/claim authority and the accepted lead designation contract. A run binds canonical scope, lead/authority, selected actionable child tickets, stable idempotency key and ticket-to-session assignments. Assignment is not claim: blocked ticket workers wait, then re-read and claim before editing. Open all requested ticket sessions is a host operation; core emits actionable launch/wake intents without depending on Holy. Preserve manual individual claims and single-worker track behavior.

Acceptance: eight tickets, three eligible and five assigned/waiting; dependency/review/integration gates; decisions/dreams/completed/foreign-held rows not blindly launched; two hosts and duplicate requests; uncertain/partial launch and evidence-based retry; late-added tickets unassigned; removed/moved tickets reassessed; manual claim wins; stale attempt/reseal; transfer without moving workers; closed worker Needs replacement with no unlimited respawn; runtime/board/host unavailable fails closed. No repeated model polling while waiting. Emit assignment-addressed notifications via coord-wake/1 and keep delivered versus acknowledged versus accepted distinct. Exercise with real CLI isolated boards and adapters under controlled fixtures. Where review/integration gates apply, use the MI approval contract rather than a shadow acceptance field. Persist enough state for host restart/recovery and publish host-facing fixtures.

Delivery: read the parent track's full locked plan and existing repository rules. Implement only this item's scope using existing Manna/Coord/MI/Holy mechanisms. No new top-level tool, parallel backlog or duplicate identity/approval store. Preserve concurrent work. Execute focused canonical tests, commit owned paths with this Manna trailer, seal receipts and return SUBMITTED for independent review; no self-acceptance. Separate installed/live field checks from source acceptance. No app installation/launch, live worker notification or spawning, board cleanup, push, PR, deployment or MI activation in this build assignment. An app-hosted test must follow the repository's test coordination rules. Cross-board relations are lineage only: verify the accepted prerequisite contract/revision explicitly and report a blocker if missing; never bypass it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-2a1305`.
4. Commit with `Manna: mn-2a1305` and run `agent-do manna done mn-2a1305` only after the work is verified.

## Filed execution gates and references

Local prerequisites: mn-8af047.
Read the full locked design in parent track mn-a2b986 before implementation.
- informed_by: manna://mb-87598702f834dad27f9bb5856a2072ea/mn-702ea1 (Existing host wake implementation; reuse contract).

Cross-board relations are references, not automatic claim blockers. Read accepted source/contract receipts on the named board before dependent implementation; if unavailable or unaccepted, report the prerequisite and do not substitute a guessed interface.
