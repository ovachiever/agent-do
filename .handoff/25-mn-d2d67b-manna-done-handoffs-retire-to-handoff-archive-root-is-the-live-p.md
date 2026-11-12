---
workflow: 2
manna: mn-d2d67b
track: mn-b7a0cc
source: Erik ruling 2026-08-22, numbering discussion
base_commit: f82ededffbe81a9b2ba8c92cfaf9c1ea2a4ff291
scope: 'Manna: done handoffs retire to .handoff/archive/ — root is the live plan only'
inputs:
- Erik ruling 2026-08-22, numbering discussion
binding: sha256:0841f34c4bdae8428acd2bdf6186f11ba5a405af5ff8a65ac5e94844d4af7d9e
---

# Handoff: Manna: done handoffs retire to .handoff/archive/ — root is the live plan only

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-d2d67b
```

## Scope

Manna: done handoffs retire to .handoff/archive/ — root is the live plan only

## Inputs

- Erik ruling 2026-08-22, numbering discussion

## Work order

Ratified by Erik 2026-08-22. Today a done item's handoff stays in .handoff/ root under its unnumbered mn- name; within a month the root is mostly dead files and the glance rots. Change: manna sync moves a done/closed item's handoff to .handoff/archive/ (same mn-<id>-<slug>.md name) in the same journaled transaction as the rename pass; prompt: pointer follows; lint flags a done handoff in root as presentation drift; README index keeps listing archived rows under a Completed section for traceability. Root invariant after this: every file in .handoff/ root is either a numbered live work order or a reference doc — nothing dead.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-d2d67b`.
4. Commit with `Manna: mn-d2d67b` and run `agent-do manna done mn-d2d67b` only after the work is verified.
