---
workflow: 2
manna: mn-c3145f
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk C: agent-do attest (stamp/verify/doctor)'
inputs: []
binding: sha256:5eb5935a8d8d807d23bfabed07af7659650984de28c84f98aafa21df7e9abd27
---

# Handoff: Moon trunk C: agent-do attest (stamp/verify/doctor)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c3145f
```

## Scope

Moon trunk C: agent-do attest (stamp/verify/doctor)

## Inputs

- None declared.

## Work order

Harness-derived provenance trailers; doctor generates per-harness attribution doc. Never model self-report. Charter ground: Law 6, self-report is inference, not readout; the stamp is the outputs-against-ground-truth organ.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c3145f`.
4. Commit with `Manna: mn-c3145f` and run `agent-do manna done mn-c3145f` only after the work is verified.
