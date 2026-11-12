---
workflow: 2
manna: mn-b7cb18
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'quantities: the authority does not know the model it runs on (claude-opus-5 absent)'
inputs: []
binding: sha256:7dba163d4b1039caf041736cbafa4092ff863352ee368abf623328797705f05b
---

# Handoff: quantities: the authority does not know the model it runs on (claude-opus-5 absent)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-b7cb18
```

## Scope

quantities: the authority does not know the model it runs on (claude-opus-5 absent)

## Inputs

- None declared.

## Work order

RECEIPT (measured 2026-08-04, after a0b5ff7): 'harness quantity lookup anthropic.claude-opus-5.max_tokens' exits 1, unknown key. 'harness quantity keys --prefix anthropic' lists opus-4-8, sonnet-5, haiku-4-5 and models_list.page_limit; grep for claude-opus-5 in models.yaml returns 0. So the authority built to stop agents inventing ceilings has no record for the current Opus model, which means a consumer asking for it correctly gets a refusal and the tempting fallback is exactly the literal the program forbids. WHAT: close the coverage gap and keep it closed — refresh the records ('models doctor' is the refresh path per CLAUDE.md), and add a coverage check so a model reachable through the router with no authority record is a loud failure rather than a silent unknown. The check belongs with the drift work (mn-741a02) if it fits there; decide and say which. WHY: an authority with holes teaches the workaround it exists to prevent.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-b7cb18`.
4. Commit with `Manna: mn-b7cb18` and run `agent-do manna done mn-b7cb18` only after the work is verified.
