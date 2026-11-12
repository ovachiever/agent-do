---
workflow: 2
manna: mn-4af2e6
track: mn-ad9fc2
source: null
base_commit: c7be565ecca8edb5ff0c397a2a6217b44669fab3
scope: 'DEAI OS M8: first pairs export plus receipted LoRA-DPO run'
inputs: []
binding: sha256:4e48dd144c6d78990040ebb959821e79bff4858ccb7ca1a2ab1805a5cbc51e63
---

# Handoff: DEAI OS M8: first pairs export plus receipted LoRA-DPO run

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-4af2e6
```

## Scope

DEAI OS M8: first pairs export plus receipted LoRA-DPO run

## Inputs

- None declared.

## Work order

Spec 5. Export pairs, one receipted run on a Studio local model, Erik-gated per run; base model is Erik's pick (spec 10.5).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-4af2e6`.
4. Commit with `Manna: mn-4af2e6` and run `agent-do manna done mn-4af2e6` only after the work is verified.
