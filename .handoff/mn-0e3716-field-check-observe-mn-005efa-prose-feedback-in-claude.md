---
workflow: 2
manna: mn-0e3716
track: null
source: mn-005efa
base_commit: 1e6df1db1ea1c672660f7706721317465343aea3
scope: 'field check: observe mn-005efa prose feedback in Claude'
inputs:
- mn-005efa
binding: sha256:09ed6cc60f6133898f2d30a143a0ff3f1e053abe4ec3563494400a4b78325448
---

# Handoff: field check: observe mn-005efa prose feedback in Claude

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-0e3716
```

## Scope

field check: observe mn-005efa prose feedback in Claude

## Inputs

- mn-005efa

## Work order

Owner: Erik. Build reference: mn-005efa, local source commit 1904787. Coordinate a permitted hook installation and live Claude session after the no-install/no-launch build lane. Verify the installed agent-do-prose-lint.py wrapper and one PostToolUse Edit|Write|MultiEdit registration; Write a flagged drafts/prose.md and observe essay-register additionalContext, Edit it clean and observe no repeat findings, and Write a source-code file and observe no prose nudge. Synthetic hook, real deai CLI, and installer serialization tests already pass. This item owns installed-host acceptance only; it does not authorize an uncoordinated install or session launch. No screenshots or visual review are required for this text-only hook.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-0e3716`.
4. Commit with `Manna: mn-0e3716` and run `agent-do manna done mn-0e3716` only after the work is verified.
