---
workflow: 2
manna: mn-6a43ba
track: mn-b7a0cc
source: Erik + session diagnosis 2026-09-02 (three failed installs behind one non-compiling in-flight file)
base_commit: da2748dbf573e5cb4fd7634ad9491489d2695dea
scope: 'coord: isolation nudge for concurrent build lanes — shared-checkout compile-state contention is real contention'
inputs:
- Erik + session diagnosis 2026-09-02 (three failed installs behind one non-compiling in-flight file)
binding: sha256:ff61d7dd938513c222328d1e65ffda7bdb5706a293aa9850a52712a9e58d2a07
---

# Handoff: coord: isolation nudge for concurrent build lanes — shared-checkout compile-state contention is real contention

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-6a43ba
```

## Scope

coord: isolation nudge for concurrent build lanes — shared-checkout compile-state contention is real contention

## Inputs

- Erik + session diagnosis 2026-09-02 (three failed installs behind one non-compiling in-flight file)

## Work order

Live incident 2026-09-02: four code lanes on the same branch with disjoint paths shared one holy-ghostty checkout; coord's isolation triggers (branch mismatch at agent-coord:46, path contention at :135-162) correctly stayed silent — yet a worker's mid-surgery file (HolySSHTransportManager.swift, uncommitted, non-compiling) made the tree unbuildable and blocked three production install attempts by other lanes. Gap: coord models WHO edits WHAT, not whether the shared tree compiles; disjoint-path build lanes still contend on compile state and build artifacts. Close it: when a writer declares focus with phase=building in a checkout that already has N>=1 other active building writers, fire the isolation nudge proactively (default-worktree posture for concurrent builders, honoring AGENT_DO_COORD_ISOLATION_NUDGE and the existing WORKTREE_CAVEAT about board/claims staying in the primary). Keep it a nudge, not a gate — same advisory register as the pre-commit guard. Optionally: coord status surfaces 'tree currently unbuildable' as a notice when any writer flags it (a cheap declared bit, not a build probe). Erik's mental model is 'workers default to worktrees'; this makes that true exactly when it matters and never when a lone lane works the checkout. House pattern registry+contracts+tests+docs; update CLAUDE.md's worktree paragraph to match.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-6a43ba`.
4. Commit with `Manna: mn-6a43ba` and run `agent-do manna done mn-6a43ba` only after the work is verified.
