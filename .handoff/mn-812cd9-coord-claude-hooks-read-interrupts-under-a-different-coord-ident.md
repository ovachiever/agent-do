---
workflow: 2
manna: mn-812cd9
track: mn-b7a0cc
source: mn-59f1e4 close, 2026-10-30
base_commit: 3da3c8966e5c76222304ccf03dd1bad3116a8d24
scope: 'coord: Claude hooks read interrupts under a different coord identity than the shell, so drop ack from the shell does not quiet the hook nudge'
inputs:
- mn-59f1e4 close, 2026-10-30
binding: sha256:91a7f89cc7ba1bf6375b17779b4d7729d009e3e40d36ebaf786d4f0809422ab3
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

## Delivery (2026-10-30, session claude-35dfcfc4870d4899)

### Cause

Claude Code runs hooks with its own process environment, not with the exports the session-start hook writes into `CLAUDE_ENV_FILE` for the Bash tool. The shell therefore reads coord as `session-<compact(session_id)>` (pinned through `AGENT_DO_COORD_SESSION`) while each hook spawn of `coord` minted a separate identity anchored to the hook process, listed the shell's session as a peer, and never saw the shell's per-reader acknowledgments.

### Fix

- `hooks/claude/agent-do-prompt-router.py`: `load_coord_state(cwd, session_id)` pins `AGENT_DO_COORD_SESSION` to the payload's `session_id` for its `coord touch`/`coord interrupts` spawns when the variable is not already set.
- `hooks/claude/agent-do-session-start.sh`: `append_coord_context` exports the same pin for its two coord reads when unset.
- `tests/test_v11_routing.py`: a fixture with a lead shell (`AGENT_DO_COORD_SESSION=lead-session-0001`), another shell, and a sender proves that the prompt-router reminds the lead of an unread action drop, does not list the lead's own shell as a peer, stays quiet about an informational drop, keeps reminding after a shell `drop ack` of an action drop until `drop resolve`, and that session-start for the other session shows the broadcast until that shell acknowledges it and never lists its own session as a peer.
- `manna managed doctor --probe` runs the prompt-router hook in its fixture with `session_id: probe-lead` and fails the probe if the hook still nudges a drop the shell acknowledged.

### Receipts (executed)

- `python3 tests/test_v11_routing.py`: passed (includes the new identity scenario).
- `python3 tests/test_session_start_reads.py`: passed.
- `agent-do manna managed doctor --probe --json` on this machine: `live: true`, probe step `hook reads as the shell identity` ok.
