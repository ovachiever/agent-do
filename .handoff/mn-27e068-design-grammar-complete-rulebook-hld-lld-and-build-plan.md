---
workflow: 2
manna: mn-27e068
track: mn-b7a0cc
source: 'Erik conversation 2026-09-14: build the rules, the entire plan, the full design document (hld, lld); fully plan, so we can build; then, stop'
base_commit: 4268a8c0ef07d5132910bc688424ba5eee5c570f
scope: 'Design grammar: complete rulebook, HLD, LLD and build plan'
inputs:
- 'Erik conversation 2026-09-14: build the rules, the entire plan, the full design document (hld, lld); fully plan, so we can build; then, stop'
binding: sha256:1186f655d97db6c6ec231671694303b1a6a0a8693ef87df04e6df2c4248c5b9d
---

# Handoff: Design grammar: complete rulebook, HLD, LLD and build plan

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-27e068
```

## Scope

Design grammar: complete rulebook, HLD, LLD and build plan

## Inputs

- Erik conversation 2026-09-14: build the rules, the entire plan, the full design document (hld, lld); fully plan, so we can build; then, stop

## Work order

Planning-only commission from Erik on 2026-09-14. Define a general generative design grammar, complete rule families, high-level architecture, low-level contracts and algorithms, fresh-session delivery, evaluation without site-template overfit, and a sequenced implementation plan. Ground in the existing agent-do/DPT/browser surfaces and twelve approved pins while keeping human verdicts separate from interpretations. Deliver the complete documents to the repo, iCloud Transfer and Obsidian, then stop. No product implementation, new tool registration, dependency installation or research rerun in this commission.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-27e068`.
4. Commit with `Manna: mn-27e068` and run `agent-do manna done mn-27e068` only after the work is verified.

## Delivered planning package, 2026-09-14

The commissioned planning work is complete. Implementation is not started. Entry points:

- [Full design document](design-grammar-plan/DESIGN.md).
- [Chapter index](design-grammar-plan/README.md).
- [Planning validation](design-grammar-plan/VALIDATION.json).
- [Delivery receipt](design-grammar-plan/DELIVERY.json).

The package specifies 20 requirements; 71 rules in 15 families; 16 operators; 19 relation
signatures; 11 algorithms; 8 reusable recipes; 16 proposed architecture decisions; 11 proposed
CLI verbs; and 10 implementation work packages. It includes HLD, LLD contracts/algorithms,
fresh-session integration, evaluation, worked examples, source inventory and traceability.

The generalization invariant is explicit: reference identities cannot select runtime geometry,
tokens or templates. The host proposes contextual meaning and character over a precise
relational representation. Native browser layout remains authoritative; DPT stays a versioned
annotation. Proposals, observations, standards and actual human verdicts remain separate.

Validation passed: identifier/reference consistency, full requirement/operator mapping,
54 local Markdown links including 25 combined-book anchors, 12 independent formula/example
checks, and all 336 protected source files unchanged. Future runtime suites and prospective
design trials were not run because this commission did not implement a product. Mermaid
source was reviewed; diagrams were not separately rendered.

Eighteen bundle files were copied and byte-checked in
`~/Library/Mobile Documents/com~apple~CloudDocs/Transfer/Generative Design Grammar Plan 2026-09-14/`.
The complete book was saved through the Obsidian tool and its body verified at
`/Users/erik/Documents/Documents/Personal-KB/Obsidian/Erkverse/+/2026-09-14 Generative Design Grammar Full Plan mn-27e068.md`.
The receipt contains exact hashes and paths, including the save tool's returned filename.

This work owns only this handoff, `design-grammar-plan/`, and the new planning item's board row.
The original `mn-c2d546` handoff, research, corpus, verdicts and commit hold are preserved.
A local planning-only commit does not include or release that original work.

Stop here. WP-00 through WP-09 are document work packages, not newly launched Manna items.
Do not create the package, install Ajv, register `design`, launch a browser, generate a site,
run a new study or publish anything without a subsequent implementation commission.
