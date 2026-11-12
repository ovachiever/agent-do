---
workflow: 2
manna: mn-00160d
track: mn-b7a0cc
source: null
base_commit: 87781bab78067fcd806ee540a094c68cb5183803
scope: 'manna reconcile: stale_claim finding for claims whose liveness cannot be verified'
inputs: []
binding: sha256:95666896bb0f8868846ee4dcccbb8b22f2e318af67ee7aa57ecd508b60f4c251
---

# Handoff: manna reconcile: stale_claim finding for claims whose liveness cannot be verified

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-00160d
```

## Scope

manna reconcile: stale_claim finding for claims whose liveness cannot be verified

## Inputs

- None declared.

## Work order

DeadClaim fires only when the claimant's process is provably gone. codex-* and cursor identities are opaque, so their claims never expire and in_progress becomes a permanent waiting room (Holy 2026-09-09: 11 items, claimants codex-*). Add a report-only finding stale_claim: status in_progress, claimed_at older than the coord idle threshold (reuse coord's named constant; no new literal, quantity doctrine), and no trailer commit for the id since claimed_at. proposed_fix names done (if landed_open also fires) or abandon. Never auto-fix: releasing a live opaque claim would strand a worker. Companion to the closing rule (ruling 2026-09-09).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-00160d`.
4. Commit with `Manna: mn-00160d` and run `agent-do manna done mn-00160d` only after the work is verified.
