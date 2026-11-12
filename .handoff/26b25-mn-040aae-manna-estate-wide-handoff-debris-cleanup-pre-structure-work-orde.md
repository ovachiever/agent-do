---
workflow: 2
manna: mn-040aae
track: mn-b7a0cc
source: Erik ruling 2026-08-22
base_commit: f82ededffbe81a9b2ba8c92cfaf9c1ea2a4ff291
scope: 'Manna: estate-wide handoff-debris cleanup — pre-structure work orders converge or archive'
inputs:
- Erik ruling 2026-08-22
binding: sha256:888016becfd7e77c52380450792a408cf34244d4566e4591be27b3db788346b6
---

# Handoff: Manna: estate-wide handoff-debris cleanup — pre-structure work orders converge or archive

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-040aae
```

## Scope

Manna: estate-wide handoff-debris cleanup — pre-structure work orders converge or archive

## Inputs

- Erik ruling 2026-08-22

## Work order

Ratified by Erik 2026-08-22. Before the enforced workflow existed, work orders accumulated in per-repo sprawl: .handoffs/ (plural), .dev/session-prompts/, freeform docs in .handoff/ roots, and claim-bearing markdown scattered elsewhere. The structure that cannot be broken now exists; the debris predates it. Sweep every estate repo (the 21-board list from the 2026-08-21 migration sweep is the roster): (1) run manna reconcile — its workflow_sprawl and doc_reference findings ARE the debris inventory; (2) live work orders outside .handoff/ get ingested through the tool (the mixed-convergence import machinery, never hand-moves); (3) historical/superseded docs move to .handoff/archive/ once mn-d2d67b lands; (4) .handoffs/ plural dirs and .dev/session-prompts/ empty out and disappear; (5) per-repo board-only commits, receipts per repo. Done means: zero workflow_sprawl findings estate-wide; no .handoffs/ directory exists anywhere; .dev/session-prompts/ gone or verifiably historical-only.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-040aae`.
4. Commit with `Manna: mn-040aae` and run `agent-do manna done mn-040aae` only after the work is verified.
