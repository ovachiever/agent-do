---
workflow: 2
manna: mn-8f0319
track: mn-455a88
source: zpc effectiveness audit 2026-08-26, deliveries.jsonl + telemetry events
base_commit: 1ff3616c097a1da3f77a80a97d602fe82120df51
scope: 'zpc triggers: honest delivery receipts + in-process matching'
inputs:
- zpc effectiveness audit 2026-08-26, deliveries.jsonl + telemetry events
binding: sha256:978e450fadfc43284cda2c5c07674b183f0c332a4a3fe84fdfe5aaab3a998692
---

# Handoff: zpc triggers: honest delivery receipts + in-process matching

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-8f0319
```

## Scope

zpc triggers: honest delivery receipts + in-process matching

## Inputs

- zpc effectiveness audit 2026-08-26, deliveries.jsonl + telemetry events

## Work order

Two defects from the mn-e209fb build, measured 2026-08-26. (1) deliveries.jsonl is written by inject --trigger before the hook's per-session dedup, so it counts matches, not deliveries: 44 rows vs 4 actual emits in 2 days, and rows carry session:'' because the hook subprocess lacks the session id — log from the hook after dedup, or mark suppressed rows. (2) The hook spawns agent-do -> bash -> python on every prompt, Bash call, and edit: 0.67s each, 1075 invocations in 2 days, 96 percent no-match — match triggers in the hook process against the global store (or a cached trigger table) and spawn nothing when nothing matches.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-8f0319`.
4. Commit with `Manna: mn-8f0319` and run `agent-do manna done mn-8f0319` only after the work is verified.
