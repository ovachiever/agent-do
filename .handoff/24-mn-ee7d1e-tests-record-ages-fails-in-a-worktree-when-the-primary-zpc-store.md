---
workflow: 2
manna: mn-ee7d1e
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'tests: record-ages fails in a worktree when the primary zpc store is non-empty — fixture isolation leak'
inputs: []
binding: sha256:117621fd9b37075a35fdd18273a49f027de412c856d062b1ee9c53153da91927
---

# Handoff: tests: record-ages fails in a worktree when the primary zpc store is non-empty — fixture isolation leak

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-ee7d1e
```

## Scope

tests: record-ages fails in a worktree when the primary zpc store is non-empty — fixture isolation leak

## Inputs

- None declared.

## Work order

test_record_ages.py::test_zpc_corrections_carry_their_age fails identically on clean main and PR trees when run from a git worktree on this machine, while GitHub CI passes it — the worktree binds zpc memory back to the primary store, so live session lessons leak into the fixture's inject output and the correction-age assertion reads the wrong records. Fixture should force an isolated store (AGENT_DO_HOME alone is evidently not enough under worktree binding).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-ee7d1e`.
4. Commit with `Manna: mn-ee7d1e` and run `agent-do manna done mn-ee7d1e` only after the work is verified.
