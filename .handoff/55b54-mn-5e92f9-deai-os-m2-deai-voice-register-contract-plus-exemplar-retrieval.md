---
workflow: 2
manna: mn-5e92f9
track: mn-ad9fc2
source: null
base_commit: c7be565ecca8edb5ff0c397a2a6217b44669fab3
scope: 'DEAI OS M2: deai voice, register contract plus exemplar retrieval'
inputs: []
binding: sha256:f3b76e10c3b66ba79fe02cb06e3c8d5bf733df1149a0f1224dfe303b062eb18c
---

# Handoff: DEAI OS M2: deai voice, register contract plus exemplar retrieval

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-5e92f9
```

## Scope

DEAI OS M2: deai voice, register contract plus exemplar retrieval

## Inputs

- None declared.

## Work order

Spec 3. The formation organ: emits distilled register contract plus corpus exemplars at write time. Acceptance: exemplars hash-trace to certified corpus.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-5e92f9`.
4. Commit with `Manna: mn-5e92f9` and run `agent-do manna done mn-5e92f9` only after the work is verified.
