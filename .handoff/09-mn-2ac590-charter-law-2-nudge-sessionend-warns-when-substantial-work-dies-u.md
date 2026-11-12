---
workflow: 2
manna: mn-2ac590
track: mn-455a88
source: Charter Law 2
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Charter Law 2 nudge: SessionEnd warns when substantial work dies unwritten'
inputs:
- Charter Law 2
binding: sha256:6a23dd5206ac7550c36de85855676a5086ff0cde9be440a37476b38b62ad5410
---

# Handoff: Charter Law 2 nudge: SessionEnd warns when substantial work dies unwritten

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-2ac590
```

## Scope

Charter Law 2 nudge: SessionEnd warns when substantial work dies unwritten

## Inputs

- Charter Law 2

## Work order

Warn-only, rides existing SessionEnd hook: if session had significant edits/findings and no handoff/commit/exogram, nudge once. Unexternalized state dies with the window. Bounded like all hook spawns.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-2ac590`.
4. Commit with `Manna: mn-2ac590` and run `agent-do manna done mn-2ac590` only after the work is verified.
