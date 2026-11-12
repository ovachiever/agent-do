---
workflow: 2
manna: mn-74982c
track: null
source: Erik's ask this session; tools/agent-aphrodite/README.md domain statement; les-6e1511
base_commit: 3aac717f2d84c34d07de955dde92415310afb546
scope: 'Aphrodite bench adapter: measure hand-built pages against a relational brief'
inputs:
- Erik's ask this session; tools/agent-aphrodite/README.md domain statement; les-6e1511
binding: sha256:4b8beb2b817c362becf64c111d81d94df45abc1d00fd7c706b4937883fc78f5c
---

# Handoff: Aphrodite bench adapter: measure hand-built pages against a relational brief

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-74982c
```

## Scope

Aphrodite bench adapter: measure hand-built pages against a relational brief

## Inputs

- Erik's ask this session; tools/agent-aphrodite/README.md domain statement; les-6e1511

## Work order

Erik (2026-09-15): leverage Aphrodite to supplement, not replace, natural design skill. Today observe/evaluate only remeasure Aphrodite's own programs; arbitrary pages are outside the domain. Proposed: a verb (e.g. 'aphrodite bench --page <html> --brief <json>') that binds a hand-built page to a brief via data-node=<id> attributes, runs the existing observation and nine-family evaluation, and emits the relational decomposition as ANNOTATION (never a rank; dpt floors and Erik's verdicts keep their roles). First consumers: Palingenesis design rounds (builders already tag data-node ids from round sim-2 on). NEW VERB = taxonomy gate: do not implement until Erik approves the verb name and shape.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-74982c`.
4. Commit with `Manna: mn-74982c` and run `agent-do manna done mn-74982c` only after the work is verified.
