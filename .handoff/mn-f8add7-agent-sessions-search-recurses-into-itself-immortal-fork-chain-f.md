---
workflow: 2
manna: mn-f8add7
track: mn-455a88
source: session 5f72481f investigation 2026-10-18; hook timeout report from the-point-revision session 43fe35ff
base_commit: fe91113e84b8347991740c5965488c61a04b0886
scope: agent-sessions search recurses into itself; immortal fork chain floods $TMPDIR
inputs:
- session 5f72481f investigation 2026-10-18; hook timeout report from the-point-revision session 43fe35ff
binding: sha256:371be50639ee70d82e28e22acd51b592c04a51d00ce74879fc8215db5a50c013
---

# Handoff: agent-sessions search recurses into itself; immortal fork chain floods $TMPDIR

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-f8add7
```

## Scope

agent-sessions search recurses into itself; immortal fork chain floods $TMPDIR

## Inputs

- session 5f72481f investigation 2026-10-18; hook timeout report from the-point-revision session 43fe35ff

## Work order

Incident 2026-10-16 16:23 CDT: session 3ffd7bd7 ran 'agent-do sessions search "Slack message to Nathan"' and '... "Nathan" --limit 15'. cmd_search checks 'command -v agent-sessions' to hand off to the hybrid CLI, but the agent-do launcher prepends tools/ to PATH, so the name resolves to tools/agent-sessions itself. The script backgrounds a copy of itself, waits 5s, SIGTERMs it, then rm -f its mktemp file; the killed copy leaks its file and its already-spawned grandchild (orphaned to launchd) continues forever. Measured 2026-10-18: 158 chain processes born per 10s, every leaked file 6.5k of JSON in /var/folders/.../T, listing that dir takes >12 min, disk0 ~11k tps. Downstream: the security-guidance plugin lists the whole temp dir before each git stash create, so its UserPromptSubmit hook blew its 30s timeout in every repo with commits (the-point-revision session, 3 prompts 2026-10-18). Chains killed 2026-10-18 11:20 (4715 processes frozen with SIGSTOP then SIGKILL; none respawned). FIX (tools/agent-sessions cmd_search): (1) resolve the CLI by walking 'type -aP agent-sessions' and taking the first whose realpath differs from realpath of BASH_SOURCE[0]; (2) call that path, never the bare name; (3) trap EXIT/TERM/INT to rm the tmpfile, reset after normal cleanup. VERIFY: run 'agent-do sessions search x --limit 3' with TMPDIR set to an empty scratch dir -> returns; 'pgrep -f agent-sessions' empty afterwards; scratch dir still empty; bash -x shows cli_bin = the pyenv binary; ./test.sh passes; 'agent-do harness contracts validate' 95/95. Leaked-file cleanup of $TMPDIR is a separate decision for Erik.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-f8add7`.
4. Commit with `Manna: mn-f8add7` and run `agent-do manna done mn-f8add7` only after the work is verified.
