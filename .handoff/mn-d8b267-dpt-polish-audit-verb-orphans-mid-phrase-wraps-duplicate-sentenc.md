---
workflow: 2
manna: mn-d8b267
track: null
source: null
base_commit: b0b668ec478c7d654de3d800b48d18f427544dde
scope: 'dpt: polish audit verb — orphans, mid-phrase wraps, duplicate sentences, floating controls, clipped captions, overflow'
inputs: []
binding: sha256:3e0dfa05fbf563549b9eb3610f4570891d1a77df3a2178961b81654524b7622e
---

# Handoff: dpt: polish audit verb — orphans, mid-phrase wraps, duplicate sentences, floating controls, clipped captions, overflow

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-d8b267
```

## Scope

dpt: polish audit verb — orphans, mid-phrase wraps, duplicate sentences, floating controls, clipped captions, overflow

## Inputs

- None declared.

## Work order

Fold rounds/home1/round2/polish_audit.js into agent-dpt as a scan that runs in the live page (agent-do browse) and reports each finding with the element and text, so every design candidate is audited by measurement before Erik sees it. Ruled as a law in the palingenesis canon 2026-09-18. TAXONOMY GATE: new verb on an existing tool — awaits Erik's approval before any code.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-d8b267`.
4. Commit with `Manna: mn-d8b267` and run `agent-do manna done mn-d8b267` only after the work is verified.
