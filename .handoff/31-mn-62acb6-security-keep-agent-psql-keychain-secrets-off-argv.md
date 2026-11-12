---
workflow: 2
manna: mn-62acb6
track: mn-b7a0cc
source: Goal 2 dependency shadow preflight 2026-08-19
base_commit: f032c18282c3368347c4271a2e247c29edb24845
scope: 'Security: keep agent-psql Keychain secrets off argv'
inputs:
- Goal 2 dependency shadow preflight 2026-08-19
binding: sha256:99a1d6273327e8627627a79c06c1277e9ca4b2e404001e643eb0efc31f0e1f64
---

# Handoff: Security: keep agent-psql Keychain secrets off argv

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-62acb6
```

## Scope

Security: keep agent-psql Keychain secrets off argv

## Inputs

- Goal 2 dependency shadow preflight 2026-08-19

## Work order

> Legacy migration source: ".dev/session-prompts/32-agent-psql-keychain-argv.md"

---
workflow: 2
manna: mn-62acb6
track: mn-b7a0cc
source: Goal 2 dependency shadow preflight 2026-08-19
base_commit: 5c00b1f157aa62e0dd809a24893d8e32358e24d4
scope: 'Security: keep agent-psql Keychain secrets off argv'
inputs:
- Goal 2 dependency shadow preflight 2026-08-19
---

# Handoff: Security: keep agent-psql Keychain secrets off argv

Board state is canonical in `.manna/`. This file is the work order for one item only.

Reconstructed 2026-08-31: the original file at this path was untracked (gitignored `.dev/`
root) and no copy survives. The board description below is the authoritative scope. The
work appears landed (commits 1083a7fd, 8adc9aa1 carry the Manna trailer); this file exists
so the board's pairing gate can validate and reconcile can close the item.

## Claim

```bash
agent-do manna claim mn-62acb6
```

## Scope

Security: keep agent-psql Keychain secrets off argv

## Inputs

- Goal 2 dependency shadow preflight 2026-08-19

## Work order

Replace the agent-psql macOS Keychain helper read/write subprocess path with bounded stdin and scrubbed environments; serialize profile mutations; bind credential expectation explicitly; preserve terminal newlines; fix session/profile publication ordering. Narrow to agent-psql Keychain helpers and track other secret subprocess paths separately.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-62acb6`.
4. Commit with `Manna: mn-62acb6` and run `agent-do manna done mn-62acb6` only after the work is verified.


## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-62acb6`.
4. Commit with `Manna: mn-62acb6` and run `agent-do manna done mn-62acb6` only after the work is verified.
