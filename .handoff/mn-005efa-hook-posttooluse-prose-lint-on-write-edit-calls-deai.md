---
workflow: 2
manna: mn-005efa
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'hook: PostToolUse prose lint on Write/Edit (calls deai)'
inputs: []
binding: sha256:3d7c39858a74c696e3f57f09da1166a2711c6051796cd2692cb2294e970c45fd
---

# Handoff: hook: PostToolUse prose lint on Write/Edit (calls deai)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-005efa
```

## Scope

hook: PostToolUse prose lint on Write/Edit (calls deai)

## Inputs

- None declared.

## Work order

Option C. Sibling of agent-do-quantity-check.py, registered the same way: fires on Write/Edit of prose files (.md and friends; path-based register detection — drafts/ gets essay pack, code files skipped), runs deai, injects flags as additionalContext so the writing agent fixes before finishing. Proven feedback pattern (quantity check demonstrates the loop). Blocked by the deai tool.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-005efa`.
4. Commit with `Manna: mn-005efa` and run `agent-do manna done mn-005efa` only after the work is verified.
