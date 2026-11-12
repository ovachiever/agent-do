---
workflow: 2
manna: mn-f1604f
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk E: ambient hooks (board injection, auto-claim, floor nudges)'
inputs: []
binding: sha256:39377f6e0eab06dc1032f99e036dae66cc3d62143e6876dc1e25bb7c06a19cb6
---

# Handoff: Moon trunk E: ambient hooks (board injection, auto-claim, floor nudges)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-f1604f
```

## Scope

Moon trunk E: ambient hooks (board injection, auto-claim, floor nudges)

## Inputs

- None declared.

## Work order

SessionStart/PreToolUse; all spawns bounded; nudge mode, never bricks a session.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-f1604f`.
4. Commit with `Manna: mn-f1604f` and run `agent-do manna done mn-f1604f` only after the work is verified.
