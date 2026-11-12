---
workflow: 2
manna: mn-d86eae
track: mn-ad9fc2
source: null
base_commit: c7be565ecca8edb5ff0c397a2a6217b44669fab3
scope: 'DEAI OS M6: deai gate, one-command bundle'
inputs: []
binding: sha256:160d620b811dc9908eb79c7dfcf36203980023c1e32efd64227e5fc85afdfb83
---

# Handoff: DEAI OS M6: deai gate, one-command bundle

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-d86eae
```

## Scope

DEAI OS M6: deai gate, one-command bundle

## Inputs

- None declared.

## Work order

Spec 3. lint plus ensemble plus stats, typed exits, stdin; substack DRAFT GATE delegates. Acceptance: byte-identical flags on archived drafts.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-d86eae`.
4. Commit with `Manna: mn-d86eae` and run `agent-do manna done mn-d86eae` only after the work is verified.
