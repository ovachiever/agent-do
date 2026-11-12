---
workflow: 2
manna: mn-13d14f
track: null
source: holy-ghostty zpc les-6d2726; 2026-09-24 session
base_commit: 8ef6c50ae8040e5ae65f576e88f5353666133c7a
scope: '[P1][MANNA] reconcile walks .dev/ and floods drift.yaml with doc_reference noise'
inputs:
- holy-ghostty zpc les-6d2726; 2026-09-24 session
binding: sha256:27d4b833a1e75829c336208b73278f0be634eefef102b22a1589b6dfbb526933
---

# Handoff: [P1][MANNA] reconcile walks .dev/ and floods drift.yaml with doc_reference noise

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-13d14f
```

## Scope

[P1][MANNA] reconcile walks .dev/ and floods drift.yaml with doc_reference noise

## Inputs

- holy-ghostty zpc les-6d2726; 2026-09-24 session

## Work order

09-24 in holy-ghostty: manna reconcile wrote 10,529 doc_reference findings (953 distinct ids) whose evidence paths all start with .dev/mn-b775ac-soak/home/, a 9.3 GB copy of session transcripts from other projects, against 50 doc_reference findings in the committed drift.yaml; the +42,310-line file was discarded on purpose (holy-ghostty zpc les-6d2726). Fix: the doc scan honours .gitignore, or at minimum skips .dev/, and drift.yaml records the scanned roots so a flood is diagnosable. Done when reconcile in a repo whose ignored .dev/ holds transcripts produces no finding with an evidence path under .dev/.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-13d14f`.
4. Commit with `Manna: mn-13d14f` and run `agent-do manna done mn-13d14f` only after the work is verified.
