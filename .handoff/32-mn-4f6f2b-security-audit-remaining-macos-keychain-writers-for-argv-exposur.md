---
workflow: 2
manna: mn-4f6f2b
track: mn-b7a0cc
source: agent-psql Keychain argv incident 2026-08-19
base_commit: f032c18282c3368347c4271a2e247c29edb24845
scope: 'Security: audit remaining macOS Keychain writers for argv exposure'
inputs:
- agent-psql Keychain argv incident 2026-08-19
binding: sha256:f77c6442c0ac919ca8ae5872cd973adc56683083c4a5b908703c8de540cb553c
---

# Handoff: Security: audit remaining macOS Keychain writers for argv exposure

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-4f6f2b
```

## Scope

Security: audit remaining macOS Keychain writers for argv exposure

## Inputs

- agent-psql Keychain argv incident 2026-08-19

## Work order

> Legacy migration source: ".dev/session-prompts/33-macos-keychain-argv-audit.md"

---
workflow: 2
manna: mn-4f6f2b
track: mn-b7a0cc
source: agent-psql Keychain argv incident 2026-08-19
base_commit: 5c00b1f157aa62e0dd809a24893d8e32358e24d4
scope: 'Security: audit remaining macOS Keychain writers for argv exposure'
inputs:
- agent-psql Keychain argv incident 2026-08-19
---

# Handoff: Security: audit remaining macOS Keychain writers for argv exposure

Board state is canonical in `.manna/`. This file is the work order for one item only.

Reconstructed 2026-08-31: the original file at this path was untracked (gitignored `.dev/`
root) and no copy survives. The board description below is the authoritative scope; the
original may have carried detail now lost.

## Claim

```bash
agent-do manna claim mn-4f6f2b
```

## Scope

Security: audit remaining macOS Keychain writers for argv exposure

## Inputs

- agent-psql Keychain argv incident 2026-08-19

## Work order

Inventory and independently harden lib/creds-helper.sh, agent-browse credentials, and agent-db Keychain writes without broadening the agent-psql unblock PR. Do not claim repository-wide remediation until each path is tested.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-4f6f2b`.
4. Commit with `Manna: mn-4f6f2b` and run `agent-do manna done mn-4f6f2b` only after the work is verified.


## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-4f6f2b`.
4. Commit with `Manna: mn-4f6f2b` and run `agent-do manna done mn-4f6f2b` only after the work is verified.
