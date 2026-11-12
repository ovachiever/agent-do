---
workflow: 2
manna: mn-368b25
track: null
source: null
base_commit: dcb45ceb8862e6504dc17204aa9330d29997e32e
scope: 'deai: deictic-time and negation-run rule families, measured'
inputs: []
binding: sha256:a931a6ce78c7f345979fb0f8438566e09db161803188017b98e10065c1d5c614
---

# Handoff: deai: deictic-time and negation-run rule families, measured

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-368b25
```

## Scope

deai: deictic-time and negation-run rule families, measured

## Inputs

- None declared.

## Work order

Two essay-register families from Erik's live catches (2026-09-25, terminal essay). (1) Deictic time: 'this week', 'this morning', 'this year', 'this afternoon', 'right now', 'today', 'yesterday' in essay prose — a dated moment is an assumption at publish time on a scheduled pipeline; boundary: gnomic/era uses may need a whitelist pass, measure against the certified corpus. (2) Negation runs: three or more consecutive negative constructions building a description by what the thing is not ('no X, no Y, don't Z'); the ruled fix is affirmative rebuild. Run agent-do deai measure per the measured-rule workflow before shipping to the essay pack. Companion family already filed: mn-d06a8f performed humility.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-368b25`.
4. Commit with `Manna: mn-368b25` and run `agent-do manna done mn-368b25` only after the work is verified.
