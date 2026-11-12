---
workflow: 2
manna: mn-96415d
track: mn-455a88
source: pairing sweep 2026-07-21
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Harness: doc_reference scan scope — archive noise and cross-board refs'
inputs:
- pairing sweep 2026-07-21
binding: sha256:271c50a6c3170d42a03fceb130245993993fb378fcdb95ffb70286403bc66239
---

# Handoff: Harness: doc_reference scan scope — archive noise and cross-board refs

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-96415d
```

## Scope

Harness: doc_reference scan scope — archive noise and cross-board refs

## Inputs

- pairing sweep 2026-07-21

## Work order

Pairing sweep 2026-07-21 findings: (1) aldebaran-group reports 1370 doc_references because months of archived handoffs/prompts reference retired IDs — the scan needs scope control (age cutoff, .mannaignore, or status-disagreement-only mode). (2) holy-ghostty flags agent-do's mn-b17dc6 as nonexistent — cross-board references read as missing because the scan only knows the local board; consider a known-foreign-boards allowlist or an mn-ID@repo citation convention. Both advisory-noise classes, no false fixes taken.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-96415d`.
4. Commit with `Manna: mn-96415d` and run `agent-do manna done mn-96415d` only after the work is verified.
