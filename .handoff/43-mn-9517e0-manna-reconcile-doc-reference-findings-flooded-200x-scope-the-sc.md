---
workflow: 2
manna: mn-9517e0
track: mn-b7a0cc
source: holy-ghostty board audit 2026-09-09 (10,290 doc_reference vs 13 landed_open)
base_commit: e2b9431f000a5eba057532d4925a1b05ec8d5cfd
scope: 'manna reconcile: doc_reference findings flooded 200x — scope the scan or tier the signal'
inputs:
- holy-ghostty board audit 2026-09-09 (10,290 doc_reference vs 13 landed_open)
binding: sha256:9e19574b4f39d385e14f5e5ae4275ea52774b0957777d72d9f415afb1df0d1c7
---

# Handoff: manna reconcile: doc_reference findings flooded 200x — scope the scan or tier the signal

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9517e0
```

## Scope

manna reconcile: doc_reference findings flooded 200x — scope the scan or tier the signal

## Inputs

- holy-ghostty board audit 2026-09-09 (10,290 doc_reference vs 13 landed_open)

## Work order

holy-ghostty's reconcile emits 10,290 doc_reference findings (46 two weeks ago): the .handoff corpus grew and every mn- id citation in every sealed work order now counts as a reference to verify, drowning the 13 real landed_open findings in noise and inflating drift badges (board showed drift 113+). Fix direction (worker's choice): scope doc_reference scanning to living docs (exclude .handoff/*.md and .handoff/.archive which cite ids as provenance BY DESIGN), or tier the output (landed_open/dead_claim/blocker_desync as findings; doc_reference as a collapsed count unless --verbose), or both. Acceptance: reconcile on holy-ghostty surfaces the actionable kinds first, doc noise under 100 or foldered, and the serve/native drift badges reflect actionable findings only.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9517e0`.
4. Commit with `Manna: mn-9517e0` and run `agent-do manna done mn-9517e0` only after the work is verified.
