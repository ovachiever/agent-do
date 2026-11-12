---
workflow: 2
manna: mn-807f18
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk B: manna floor/claim_policy/gh_issue metadata + sync github + export --registry'
inputs: []
binding: sha256:4e23fb3661035dcbd368cdadd42e4ec3fa80ce35ca7187359a27fb5faaffc232
---

# Handoff: Moon trunk B: manna floor/claim_policy/gh_issue metadata + sync github + export --registry

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-807f18
```

## Scope

Moon trunk B: manna floor/claim_policy/gh_issue metadata + sync github + export --registry

## Inputs

- None declared.

## Work order

Rust core. Registry becomes a build product. Decide identity bridge (operator GH login recommended) here. Claim = one command that sets up the workspace: GH issue assign (atomic zero-push claim) + manna in_progress + canonical branch mn-<id>/<slug> + draft PR offered at first commit (WIP visibility, never the claim). Canonical branch names make CI branch-to-issue mapping self-documenting. Deploy workflows paths-ignore .manna/.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-807f18`.
4. Commit with `Manna: mn-807f18` and run `agent-do manna done mn-807f18` only after the work is verified.
