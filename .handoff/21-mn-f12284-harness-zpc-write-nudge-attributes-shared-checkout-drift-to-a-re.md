---
workflow: 2
manna: mn-f12284
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Harness: zpc write-nudge attributes shared-checkout drift to a read-only session'
inputs: []
binding: sha256:f3e0f944e929432070d86a105369b713b40927dd68352afa993063cc3660c35d
---

# Handoff: Harness: zpc write-nudge attributes shared-checkout drift to a read-only session

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-f12284
```

## Scope

Harness: zpc write-nudge attributes shared-checkout drift to a read-only session

## Inputs

- None declared.

## Work order

Stop nudge fired on session-fad251dac02f (read-only PR triage, zero file writes) naming .github/workflows/ci.yml — drift actually belonged to peer codex-01a001a9d8637412 working the same checkout. The nudge diffs the working tree, not the session's own writes, so any stopping session inherits every peer's uncommitted changes. Sibling of mn-010cd0 (worktree misread); fix likely shares a cause: scope the nudge to files the session itself touched, or cross-check coord peers before firing.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-f12284`.
4. Commit with `Manna: mn-f12284` and run `agent-do manna done mn-f12284` only after the work is verified.
