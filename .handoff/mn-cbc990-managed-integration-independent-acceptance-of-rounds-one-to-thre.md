---
workflow: 2
manna: mn-cbc990
track: mn-b7a0cc
source: mn-54fe40 closed mechanically 2026-11-04T03:00:51Z by the reconcile cure while SUBMITTED; pending acceptance and checkpoint C carried here
base_commit: fb540b72ee5419796e1dc6549650dcb61a3996e6
scope: 'Managed Integration: independent acceptance of rounds one to three (9fe3a44) and the bounded live pilot (checkpoint C)'
inputs:
- mn-54fe40 closed mechanically 2026-11-04T03:00:51Z by the reconcile cure while SUBMITTED; pending acceptance and checkpoint C carried here
binding: sha256:0e40881d59e69cbf09fa7dd4e198afa5f9235fdce83f4421fc31c3108ee93ed2
---

# Handoff: Managed Integration: independent acceptance of rounds one to three (9fe3a44) and the bounded live pilot (checkpoint C)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-cbc990
```

## Scope

Managed Integration: independent acceptance of rounds one to three (9fe3a44) and the bounded live pilot (checkpoint C)

## Inputs

- mn-54fe40 closed mechanically 2026-11-04T03:00:51Z by the reconcile cure while SUBMITTED; pending acceptance and checkpoint C carried here

## Work order

mn-54fe40 delivered Managed Integration (90f49ca), corrections after independent review (ba76f34) and after independent re-review (9fe3a44: the claim incarnation and the work-order digest pinned in submissions and landing intents), each returned SUBMITTED for independent review and never self-closed. The board closed mn-54fe40 mechanically at 2026-11-04T03:00:51Z (manna reconcile --fix run by another session's SessionEnd hook; defect filed as mn-4e7229), so the acceptance work still pending needs this item to stay discoverable. Scope: (1) independent review of 9fe3a44 against .dev/independent-integration-review/review-round2.md: accept, or file each remaining blocker as a new item citing mn-54fe40 and this one. (2) After acceptance and Erik's explicit selection of the pilot repository and the local integration authority, enable the bounded pilot (docs/MANAGED-INTEGRATION.md, section 'Enabling a pilot'), run two real assignments and one demonstrated recovery, and report implementation, acceptance and activation separately. Boundaries unchanged from mn-54fe40: no pilot without that explicit authorization, no push, pull request, deployment, bulk branch work or estate-wide rollout. Receipts so far: 21 fixtures in tests/test_git_integration.py (the round-two seven fail on an archive of 90f49ca, the round-three three on an archive of ba76f34); the sealed handoff of mn-54fe40 carries every round's dispositions and executed checks.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-cbc990`.
4. Commit with `Manna: mn-cbc990` and run `agent-do manna done mn-cbc990` only after the work is verified.
