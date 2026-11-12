---
workflow: 2
manna: mn-b17dc6
track: mn-69368a
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Companion: [P1 SECURITY] voice speak — replace eval''d shell-string with argument arrays'
inputs: []
binding: sha256:a1f174b6aff5176eceb2d1ceec2f0e02e65f3945cf639a2d2f542589afcd2b86
---

# Handoff: Companion: [P1 SECURITY] voice speak — replace eval'd shell-string with argument arrays

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-b17dc6
```

## Scope

Companion: [P1 SECURITY] voice speak — replace eval'd shell-string with argument arrays

## Inputs

- None declared.

## Work order

tools/agent-voice builds a shell string and eval's it with interpolated text: model output through this path is command injection. Fix: exec with argument arrays + adversarial tests. Consumer: holy-ghostty C4 blocks on this (Companion mouth). P1.

SCHEDULED 2026-08-07 (Erik, via holy-ghostty /board audit): fix now — small and contained. Audit correction: there are TWO eval sites, not one — tools/agent-voice line 66 (macOS say) AND line 74 (Linux espeak); both build cmd="$cmd \"$text\"" then run eval "$cmd". Replace both with argument-array exec; adversarial tests must cover $(...), backticks, quotes, newlines, and NUL.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-b17dc6`.
4. Commit with `Manna: mn-b17dc6` and run `agent-do manna done mn-b17dc6` only after the work is verified.
