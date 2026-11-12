---
workflow: 2
manna: mn-bdbc10
track: mn-ad9fc2
source: null
base_commit: c7be565ecca8edb5ff0c397a2a6217b44669fab3
scope: 'DEAI OS M3: registers.yaml plus .deai.yaml resolution'
inputs: []
binding: sha256:f6b2831aaa963789052f2bac14cba12e7b44cda4c74144714032700fdd50bbac
---

# Handoff: DEAI OS M3: registers.yaml plus .deai.yaml resolution

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-bdbc10
```

## Scope

DEAI OS M3: registers.yaml plus .deai.yaml resolution

## Inputs

- None declared.

## Work order

Spec 2, 4. Surface-to-pack map; one-line per-repo override; CLAUDE.md voice paragraphs collapse to the pointer once M2 serves content.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-bdbc10`.
4. Commit with `Manna: mn-bdbc10` and run `agent-do manna done mn-bdbc10` only after the work is verified.
