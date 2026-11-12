---
workflow: 2
manna: mn-6be265
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'zpc security: a tracked .zpc store injects a repo''s own text as project memory'
inputs: []
binding: sha256:204fb5740395582b5a22f464893468f162032c43895ce328405995b914b2a048
---

# Handoff: zpc security: a tracked .zpc store injects a repo's own text as project memory

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-6be265
```

## Scope

zpc security: a tracked .zpc store injects a repo's own text as project memory

## Inputs

- None declared.

## Work order

ADJACENT to mn-84b9dc, found while closing it, NOT introduced by it. .zpc/ is gitignored in this repo but nothing stops any other repository from tracking .zpc/memory/lessons.jsonl. On clone it is a directory the cloning user owns, so the store walk accepts it and the session-start hook injects its contents under a heading that tells the agent this is the project's recorded truth (hooks/claude/agent-do-session-start.sh, append_zpc_memory). Repo content still becomes agent instructions; mn-84b9dc only closed the redirection half (a repo can no longer point at ANOTHER store). SCOPE: this is a design decision, not a bug fix — tests/test_worktree_binding.py::test_binding_is_bounded currently asserts a tracked store IS respected, on the reading that memory travelling with a branch is legitimate. Options: (a) keep, documented; (b) refuse stores git tracks (git ls-files --error-unmatch), which breaks the deliberate tracked-store case; (c) accept tracked stores but mark injected content as untrusted in the hook's heading. Erik picks.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-6be265`.
4. Commit with `Manna: mn-6be265` and run `agent-do manna done mn-6be265` only after the work is verified.
