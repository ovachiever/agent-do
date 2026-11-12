---
workflow: 2
manna: mn-37768a
track: mn-b7a0cc
source: 'Erik ratified 2026-09-03; consumer: Holy board mode + web cockpit consistency'
base_commit: 1a7b146dddcb7e4ae6f826829883f260ab8ed038
scope: 'manna state --json: attach cached AI digests so every face renders the same one-liner'
inputs:
- 'Erik ratified 2026-09-03; consumer: Holy board mode + web cockpit consistency'
binding: sha256:c07c2fcbfd32151b7d0eefb536951fdbf99fe2242d09105ef6ede7bbbe6b5228
---

# Handoff: manna state --json: attach cached AI digests so every face renders the same one-liner

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-37768a
```

## Scope

manna state --json: attach cached AI digests so every face renders the same one-liner

## Inputs

- Erik ratified 2026-09-03; consumer: Holy board mode + web cockpit consistency

## Work order

Two digest caches exist for the same items: serve generates and caches one-liners in ~/.agent-do/manna/serve/digests/<slug>.json for the web cockpit, and Holy's native board generates its own into its SQLite — same item can render different digests in the two faces, and every new client pays the generation cost again. Fix at the contract: manna state --json reads the serve digest cache when present and attaches digest (and summary, when cached) fields to each row — attach-only, never generate (the core stays model-free and fast; generation ownership stays with the presentation layers that hold API access). Serve's own post-derive attachment then collapses to redundancy it can drop; Holy prefers attached values and generates only gaps (sibling holy-ghostty pre-warm ticket filed today). Document the cache as shared presentation state readable by any human-facing client, agents still never read digests (keep the digest.py header doctrine, amended from 'no one reads them' to 'no agent reads them, any human face may'). House pattern registry+contracts+tests+docs; acceptance: state output carries digest fields exactly matching the serve cache, absent fields when no cache exists, zero added latency measurable on a cache-miss board.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-37768a`.
4. Commit with `Manna: mn-37768a` and run `agent-do manna done mn-37768a` only after the work is verified.
