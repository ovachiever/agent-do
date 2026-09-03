---
workflow: 2
manna: mn-d4b0fd
track: null
source: null
base_commit: c946237d65f2d39e5cd4ca6dc62619935a38dd71
scope: 'agent-pangram: paid Pangram API tool'
inputs: []
binding: sha256:a06ca929a766c1a015370dcb0e67571d8bad42960e4c76d07aa08f64b9636761
---

# Handoff: agent-pangram: paid Pangram API tool

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-d4b0fd
```

## Scope

agent-pangram: paid Pangram API tool

## Inputs

- None declared.

## Work order

Erik-approved 2026-09-03 (taxonomy ruling mn-1aaad3). New tool wrapping Pangram's paid API: document scan, per-sentence heatmap, batch mode. Consumer is the substack-writings invariant program (mn-739746 there): operating-curve experiments, draft diagnostics, and targeted re-speak workflow (Erik ruled heatmap-targeted re-dictation approved, with AI disclosure standing regardless of score). Connect-Snapshot-Interact-Verify-Save contract; key via env, never committed.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-d4b0fd`.
4. Commit with `Manna: mn-d4b0fd` and run `agent-do manna done mn-d4b0fd` only after the work is verified.
