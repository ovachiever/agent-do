---
workflow: 2
manna: mn-8f9ef3
track: mn-b7a0cc
source: mn-613088 rescoped 2026-08-24; original trunk F description
base_commit: 97b0f1cef30cd98e4ed1387d00b5a01047fb273e
scope: 'Board view: policy/floor layer and notify rules (trunk F remainder)'
inputs:
- mn-613088 rescoped 2026-08-24; original trunk F description
binding: sha256:0dbb04ed1681496d475a98e68012642781af06f25520a22907a031a2144f7c3a
---

# Handoff: Board view: policy/floor layer and notify rules (trunk F remainder)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-8f9ef3
```

## Scope

Board view: policy/floor layer and notify rules (trunk F remainder)

## Inputs

- mn-613088 rescoped 2026-08-24; original trunk F description

## Work order

The rest of Moon trunk F's original scope, layered onto the page manna serve now renders: floors and claim_policy from trunk B/D shown per item, and notify rules (claim_conflict, unblocked, floor_violation) emitted from board transitions the daemon already observes. Read model first; the page stays read-only. Blocked on the policy engine (mn-404dd7).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-8f9ef3`.
4. Commit with `Manna: mn-8f9ef3` and run `agent-do manna done mn-8f9ef3` only after the work is verified.
