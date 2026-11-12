---
workflow: 2
manna: mn-f568d0
track: mn-b7a0cc
source: 'Erik 2026-11-11: create a manna to prove this on copies so we can review; supersedes combined build-and-live-migrate authorization'
base_commit: f528ac6584423f9999777f8546ad001868539fd0
scope: 'Manna: prove Roadmap/Track/Ticket modernization on isolated board copies before live rollout'
inputs:
- 'Erik 2026-11-11: create a manna to prove this on copies so we can review; supersedes combined build-and-live-migrate authorization'
binding: sha256:cbbab1f05afaa3ebec2bbe114e61c956936db86ae756ebeecd6aab9f05b895a9
---

# Handoff: Manna: prove Roadmap/Track/Ticket modernization on isolated board copies before live rollout

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-f568d0
```

## Scope

Manna: prove Roadmap/Track/Ticket modernization on isolated board copies before live rollout

## Inputs

- Erik 2026-11-11: create a manna to prove this on copies so we can review; supersedes combined build-and-live-migrate authorization

## Work order

Build the proposed modernization and prove it on copies before any live rollout. This item owns the implementation and rehearsal previously bundled into mn-336a16; that item now owns only the reviewed rollout and is blocked by this one. Start in agent-do, read both repositories' instructions and coordinate paths before editing. One worker owns this proof. Filing does not start implementation or launch a worker.

### Product contract

- Roadmap: ongoing organizational direction, never claimable or launchable even with an old work-order pointer.
- Track: bounded executable plan, clear outcome and completion criteria, live children and dependencies, canonical sealed work order. Normal readiness and acceptance gates still apply.
- Ticket: one assignment; keep the existing `item` machine spelling where compatible. Roadmap membership is optional.
- Dream: parked planning status, not another structural kind. Conversion must preserve existing dream records without activating them. Goal remains outcome text, not a new required object.
- Claiming a Track reserves no children and grants no integration, publishing or acceptance authority. Children remain independently claimable. Track execution rereads canonical eligibility and each child's instructions before claiming work.
- Holy and standalone Manna agree: all matching Tracks occur once under Tracks, Roadmaps separately, tickets in workflow sections. Preserve status filters, gold Track identity, progress, search, selection and parent context. Command-click only locates records.

Read mn-336a16's full product requirements and preservation rules as the shared specification. Its live-apply steps are outside this item's authority. Existing lead/team features, MI activation and unrelated cleanup lanes remain separate work.

### 1. Read-only inventory and faithful copies

1. Inventory registered boards and actual configured repository roots, including `/Users/erik/Custom-Coding`. Identify canonical federation identities, replicas, worktrees, inaccessible roots and repos without boards. Do not initialize or repair real boards or registrations. Record ambiguities rather than choosing a winner by timestamp.
2. Capture consistent snapshots of canonical boards, work orders and required history using a supported snapshot or a verified stable read. If files change while read, mark the capture inconsistent and retry only that capture. Snapshot before/after comparison must not mistake another agent's concurrent work for this worker's mutation.
3. Rehearse on copies of every accessible canonical board; group records by meaningful shapes and report full coverage. Include agent-do and Holy. Retain exact source hashes, versions, identities and copy provenance. Preserve original snapshots separately from working copies. Synthetic adversarial fixtures supplement real copies; they do not replace them.
4. Keep proof artifacts under a dedicated `.dev/mn-f568d0/` root. Isolate homes, registries, caches, Coord state, board roots, database paths and executable selection. Copied symlinks, absolute paths, `.git` worktree indirection, federation lookups and app defaults must not lead writes back to live repositories or user state. Remap copy-only references explicitly and retain the mapping. Keep identity keys and credentials out of copies and exports; use fixture identities where execution needs authentication and distinguish that from preservation of copied claim records.
5. Prove isolation before mutation: enumerate resolved write targets and use filesystem/process guards or equivalent executed checks to refuse paths outside the rehearsal root. Test a deliberately escaping reference. Do not treat an environment-variable declaration alone as proof. Canonical claiming and return paperwork for this item are the only intended live Manna writes.

### 2. Implement the real candidate in isolated source checkouts

1. Implement the canonical model, versioned reader/writer compatibility, creation templates, supported conversion commands, documentation and tests in isolated agent-do and Holy checkouts. Use production CLI paths against isolated boards; no direct JSONL rewrite or mock migration sold as a pass.
2. Keep candidate source off the installed entry points: agent-do may execute directly from its primary checkout. Local candidate branches/commits are allowed, but do not merge into an installed source tree, install binaries, start Holy or activate new code in live consumers.
3. Migration must preview changes, preserve IDs and required metadata, detect concurrent changes under the write guard, journal recoverable changes and resume idempotently. Test snapshots and recovery without overwriting unrelated subsequent edits. Existing active claim/work-order bindings stay intact or the affected conversion is explicitly deferred.
4. A Track receives a reviewed canonical work order and seal without inventing scope, activating a Dream, overwriting substantive instructions or reopening completed history. Organizational umbrellas become Roadmaps by meaning, not title prefixes or child counts. Ambiguous classifications receive a concrete question and a deferred disposition.
5. Exercise current installed reader/writer versions as well as the candidate on copies. Old tools must not silently erase new fields or meanings. If compatibility requires a coordinated upgrade, demonstrate refusal and document that rollout prerequisite instead of bypassing it.

### 3. Required executed proof

Use the owning manifests and isolated test harnesses. Before app-hosted tests, verify all launch, wake, discovery and persistence paths are confined to fixtures; if that cannot be established, stop those tests and report the gap. No real tmux server/session/pane activity is authorized, including starting private servers.

| Proof | Required evidence |
|---|---|
| Canonical semantics | Real CLI refuses Roadmap dispatch even with a pointer; parked Dreams remain parked; finite Tracks and standalone Tickets work. |
| Ordered execution | Child readiness, independent child claims, other-worker ownership and integration/review/acceptance blockers remain authoritative. No worker launches are needed to test assignment contracts. |
| Holy presentation | Isolated Swift fixtures show each matching Track once, Roadmaps separately, correct filters/progress/actions, and unchanged manual ticket dispatch. |
| Data preservation | Field-level before/after diff covers IDs, membership, blockers, status/history, claims/attempts, submissions/approvals and handoff contents/digests. Every difference has an allowed reason; active and completed records are not silently changed. |
| Failure handling | Inject interruption at real durable write boundaries, then recover. Exercise conflicting writes, stale snapshots, ambiguous replicas, malformed/unknown metadata and escaping paths. No partial board is silently accepted. |
| Repeatability | Second apply is a no-op on each completed cohort, with no duplicate IDs, work orders, relations or new claims. Reproduce from an untouched snapshot. |
| Reader compatibility | Candidate and actual supported old versions read/write or explicitly refuse safely on copies. Report upgrade requirements. |
| Isolation | Executed evidence identifies actual write destinations and confirms no test-driven live mutation or runtime activation. Source boards may change through other agents; account for that separately. |

Run relevant existing suites, not only newly written tests. Report exact commands, exit codes, denominators and source revisions. Compilation is not an executed test. A skipped or blocked scenario remains a gap. Do not fabricate a live claim proof to make copied production identities executable.

### 4. Review packet and release gate

Return a short human-readable report plus machine-readable per-board manifest: inventory denominator, copied/excluded/unavailable boards, proposed Roadmap/Track classifications with reasons, changed/unchanged/deferred counts, before/after diffs, exact candidate revisions, test receipts and reproduction commands. Keep full board snapshots local; copies exported to Transfer/Obsidian must not disclose credentials or private runtime artifacts. Include explicit remaining decisions and a recommended low-risk first live board; do not migrate it.

An independent reviewer must be able to rerun the candidate on untouched copies and inspect the classifications and preservation evidence. Return **SUBMITTED for independent review**, reseal the handoff and stop. Do not run `manna done` for this item, remove mn-336a16's blocker, or treat green tests as acceptance. A reviewer records acceptance against exact source revisions and snapshot/receipt hashes, then closes this proof item. A changed migration invalidates that verdict until reviewed again. Unresolved safety or coverage gaps prevent release; named intentional deferrals require a review disposition.

Passing this proof does not itself install software or migrate a real board. The downstream worker must verify the recorded acceptance, required installed compatibility and current board state, then execute the separately scoped staged rollout.

### Boundaries and deliverables

No live board conversion, source activation, app install/restart, worker launch, wake-up, Clear/Attach/Restore, tmux change, publishing, push, PR, deployment, automatic model API processing job, broad cleanup or deletion. Preserve foreign changes and coordinate narrow owned paths. Do not alter another worker's live claim or work order. Ask only about concrete ambiguity or an unfulfilled prerequisite; continue independent safe proof work.

Commit owned candidate code with `Manna: mn-f568d0`. Save reports under repo `.dev/`, canonical handoff here, and copy review documents to iCloud Transfer and Obsidian `+/Holy Artifacts/Manna` via `agent-do obsidian save` with explicit folder. Record where the candidate branches and untouched snapshots are located.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-f568d0`.
4. Commit owned changes with `Manna: mn-f568d0`; return SUBMITTED with exact evidence. No self-close. Independent review and recorded acceptance are required before a reviewer closes this item and releases mn-336a16.
