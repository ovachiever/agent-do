---
workflow: 2
manna: mn-0eff4d
track: null
source: mn-772f53
base_commit: f7f32d72074e6320b4b16309862fac238e5e9930
scope: 'field check: combined polish on Palingenesis Today'
inputs:
- mn-772f53
binding: sha256:c1143f0264b913d5a95e13825db1769dabb59c02e3e2207af74d455f3ad2d4f5
---

# Handoff: field check: combined polish on Palingenesis Today

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-0eff4d
```

## Scope

field check: combined polish on Palingenesis Today

## Inputs

- mn-772f53

## Work order

Owner: Erik. Follow-up to mn-772f53 and companion mn-17c022. The readiness build has 63 executed no-browser tests and 5 executed native-browser readiness fixtures passing; initial failing evidence is retained in .dev/mn-772f53. The companion geometry lane still owns its separate acceptance and lifecycle. In a coordinated closing window after authorization for that lane, run python3 tools/agent-design/test/test_settle_browser.py and python3 tools/agent-design/test/test_polish.py against the combined primary checkout. Then audit the actual Palingenesis Today URL with a confirmed ready text marker or JavaScript boolean expression and a fresh --out path. Verify the audit contains settled application text instead of Assembling/unavailable/Offline, retains actual wait outcomes and durations, and preserves meaningful geometry findings. Do not guess the URL or readiness signal and do not treat source compilation as browser execution. This field item does not authorize installs, publication, or uncoordinated session launches.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-0eff4d`.
4. Commit with `Manna: mn-0eff4d` and run `agent-do manna done mn-0eff4d` only after the work is verified.
