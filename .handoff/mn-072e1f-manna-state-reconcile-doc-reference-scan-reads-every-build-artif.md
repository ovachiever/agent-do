---
workflow: 2
manna: mn-072e1f
track: mn-b7a0cc
source: 'Erik, 2026-09-02 17:07: ''go ahead and file the manna in agent-do to fix this'' (after asking why the first board read takes seconds instead of milliseconds)'
base_commit: 2e08f4b345d1c78930bd0cc0574868b2ff34dd6b
scope: 'manna state/reconcile: doc-reference scan reads every build artifact under .dev (12 s per read in holy-ghostty)'
inputs:
- 'Erik, 2026-09-02 17:07: ''go ahead and file the manna in agent-do to fix this'' (after asking why the first board read takes seconds instead of milliseconds)'
binding: sha256:f389524efedd1a6342d350cc55495d92c610902f216bdfc8ee727a72c466a837
---

# Handoff: manna state/reconcile: doc-reference scan reads every build artifact under .dev (12 s per read in holy-ghostty)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-072e1f
```

## Scope

manna state/reconcile: doc-reference scan reads every build artifact under .dev (12 s per read in holy-ghostty)

## Inputs

- Erik, 2026-09-02 17:07: 'go ahead and file the manna in agent-do to fix this' (after asking why the first board read takes seconds instead of milliseconds)

## Work order

Symptom: 'agent-do manna state --json' takes 12–15 s wall (8.5 s user, 5.8 s sys) in holy-ghostty, and 'manna reconcile --json' the same; the ledger itself is 101 rows. Holy's Board mode and manna serve both pay it on every read.

Cause (profiled 2026-09-02 with 'sample' on manna-core, 4,125 of 4,128 samples): derive_board_state runs the live reconcile, whose check_doc_references → scan_dir_for_ids (tools/agent-manna/src/main.rs, doc_reference_dirs) recursively opens and reads every file under 1 MB in .handoff, .dev, .zpc, and ~/.claude/projects/<flat>/memory looking for mn- ids. In holy-ghostty .dev holds 123,235 files / 12 GB (DerivedData, worktrees, xcresult bundles, artifacts) against 5,958 tracked files, so the scan reads the build tree, and the cost grows with every lane's build.

Fix: keep the doc_reference check but make scan_dir_for_ids scan documents only — either an allowlist of text extensions (.md .txt .yaml .yml .json .jsonl) or prune build/cache trees by name (DerivedData*, worktrees, *.xcresult, .build, target, node_modules, Build, *.noindex) — and add a regression test with a fixture .dev containing a large non-doc subtree. Acceptance: manna state --json in holy-ghostty under 1 s wall with the same doc_reference findings (84 today) as before; manna serve's /api/state inherits it.

Receipts: sample profile and timings in Holy session claude-76c4ae07f5c140e5 on 2026-09-02; Holy side mitigated with a per-repo state cache (holy-ghostty bc7ebb722) but every first open still pays the scan.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-072e1f`.
4. Commit with `Manna: mn-072e1f` and run `agent-do manna done mn-072e1f` only after the work is verified.
