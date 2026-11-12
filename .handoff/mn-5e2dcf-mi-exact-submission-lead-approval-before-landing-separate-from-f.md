---
workflow: 2
manna: mn-5e2dcf
track: mn-a2b986
source: Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
base_commit: 5229e77b91e408f7833fd646d021e4a0d427f294
scope: 'MI: exact-submission lead approval before landing, separate from final acceptance'
inputs:
- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
binding: sha256:8fdb0b46f32d6264eeb7e7fe55acef0eed39c529e955caaeb8bf4aa93389d952
---

# Handoff: MI: exact-submission lead approval before landing, separate from final acceptance

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-5e2dcf
```

## Scope

MI: exact-submission lead approval before landing, separate from final acceptance

## Inputs

- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff

## Work order

Extend existing Managed Integration with explicit checks-first and review-and-checks repository policies, preserving existing opt-in/off behavior. Consume the accepted lead authority contract; review-and-checks is the team default. Do not enable a repo during implementation. Bind approval to canonical board/item, claim incarnation/attempt, submission id, revision, work-order/policy evidence and authorized reviewer. Keep approval-to-integrate distinct from final acceptance. Reject author-as-independent-reviewer when policy requires independence.

Acceptance: refuse missing/revoked approval, old lead new approval, resubmission, reclaim, reseal, policy change and altered integration content. Define what exact candidate/tree approval covers; a changed base must be rebuilt/checked, and conflict resolutions or introduced changes may not inherit approval for different code. Valid historical approvals survive lead transfer unless independently invalidated; a transfer revokes new former-lead decisions. Recheck conditions before ref update and recovery-before-landing; after-landing recovery only completes records. Retain exact-once landing, dirty target protections, no credentials in check environment and all current MI regressions. Exercise two submissions, failed review/correction, transfer mid-check, interrupted authority/approval writes, and preserved checks-first behavior. No live pilot in this item.

Delivery: read the parent track's full locked plan and existing repository rules. Implement only this item's scope using existing Manna/Coord/MI/Holy mechanisms. No new top-level tool, parallel backlog or duplicate identity/approval store. Preserve concurrent work. Execute focused canonical tests, commit owned paths with this Manna trailer, seal receipts and return SUBMITTED for independent review; no self-acceptance. Separate installed/live field checks from source acceptance. No app installation/launch, live worker notification or spawning, board cleanup, push, PR, deployment or MI activation in this build assignment. An app-hosted test must follow the repository's test coordination rules. Cross-board relations are lineage only: verify the accepted prerequisite contract/revision explicitly and report a blocker if missing; never bypass it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-5e2dcf`.
4. Commit with `Manna: mn-5e2dcf` and run `agent-do manna done mn-5e2dcf` only after the work is verified.

## Filed execution gates and references

Local prerequisites: mn-8af047.
Read the full locked design in parent track mn-a2b986 before implementation.
