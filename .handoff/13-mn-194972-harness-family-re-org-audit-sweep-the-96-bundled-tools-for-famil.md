---
workflow: 2
manna: mn-194972
track: mn-455a88
source: media taxonomy discussion 2026-07-22
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Harness: family re-org audit — sweep the 96 bundled tools for family candidates'
inputs:
- media taxonomy discussion 2026-07-22
binding: sha256:7cc7101be7c6dbb4ac42782c7b1e19062d077e211e232df0649cf0b23e67287e
---

# Handoff: Harness: family re-org audit — sweep the 96 bundled tools for family candidates

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-194972
```

## Scope

Harness: family re-org audit — sweep the 96 bundled tools for family candidates

## Inputs

- media taxonomy discussion 2026-07-22

## Work order

The taxonomy gate governs future tools; this audits the EXISTING surface by the same rule. Sweep registry.yaml for flat tools that read as verbs on a shared domain (candidates to evaluate, not prejudge: perception tools, messaging tools, per-vendor cloud tools vs the cloud family surface, dns/net). Output: a proposal doc mapping keep-flat vs fold-into-family with migration cost per tool (family surfaces keep legacy leaf commands working, hardware precedent), then Erik rules. No renames land without his blessing.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-194972`.
4. Commit with `Manna: mn-194972` and run `agent-do manna done mn-194972` only after the work is verified.
