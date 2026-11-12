---
workflow: 2
manna: mn-d6a009
track: mn-b7a0cc
source: mn-e6e1a8 worker observation, 2026-11-03
base_commit: 9776e7d1dc08f601fa737f9eed91fdcccd1f99e9
scope: 'coord/router: the hook''s five-interrupt slice is cut before blocking kinds are filtered, so five notices hide every dependency'
inputs:
- mn-e6e1a8 worker observation, 2026-11-03
binding: sha256:4ee5b20aa07bb8f143f34f77a33b117ab415eca26f975d130777bdfb9cc0edc6
---

# Handoff: coord/router: the hook's five-interrupt slice is cut before blocking kinds are filtered, so five notices hide every dependency

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-d6a009
```

## Scope

coord/router: the hook's five-interrupt slice is cut before blocking kinds are filtered, so five notices hide every dependency

## Inputs

- mn-e6e1a8 worker observation, 2026-11-03

## Work order

Observed while closing mn-e6e1a8. CoordStore.interrupts sorts by kind rank (contention 0, notice 1, dependency 2, novelty 3) and truncates to limit (tools/agent-coord:3519); hooks/claude/agent-do-prompt-router.py:778 calls 'interrupts --json --limit 5' and only then keeps BLOCKING_INTERRUPT_KINDS. A session with five or more notices never has an action drop, approval, or need-key dependency reach its hook: the obligation is listed by 'coord interrupts', but the work-boundary reminder the drop design promises never fires. Live instance: the mn-e6e1a8 worker session in this repo carried exactly five unacknowledged broadcast info drops (45 to 79 days old), so any dependency addressed to it was invisible to its prompt-router hook. Fix candidates: let the hook ask for blocking kinds only (an interrupts --kind filter), or rank blocking kinds ahead of notices in the sort, and take the slice size from the quantity authority rather than the literal 5. Regression: a fixture with five broadcast info drops plus one action drop addressed to the worker; the worker's router hook must name the action drop.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-d6a009`.
4. Commit with `Manna: mn-d6a009` and run `agent-do manna done mn-d6a009` only after the work is verified.
