---
workflow: 2
manna: mn-404dd7
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk D: policy engine (init/show/check/install) + org scoping'
inputs: []
binding: sha256:32fedbe2008e512ca5ec3548a941d95008fc4c573ed5acf27bc66812720e5005
---

# Handoff: Moon trunk D: policy engine (init/show/check/install) + org scoping

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-404dd7
```

## Scope

Moon trunk D: policy engine (init/show/check/install) + org scoping

## Inputs

- None declared.

## Work order

policy.yaml as data; one engine with local and CI faces; inert outside policy scope. Includes policy doctor [--fix] + policy setup: verify/repair binary, registered harness hooks, repo git hooks, live stamping, gh auth, policy resolution. CI validates outcomes independent of local setup so missing installs degrade to advisory gaps, never enforcement holes. Charter ground: Law 7 (authority by source, never position: the CI wall) and Law 10 (model floors hold when context pressure pushes).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-404dd7`.
4. Commit with `Manna: mn-404dd7` and run `agent-do manna done mn-404dd7` only after the work is verified.
