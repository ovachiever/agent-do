---
workflow: 2
manna: mn-c2dc8b
track: mn-455a88
source: June moon checklist item 8
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Harness: undocumented verbs — promote help-only verbs into registry commands + contracts'
inputs:
- June moon checklist item 8
binding: sha256:7a5c7d5f75af8ede4c828bda7e5a97369eb4b7ba7904b8aa20352d53a42047f4
---

# Handoff: Harness: undocumented verbs — promote help-only verbs into registry commands + contracts

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c2dc8b
```

## Scope

Harness: undocumented verbs — promote help-only verbs into registry commands + contracts

## Inputs

- June moon checklist item 8

## Work order

Carried over from June moon-loop checklist item 8 (counted 431 then; RE-VERIFY the count first, much has shipped since). Promote legitimate help-only verbs into registry commands with contracts via lexicon/propose; aliases and sub-actions excluded. Gate must stay green at every step.

EVIDENCE (Lane 7 spot-checks 2026-07-21): slack --help carries webhook/snapshot/channels undeclared; sms omits export; cloudflare declares 18 of ~23 (worker, worker-logs, page, r2-objects, waf-rules, account undeclared). drift only catches declared-but-missing; this is the reverse channel. docs/TOOLS.md now mirrors registry truth, so closing this item completes the public reference too.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c2dc8b`.
4. Commit with `Manna: mn-c2dc8b` and run `agent-do manna done mn-c2dc8b` only after the work is verified.
