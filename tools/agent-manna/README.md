# Manna

> Git-backed issue tracking and context management for AI agents

Manna is a compact issue tracking system designed specifically for AI agent workflows. It provides issue tracking with dependencies, session-based claims for multi-agent coordination, generated handoff work orders, and context injection for AI prompts.

## Overview

### Why Manna?

Traditional issue trackers (Jira, Linear, GitHub Issues) are designed for human workflows. Manna is designed for **AI agents**:

- **YAML output** - Machine-readable, LLM-friendly format
- **Session-based claims** - Prevents multiple agents from working on the same issue
- **Context injection** - Generates context blobs for AI prompts
- **Git-backed** - JSONL storage that diffs cleanly in version control
- **Fast** - All operations complete in <100ms

### Features

- **Full issue lifecycle commands** for tracks, items, dreams, and dependencies
- **Dependency tracking** with blockers
- **Session management** for multi-agent coordination
- **Generated `.handoff/` work orders** with bidirectional board linkage
- **Fail-closed claims** when an item's handoff contract drifts
- **File locking** for concurrent safety
- **Corruption recovery** for partial writes

## Installation

### Prerequisites

- Rust toolchain (1.70+)
- Cargo package manager

### Build

```bash
cd /path/to/agent-do/tools/agent-manna
cargo build --release
```

The Rust binary is `manna-core`. The wrapper resolves `target/release/manna-core`,
falls back to `target/debug/manna-core`, and can also use a `manna-core` binary on
`$PATH`.

### Verify Installation

```bash
./agent-manna --help
```

## Quick Start

```bash
# Initialize manna in current directory
agent-do manna init

# Admit an existing nonempty board into strict pairing
agent-do manna migrate

# Create an issue
agent-do manna create "Fix authentication bug" "Users can't login with SSO"

# Derive dense priority names and the board index
agent-do manna sync

# List all issues
agent-do manna list

# Read the complete derived board model
agent-do manna state --json

# Read every board registered on this machine
agent-do manna estate --json

# Claim an issue to work on
agent-do manna claim mn-abc123

# Mark as done when complete
agent-do manna done mn-abc123

# Generate context for AI prompt
agent-do manna context
```

## Commands

### `init`

Initialize `.manna/` and the tracked `.handoff/` work-order root in the current
location. New or empty boards receive strict workflow version 2, board-owned
`.manna/handoff-order.yaml`, and a generated `.handoff/README.md`. Existing
nonempty legacy boards are classified explicitly and left unchanged. Strict
mode is pinned independently in `.manna/board.yaml`; deleting the workflow
config cannot turn validation off. Local ignore rules are narrowed so
the board and work orders remain Git-visible while the runtime lock stays
ignored. Every successful init also creates or preserves the tracked public
identity in `.manna/federation.yaml`; no relation is inferred.

```bash
agent-do manna init
```

**Output:**
```yaml
success: true
initialized: true
path: .manna
workflow: strict
workflow_version: 2
handoff_path: .handoff
gitignore_updated: false
recovered_transactions: 0
upgraded_items: 0
restored_config: false
federation_path: .manna/federation.yaml
board_id: mb-5c54d1b4cce04f8b9f4418a9180ad87e
federation_created: true
```

### `migrate`

Explicitly admit a nonempty legacy or mixed board into strict workflow version
2. One authenticated write-ahead transaction establishes the board identity,
creates and seals canonical handoffs for every legacy active item, annotates
done rows as grandfathered history, exempts tracks and dreams, and releases
claims that lack ownership proofs. Existing strict pairs are verified and
passed through byte-for-byte with their seals and ownership intact. A legacy
Markdown work order under `.handoff/` is adopted in place: migration wraps its
original contents in canonical frontmatter and required sections instead of
discarding it. Partial legacy frontmatter and old Claim sections remain inert
work-order content; only the canonical Claim section is authoritative. Active
description-first pointers may append ` — <note>` after the Markdown path;
that note remains row context and is never treated as part of the filename.
If an earlier migration admitted that malformed pointer, rerunning `migrate`
adds the exact source and provenance to the existing sealed handoff without
discarding its authorized body, then rebinds the row through the same journal.
Active
absolute pointers inside the project are normalized to repository-relative
provenance. An absolute pointer outside the project may import one regular
UTF-8 Markdown file when the file itself is not a symlink and the resolved path
does not enter Git metadata; its original path is recorded in the sealed
handoff. Imported source bytes are authenticated
separately from any target bytes the transaction may replace. Once those exact
bytes exist in every consuming sealed handoff, an in-project source outside
`.handoff/` moves to a deterministic
`.handoff/.archive/legacy-sources/*.source` evidence file in the same journaled
transaction. Cross-project sources remain untouched. Rerunning `migrate`
repairs boards admitted before source retirement existed while preserving
unaffected strict row and handoff bytes. Unique
hand-numbered prefixes seed first-class priority once; `manna sync` owns every
name afterward. Board identity is published last, so interruption leaves a
recoverable journal instead of a half-strict board. Repeating the command after
success is a byte-stable no-op. Migration then creates or preserves the same
tracked federation identity before reporting success. Its output includes
`federation_path`, `board_id`, and whether that manifest was newly created.

```bash
agent-do manna migrate
```

Ordinary strict writes never invoke migration and retain the same fail-closed
pair, ownership, Git visibility, and symlink checks. A row carrying a strict
handoff digest remains strict even if someone deletes its document binding;
`migrate` refuses that tampering instead of adopting or resealing it.

### `status`

Show current session status and claimed issues.

```bash
agent-do manna status
```

**Output:**
```yaml
success: true
session_id: ses_abc123
claimed_issues:
  - mn-def456
```

### `state [--json]`

Emit the canonical whole-board model used by native clients and `manna serve`.
It joins the complete public issue rows with unresolved blockers, reverse
dependents, handoff priority and existence, claimant liveness and pulse, Manna
trailer commits, federation resolution, Git state, drift, and the derived
`now`, `next`, `decisions`, `waves`, `dreams`, and `tracks` sections.
For a board registered with `manna serve`, it also reads the shared local
presentation cache and attaches hash-current `digest` and `summary` fields to
every matching row copy. This path is attach-only: it never registers a board,
creates cache state, or invokes a model. A missing or stale cache value leaves
the optional field absent.

```bash
agent-do manna state --json
```

The output never includes `claim_token_hash`, `legacy_migration`, or the
serve daemon's per-process `act_token` and `actor`. `description`,
`blocked_by`, and `prompt` remain present when the board row carries them, so
consumers do not need to join `list` and `show` themselves. Custom decision
markers can be added with repeated `--decision-marker '[NAME]'` flags. Because
the sections and counts claim whole-board coverage, a malformed JSONL row
fails `state` closed instead of being silently omitted.
The optional digest and summary fields are presentation material for human
interfaces. Agents continue to ground decisions in the durable board fields.

### `estate [--json]`

Emit every board in `$AGENT_DO_HOME/manna/serve/boards.json` through the same
derivation used by `manna serve` at `/api/boards`, without starting, probing,
or contacting the daemon. The command works outside a project and includes
registered roots that no longer exist so clients can report registry drift
instead of silently narrowing the estate.

```bash
agent-do manna estate --json
```

Each board row includes its root and slug, effective status counts, dreams,
decisions, drift count and source timestamp, latest issue update, and the
coord attention rollup (`needs_you`, `working`, `here`, and `gone`). The top
level carries the registry path, decision markers, aggregate attention totals,
and any still-building presence count. Output is YAML by default or JSON with
`--json`.

### `create <title> [description]`

Create a new issue. On strict boards, each actionable item also creates a
repository-relative `.handoff/<mn-id>-<slug>.md` work order and stores that
path in the issue's `prompt` field. A new track (`--type track`) is paired the
same way: its generated document is the dispatch protocol one agent follows to
work the track's items in dependency order (see "Tracks as whole-track build
assignments" below). Dreams never pair. A write-ahead transaction makes the row and
file recover as one pair after interruption. The transaction is HMAC-bound to
the canonical project root, complete rows, filename, canonical paths, and
payload, then installed with atomic no-clobber semantics.

```bash
agent-do manna create "Fix login bug"
agent-do manna create "Implement feature" "Full description here"
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: open
  created_at: "2026-01-29T10:00:00Z"
  updated_at: "2026-01-29T10:00:00Z"
  blocked_by: []
```

**Constraints:**
- Title: 1-500 characters

### `order <id> <position>` and `sync`

Priority is an ordered ID list in `.manna/handoff-order.yaml`. Move an item to
a one-based position, or converge presentation after any other board mutation:

```bash
agent-do manna order mn-abc123 1
agent-do manna sync
```

Both paths use the native recoverable rename transaction. Sync assigns dense,
board-wide fixed-width priorities with a two-digit minimum (`01..N`) and
expands the whole plan at 100 or more items (`001..N`). It derives the single
same-width blocker launch gate from the highest-numbered still-open blocker,
repoints every moved row, and regenerates `.handoff/README.md`. Dependencies
remain in `blocked_by`; filenames are never authority. Claimed handoffs do not
move, and their current number stays
reserved until release. Completed pairs return to unnumbered sealed history on
sync, so every bare numbered handoff remains a truthful launch signal.

```yaml
success: true
changed: true
renamed: 3
ordered_items: 8
held_claimed: []
```

### `claim <id>`

Claim an issue for the current session. Sets status to `in_progress`.

```bash
agent-do manna claim mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: in_progress
  claimed_by: ses_test123
  claimed_at: "2026-01-29T10:05:00Z"
```

**Notes:**
- Claim validation and the status change happen under one board lock, so one
  issue has exactly one winner under contention
- Attempting to claim an already-claimed issue returns an error
- Strict claims verify the board identity, Git visibility, symlink-safe path,
  structured frontmatter, exact Claim section, and whole-document SHA-256
  binding
- After claim, only the pinned `claimed_by` session may mutate or close the row
- A track is claimable only once it carries a dispatch work order (new tracks
  do; an older container track takes one through `handoff attach`). Claiming a
  track without one exits 2 and names that command; its items stay claimable
  individually either way

### `done <id>`

Mark an issue as completed and remove its ID from every dependent's
`blocked_by` list in the same locked, atomic board write. Dependents whose last
blocker clears return to `open`, or `in_progress` if already claimed. Dependents
with other blockers remain `blocked`; completed dependents stay `done`.

```bash
agent-do manna done mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: done
released:
  - mn-def456
```

`released` lists the dependents that became unblocked, in board order, and is
`[]` when none did. They are ready immediately after `done` returns. Deleted or
missing blockers and stale boards from older binaries remain the responsibility
of `reconcile --fix`.

For a **managed** item (one a coordinator put under `managed require`), `done`
takes none of the paths above. It needs a current submission, a pinned
integration target, every required check accepted for the current attempt at
that target, and an identity that is the operator, a granted coordinator, or
the claim-holder; trailer commits are receipts, never acceptance. Pass
`--assessment <digest>` from `assess` and the close refuses when the item's
acceptance state moved since that look. See "Managed lifecycle" below.

For a **track**, `done` closes only when every item in the track is done. Any
other state refuses with exit 2, writes nothing, and lists the open items with
their status; a submitted-but-unaccepted managed item is open. The same gate
runs under the board lock on every close path (owner, operator, landed
evidence, acceptance) and inside the locked write of `reconcile --fix`, where
it reads the items as they are at that moment rather than as they were when
the board was inspected: an item created under or moved into the track in
between refuses the close. No authority closes a track over open work. An
empty track cannot close: give it items or `delete` it.

### Managed lifecycle

Coordinator-owned closure: a worker submits, its session may vanish, and an
authorized coordinator accepts and closes (or releases) without resuming or
impersonating it. Records live in `.manna/coordinators.json`,
`.manna/managed.json`, and the append-only `.manna/lifecycle.jsonl`, written
under the board lock and never inside `issues.jsonl` rows.

```bash
agent-do manna identity                       # this session's label + proof (never the token)
agent-do manna coordinator grant --session ses_lead --proof sha256:... \
    --item mn-abc123 --reason "lead for this item"      # operator terminal only
agent-do manna managed require mn-abc123 --check integration --check deployed
agent-do manna submit mn-abc123 --report report.md --revision feat/x   # claim-holder
agent-do manna assess mn-abc123 --target origin/staging --json          # read-only
agent-do manna accept mn-abc123 --check integration --target origin/staging \
    --evidence "merge 1a2b3c reachable from staging" --submission sub-1a2b3c4d5e6f --attempt 1
agent-do manna accept mn-abc123 --check deployed --target origin/staging --evidence "release 42" \
    --submission sub-1a2b3c4d5e6f --attempt 1
agent-do manna managed recover mn-abc123     # finish a transaction whose audit or state write failed
agent-do manna managed recover board         # finish a grant or revocation that did not fully land (operator)
agent-do manna done mn-abc123 --assessment assess:...   # coordinator closes; worker not needed
agent-do manna managed correct mn-abc123 --reason "tests missing"
agent-do manna managed release mn-abc123 --reason "worker gone" --isolated-checkout /path/to/worktree
agent-do manna managed history mn-abc123
agent-do manna managed doctor --probe         # commands, hook registration, verified end to end
```

Authority never comes from a coord role, a pulse, a claimed label, or a
worker's shared secret: a grant binds a session label to its ownership proof
and to explicit items or tracks, and only the operator issues one. Every
mutation reloads the row and the grants under the board lock and re-derives
authority there, so a grant revoked meanwhile refuses. An acceptance names
the exact submission and attempt the coordinator reviewed (`--submission`,
`--attempt`, both printed by `assess`) and is refused under the lock when
either moved; a resubmission (after `managed correct` or otherwise) needs a
fresh verdict before anyone can close. Each mutation's outcome is durable as
an intent before its state and audit writes, so a failed write leaves the
item refusing to move until `managed recover` finishes the transaction.
Recovery decides who may finish it under the board lock, against the grants
and the pending transactions as they are then: a grant that was live when
recovery started and is revoked by the time it holds the lock refuses, with
nothing written, and only the transactions that look authorized are
replayed. A
grant or revocation is a board-level transaction: while one is incomplete
the grants file is not the truth, so nothing managed moves and no grant
changes until the operator runs `managed recover board`. A close whose row
landed but whose audit did not exits nonzero, reports the row as done, and
names the transaction: it is not a clean close until recovered. The
`assessment` token is `assess:v2:...` only when closable and `blocked:v2:...`
otherwise; `done --assessment` refuses a blocked token and recomputes a
closable one's conditions under the lock. Each release
advances the attempt in the same locked transaction that releases the claim,
so a superseded worker cannot submit or complete; an interrupted release is
reported by `assess` and completed by the coordinator's next `managed
release`. Release needs coord to have verified the worker dead or stopped, or
`--isolated-checkout` naming a validated separate git working tree; a stale
or idle lease, an unknown peer, and a bare path all refuse.
`reconcile --fix` never closes or releases a managed item.

### `abandon <id>`

Release a claimed issue without completing it. It returns to `open` when clear
or remains `blocked` when unresolved blocker edges remain.

```bash
agent-do manna abandon mn-abc123
```

`abandon` rejects every session except the current owner. `done` closes on
receipts, strongest authority first: `evidence` (a commit carrying
`Manna: <id>` that touched a path outside `.manna/` and `.handoff/` closes the
item from any live status over any claimant, and the commits are listed),
`operator` (the human's terminal identity closes any live item), or `owner`
(the claim-holder's proof plus `in_progress`). The response names the
`authority`; paperwork drift is returned as `warnings` and never holds a
close. `done` also provides the explicit unclaimed close transition for a
parked dream, because a dream cannot be claimed.

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: open
  claimed_by: null
```

### `block <id> <blocker_id>`

Add a blocker dependency. The issue's status becomes `blocked`.

```bash
agent-do manna block mn-abc123 mn-def456
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Implement feature
  status: blocked
  blocked_by:
    - mn-def456
```

### `unblock <id> <blocker_id>`

Manually remove a blocker dependency. If no blockers remain, status returns to
`open`, or `in_progress` if already claimed; completed issues stay `done`.
Completing a blocker with `done` removes its edges automatically, so no manual
`unblock` is needed for completed work.

```bash
agent-do manna unblock mn-abc123 mn-def456
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Implement feature
  status: open
  blocked_by: []
```

### `list [--status <status>]`

List issues with optional status filter.

```bash
agent-do manna list
agent-do manna list --status open
agent-do manna list --status in_progress
agent-do manna list --status blocked
agent-do manna list --status done
```

**Output:**
```yaml
success: true
issues:
  - id: mn-abc123
    title: Fix login bug
    status: open
  - id: mn-def456
    title: Implement feature
    status: in_progress
    claimed_by: ses_test123
```

### `show <id>`

Show full details of an issue.

```bash
agent-do manna show mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  description: Users can't login with SSO
  status: open
  created_at: "2026-01-29T10:00:00Z"
  updated_at: "2026-01-29T10:05:00Z"
  blocked_by: []
  claimed_by: null
  claimed_at: null
```

For a track, `show` also carries a `children` block derived from the board at
that moment: `total`, `done`, `open`; `eligible` (claimable now, in dispatch
order: handoff priority, then the oldest row, then the lowest id) and `next`
(its first entry, or `null`); `held` (items another session holds, with the
owner), `waiting` (items whose blockers are open, `missing` from the board, or
part of a `cycle`), `decisions` (open items carrying a decision marker, a
human's to rule on), `dreams`, `added_since_claim` (items created after the
track was claimed), and `stall`, a sentence saying why `next` is null. Items
print exactly as before; the block is absent.

### `handoff seal <id>` and `handoff attach <track-id>`

Bind an intentional edit to the board. The command preserves the handoff body,
normalizes authoritative frontmatter, computes the canonical document SHA-256
with the self-referential binding field normalized,
and updates the paired `handoff_digest` transactionally.

```bash
agent-do manna handoff seal mn-abc123
```

Until sealing succeeds, `claim` fails closed. A comment containing a claim
command is never a handoff.

`handoff attach <track-id>` gives an existing track its dispatch work order,
idempotently: a track that already carries a valid pair reports
`changed: false`; a document already sitting at the canonical path is adopted
(body kept byte for byte, frontmatter normalized, binding computed) rather than
overwritten, and reports `adopted: true`; otherwise the generated protocol is
created. A document that does not validate refuses with the defect named and
nothing written. The attach transaction carries the lifecycle unchanged: it
never touches the claim, status, dependencies, or items, and on a claimed
track only the holder may run it. Items refuse (they pair at creation) and
dreams refuse (convert first).

```bash
agent-do manna handoff attach mn-track1
```

### `update <id> [metadata]`

Update title, description, type, track, source, or a legacy prompt pointer.
Strict item metadata updates first verify the existing seal, then propagate
authoritative frontmatter without approving body edits. Item conversion attaches or
archives the handoff transactionally. `update --status` is rejected; use the
lifecycle verbs `claim`, `done`, `abandon`, `block`, and `unblock`.

### `delete <id>`

Delete a row. On a strict board, Manna archives the paired handoff under
`.handoff/.archive/` and removes the row through one recoverable transaction.

### `context [--max-tokens <n>]`

Generate a context blob for AI agent prompts. Default max tokens: 8000.

```bash
agent-do manna context
agent-do manna context --max-tokens 4000
```

**Output:**
```yaml
success: true
context: |
  # Manna Context

  ## Open Issues (2)
  - mn-abc123: Fix login bug [open]
  - mn-ghi789: Add tests [open]

  ## In Progress Issues (1)
  - mn-def456: Implement feature [in_progress, claimed by ses_test123]

  ## Blocked Issues (0)
```

### `serve [--open] [--json] [--port N]`

The human window: a read-only cockpit on `127.0.0.1:7777`. `/` is the estate
(every registered board with needs-you / working / here); `/<name>` is one
board:

- **three tabs** — `inbox` (every ask, one shape per row: who/what · the ask ·
  the verb you perform: grant, fix, rule, split, close, read, launch),
  `board` (now / next / waiting, chips `live · +done · dreams · track`, a
  `list | timeline` switch), `coordination` (needs you, peers with what they
  hold, claims with contention, drops)
- **inspector** on the right: the item's manna title and description, blockers
  and dependents, claimant with pulse, trailer commits, one-click copy of the
  handoff path, id, and `show` command; or a peer's session, pulse, holdings
- **status strip** at the bottom: drift (live `reconcile --json`, read-only)
  and the daemon's health; `debug ▸` opens the sheet with every finding
- **⌘K / jump**: sheets, items, peers, other boards
- **digests**: each row shows a one-line digest of the item (fast model,
  hash-keyed cache under `$AGENT_DO_HOME/manna/serve/digests/`, regenerated
  only when title or description change, title as fallback). The Rust
  `manna state` contract attaches current cache values for every human-facing
  client; serve only schedules missing values. The manna title stays in the
  inspector. Set `AGENT_DO_SERVE_AI=off` to keep titles only.

Finish: ledger density on a 12px floor, one-line rows, zebra, a severity
stripe leading each row, outlined state pills, prompt headers (`$ manna next`),
raised-row selection. Ratified through four wireframe rounds (2026-08-24).

```bash
agent-do manna serve            # register this board, start the daemon if needed, print the URL
agent-do manna serve --open     # same, and open it
agent-do manna serve --scan ~/Projects        # register every board below a directory
agent-do manna serve --decision-marker "[NAME]"   # a leading title tag that means "a human must rule"
agent-do manna serve --status | --stop
```

**Reconcile by click.** Drift shows up as inbox asks, each with a verb that is
a button: `close` (an item whose work landed: `claim` then `done`), `rule`
(a stale dream: `promote` or `delete`, delete on a second click), `sync`
(work-order filenames behind their priority), `apply` (the two repairs
`reconcile --fix` calls safe). A click runs exactly that manna verb through the
daemon's own pinned identity (`$AGENT_DO_HOME/manna/serve/identity.json`, mode
600, the same `MANNA_SESSION_ID` + `MANNA_SESSION_TOKEN` pin scripted lanes
use), behind the loopback Host/Origin checks and a per-process token the page
carries; manna's own refusals print on the row verbatim. Nothing on the page
edits a file. The SessionEnd hook applies the same two safe repairs.

Agents never need the daemon: `state --json` is the complete board contract,
and `estate --json` is the registered-board index contract. `context`, `list`,
and `show` remain the narrower task-oriented reads.
Private claim proofs (`claim_token_hash`) never leave the board directory.
Implementation: `serve/serve.py` (daemon, registry, two-clock cache),
`serve/board.py` (core-state adapter and estate helpers), `serve/digest.py`
(digests), `serve/estate.py` (daemon-independent estate CLI adapter), and
`src/state.rs` (the canonical derivation).

## Tracks as whole-track build assignments

A track is an organizational container, and it can also be an assignment: the
owner selects either the track (one agent works its items in dependency order)
or individual items (ordinary multi-agent dispatch). Both go through the same
board claim flow; nothing new is clicked or configured.

**Flow.** `create --type track` pairs the track with a sealed dispatch work
order; an older container track takes one through `handoff attach <id>`. The
paired track enters `.manna/handoff-order.yaml` and the generated index like an
item (`order <id> <n>` moves it). `state` derives it as `ready` while the board
offers an item to claim (or every item is done and the track can close), as
`waiting` while all remaining work is held elsewhere, cycled, missing a
dependency, or a human's to rule on, as `active` once claimed, and `done` when
closed; a track without a handoff keeps `effective: track`. A ready track sits
in `next` with `prompt`, `handoff_digest`, and `handoff_exists`, the fields a
launcher reads, and its `kind` stays `track`, so grouping is unchanged. The
dispatched agent claims the track, runs `show <track> --json`, claims
`children.next` individually, follows that item's own sealed work order to its
own close, re-reads `show` before every selection, and stops when `next` is
null, recording `children.stall`. A lane that ends releases the track with
`abandon`; a successor claims it and rebuilds progress from the board.

**Limits, by design.**
- Holding a track grants only the right to claim its eligible items one at a
  time. It reserves no item, blocks no independent worker (the board's atomic
  claim decides), confers no coordinator authority, accepts nothing, and
  authorizes no merge, deploy, push, or pull request.
- A refused child claim is final for that child: the agent takes the next
  eligible item or stops. Nothing retries around a refusal.
- Items added to a track after the claim appear under `added_since_claim`;
  each carries its own sealed work order, and the agent names the change of
  scope before claiming one. Items moved out or deleted leave the list; one
  the agent already holds stays its own under its own work order.
- The track closes only when every item in it is done (see `done`); an empty
  track cannot close. Nothing here wakes an idle or closed worker, spawns
  one, or schedules anything: the board changes state, and whoever reads it
  next acts.
- A paired track is `effective: ready|waiting|active|done` on every consumer
  of `state`. The Holy board's worker dispatch additionally guards
  `kind == "item"` in its refusal
  (`macos/Sources/HolyGhostty/Board/HolyMannaBoardWorker.swift`,
  `HolyMannaWorkerDispatch.refusal`); until that guard admits a ready track,
  Holy will refuse to launch one even though the row carries every field it
  reads. That counterpart is Holy's to change; `manna serve`'s launch pointer
  needs nothing.
- Older `manna-core` binaries read a strict board that holds a paired track as
  invalid (`cannot carry an item handoff`); rebuild them. No track gains a
  handoff until someone creates one or runs `handoff attach`.

## Architecture

### Storage

Manna stores canonical board state in `.manna/` and durable work orders in
`.handoff/`:

```
.manna/
├── issues.jsonl     # Issue records (one JSON per line)
├── sessions.jsonl   # Session event log
├── board.yaml       # Independent strict or legacy identity
├── workflow.yaml    # Strict workflow version and handoff root
├── handoff-order.yaml # First-class ordered item priority
└── transactions/    # Ignored crash-recovery journal
.handoff/
├── README.md        # Generated workflow contract and index
├── NN...[bMM...]-mn-*.md  # Fixed-width priority and launch-gate presentation
└── .archive/        # Retired work orders
```

**Why JSONL?**
- Simple, human-readable format
- Git-friendly (line-based diffs)
- No database dependencies
- Easy corruption recovery (skip malformed lines)

### ID Format

Issues use hash-based IDs:

```
mn-{6-hex}
```

Examples: `mn-abc123`, `mn-f4e5d6`

IDs automatically extend (7, 8, ... chars) on collision.

### Session Management

Claim ownership uses two pinned environment variables:

- `MANNA_SESSION_ID`: public session label stored as `claimed_by`
- `MANNA_SESSION_TOKEN`: private bearer token of at least 32 characters; only
  its SHA-256 digest is stored in the board

Lifecycle mutations fail closed when either value is absent and no host
identity applies. Session hooks pin both across shell invocations. Codex and
other hosts that expose an opaque runtime identity derive the proof under a
machine-local key outside the repository. A plain interactive shell (stdin is
a terminal, nothing pinned) derives the operator identity `operator-<login>`
under the same key; the operator is the estate's root and `require_owner`
never refuses it. Agent hosts run on pipes and never reach that branch;
`MANNA_OPERATOR=0` opts a terminal out. Scripted lanes on pipes must export
both pins explicitly. A visible owner label alone cannot complete, abandon,
or edit its claim.

### Exit Codes

| Code | Meaning | Examples |
|------|---------|----------|
| 0 | Success | Command completed |
| 1 | User error | Invalid input, issue not found |
| 2 | System error | I/O error, lock failed |

### Concurrency

All write operations use file locking (`fs2` crate):
- Exclusive locks prevent concurrent writes
- Unique no-follow temp files plus atomic rename for board updates
- Atomic create-if-absent installation for pair journals and private keys
- Safe for parallel agent execution

## Integration

### With agent-do

Manna is registered in agent-do's registry:

```bash
agent-do manna <command> [args]
```

### Session Hooks

Use with agent-do hooks for automatic session tracking:

**SessionStart hook:**
```bash
export MANNA_SESSION_ID="ses_$(uuidgen)"
export MANNA_SESSION_TOKEN="$(openssl rand -hex 32)"
```

**PreCompact hook:**
```bash
CONTEXT=$(agent-do manna context --max-tokens 2000)
# Inject $CONTEXT into AI prompt
```

### Scripting

```bash
#!/bin/bash
# Create issue and capture ID
output=$(agent-do manna create "Automated task")
id=$(echo "$output" | grep -o 'id: mn-[a-f0-9]*' | awk '{print $2}')

# Work on it
agent-do manna claim "$id"
# ... do work ...
agent-do manna done "$id"
```

## Development

### Project Structure

```
agent-manna/
├── agent-manna          # Bash wrapper (26 LOC)
├── src/
│   ├── main.rs          # CLI entry point
│   ├── lib.rs           # Library exports
│   ├── id.rs            # ID generation
│   ├── issue.rs         # Issue types and operations
│   ├── store.rs         # JSONL storage
│   └── error.rs         # Error types
├── test/
│   └── integration.sh   # Integration tests
├── Cargo.toml
├── DESIGN.md            # Architecture documentation
├── SCHEMA.md            # JSONL format specification
└── README.md            # This file
```

### Running Tests

```bash
# Unit tests
cargo test

# Integration tests
./test/integration.sh
```

### Test Coverage

- **55 unit tests** covering all modules
- **~20 integration tests** covering full workflows and edge cases

### Dependencies

| Crate | Purpose |
|-------|---------|
| clap | CLI argument parsing |
| serde | Serialization framework |
| serde_json | JSON parsing for JSONL |
| serde_yaml | YAML output formatting |
| chrono | Timestamp handling |
| sha2 | SHA256 hashing for IDs |
| fs2 | Cross-platform file locking |
| thiserror | Error type derivation |
| rand | Random number generation |

### Design Principles

1. **Minimal** - <5K LOC total
2. **Git-friendly** - JSONL diffs cleanly
3. **Agent-first** - YAML output, no colors/spinners
4. **Robust** - Atomic lifecycle mutations plus recoverable row/file transactions
5. **Simple** - No database or async runtime; explicit board and workflow identities
6. **Fast** - <100ms for all operations

## Troubleshooting

### "Storage not initialized"

Run `manna init` in your project directory:
```bash
agent-do manna init
```

### "Issue not found"

Verify the ID with:
```bash
agent-do manna list
```

### "Issue already claimed"

Another session has claimed this issue. Check who:
```bash
agent-do manna show mn-abc123
```

Only the owning pinned session can finish, abandon, update, block, unblock, or
delete claimed work. If that session is provably dead, use `manna reconcile
--fix`; do not impersonate its ID.

### Binary not found

Build the Rust binary:
```bash
cd /path/to/agent-manna
cargo build --release
```

## License

See repository root for license information.
