---
workflow: 2
manna: mn-54cec0
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk G: VID adoption pass + NewCo portable spec (policy.yaml + 10-line workflow)'
inputs: []
binding: sha256:92ca1348df094bb3eebcfe714c2ad9136d8473630257b2d6403323bf77333970
---

# Handoff: Moon trunk G: VID adoption pass + NewCo portable spec (policy.yaml + 10-line workflow)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-54cec0
```

## Scope

Moon trunk G: VID adoption pass + NewCo portable spec (policy.yaml + 10-line workflow)

## Inputs

- None declared.

## Work order

Retrofit under the running workstream; portable spec is the file+engine, not prose.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-54cec0`.
4. Commit with `Manna: mn-54cec0` and run `agent-do manna done mn-54cec0` only after the work is verified.
