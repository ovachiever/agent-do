---
workflow: 2
manna: mn-a45739
track: mn-69368a
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Companion: agent-do dictate (the Chair''s ears), Wispr-class streaming dictation'
inputs: []
binding: sha256:a92abd6fd213315470a4ef49ae728c39639b959f2b194b4f49bc483e16784293
---

# Handoff: Companion: agent-do dictate (the Chair's ears), Wispr-class streaming dictation

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-a45739
```

## Scope

Companion: agent-do dictate (the Chair's ears), Wispr-class streaming dictation

## Inputs

- None declared.

## Work order

Wispr+++ on TeleFollower's proven ~400 Swift lines: shared-mic AVAudioEngine capture, Deepgram Nova-3 streaming (text lands on key release), Carbon hold-to-talk, insertion via live-gated macos substrate. Keyterm priming from working vocabulary (coord paths, manna titles) must be OPT-IN per scope: cloud exfiltration boundary. Fallback: transcribe --method local-whisper. Consumer: holy-ghostty C4 (mn-a40d06 there) depends on this. Grab-safe, no deps.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-a45739`.
4. Commit with `Manna: mn-a45739` and run `agent-do manna done mn-a45739` only after the work is verified.
