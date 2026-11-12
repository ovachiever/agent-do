---
workflow: 2
manna: mn-fa98a3
track: mn-b7a0cc
source: null
base_commit: 87781bab78067fcd806ee540a094c68cb5183803
scope: 'manna handoff: the Completion section states the closing rule'
inputs: []
binding: sha256:3f5bcccfe4e2461814c2d4a68ba49c54e6e020097216ecd0752cd92401398ce4
---

# Handoff: manna handoff: the Completion section states the closing rule

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-fa98a3
```

## Scope

manna handoff: the Completion section states the closing rule

## Inputs

- None declared.

## Work order

Generated work orders (tools/agent-manna/src/workflow.rs, the '## Completion' template) say 'run manna done only after the work is verified' and never say what verified means; Holy workers read it as 'after Erik accepts' and held 11 items in_progress for days (2026-09-09). Change the template text: verified = this file's verification steps passed plus the trailer commit; close on that; a check needing Erik's judgment is filed as its own item ('field check: ...', owner Erik) and this item closes; nothing reopens, a failed check is a new item citing this id. Update the fixtures and tests that pin the template. Ruling recorded in CLAUDE.md Manna conventions and zpc decision 2026-09-09.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-fa98a3`.
4. Commit with `Manna: mn-fa98a3` and run `agent-do manna done mn-fa98a3` only after the work is verified.
