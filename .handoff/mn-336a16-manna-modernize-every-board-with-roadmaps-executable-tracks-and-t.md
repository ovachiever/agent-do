---
workflow: 2
manna: mn-336a16
track: mn-b7a0cc
source: 'Erik 2026-11-11: agreed Roadmap / Track / Ticket semantics, Dream as planning status, and requested one worker to modernize every repository board'
base_commit: b06fc38cea3a308a4b66f2af334c4b6656b64abd
scope: 'Manna: modernize every board with Roadmaps, executable Tracks and Tickets'
inputs:
- 'Erik 2026-11-11: agreed Roadmap / Track / Ticket semantics, Dream as planning status, and requested one worker to modernize every repository board'
binding: sha256:8cae520980a67112a4b274a7d294c43b1ad7fea9d895de8fdf77d030cd33977c
---

# Handoff: Manna: modernize every board with Roadmaps, executable Tracks and Tickets

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-336a16
```

## Scope

Manna: modernize every board with Roadmaps, executable Tracks and Tickets

## Inputs

- Erik 2026-11-11: agreed Roadmap / Track / Ticket semantics, Dream as planning status, and requested one worker to modernize every repository board

## Work order

One worker owns the complete change: implement the shared semantics in agent-do and Holy, then modernize existing canonical boards and work orders. This is implementation plus a verified migration, not an inventory-only return. Use the checkpoints below within this assignment. Do not launch other workers or turn every repository into another implementation lane.

### Agreed product model

| Concept | Meaning and behavior |
|---|---|
| Roadmap | An ongoing organizational direction containing related work. It is not claimable or launchable, even if an old document pointer exists. |
| Track | A bounded, executable plan with a clear outcome, completion conditions, child work and a sealed execution work order. It can be assigned as a whole when its normal eligibility gates allow. |
| Ticket | One concrete assignment. Preserve the existing `item` machine spelling if that avoids needless compatibility churn; the user-facing vocabulary is Ticket. |
| Dream | Parked, uncommitted planning status, not a fourth structural container. It does not authorize dispatch. Preserve legacy dream records during conversion. |
| Goal | The outcome described in the work order. Do not add a mandatory Goal object or another management hierarchy. |

Roadmap membership is optional. Standalone tracks and tickets remain valid. Do not manufacture wrapper tracks to fit a grammar. Claiming a track reserves no children, prevents no independent child claims and grants no publishing, integration, deployment or acceptance authority. Keep role, assignment and permission separate.

Examples, to be checked against their actual work orders: Holy's `mn-eb7a80` reliability/continuity umbrella is a Roadmap candidate; `mn-5db142` Holy 1.0 release gates is a Track. Do not classify solely from titles, prefixes or child counts. Preserve mn IDs and provenance when the entity's meaning is clear. Ask about a genuinely ambiguous scope rather than inventing a finish line.

### Checkpoint 1: establish the estate and current contracts

1. Start in `/Users/erik/Custom-Coding/agent-do`. Read each affected repository's instructions before edits; coordinate ownership of shared surfaces. Holy is `/Users/erik/Custom-Coding/holy-ghostty`.
2. Read `manna estate --json`, registered board metadata and actual repositories under the configured project roots, including `/Users/erik/Custom-Coding`. Discover boards omitted from the registry and report repos with no board. Do not use an old fixed board count or initialize a board in the workspace holding directory. Explain exclusions such as generated fixtures, vendored repositories, archived checkouts and inaccessible roots.
3. Resolve one authoritative board per project using federation identity and repo/worktree evidence. Replicas, clones and worktrees are not independent projects to migrate repeatedly. Refuse ambiguous or divergent replica writes; record the precise conflict and continue independent boards. Do not delete registrations, fork board identities or select the newest-looking file as a substitute for resolution.
4. Capture a complete per-board inventory and baseline: paths, identities, kinds, states, memberships, blockers, claims/attempts, submissions, acceptance records, handoff pointers/digests and current reader versions. Identify affected records and the intended disposition before applying changes. Keep this manifest in `.dev/`; Manna remains the canonical work ledger.

### Checkpoint 2: implement the model and safe conversion in agent-do

1. The inspected CLI currently exposes `type: track|item|dream`; Roadmap and Dream-as-status are new behavior. Implement them in the canonical model, readers/writers, CLI, derived state and human board, using explicit version/compatibility handling. Do not simulate the change with title prefixes or raw JSONL edits. Preserve existing fields and unknown metadata where required by the compatibility contract.
2. Add or extend the supported conversion/migration commands. They must provide a reviewable preview, protect concurrent changes, journal recoverable writes and resume idempotently. Rerunning a completed conversion must not create duplicate rows, documents, memberships or new claims. Snapshot the board and owned documents before each apply; demonstrate recovery in isolated fixtures.
3. A new active Track receives a canonical paired/sealed work order through normal creation. An existing finite track gets an idempotent, reviewed work order without overwriting substantive instructions. Roadmaps cannot be claimed, dispatched or completed as if they were executable tracks. Preserve the existing child-closure gate for Tracks.
4. Track execution reads live children and readiness from Manna before each selection, uses each child's own sealed instructions, claims children individually, respects other owners and stops at real review/human/permission blockers. The work order defines completion and where to record progress for a successor. No copied child list becomes another source of truth.
5. Preserve the distinction between kind, planning status, execution readiness, ownership and acceptance. A Dream remains unclaimable until deliberately activated. A sealed Track with blocked children remains blocked. A commit or submission alone must not become acceptance. Retain work-order and submission revision bindings.
6. Update creation templates, contracts, documentation, bootstrap guidance and tests so new records stay modern. This is not a one-time cosmetic rewrite followed by tools recreating the old ambiguity.

### Checkpoint 3: make Holy and standalone Manna agree

1. Update Holy's decoding, presentation, filters and existing claim/launch guards for the same canonical meanings. Keep the CLI/serve experience usable without Holy.
2. In unfiltered Live/All Board views, all matching Tracks appear exactly once under Tracks, regardless of whether ready, active or blocked. Roadmaps have their own clearly labeled organizational section. Preserve existing status filters: Live excludes completed work, All includes it, and Done still finds completed records. Tickets retain their normal workflow sections. Remove the misleading split represented by “2 more in the sections below.”
3. Preserve track gold identity, canonical child progress, selection, search, parent context and visible state. Keep roadmap identity visually distinct. Claimability controls the action, not which section contains a Track. Command-click continues to locate a record; it must not launch work.
4. Keep current manual ticket dispatch and single-worker track execution working. The separately filed lead/team tracks `agent-do:mn-a2b986` and `holy-ghostty:mn-dff267` are not authorization to implement team launch, grant lead powers, enable MI pilots or perform wake-ups in this assignment.
5. Prove compatibility before the first real board conversion. An installed older writer must not erase new meaning or corrupt the board. If a reader rollout is required, report the exact prerequisite and hold unsafe conversions until it is satisfied. Do not bypass this with manual state edits or an alternate launch path.

### Checkpoint 4: apply the verified modernization across canonical boards

1. Apply supported, tested commands to every eligible canonical board in the inventory. Unfinished bounded Tracks receive reviewed execution work orders, correct relationships and seals. Organizational umbrellas become Roadmaps. Normalize legacy Dreams without activating them. Keep historical completion/evidence intact; do not reopen done work or generate executable assignments for completed history.
2. Preserve all current IDs, valid blockers, priority, ownership, attempts, branches, submissions and recorded approvals unless an explicitly supported conversion requires a documented change. Re-read state under the conversion guard immediately before mutation.
3. Do not revise or reseal another worker's active work order, reparent its assignment, or change its claim binding underneath it. Preserve it and record a concrete deferred action tied to the existing owner. A stale presence alone never authorizes taking over a claim. Continue work on independent records.
4. Repair relevant pairing or vocabulary defects through the tool. Do not sweep unrelated board drift, archive/delete old documents, or close/release work as cleanup. Keep these existing assignments separate: `mn-d2d67b` completed-handoff retirement, `mn-040aae` historical handoff debris, `mn-15fed0` decision state and `mn-42501b` completion reports. Reuse their implemented mechanisms if present; this task does not approve their unfinished scope by implication.
5. Record per-repo changed and unchanged counts, conversions, work orders/seals verified, and named blocked/deferred records. Preserve foreign working-tree edits. Make scoped local commits only for owned changes, with `Manna: mn-336a16`; do not sweep shared board files containing unrelated changes into a commit.

### Checkpoint 5: acceptance and return

Execute meaningful regressions for: Roadmap claim refusal despite a document pointer; finite Track dispatch; parked Dream refusal and deliberate activation; standalone tickets; individual child claims while a Track is claimed; dependency order and acceptance barriers; all Tracks grouped once in Holy; legacy reads and conversion; interrupted/repeated migration; replica ambiguity; active-claim and work-order digest preservation; and historical done records remaining done. Exercise the real CLI on isolated repository fixtures. Use isolated Swift fixtures, with app-host guards that keep tests off live boards and sessions. Discover exact commands from each repo's current manifest and test harness.

For every inventory entry, report migrated, already conforming, intentionally historical, no-board, inaccessible or blocked, with evidence. Missing/inaccessible boards and unresolved classification/ownership problems are not passes. Do not claim every repo is modern while required conversions remain. Reconcile the denominator so a successor knows precisely what is left. Show a second migration pass is a no-op on the completed cohort.

Return exact source revisions, executed test counts, per-board receipts, remaining gates and the next action. Follow the repository's actual closure requirements: do not close on unexecuted checks or turn submission into acceptance. Keep an installed visual check separate if one is required; do not perform it under this work order. Independent review must be able to reproduce the migration from the saved baseline and commands.

### Authorization and boundaries

Claiming this item authorizes the implementation and safe board/work-order migrations described above. Filing it does not start them. Do not implement product features in the other repositories; their scope here is board records, execution work orders and directly relevant workflow guidance.

No worker launches, automatic model API processing jobs, publishing, pushes, PRs, deployment, app install/restart, live wake delivery, Clear/Attach/Restore actions, or tmux server/session/pane changes. No deletion of history, board registrations or remote refs. Use existing tool paths and preserve the user's active work. When migration impact is genuinely uncertain, isolate the affected record/cohort and ask with the concrete evidence rather than blocking unrelated safe progress.

Keep receipts in repo `.dev/`, canonical work orders in `.handoff/`, and copy substantive Manna documents to iCloud Transfer and Obsidian `+/Holy Artifacts/Manna` using `agent-do obsidian save` with the explicit folder. Product design documents belong in `+/Holy Artifacts/agent-do` or `+/Holy Artifacts/holy-ghostty`. Do not put workflow paperwork in the vault's bare `+` inbox.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-336a16`.
4. Commit with `Manna: mn-336a16` and run `agent-do manna done mn-336a16` only after the work is verified.
