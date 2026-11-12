---
workflow: 2
manna: mn-43932b
track: mn-69368a
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'brief: contract v2 — verb labels, scope, state sentence (adopted panel-v2 critique)'
inputs: []
binding: sha256:fba9e1a7c0ed69dc787c8758fbfd5005fd57d5a080f1c8588d6eb10f8eab57b3
---

# Handoff: brief: contract v2 — verb labels, scope, state sentence (adopted panel-v2 critique)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-43932b
```

## Scope

brief: contract v2 — verb labels, scope, state sentence (adopted panel-v2 critique)

## Inputs

- None declared.

## Work order

Erik-commissioned external design review, adopted 2026-08-11 (full text in holy-ghostty .dev/session-prompts/10-INTELLIGENT-INBOX.md §Panel v2). Engine slice: (1) deterministic verb labels — map each verified attention reason to a human verb phrase (review_requested → "Review {subject}"; claimed-no-session → "Resume or release {subject}"; landed_open → "Close {subject} — its code landed"; blocker_desync → "Clear a resolved blocker"; etc.), rule-based, never model-invented; (2) the voice adapter MAY compress the noun phrase only (≤~52 chars, strip [TAGS]/commit prefixes/ids, preserve quantities like "19 updates", fall back to sanitized original when unsure — same receipts covenant); (3) per-thread and per-suggestion scope field: "everywhere" (cross-project GitHub) vs "focused" (the caller,s board/project); (4) a deterministic state sentence field ("2 decisions here. 30 reviews elsewhere." with the mechanically-honest degraded variants) so every consumer shares one voice; (5) housekeeping bundle labels ("11 finished tasks ready to close") beside raw suggestion kinds. This changes payload shape → contract 2 with the version bump discipline; consumer (holy-ghostty mn-5dc58b lineage) pins from a live capture as before.

CRITIQUE ROUND 2 REFINEMENTS (2026-08-11 17:18, adopted): (a) SCOPE IS REPO-MEMBERSHIP, NOT SOURCE — "here" = concerns the caller's focused repo across ALL sources (a PR on the focused repo is HERE); "elsewhere" = other repos; source (github/manna/session/drift) is secondary provenance only. Compute scope engine-side by comparing each thread's repo against the caller context. (b) The voiced paragraph must ADD MEANING or stay silent — never restate the state sentence's counts ("Both Holy Ghostty claims have gone quiet." is the bar); emit it as an optional insight field, empty when the model has nothing beyond the counts. (c) Reason strings are interface language: emit human forms ("Claimed, but no agent is active", "Review requested"), never classifier vocabulary (claimed in_progress, maintainer_unreviewed). (d) Library sectioning: group by This repo / Other repos with source as sub-provenance.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-43932b`.
4. Commit with `Manna: mn-43932b` and run `agent-do manna done mn-43932b` only after the work is verified.
