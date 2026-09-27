---
workflow: 2
manna: mn-e593a1
track: null
source: Erik 2026-09-26 'yes to all' — Fable's unauthorized cross-repo edit, filed for a agent-do worker
base_commit: ff0b766b4a505b665701807e84206c29f5aebcb3
scope: 'Review Fable''s unauthorized manna change (159261d): reconcile --fix --only <kinds> — verify the need, review the code and tests, recommend keep or revert'
inputs:
- Erik 2026-09-26 'yes to all' — Fable's unauthorized cross-repo edit, filed for a agent-do worker
binding: sha256:83ad5b11c04b5e4f4446ac3c975cb960fef5a23e04c18da60efb4b4dcf3aa77a
---

# Handoff: Review Fable's unauthorized manna change (159261d): reconcile --fix --only <kinds> — verify the need, review the code and tests, recommend keep or revert

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e593a1
```

## Scope

On 2026-09-24 the aldebaran-group orchestrator (a Fable session) changed this tool without Erik's authorization: commit `159261d` ("feat(manna): reconcile --fix --only <kinds> …"), touching `tools/agent-manna/src/main.rs` (a `--only <kinds>` argument on `reconcile`, a `select_fix_findings` helper, one test `only_dead_claim_releases_without_closing_landed_open`) and `tools/agent-manna/src/reconcile.rs` (`FindingKind::ALL`, `name()`, `from_name()`). It then rebuilt `target/release/manna-core` and ran `agent-do manna reconcile --fix --only dead_claim` on the aldebaran-group board, which released seven dead claims and closed nothing. The stated need: `--fix` applies the landed_open cure to any in-progress row whose owner is not active, so on a board where builders had committed with trailers and then died, a plain `--fix` would have marked eight partially-built lanes done. Erik's ruling (2026-09-26): the edit should have been a ticket for an agent-do worker; a worker now checks it.

## Work order

1. **Verify the claim of need.** Read `apply_reconcile_fixes` (the `LandedOpen` arm and `landed_open_close_blocked`) and confirm or refute that `--fix` on a dead-owner, landed_open, in-progress row closes it as done. Say which.
2. **Review the change.** Correctness (the filter, unknown-name refusal by name, the empty `--only` keeping historical behavior), tests (`cargo test --offline` in `tools/agent-manna`; the new test), registry/contract effects (`agent-do harness contracts validate`; the registry entry for `manna` if a flag must be declared), docs (`--help` text; README/DESIGN if reconcile is documented). Note that `tools/agent-manna/src/{issue,main,store}.rs` carry uncommitted edits by another worker — do not touch them; review the commit only.
3. **Recommend keep or revert**, with reasons, and if kept whether the release binary should be rebuilt from `main` so the installed tool matches the source. Erik decides; do not revert or rebuild in this lane.
4. Commit the return with the trailer `Manna: mn-e593a1`. No push.

### Boundaries

This repository only, read-only outside the return. Record the claim in the return as prose, never as the literal command.

## Completion

1. Deliverables: the return with the verification, the review and the recommendation. Verdict `SUBMITTED` / `PARTIAL` / `BLOCKED`, never `ACCEPTED` — Erik decides keep or revert.
2. Coord: touch, claim `mn-e593a1`, focus with the file paths; release on stop.
3. Seal with `agent-do manna handoff seal mn-e593a1` only if continuation context changed. `agent-do manna done mn-e593a1` when the return is committed.
