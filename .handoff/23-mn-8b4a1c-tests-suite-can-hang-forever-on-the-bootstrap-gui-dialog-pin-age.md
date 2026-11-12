---
workflow: 2
manna: mn-8b4a1c
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'tests: suite can hang forever on the bootstrap GUI dialog — pin AGENT_DO_BOOTSTRAP_AUTO_RESPONSE in test env'
inputs: []
binding: sha256:158889aa22abdaed89421d71253a5c2be08ae961dd46cf2892c27d59c7e0c1e4
---

# Handoff: tests: suite can hang forever on the bootstrap GUI dialog — pin AGENT_DO_BOOTSTRAP_AUTO_RESPONSE in test env

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-8b4a1c
```

## Scope

tests: suite can hang forever on the bootstrap GUI dialog — pin AGENT_DO_BOOTSTRAP_AUTO_RESPONSE in test env

## Inputs

- None declared.

## Work order

test_v11_routing.py spawns hooks/claude/agent-do-session-start.sh against fresh temp projects; on macOS with osascript present the hook raises a real 'agent-do Bootstrap' display dialog and blocks unbounded (observed 47m) until a human clicks. The hook already has the escape hatch (AGENT_DO_BOOTSTRAP_AUTO_RESPONSE=not_now, verified: test passes with it) — the test run() env should pin it, and the hook arguably needs a no-TTY/headless guard or a bounded osascript timeout as defense in depth.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-8b4a1c`.
4. Commit with `Manna: mn-8b4a1c` and run `agent-do manna done mn-8b4a1c` only after the work is verified.
