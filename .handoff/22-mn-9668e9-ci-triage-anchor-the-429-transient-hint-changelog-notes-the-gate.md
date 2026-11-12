---
workflow: 2
manna: mn-9668e9
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'ci triage: anchor the 429 transient hint + CHANGELOG notes the gate-authoring opt-in'
inputs: []
binding: sha256:55e95b766384783ddb602604c7a07d38bbfcc82cfddd59eb16d1ac3fa3f25bf7
---

# Handoff: ci triage: anchor the 429 transient hint + CHANGELOG notes the gate-authoring opt-in

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9668e9
```

## Scope

ci triage: anchor the 429 transient hint + CHANGELOG notes the gate-authoring opt-in

## Inputs

- None declared.

## Work order

Two CodeRabbit minors accepted at merge of #23: (1) lib/ci_triage.py TRANSIENT_HINTS matches bare '429' as substring — version strings and byte counts false-flag transient; anchor to 'HTTP 429'/'429 Too Many Requests'. (2) CHANGELOG's C4 description omits that gate-authoring requires AGENT_DO_CI_GATE_AUTHORS (empty default), so out-of-the-box ci/** failures classify unknown; add the opt-in wording.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9668e9`.
4. Commit with `Manna: mn-9668e9` and run `agent-do manna done mn-9668e9` only after the work is verified.
