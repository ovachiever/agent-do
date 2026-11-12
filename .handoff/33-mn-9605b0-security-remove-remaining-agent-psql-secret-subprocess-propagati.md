---
workflow: 2
manna: mn-9605b0
track: mn-b7a0cc
source: agent-psql Keychain implementation audit 2026-08-19
base_commit: f032c18282c3368347c4271a2e247c29edb24845
scope: 'Security: remove remaining agent-psql secret subprocess propagation'
inputs:
- agent-psql Keychain implementation audit 2026-08-19
binding: sha256:973b0f63394b3e4a2e55bb15341efeae8498c2dd086204e1e02bc508d132ad18
---

# Handoff: Security: remove remaining agent-psql secret subprocess propagation

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9605b0
```

## Scope

Security: remove remaining agent-psql secret subprocess propagation

## Inputs

- agent-psql Keychain implementation audit 2026-08-19

## Work order

> Legacy migration source: ".dev/session-prompts/34-agent-psql-secret-propagation.md"

---
workflow: 2
manna: mn-9605b0
track: mn-b7a0cc
source: agent-psql Keychain implementation audit 2026-08-19
base_commit: 5c00b1f157aa62e0dd809a24893d8e32358e24d4
scope: 'Security: remove remaining agent-psql secret subprocess propagation'
inputs:
- agent-psql Keychain implementation audit 2026-08-19
---

# Handoff: Security: remove remaining agent-psql secret subprocess propagation

Board state is canonical in `.manna/`. This file is the work order for one item only.

Reconstructed 2026-08-31: the original file at this path was untracked (gitignored `.dev/`
root) and no copy survives. The board description below is the authoritative scope; the
original may have carried detail now lost.

## Claim

```bash
agent-do manna claim mn-9605b0
```

## Scope

Security: remove remaining agent-psql secret subprocess propagation

## Inputs

- agent-psql Keychain implementation audit 2026-08-19

## Work order

Audit and harden non-Keychain agent-psql paths that pass password-bearing profile URIs or retrieved passwords through child-process argv/environment. Include env-fallback identity commands, profile parsing/injection, masking, and read paths. Do not broaden mn-62acb6 or claim those paths fixed until independently tested.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9605b0`.
4. Commit with `Manna: mn-9605b0` and run `agent-do manna done mn-9605b0` only after the work is verified.


## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9605b0`.
4. Commit with `Manna: mn-9605b0` and run `agent-do manna done mn-9605b0` only after the work is verified.
