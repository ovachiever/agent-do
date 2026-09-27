---
workflow: 2
manna: mn-4061c8
track: mn-b7a0cc
source: null
base_commit: ff0b766b4a505b665701807e84206c29f5aebcb3
scope: 'Manna: close and claim gates — sprawl advisory, git-aware walk, done on evidence, operator identity, wrong-board pointer'
inputs: []
binding: sha256:85e3690734b4459f32956a4a8079ae93ea8aa9cac9cd10e80232790b91576d08
---

# Handoff: Manna: close and claim gates — sprawl advisory, git-aware walk, done on evidence, operator identity, wrong-board pointer

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-4061c8
```

## Scope

Manna: close and claim gates — sprawl advisory, git-aware walk, done on evidence, operator identity, wrong-board pointer

## Inputs

- None declared.

## Work order

Erik's ruling 2026-09-26 after three refusals in one day (mn-e9f9a9 identity-not-pinned from a bare terminal; mn-1e66a6 and mn-51c2d2 claims refused on vms.io by zpc counsel briefs under ignored .zpc/.state). Reconcile across all 35 boards: the shadow-workflow detector walks ignored state and external symlinks; id-less symlink findings pass is_none_or and refuse every claim on 7 boards. Ship: (1) sprawl is advisory in claim/done (warnings, never refusals; lint/reconcile keep reporting); (2) the walk lists git tracked plus untracked-not-ignored files and never traverses or flags a plain symlink; (3) id-less findings never attach to an item; (4) done closes on trailer evidence: a commit carrying Manna: <id> that touches a path outside .manna/ and .handoff/ authorizes the close from any status and any claimant, identity still journaled; (5) operator identity: no runtime identity plus a TTY stdin derives operator-<user> under the machine key, operator holds root lifecycle authority; (6) claim/done resolve the issue before demanding identity and name the board that holds a missing id via the estate registry. Tests for each; rebuild; docs.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-4061c8`.
4. Commit with `Manna: mn-4061c8` and run `agent-do manna done mn-4061c8` only after the work is verified.
