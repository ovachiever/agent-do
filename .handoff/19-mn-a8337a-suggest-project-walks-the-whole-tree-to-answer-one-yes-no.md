---
workflow: 2
manna: mn-a8337a
track: mn-455a88
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: suggest --project walks the whole tree to answer one yes/no
inputs: []
binding: sha256:933c7fb74dc4cd43e1c90ad672e66190d86c8f13ce83bef716cc9da44d2c924b
---

# Handoff: suggest --project walks the whole tree to answer one yes/no

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-a8337a
```

## Scope

suggest --project walks the whole tree to answer one yes/no

## Inputs

- None declared.

## Work order

MEASURED 2026-08-10 by cProfile against /Users/erik/Custom-Coding/palingenesis: 'agent-do suggest --project' takes 10.5s, of which 7.6s is one line. bin/suggest:124 — 'if (project_root / "migrations").exists() or list(project_root.rglob("*.sql")):' — recursively walks the entire project to decide whether to add a database signal: 195,249 posix.scandir calls, pathlib _select_from 5.19s + scandir 3.54s. It descends node_modules, .venv, Rust target/, .git. Two defects in one line: the walk is unbounded (no prune list, no depth limit), and list() forces the complete enumeration when the answer is known at the first match. No AI is involved anywhere in this path — verified AGENT_DO_SUGGEST_AI=off 11.1s vs on 11.3s — so no model or setting is the cause. FIX: next(rglob, None) instead of list(); prune node_modules/.venv/target/dist/.git; consider a depth bound. Compare bin/suggest:103 which uses a non-recursive glob for *.xcodeproj and costs nothing. Also sweep the file for sibling rglob calls. WHY IT STILL MATTERS after the session-start block is deleted (mn-50338f): a command anyone may run interactively should not take 10.5s, and 'harness census entries' style walks elsewhere may share the pattern.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-a8337a`.
4. Commit with `Manna: mn-a8337a` and run `agent-do manna done mn-a8337a` only after the work is verified.
