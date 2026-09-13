---
workflow: 2
manna: mn-78ebe6
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'guard: pre-commit prose lint for non-Claude harnesses (calls deai)'
inputs: []
binding: sha256:558b77dedbf1a931a0620fce37f2356d5d6277218921f53ed8e9209373a4a6ce
---

# Handoff: guard: pre-commit prose lint for non-Claude harnesses (calls deai)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-78ebe6
```

## Scope

guard: pre-commit prose lint for non-Claude harnesses (calls deai)

## Inputs

- None declared.

## Work order

Option E. Warn-only pre-commit guard (coord guard pattern) linting changed prose files at commit time — catches codex/droid/cursor output that never passes through Claude hooks. Blocked by the deai tool.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-78ebe6`.
4. Commit with `Manna: mn-78ebe6` and run `agent-do manna done mn-78ebe6` only after the work is verified.
