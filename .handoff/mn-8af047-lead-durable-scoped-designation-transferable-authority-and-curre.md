---
workflow: 2
manna: mn-8af047
track: mn-a2b986
source: Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
base_commit: 5229e77b91e408f7833fd646d021e4a0d427f294
scope: 'Lead: durable scoped designation, transferable authority and current handoff'
inputs:
- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
binding: sha256:ad08239c8232bfe8c4cce7346615f59be574e37fd5416a09a8d8abb4d870c37b
---

# Handoff: Lead: durable scoped designation, transferable authority and current handoff

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-8af047
```

## Scope

Lead: durable scoped designation, transferable authority and current handoff

## Inputs

- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff

## Work order

Build the standalone lead designation and transfer foundation for the parent plan. One accountable lead per canonical project/track; track precedence over project; one session may lead several scopes. Bind exact existing session identity/proof and generation, authority grants, brief pointers and append-only history. No designation-triggered work or launch; no implicit operator/publishing permissions. Reuse managed grants and existing identity proof paths, and define a stable machine-readable contract plus fixtures for Holy. Transfer works with the old lead absent, retains worker assignments and historical evidence, routes future decisions to the new lead, and fences old/in-flight authority at the actual effect. Existing valid approvals remain valid unless their revision/policy/revocation conditions invalidate them; new old-lead decisions refuse. Reconstruct current brief/read model from canonical records with unavailable sources named, not a copied ledger.

Acceptance: real CLI fixtures for project fallback and track override, concurrent appointment/transfer, same session on multiple scopes, dead/unavailable outgoing lead, restart, retained valid historical decisions, revoked/new-old-lead rejection under lock, authority does not increase on designation, no worker spawn, and standalone operation without Holy. Publish versioned read/mutation contract and fixtures before dependent lanes consume it. Include precise recovery/idempotency and audit behavior, and test partial write recovery. Select the narrow owning subsystem in the initial source review and document it.

Delivery: read the parent track's full locked plan and existing repository rules. Implement only this item's scope using existing Manna/Coord/MI/Holy mechanisms. No new top-level tool, parallel backlog or duplicate identity/approval store. Preserve concurrent work. Execute focused canonical tests, commit owned paths with this Manna trailer, seal receipts and return SUBMITTED for independent review; no self-acceptance. Separate installed/live field checks from source acceptance. No app installation/launch, live worker notification or spawning, board cleanup, push, PR, deployment or MI activation in this build assignment. An app-hosted test must follow the repository's test coordination rules. Cross-board relations are lineage only: verify the accepted prerequisite contract/revision explicitly and report a blocker if missing; never bypass it.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-8af047`.
4. Commit with `Manna: mn-8af047` and run `agent-do manna done mn-8af047` only after the work is verified.

## Filed execution gates and references

Local prerequisites: none.
Read the full locked design in parent track mn-a2b986 before implementation.
