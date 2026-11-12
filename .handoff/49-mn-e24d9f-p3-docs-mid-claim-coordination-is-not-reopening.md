---
workflow: 2
manna: mn-e24d9f
track: null
source: holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 12
base_commit: 8ef6c50ae8040e5ae65f576e88f5353666133c7a
scope: '[P3][DOCS] Mid-claim coordination is not reopening'
inputs:
- holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 12
binding: sha256:851c3e633e2e02e8109bee34c6c173127109a8d275870d63bc42fa432440e67d
---

# Handoff: [P3][DOCS] Mid-claim coordination is not reopening

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e24d9f
```

## Scope

[P3][DOCS] Mid-claim coordination is not reopening

## Inputs

- holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 12

## Work order

Doctrine (Erik, 09-22): a claim-holder may take drops and notes while an item is in_progress; that is coordination, not a reopen. Record it in the manna docs next to the closing doctrine, and make manna lint never flag a drop or note on an in_progress item as a reopen. Done when the doc states it and lint carries a test for it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e24d9f`.
4. Commit with `Manna: mn-e24d9f` and run `agent-do manna done mn-e24d9f` only after the work is verified.
