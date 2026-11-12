---
workflow: 2
manna: mn-91c878
track: mn-455a88
source: session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)
base_commit: a1ff599ef4e01962454df2e2391323d2127a752c
scope: 'agent-sessions search: CLI handoff cannot deliver — 5 s literal wait vs 19–24 s measured run; UUID grep drops 76,188 of 79,674 ids'
inputs:
- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)
binding: sha256:69b72b8dfcfef9f4dd3e382f962b99046269b6417db46ef2b0924ae30eeebb9f
---

# Handoff: agent-sessions search: CLI handoff cannot deliver — 5 s literal wait vs 19–24 s measured run; UUID grep drops 76,188 of 79,674 ids

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-91c878
```

## Scope

agent-sessions search: CLI handoff cannot deliver — 5 s literal wait vs 19–24 s measured run; UUID grep drops 76,188 of 79,674 ids

## Inputs

- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)

## Work order

Site: tools/agent-sessions cmd_search. The search verb hands off to the pip CLI agent-sessions (resolved by realpath since 0e2271f), waits at most 5 s (line 206, `[[ $waited -lt 5 ]]`, a bare literal in a timeout slot), kills it, and falls back to sqlite FTS (line 244).

Measured 2026-10-19 09:36 on an idle machine: /Users/erik/.pyenv/versions/3.11.11/bin/agent-sessions search "security hook timeout" took 19.2 s wall (2026-10-18 under load: 24 s). The handoff therefore never completes: every search pays 5 s, kills the child, and returns FTS-only results.

Even a completed handoff would lose most ids. Line 223 extracts only UUID-shaped ids. Census of ~/.cache/agent-sessions/sessions.db on 2026-10-19 (79,674 rows): claude-code uuid 2,227 / agent-xxxxxxx 4,418; codex uuid 497; droid uuid 762; cursor other 9; opencode ses_ 71,761. UUIDs are 3,486 rows; 76,188 rows (opencode ses_, claude agent-* ids, cursor) can never match.

Erik rules at claim time which outcome this item delivers: (1) remove the handoff branch and keep FTS only, or (2) keep it: wait for the CLI to finish with no literal timeout (its own run time is the authority), and match every id format the database holds (one SQL IN over the ids the CLI printed, no shape filter). Either way the numbers rule applies: no bare wait literal survives (harness bounds scan tools/agent-sessions also lists 11 bare limit literals, estate-wide 195, not this item).

Verification: agent-do sessions search "security hook timeout" returns within the FTS path time when (1), or returns ids of every harness when (2); no process named agent-sessions survives the command (pgrep -f tools/agent-sessions empty); ./test.sh green; harness contracts validate 0 warnings.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-91c878`.
4. Commit with `Manna: mn-91c878` and run `agent-do manna done mn-91c878` only after the work is verified.
