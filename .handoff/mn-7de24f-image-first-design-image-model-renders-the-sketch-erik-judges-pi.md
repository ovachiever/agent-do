---
workflow: 2
manna: mn-7de24f
track: null
source: null
base_commit: b0b668ec478c7d654de3d800b48d18f427544dde
scope: 'agent-do design: image-first rounds (brief · imagine · ballot · measure · reproduce · polish) — replaces dpt and aphrodite'
inputs: []
binding: sha256:aa0369d5b86f05f182a6ee217ee2f0c3763d0d832e0d39acd05939a494529a1e
---

# Handoff: Image-first design: image model renders the sketch, Erik judges pictures, an instrument extracts measured geometry from the chosen image, a builder reproduces it in HTML under the copy contract

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7de24f
```

## Scope

Image-first design: image model renders the sketch, Erik judges pictures, an instrument extracts measured geometry from the chosen image, a builder reproduces it in HTML under the copy contract

## Inputs

- None declared.

## Work order

Image-first design: image model renders the sketch, Erik judges pictures, an instrument extracts measured geometry from the chosen image, a builder reproduces it in HTML under the copy contract

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7de24f`.
4. Commit with `Manna: mn-7de24f` and run `agent-do manna done mn-7de24f` only after the work is verified.

## Implementation delivered, rehearsal pending

The six approved `agent-do design` verbs are implemented and integrated into local `main` through `ad4da1d50507c78450d5b18abfc26678cab24043`. No push or Artifact publication has occurred. The authoritative amendments are recorded in [APPROVED-AMENDMENTS-2026-09-18.md](image-first-design/APPROVED-AMENDMENTS-2026-09-18.md); the original proposal and source prompts remain unchanged.

The [implementation report](image-first-design/IMPLEMENTATION-2026-09-18.md) describes behavior, commands, evidence, limits and stage commits. `tools/agent-design/README.md` is the operating reference.

Verified: 49 focused design tests passed on the final implementation; `./test.sh` passed 126 checks with zero failures; contracts validation reported zero errors and warnings; design contract drift is empty. The last localized fixes received the complete focused rerun after the root suite's design portion. Receipts and the unchanged Home regression render are in `.dev/`, mirrored to iCloud Transfer. Home is regression evidence only.

No paid image-generation or builder request has run. Provider model authority was refreshed from official documents without spending on generation. Claude remains the only ballot host, using `/ballot` after a real `agent-do coord drop add` handoff. No host receipt has been fabricated.

Needed next: Erik names a new surface and approves its copy file and node-tagged facts. Then run the no-spend dry run, real generation, image-ballot handoff, measured reproduction with live copy and polish checks, and page-ballot handoff. Stop at each human ruling and preserve Erik's readback verbatim. Report actual returned usage, HTML, renders and audit numbers. Leave this item open until that rehearsal is complete.
