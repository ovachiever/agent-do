---
workflow: 2
manna: mn-481318
track: null
source: palingenesis session-ce51164139cf, 2026-09-21; zpc les-df9aff
base_commit: 51982db3f382c1e6403b3b977f51cb9c0adbfcb8
scope: 'git commit: --help is taken as the commit message and commits whatever is staged'
inputs:
- palingenesis session-ce51164139cf, 2026-09-21; zpc les-df9aff
binding: sha256:eb56607ab8f4846999316100b5a510ce99e8697336f0c70056a983957007e792
---

# Handoff: git commit: --help is taken as the commit message and commits whatever is staged

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-481318
```

## Scope

git commit: --help is taken as the commit message and commits whatever is staged

## Inputs

- palingenesis session-ce51164139cf, 2026-09-21; zpc les-df9aff

## Work order

Observed 2026-09-21 in palingenesis: 'agent-do git commit --help' created commit f3e1c75 titled '--help' from five staged deletions instead of printing usage (undone with git reset --soft HEAD~1). The verb takes [msg] positionally and does not reject flag-shaped messages. Fix: reject a message beginning with '-' and print the verb's usage; add a test that 'agent-do git commit --help' exits 0, prints usage, and leaves HEAD unchanged.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-481318`.
4. Commit with `Manna: mn-481318` and run `agent-do manna done mn-481318` only after the work is verified.
