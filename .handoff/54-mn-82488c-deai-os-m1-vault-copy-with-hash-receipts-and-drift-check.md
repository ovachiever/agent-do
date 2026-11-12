---
workflow: 2
manna: mn-82488c
track: mn-ad9fc2
source: null
base_commit: c7be565ecca8edb5ff0c397a2a6217b44669fab3
scope: 'DEAI OS M1: vault COPY with hash receipts and drift check'
inputs: []
binding: sha256:25fd3272264e75e298fcd10f4d14b9f1ea664f6527527a450bb5f3ac4b78095d
---

# Handoff: DEAI OS M1: vault COPY with hash receipts and drift check

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-82488c
```

## Scope

DEAI OS M1: vault COPY with hash receipts and drift check

## Inputs

- None declared.

## Work order

Spec 2, 7-M1. Copy substack-writings/voice into this repo, hashes both sides, drift check standing; substack untouched (copy-never-move ruling); cutover later, Erik-gated.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-82488c`.
4. Commit with `Manna: mn-82488c` and run `agent-do manna done mn-82488c` only after the work is verified.
