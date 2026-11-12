---
workflow: 2
manna: mn-a2b986
track: null
source: Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
base_commit: 5229e77b91e408f7833fd646d021e4a0d427f294
scope: 'Transferable leads and coordinated track teams: standalone authority and integration'
inputs:
- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff
binding: sha256:834666c0f29008ad3067a8a6761522fa7f33d00ef9545f88a54704bd8b18d174
---

# Handoff: Transferable leads and coordinated track teams: standalone authority and integration

Board state is canonical in `.manna/`. This file is the work order for one track: one agent works the track's items in dependency order, one claim at a time. It is not a claim on the items, a progress ledger, or coordinator authority.

## Claim

```bash
agent-do manna claim mn-a2b986
```

## Scope

Transferable leads and coordinated track teams: standalone authority and integration

## Inputs

- Erik approved transferable lead/team plan, 2026-11-06; full contract in agent-do lead track handoff

## Work order

# Transferable project leads and coordinated track teams

Locked design: Erik's approved conversation plan, 2026-11-06. This filing authorizes work-order preparation, not implementation, worker launches, live notifications, publishing, deployment, or pilot activation. Canonical backlog and progress remain Manna; this document describes product invariants rather than a parallel ledger.

## Product and role
Any existing agent session can be designated lead for a project or track. No special agent type, new session requirement, fixed lifespan, or automatic context-quality scoring. A brainstorming session may become a lead when an idea becomes a workstream. Holy offers Make lead, Transfer lead, and Give this track its own lead. Designation alone launches no workers and starts no implementation.

One accountable lead per scope. An item resolves its track lead first and otherwise its project lead. Several scopes may have different leads, and one session may lead several scopes. A project lead may see track progress but may not silently override a track lead. No nested management hierarchy or lead elections in this build.

Agent-do is standalone and owns the durable designation: canonical project/board or track coordinate, exact session identity and proof binding, monotonically changed designation generation, explicitly granted authority, current brief pointers, and append-only appointment/transfer/authority history. Reuse the existing Manna/Coord/managed authority machinery rather than creating a second identity, backlog, credential store, or acceptance ledger. Choose the narrowest owning subsystem and extend its structured command contract; do not introduce an unrelated top-level tool. Holy is an adapter and UI, never the sole source of truth. The brief names objectives, current decisions, blockers and pending reviews by canonical IDs; it is not a copied progress ledger.

Role is distinct from authority. Authorities cover assignments, review/corrections, integration approval, final acceptance, named integration targets and separately granted publishing/PR/deployment operations. Appointment must not mint operator authority or bypass existing grants. Standing permissions avoid repeated questions within their scope. Every consequential operation verifies current scope, exact identity, generation, and authority, including after waiting for a lock and immediately before an external effect. Do not impersonate Erik. Launch authority is explicit and distinct from designation. Existing no-push/no-live-operation boundaries hold until authorized.

## Execution choices
Preserve Build item and Build track with one worker. Add Build track with a team. Single-worker tracks still claim children individually, obey required review, and do not monopolize child tickets. Team launch opens one session per actionable child ticket selected for that run, including currently blocked children: an eight-ticket track may open eight sessions while only three eligible workers begin. Decisions and dreams are not implementation workers. Completed items and tickets already owned elsewhere are displayed accurately, not relaunched.

Show the exact planned team and counts before launch (or operate under recorded standing launch authority). Record a stable launch/run identifier and each ticket-to-session assignment. Waiting is assignment, not an active Manna claim. Eligible workers re-read canonical state and claim before editing. Blocked sessions remain quiet, without model polling, token-spending loops, or asking Erik to relay messages. Manna decides order from dependencies and required gates; agents cannot negotiate around blockers through messages. Integration, review, acceptance and completion are distinct gates: a commit or submitted report never satisfies them by implication.

Repeated launch, concurrent hosts, partial launch, disconnect, crash, and retry must not create duplicate workers. A changed claim, work order, attempt, scope, lead or assignment invalidates stale operations appropriately. A manually launched worker that wins a ticket must be respected; never steal ownership. New tickets added after launch appear unassigned and need an explicit launch decision. Removed or moved tickets are reassessed, not blindly continued. A failed/closed worker becomes Needs replacement; no unbounded respawn. Replacement requires an explicit action or separately granted standing policy. Record uncertainty when a launch/delivery may have happened; reconcile evidence before retrying.

## Lead responsibilities and review
The lead translates requests into work orders, assigns workers, tracks progress, resolves questions, inspects submissions or commissions an independent reviewer, requests corrections, approves integration, accepts completed work and explains the project. It does not implement product code under the same role and then approve its own changes. Investigation, diff inspection, verification and integration are legitimate lead work; implementation corrections return to a worker. Approval records retain evidence of who reviewed what; review policy rejects author-as-independent-reviewer where independence is required.

Approval to integrate and final task acceptance are separate. Worker submits an exact revision and receipts; authorized lead approves that submission; MI prepares and validates an integration candidate; MI lands only while submission, claim incarnation, work-order binding, policy, target and approval remain valid; final acceptance checks any remaining installed/deployed/user-facing requirements. Existing repository policy must support checks-first as a preserved explicit option and review-and-checks as the orchestrated-team default. Do not silently activate MI or migrate an existing repository's policy.

An approval is bound to board/item, attempt, submission id, exact revision and the applicable work-order/policy evidence. Changed submissions invalidate it. Main advancing requires candidate rebuild and checks under the existing MI rules. Conflict resolutions or other introduced changes cannot silently inherit approval for different code: define and enforce exactly which resulting tree the approval covers. Revoked/expired or uncertain authority cannot authorize new effects. Recovery before landing revalidates the gate; recovery after landing completes the receipt without landing twice. Approval to integrate cannot be passed as final acceptance, and a trailer is never review approval.

## Transfer and continuity
Transfer changes the authoritative appointment and routes future questions/submissions to the new lead. Workers, branches and assignments stay put. The new lead gets the current brief plus canonical board, submission, approval, integration and blocker state, including honest unavailable-source status. The old lead loses authority for new decisions. Previously valid recorded approvals retain their original evidence and revision binding unless explicitly revoked or otherwise invalidated; transfer alone must not erase valid historical approvals. Test this distinction against in-flight actions, whose authority is rechecked before their consequential step. Completed effects remain completed. An outgoing lead need not be alive or cooperative; its final handoff is helpful but never required for transfer. Restarting Holy or replacing a conversation reconstructs state from agent-do.

## Wake delivery and UI
Use the existing coord-wake/1 contract, including durable dispatch-started before transport and unknown outcomes that prohibit blind retry. Holy uses its supported background inbox/readiness path, not GUI automation or unsolicited tmux input. Verify session incarnation and input readiness, preserve drafts and focus, queue while busy, and distinguish transport submission, prompt observation and worker acknowledgment. No delivery receipt grants approval or alters claims. Waiting workers wake only when their assignment and prerequisites are still current. Reuse mn-88d1ac, Holy mn-702ea1 and field check mn-aefa29; do not duplicate their work or treat their open live gate as passed.

Existing Holy surfaces gain a Lead badge, responsible lead on project/track views, assignment labels, scope/authority controls, and working/waiting/awaiting-review/needs-replacement/done team state. Waiting states name concrete prerequisite IDs and gates. Command-click remains selection, not launch. No new dashboard; do not flood the lead with every worker command. Remote/unavailable hosts remain explicit and never fall back silently to another board or host.

## Delivery order and acceptance
1. Agent-do durable scoped lead designation, transfer, authority, history, read model and recoverable state. Publish fixtures for Holy.
2. Agent-do pre-landing MI review gate and agent-do team assignment/eligibility lifecycle can proceed in parallel after the lead contract is accepted. Holy lead controls can proceed in parallel against that accepted contract.
3. Existing Holy wake support and its field check proceed independently. Holy team execution follows core assignments, lead controls, MI gate and wake implementation; installed acceptance requires the live wake gate.
4. Combined field check in one opted-in project: designate an existing lead, launch a team with ready and blocked items, verify quiet wait and automatic wake, reject/correct a submission, prevent old approval reuse, land under review policy, transfer lead mid-run without restarting workers, recover after Holy restart and partial launch, respect manual individual dispatch, and prove no duplicate launches or focus theft. Name source revisions, policy/authority, host/build and concrete receipts. Live checks require Erik's separately authorized project, sessions and build.

Cross-board depends_on relations currently express lineage, not an enforced block. Work orders must name exact cross-repo prerequisites and require their accepted contract/source evidence before dependent implementation and live effects. Local blocked_by edges enforce local order. Do not assume federation metadata alone enforces execution eligibility; runtime team behavior must use authoritative supported eligibility and fail closed on unavailable required evidence.

Each build returns SUBMITTED for independent review with exact commits, executed focused tests, sealed receipts and all remaining live gates. Keep field checks separate from source completion, preserve foreign dirt, commit only owned paths, and do not run board cleanup. No mandatory conversion of all existing items, new dependency/framework, automatic context scoring, elections, lead hierarchy, mandatory team execution, automatic publishing grant or hidden always-running model job. Existing single-worker track and MI pilot remain independently testable.

**Track dispatch protocol.** Every item in this track keeps its own claim, its own sealed work order, and its own close. The steps below are the whole assignment.

1. Read the track from the canonical board: `agent-do manna show mn-a2b986 --json`. `children.next` names the one item to claim now: open, unclaimed, every blocker done, highest handoff priority first (`.manna/handoff-order.yaml`), then the oldest row, then the lowest id. `children.eligible` lists the rest in that order; `children.held`, `children.waiting`, and `children.decisions` say what is not yours to take; `children.stall` says why `next` is null.
2. Claim that item individually: `agent-do manna claim <item-id>`. A refusal (claimed elsewhere, blocked, a changed or unsealed work order) is final for that item: take the next eligible item instead. Never retry around a refusal, never claim through another identity, and never work an item you do not hold.
3. Read the item's sealed handoff named by its `prompt` field and follow it to completion exactly as a single-item worker would: its owned paths, its verification receipts, a Conventional Commit carrying `Manna: <item-id>`, and its own close. `agent-do manna done <item-id>` closes an ordinary item; a managed item takes `agent-do manna submit` instead, and a submission is not acceptance: the item stays in progress until its coordinator accepts it.
4. Refresh before every selection by running step 1 again. The board is the only record of progress. Items added to the track since your claim are listed under `children.added_since_claim`: each carries its own sealed work order, so name the change of scope in your report before claiming one; nothing is claimed silently. Items moved out of the track or deleted disappear from the list; one you already hold stays yours under its own work order.
5. Continue while `children.next` is non-null. When it is null and `children.open` is not zero, record the exact blocker (`children.stall`, the item ids, the owner of a claim held elsewhere, the external prerequisite) in your report and in this handoff's receipts, reseal, and stop. A lane that ends releases the track with `agent-do manna abandon mn-a2b986`; every item claim and every commit stays where it is, and a successor claims the track and rebuilds progress from the board, never from this file.
6. Holding this track grants only the right to claim its eligible items one at a time. It reserves no item, blocks no independent worker (any session may claim this track's items at any time; the board's atomic claim decides), confers no coordinator authority, accepts nothing, and authorizes no merge, deploy, push, or pull request.

## Completion

1. `agent-do manna done mn-a2b986` closes the track only when every item in it is done; the board refuses otherwise and lists what is open. Submitted-but-unaccepted items are open. An empty track cannot close; delete it or give it items.
2. Update this handoff only when continuation context changed; seal with `agent-do manna handoff seal mn-a2b986`.
3. Commit board paperwork with `Manna: mn-a2b986` only on a commit that advances the track itself; item work carries the item's own trailer.

## Filed execution gates and references

Local prerequisites: none.
- counterpart: manna://mb-87598702f834dad27f9bb5856a2072ea/mn-dff267 (Holy controls, team sessions and field check).

Cross-board relations are references, not automatic claim blockers. Read accepted source/contract receipts on the named board before dependent implementation; if unavailable or unaccepted, report the prerequisite and do not substitute a guessed interface.

First build: mn-8af047. After its independent acceptance, mn-5e2dcf and mn-2a1305 may run in parallel with Holy mn-6b97d6. Holy team execution and the final field check follow their recorded prerequisites. Filing this plan does not start these lanes.
