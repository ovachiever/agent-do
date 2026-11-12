---
workflow: 2
manna: mn-5cdd6e
track: mn-b7a0cc
source: Independent review of mn-ed4353 on 2026-11-03; .dev/mn-ed4353-review/probe.log
base_commit: 373470fec68e88594ccfb996aa46c7c30d90e039
scope: 'Corrective: assignment targeting must refuse ambiguous delivery and expire approvals on claim turnover'
inputs:
- Independent review of mn-ed4353 on 2026-11-03; .dev/mn-ed4353-review/probe.log
binding: sha256:7b3e06e55914f61b69359ab7eaea13793bd8da7296294508d161c40f8b336274
---

# Handoff: Corrective: assignment targeting must refuse ambiguous delivery and expire approvals on claim turnover

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-5cdd6e
```

## Scope

Corrective: assignment targeting must refuse ambiguous delivery and expire approvals on claim turnover

## Inputs

- Independent review of mn-ed4353 on 2026-11-03; .dev/mn-ed4353-review/probe.log

## Work order

Independent review of mn-ed4353 / 0342d6b found two reproducible acceptance blockers through the real CLI. Preserve the original done item as history; this corrective item carries remaining acceptance. Managed Integration mn-54fe40 must wait for independent acceptance of this correction.

P1: Ambiguous destination still delivers and counts acknowledgment.
Two live Coord records with distinct anchors and the same Manna proof produce destination.state=ambiguous and no selected recipient. Nevertheless either candidate sees the approval under drops --for-me and can drop ack it; delivery.stage becomes acknowledged while recipient.state remains ambiguous. _drop_targets_me uses proof membership without requiring unique resolution; ack_drop and _exact_recipient_ids inherit this. Fix the invariant consistently across delivery, interrupts/hooks, acknowledgment, resolution and pending delivery: ambiguity cannot confer recipient authority or satisfy delivery. Preserve same-harness aliases when identity is genuinely verified. A formerly unique mapping becoming ambiguous must also be handled explicitly.

P1: Same-worker reclaims silently inherit old approval.
Claim, record scoped approval, abandon, then reclaim the same item from the same worker session. claimed_at changes but claim proof is unchanged; the old approval remains visible with delivery.stale=null. _staleness checks only proof, done status and work-order digest; it does not check the pinned claim epoch or managed attempt. Bind to the full assignment instance, including canonical board and claim generation/managed attempt, and revalidate at delivery and lifecycle actions. Unknown attempt observations must be explicit and cannot silently weaken approval binding. Explicit authorized readdressing may create a new revision; never auto-renew authorization.

Receipts and reproduction
.dev/mn-ed4353-review/probe.py and probe.log preserve both exact CLI sequences in isolated fixtures. Source pointers: tools/agent-coord _drop_targets_me, _exact_recipient_ids, _staleness, _deliver_pending_item_drops, ack_drop and _may_resolve_drop. Existing test_assignment_targeting verifies ambiguous lookup but never candidate read/ack, and different-worker reassignment but not same-worker reclaim.

Acceptance
Add regressions for both sequences through actual CLI and hook paths, plus managed attempt turnover, late pending delivery and mapping changes after recording. Demonstrate regressions fail on 0342d6b behavior and pass with correction. Run coord v2 and hook routing suites and relevant validation. Preserve action/info behavior, role/broadcast semantics, history and honest receipt stages. No live approval relay, no live session retirement, no paid credential access/API calls, no push or PR, no Managed Integration implementation. Use isolated fixtures, preserve foreign changes. Commit with this item's Manna trailer, seal handoff and return SUBMITTED for independent review. Do not self-close. Reviewer acceptance must cite exact source and executed receipts before unblocking mn-54fe40.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-5cdd6e`.
4. Commit with `Manna: mn-5cdd6e`, return SUBMITTED, and leave closure to the independent reviewer after acceptance.

## Implementation return (2026-11-03)

SUBMITTED for independent review. Source commit `7096b00`. Both regression tests fail against the original Coord code at `0342d6b` and pass with this correction. Full Coord v2 (19 scenarios), Coord v1, routing, syntax and whitespace checks passed. The full root and Rust suites were not rerun for this Python-only implementation. One initial focused hook-context assertion failed; unchanged focused rerun and final full suite passed.

Receipts: `.dev/mn-ed4353-review/fix-return.md`, `baseline-regressions.log`, `fix-regressions.log`, `fix-full-coord-v2.log`, `fix-coord-v1.log`, `fix-routing.log`.

Current-recipient uniqueness now governs delivery, acknowledgment and resolution. Canonical board, claim timestamp and managed attempt are revalidated; stale pending drops do not ring and old approvals require explicit readdressing. Need-key matching cannot bypass item targeting. Managed generation is read directly from atomic sidecar metadata to avoid a recursive Coord/assess lock cycle, with unreadable state refusing authorization. No new command or schema.

Item remains in_progress; the implementer has not independently accepted its own correction. Managed Integration `mn-54fe40` remains blocked by this item. No push, PR, real credential retrieval or paid API job. Shared board edits remain uncommitted to preserve unrelated work.
