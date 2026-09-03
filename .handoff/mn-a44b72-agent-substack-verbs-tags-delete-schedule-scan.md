---
workflow: 2
manna: mn-a44b72
track: null
source: null
base_commit: c946237d65f2d39e5cd4ca6dc62619935a38dd71
scope: 'agent-substack: verbs tags/delete/schedule/scan'
inputs: []
binding: sha256:b2270162d13d5f1db0999c5f2c4e94a7ae2b2d6b4117c36983b91f63315199b6
---

# Handoff: agent-substack: verbs tags/delete/schedule/scan

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-a44b72
```

## Scope

agent-substack: verbs tags/delete/schedule/scan

## Inputs

- None declared.

## Work order

Erik-approved 2026-09-03 (taxonomy ruling mn-1aaad3 on the substack-writings board). Four verbs: tags (attach/list post tags via /api/v1/publication/post-tag and /api/v1/post/<id>/tag/<tag_id>; standard set lives in substack-writings CLAUDE.md), delete (drafts only, destructive-flagged), schedule (set publish datetime; substack-writings runs daily 5:55 AM Central), scan (trigger/read Pangram analysis if exposed). Contracts gate must stay green; button-marker converter support already shipped.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-a44b72`.
4. Commit with `Manna: mn-a44b72` and run `agent-do manna done mn-a44b72` only after the work is verified.
