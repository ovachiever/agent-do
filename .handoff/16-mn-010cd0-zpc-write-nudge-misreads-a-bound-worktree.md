---
workflow: 2
manna: mn-010cd0
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: zpc write-nudge misreads a bound worktree
inputs: []
binding: sha256:6fd102198b6de7d2ae1509f5a8279ce96a32554d7c870dce73b1b826bc4ee788
---

# Handoff: zpc write-nudge misreads a bound worktree

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-010cd0
```

## Scope

zpc write-nudge misreads a bound worktree

## Inputs

- None declared.

## Work order

The Stop hook hooks/claude/agent-do-zpc-write-nudge.sh resolves the store cwd-only ([ -d .zpc ] at line 61, STATE_DIR at :64, zpc_line_count glob at :80). In a worktree bound by 'agent-git worktree add' (mn-68d471) that .zpc is a pointer directory: the hook counts 0 memory lines forever and writes its baseline into the stub, so from the second Stop on it nudges 'you changed code and wrote no memory' even when every lesson landed in the primary store. Not lossy, just wrong. FIX: follow the pointer for STATE_DIR and zpc_line_count only, keeping cwd for the git change detection (the code moved in the worktree, the memory lives in the primary) — same trust rules as tools/agent-zpc/lib/common.sh:_zpc_store_pointer_target. The position-nudge hook shares the cwd-only check but only tests existence, so it is unaffected.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-010cd0`.
4. Commit with `Manna: mn-010cd0` and run `agent-do manna done mn-010cd0` only after the work is verified.
