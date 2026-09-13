---
workflow: 2
manna: mn-e6e2e0
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'deai: prose-tell linter as a first-class tool with register packs'
inputs: []
binding: sha256:0ec382bff8f40b6333a4f36cf1850405d0059d3d68c710e5c5f1d6d416802033
---

# Handoff: deai: prose-tell linter as a first-class tool with register packs

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e6e2e0
```

## Scope

deai: prose-tell linter as a first-class tool with register packs

## Inputs

- None declared.

## Work order

Erik-approved 2026-09-13 (the de-AIer global hookup, option B — the keystone the hook and guard call). Migrate the canonical rulebook from substack-writings (scripts/lint-ai-speak.py + voice/ai-speak-lexicon.md, ceilings measured on Erik's 120k-word certified corpus) into an agent-do tool: agent-deai lint <file> [--register essay|email|default|product-answer]. Register packs are the design center — essay pack strict; default pack must NOT flag literal technical usage (structural, robust, architecture in code docs) or it cries wolf and dies; each pack carries its own ceilings and whitelists with provenance. Contracts gate stays green; substack-writings keeps a thin wrapper or migrates its draft gate to call this. New tells keep arriving from Erik's ear (three in three days: tour-guide, costume, wink) — design for cheap rule addition with a measured-ceiling requirement (no bare literals).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e6e2e0`.
4. Commit with `Manna: mn-e6e2e0` and run `agent-do manna done mn-e6e2e0` only after the work is verified.
