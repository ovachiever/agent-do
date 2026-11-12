---
workflow: 2
manna: mn-15fed0
track: mn-b7a0cc
source: mn-613088 build, 2026-08-24
base_commit: 97b0f1cef30cd98e4ed1387d00b5a01047fb273e
scope: 'manna: typed decision state replaces the [ERIK] title convention'
inputs:
- mn-613088 build, 2026-08-24
binding: sha256:dcd200a2e5808397acbb2d554a71c39546742d2f91d12e6dfcd9b249c129a91e
---

# Handoff: manna: typed decision state replaces the [ERIK] title convention

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-15fed0
```

## Scope

manna: typed decision state replaces the [ERIK] title convention

## Inputs

- mn-613088 build, 2026-08-24

## Work order

manna serve's NEEDS DECISION section detects [ERIK]/[HUMAN]/[DECISION] in titles because the board has no typed 'a human must rule' state. Add one (a field or a status the lifecycle verbs respect) so the convention becomes data: claim refuses a decision-gated item until the ruling is recorded, and the page reads the field, not the title. Migrate existing marked titles. Surfaced building mn-613088 (2026-08-24).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-15fed0`.
4. Commit with `Manna: mn-15fed0` and run `agent-do manna done mn-15fed0` only after the work is verified.
