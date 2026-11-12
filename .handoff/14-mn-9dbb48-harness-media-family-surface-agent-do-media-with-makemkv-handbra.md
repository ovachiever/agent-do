---
workflow: 2
manna: mn-9dbb48
track: mn-455a88
source: media taxonomy discussion 2026-07-22 + PR 21/22 reviews
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Harness: media family surface — agent-do media with makemkv/handbrake as first providers'
inputs:
- media taxonomy discussion 2026-07-22 + PR 21/22 reviews
binding: sha256:9efd65a64ff8f01ca0c35ed64727c7d65bfd777a6b4b9432a99f4d9b04dbda60
---

# Handoff: Harness: media family surface — agent-do media with makemkv/handbrake as first providers

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9dbb48
```

## Scope

Harness: media family surface — agent-do media with makemkv/handbrake as first providers

## Inputs

- media taxonomy discussion 2026-07-22 + PR 21/22 reviews

## Work order

One registry entry, verbs rip/convert (later tag, library); providers underneath per the hardware/meetings pattern. Guidance posted to PRs #21/#22 asking Chris to reshape; handbrake bundles as a provider, makemkv provider can carry its DMCA-adjacent language at the implementation layer where the family surface stays neutral verbs. Lands via Chris's re-rolled PRs; this item tracks the family surface itself (registry entry, contracts, family tool dispatcher).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9dbb48`.
4. Commit with `Manna: mn-9dbb48` and run `agent-do manna done mn-9dbb48` only after the work is verified.
