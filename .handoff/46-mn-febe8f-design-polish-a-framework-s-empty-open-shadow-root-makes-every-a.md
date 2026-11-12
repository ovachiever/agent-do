---
workflow: 2
manna: mn-febe8f
track: null
source: null
base_commit: 8ef6c50ae8040e5ae65f576e88f5353666133c7a
scope: 'design polish: a framework''s empty open shadow root makes every audit incomplete'
inputs: []
binding: sha256:761ba0edfb66b410302793fdba6327ed9a9df02c9bf1d8300ddfaea7208826f1
---

# Handoff: design polish: a framework's empty open shadow root makes every audit incomplete

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-febe8f
```

## Scope

design polish: a framework's empty open shadow root makes every audit incomplete

## Inputs

- None declared.

## Work order

Measured 2026-09-24 on the deployed Palingenesis front page (/home, ccf7bd4) at 1440x1000, 1024x768, 768x1024 and 390x844: zero findings in all six categories, fonts loaded, no generated content, canvas, clipping, control values or frames uninspected, yet complete=false and so clean=false at every size because coverage.shadow_roots is 1. The one shadow root is Next.js's own <next-route-announcer>: an open-mode, empty (textContent ''), 0x0 aria-live region the framework appends to every page of every Next app, so under polish.js:265 (complete requires shadow_roots===0) no page of the dashboard can ever be clean, whatever it renders. Fix: pierce open shadow roots and measure their text runs like light DOM (an open root is inspectable), and count only closed shadow roots as uninspected; or, at minimum, treat an open shadow root with no rendered text and a 0x0 host as inspected. Companion to mn-772f53 and mn-17c022. Receipts: palingenesis .handoff/.archive/mn-7d9004-live-proof-2026-09-24/polish-*.json.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-febe8f`.
4. Commit with `Manna: mn-febe8f` and run `agent-do manna done mn-febe8f` only after the work is verified.
