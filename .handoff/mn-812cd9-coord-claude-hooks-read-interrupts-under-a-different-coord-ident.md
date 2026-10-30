---
workflow: 2
manna: mn-812cd9
track: mn-b7a0cc
source: mn-59f1e4 close, 2026-10-30
base_commit: 3da3c8966e5c76222304ccf03dd1bad3116a8d24
scope: 'coord: Claude hooks read interrupts under a different coord identity than the shell, so drop ack from the shell does not quiet the hook nudge'
inputs:
- mn-59f1e4 close, 2026-10-30
binding: sha256:4cafda7dc344f82b8f903df88797fa58773419739ddc34bcd33b52ce9e566753
---

# Handoff: coord: Claude hooks read interrupts under a different coord identity than the shell, so drop ack from the shell does not quiet the hook nudge

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-812cd9
```

## Scope

coord: Claude hooks read interrupts under a different coord identity than the shell, so drop ack from the shell does not quiet the hook nudge

## Inputs

- mn-59f1e4 close, 2026-10-30

## Work order

Observed 2026-10-30 while closing mn-59f1e4: the prompt-router and session-start hooks run coord touch/interrupts under an identity that lists the shell's own session (session-35dfcfc4870d) as a peer. Per-reader drop acks are therefore invisible to the hook reader; drop resolve quiets both. Fix: have the hooks resolve the same AGENT_DO_COORD_SESSION anchor the shell uses (session-start pins it via CLAUDE_ENV_FILE but the hook process itself may not inherit it), or have the hook pass the session_id from its stdin payload as AGENT_DO_COORD_SESSION. Verify with tests/test_v11_routing.py and a fixture where a shell ack silences the hook.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-812cd9`.
4. Commit with `Manna: mn-812cd9` and run `agent-do manna done mn-812cd9` only after the work is verified.
