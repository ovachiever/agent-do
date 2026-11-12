---
workflow: 2
manna: mn-42501b
track: null
source: holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 1
base_commit: 8ef6c50ae8040e5ae65f576e88f5353666133c7a
scope: '[P1][MANNA] Full report lands on the ledger at done; the drop note carries only the pointer'
inputs:
- holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 1
binding: sha256:101da16b5ba07e5ba4fdbb40717c3949a89b0c39fd0c21b6c7da57868c0db696
---

# Handoff: [P1][MANNA] Full report lands on the ledger at done; the drop note carries only the pointer

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-42501b
```

## Scope

[P1][MANNA] Full report lands on the ledger at done; the drop note carries only the pointer

## Inputs

- holy-ghostty/.handoff/SESSION-HANDOFF-2026-09-24.md §4 item 1

## Work order

Ruling (Erik, 09-22): when an agent finishes an item it writes its full last response, what was done, the receipts, what was left, onto the manna item at done; the drop or handoff note to another agent carries only the pointer (mn-id plus path). Pairs with mn-dd4384 (doorbell): the bell says the ledger has entries for you, the ledger holds the report. Done when manna done accepts a report (file or stdin) and stores it on the item, manna show prints it, and the holy-ghostty Board can render it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-42501b`.
4. Commit with `Manna: mn-42501b` and run `agent-do manna done mn-42501b` only after the work is verified.
