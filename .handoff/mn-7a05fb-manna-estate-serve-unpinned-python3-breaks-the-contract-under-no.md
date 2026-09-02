---
workflow: 2
manna: mn-7a05fb
track: mn-b7a0cc
source: holy-ghostty mn-330752 worker report 2026-09-01 + env repro 2026-09-02
base_commit: a6534c30359fa1f7c03a930e6bf0da11643cd9fd
scope: 'manna estate/serve: unpinned python3 breaks the contract under non-login environments'
inputs:
- holy-ghostty mn-330752 worker report 2026-09-01 + env repro 2026-09-02
binding: sha256:abaf73e2737e383c9127c114ceb25088439a3444c893e8d3f70eee02b3665606
---

# Handoff: manna estate/serve: unpinned python3 breaks the contract under non-login environments

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7a05fb
```

## Scope

manna estate/serve: unpinned python3 breaks the contract under non-login environments

## Inputs

- holy-ghostty mn-330752 worker report 2026-09-01 + env repro 2026-09-02

## Work order

Live repro 2026-09-02: 'agent-do manna estate --json' works from a login shell (pyenv 3.11 + PyYAML) but fails with ModuleNotFoundError: No module named 'yaml' under a bare PATH (env -i PATH=/usr/bin:/bin) — which is exactly how Holy invokes it, so Holy's new Board mode surfaces the canonical failure and its estate strip cannot populate (holy-ghostty mn-330752 is held open on this). Cause: tools/agent-manna/agent-manna:51 and :59 'exec python3 serve/estate.py|serve.py' take whatever python3 PATH offers; serve/board.py imports yaml. Fix directions (worker's choice): resolve and pin a known-good interpreter the way the install path does (and record it), vendor out the yaml dependency on the estate/board read path, or route the estate read through the Rust core which already parses board files. Acceptance: 'env -i PATH=/usr/bin:/bin agent-do manna estate --json' returns the full estate model, and Holy's Board mode estate strip populates without a login shell. Same hardening applied to the serve entry (:59) so the daemon survives non-login starts.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7a05fb`.
4. Commit with `Manna: mn-7a05fb` and run `agent-do manna done mn-7a05fb` only after the work is verified.
