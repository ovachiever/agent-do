---
workflow: 2
manna: mn-9d54e7
track: null
source: null
base_commit: 7b7e7c5952201fd3d6e7928d0c7895c26d448f15
scope: 'deai: work-message register, ceremony shell family, measured'
inputs: []
binding: sha256:be7df52ef5af40ea4ff56b8d3122df3a7644ce93cd3ec5ca688297d65653e5ca
---

# Handoff: deai: work-message register, ceremony shell family, measured

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-9d54e7
```

## Scope

deai: work-message register, ceremony shell family, measured

## Inputs

- None declared.

## Work order

From Erik's 2026-10-05 three-draft Chris/OOM catch (and the 2026-09-25 leadership texts): outbound work messages fail on SHAPE tells the essay register never sees. Lintable shells for a work-message register: salutation openers ('Hey NAME,' 'Hi NAME,' as message-initial), gratitude ceremony openers ('thanks for catching/flagging/raising' message-initial), closing offers ('let me know', 'happy to', 'hope this helps'), bullets/numbered lists inside messages, sign-offs. The unlintable half (completeness-compulsion, performed casualness) is handled at formation: the say-the-thing skill now carries the law plus receipted sent exemplars machine-wide; the durable home is DEAI OS M2 voice emission per .handoff/deai-os-spec.md, still awaiting Erik's go. Run deai measure against the sent-message corpus before shipping; false-positive ceiling per the spec (a real first-contact greeting must not flag).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-9d54e7`.
4. Commit with `Manna: mn-9d54e7` and run `agent-do manna done mn-9d54e7` only after the work is verified.
