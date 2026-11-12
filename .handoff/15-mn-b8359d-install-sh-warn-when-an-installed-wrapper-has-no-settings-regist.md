---
workflow: 2
manna: mn-b8359d
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'install.sh: warn when an installed wrapper has no settings registration'
inputs: []
binding: sha256:55cf539d3f5eb9df6846975622050750e97dc30c8b4f427850d823d3046fa5d4
---

# Handoff: install.sh: warn when an installed wrapper has no settings registration

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-b8359d
```

## Scope

install.sh: warn when an installed wrapper has no settings registration

## Inputs

- None declared.

## Work order

WHAT: install.sh installs hook wrappers unconditionally (step 4) but only merges settings.json when --register-hooks / interactive-yes. A run without the flag therefore leaves wrappers on disk for hooks that never fire, silently — this happened live 2026-07-28: correction-keys wrapper installed 13:19, never registered, w/d/s dead with no signal. FIX: at the end of a run, compare installed wrapper names against the registered set in settings.json and print a loud line naming each dead wrapper plus the exact re-run command. Read-only check, no auto-write. SOURCE: orchestrator verification 2026-07-28.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-b8359d`.
4. Commit with `Manna: mn-b8359d` and run `agent-do manna done mn-b8359d` only after the work is verified.
