---
workflow: 2
manna: mn-882c9e
track: mn-455a88
source: mn-58c9ea
base_commit: 4010d8a1842224a890298514ba5f84626dc6e580
scope: 'Harness: optional live Gmail search provider for email'
inputs:
- mn-58c9ea
binding: sha256:fca5dbfa7ccb51b5fd1a1ec488750de217ab91117931e4740f2b8b6c02871faf
---

# Handoff: Harness: optional live Gmail search provider for email

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-882c9e
```

## Scope

Harness: optional live Gmail search provider for email

## Inputs

- mn-58c9ea

## Work order

Follow-up to mn-58c9ea. Gmail accounts currently use the local Mail index plus an explicit coverage guard. Add read-only live Gmail search via Gmail API or IMAP X-GM-RAW behind the existing email verbs, reuse secure credentials, preserve per-account coverage receipts and provider provenance, and verify with fixtures before a coordinated live pass. Optional provider expansion; no sending, app launch, or credential migration from another project.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-882c9e`.
4. Commit with `Manna: mn-882c9e` and run `agent-do manna done mn-882c9e` only after the work is verified.
