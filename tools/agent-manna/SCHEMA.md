# Manna JSONL Schema

This document defines the exact JSONL (JSON Lines) format for Manna's storage files.

## Storage Location

All data is stored in `.manna/` directory:
- `.manna/issues.jsonl` - Issue records (one JSON object per line)
- `.manna/sessions.jsonl` - Session event log (one JSON object per line)
- `.manna/board.yaml` - Independent board identity (`strict` or `legacy`)
- `.manna/handoff-order.yaml` - First-class ordered priority for paired items
- `.manna/drift.yaml` - Latest reconcile findings (written by `reconcile --write-drift`)
- `.manna/workflow.yaml` - Strict workflow version and canonical handoff root
- `.manna/federation.yaml` - Required tracked board identity and optional outbound cross-board relations
- `.manna/federation-archive/*.yaml` - Tracked manifests retired by an intentional project fork
- `.manna/transactions/` - Ignored write-ahead journal for interrupted pair changes
- `.manna/transactions/legacy-board-migration.yaml` - Authenticated whole-board admission journal, present only while migration is pending
- `.manna/transactions/federation.yaml` - Authenticated federation mutation journal, present only while a write is pending

Durable work orders live in tracked `.handoff/`:
- `.handoff/README.md` - Generated ownership contract and board-derived index
- `.handoff/<NN...>[b<MM...>]-mn-xxxxxx-<slug>.md` - Synchronized fixed-width
  work-order presentation
- `.handoff/.archive/` - Retired handoffs preserved by delete and item conversion
- `.handoff/.archive/legacy-sources/*.source` - Exact non-Markdown evidence for imported in-project legacy work orders retired during migration

## federation.yaml

Federation identity is default board infrastructure; cross-board relations are
optional. `manna init`, `manna migrate`, bootstrap repair, and first-use global
inbox creation create or preserve this file under the board-wide lock before
reporting success. `manna federation init` remains an idempotent repair and
manual backfill command:

```yaml
version: 1
board_id: mb-5c54d1b4cce04f8b9f4418a9180ad87e
relations:
- from: mn-27a833
  kind: informed_by
  to: manna://mb-973809091a7444329b38fa9a1ee7979f/mn-55530d
  hint: agent-do
```

`board_id` is `mb-` plus exactly 32 lowercase hexadecimal characters generated
from 128 random bits. It is public identity, not a credential. Normal clones
and Git worktrees retain the ID as replicas of one logical board. An
intentional project fork must use `manna federation fork --reason <text>`,
which archives the exact inherited manifest, generates a new ID, and starts
with no active relations.

Each relation contains a local `from` issue, one closed vocabulary kind
(`counterpart`, `informed_by`, `depends_on`, or `supersedes`), a portable
`manna://<board_id>/<issue_id>` target, and an optional human-only `hint`.
Relations serialize in deterministic `(from, kind, to)` order. Exact
duplicates, missing local sources, malformed coordinates, and same-board
targets are invalid. Target status, title, claimant, local path, and resolution
cache are never stored here.

The manifest declares lineage only. It cannot claim, block, unblock, complete,
reopen, delete, reseal, or reconcile any issue. Local `blocked_by`, handoff
pairing, ownership proofs, and `Manna:` trailer evidence remain exclusively
local. `relate` and `unrelate` require the exact owner proof when the source is
actively claimed or blocked; open and done sources accept an authenticated
declaration without rewriting either issue or handoff bytes.

`manna relations` reads the tracked declaration. `--resolve` optionally reads
the machine-local serve registry and reports `resolved`, `unavailable`,
`missing`, or `ambiguous`; it never searches the network or writes a board.
Unavailable boards are a valid degraded read. `--check` exits 1 only for a
present board missing the target or for divergent replicas. Counterpart edges
also report `confirmed`, `one_way`, `unavailable`, or `ambiguous` reciprocity.

Manifest writes and forks share the board lock and an HMAC-authenticated,
project-bound journal carrying exact before and after bytes. Recovery accepts
only those exact states. Lint and reconcile validate local shape, sources,
tracking, archive, and pending-transaction convergence without consulting the
registry. A missing manifest is readable as incomplete recovery state but fails
lint with the exact `agent-do manna init` convergence command.

## issues.jsonl

Each line is a complete JSON object representing one issue.

### Example
```jsonl
{"id":"mn-a1b2c3","title":"Fix login","status":"open","description":null,"created_at":"2026-01-29T10:00:00Z","updated_at":"2026-01-29T10:00:00Z","blocked_by":[],"claimed_by":null,"claimed_at":null}
```

### Field Definitions

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `id` | String | Yes | Format: `mn-{6-hex}`, auto-extends on collision | Unique issue identifier |
| `title` | String | Yes | 1-500 characters | Issue title/summary |
| `status` | String | Yes | Enum: `open`, `in_progress`, `blocked`, `done` | Current issue state |
| `description` | String or null | No | Optional long-form text | Detailed description |
| `created_at` | String | Yes | ISO8601 timestamp | When issue was created |
| `updated_at` | String | Yes | ISO8601 timestamp | Last modification time |
| `blocked_by` | Array | Yes | Array of issue IDs (strings) | Issues blocking this one |
| `claimed_by` | String or null | No | Session ID or null | Who is working on this |
| `claimed_at` | String or null | No | ISO8601 timestamp or null | When it was claimed |
| `claim_token_hash` | String or null | No | `sha256:<64 lowercase hex>`; present exactly when `claimed_by` is present | Proof digest for the owning session's private bearer token |
| `type` | String | No | Enum: `track`, `item`, `dream`; omitted when `item` (default) | Issue type: umbrella track, work item, or intake spark |
| `track` | String or null | No | ID of an existing `type: track` issue; tracks don't nest | Track this issue belongs to |
| `source` | String or null | No | Free text (note path, URL, conversation) | Where this issue came from |
| `prompt` | String or null | No | Strict boards require repository-relative Markdown below `.handoff/` | Work-order file paired with this item |
| `handoff_digest` | String or null | No | `sha256:<64 lowercase hex>` | Board-side binding for the canonical handoff with its binding field normalized |
| `legacy_migration` | Object or null | No | Version 1 annotation written only by `migrate` | Historical admission disposition (`paired`, `history`, or `exempt`), migration time, prior pointer, and released legacy owner when applicable |

v1 rows carry none of the new optional fields (`type`, `track`, `source`,
`prompt`, `handoff_digest`, `claim_token_hash`); they deserialize as `type: item` and re-serialize unchanged (lazy
upgrade — the file is never rewritten just to add defaults).

### Workflow and handoff pairing

New or empty boards initialized by Manna are strict workflow version 2.
`.manna/board.yaml` pins that decision independently, so removing
`.manna/workflow.yaml` is corruption, never a downgrade. `manna init` restores
the strict config. A version-2 digest prevents re-entry into the binding-creating
version-1 migration path, so restoration cannot bless edited contents. A pre-workflow nonempty board
is classified once as `legacy` in `board.yaml`; later commands read that
identity instead of inferring mode from missing files.

`create` generates the item handoff and writes its path into `prompt`; neither
side is optional for an active item. Structured frontmatter binds workflow
version, item, track, source, base commit, scope, inputs, and the SHA-256 of
the canonical document with its self-referential binding field normalized. The same digest is stored in `handoff_digest`. Tracks
and dreams do not carry handoffs. A strict pointer cannot be repointed or
cleared through `update`; after editing the document, run
`manna handoff seal <id>` to update the binding deliberately.

### Ordered handoff presentation

`.manna/handoff-order.yaml` is the priority authority:

```yaml
version: 1
items:
- mn-a1b2c3
- mn-d4e5f6
```

`manna order <id> <position>` mutates that ordered list and synchronizes it.
`manna sync` normalizes the list to current paired items, assigns dense,
board-wide fixed-width priorities, renames each work order, repoints `prompt`,
and regenerates `.handoff/README.md` from one board snapshot. Width is at least
two digits (`01..N`) and expands for the whole plan at 100 or more items
(`001..N`). Priority never encodes dependency. Every dependency remains in
`blocked_by`.

A bare filename is safe to launch. The same-width `bMM...` field means the item
is held by its highest-numbered still-open blocker; the README preserves the
full blocker list. Closing blockers updates or removes the marker on the next
sync. Claimed work orders are never renamed. Their existing number remains
reserved until release, and lint/reconcile report any held filename drift.

The native `Rename` pair transaction HMAC-binds exact before/after board rows,
all moves, priority YAML, and README bytes. It stages every source before
installing any destination, so swaps are no-clobber and recovery is
idempotent. Handoff content binding excludes the path, so this operation does
not reseal or otherwise authorize document edits.

`claim` enforces the pair before state changes. The file must exist, be
Git-visible, remain below `.handoff/` without crossing a symlink, carry exact
structured metadata, and match the board-side content binding. A loose comment
or claim-like string has no authority. A violation exits 2 and leaves the
board unchanged. `lint` applies the same contract, and
`reconcile` (kind `prompt_pairing`) checks both directions:

- **Forward**: an issue's pointer resolves to an existing file that never
  mentions the issue's id.
- **Reverse**: a claim command in `.handoff/**/*.md` — a line
  containing `manna claim mn-xxxxxx`, any invocation prefix
  (`agent-do manna claim`, absolute-path binary, `MANNA_SESSION_ID=...`
  pins) — targets a board issue whose pointer is missing or does not
  resolve back to that file. The claim relationship is the signal: bare id
  mentions elsewhere in a prompt file are data, not pairing promises.
  Foreign-board ids are ignored (cross-repo prompts are legal).

Strict reconcile reports `workflow_sprawl` for live claim-bearing Markdown
anywhere outside `.handoff/`. Internal directory aliases are scanned; external
and handoff-like symlink roots fail closed. It reports
`orphan_handoff` for structured Manna work orders with no live actionable item.
Freeform research and session-continuation Markdown may share `.handoff/`
without impersonating a generated work order. These
integrity findings make reconcile exit 1; informational drift remains
advisory.

Boards explicitly classified as legacy keep
the prior absolute-pointer behavior, the description-first-line
`PROMPT: <path>` fallback, and the `.dev/session-prompts/` reverse scan. Init
does not rearrange those boards implicitly. `manna migrate` is the explicit
admission path for both pure legacy and mixed legacy/strict boards. It uses one
authenticated whole-board transaction to verify and preserve existing strict
pairs, create and seal every legacy active item pair, adopt the exact contents
of malformed `.handoff/` work orders, import active absolute cross-project
Markdown pointers, annotate done rows as pointer-free history, annotate active
tracks and dreams as exempt, release unauthenticated claims, and publish strict
board identity last. Partial frontmatter and old Claim sections in imported
text are inert content; strict authority comes from the row digest and the one
canonical Claim section. A description-first `PROMPT: path.md — note` line
ends its pointer at the em-dash separator; the remaining note stays contextual
prose. A board admitted by the preceding parser is repaired on the next
`migrate` through a content-preserving authenticated rebind. In-project
absolute source paths normalize to
repository-relative provenance, while a cross-project source retains its
original absolute path in the sealed document. The transaction authenticates
source bytes separately from target-before bytes so recovery cannot substitute
or overwrite unimported content. After every consuming handoff preserves those
exact bytes, a local source outside `.handoff/` is atomically moved to the
deterministic `.handoff/.archive/legacy-sources/` evidence root. Its `.source`
suffix keeps preserved claim text from becoming a second executable Markdown
workflow. Shared sources archive once, external sources are never mutated, and
`migrate` repairs already-admitted boards whose local sources were left behind
without changing unaffected strict rows or handoff seals. Unique handmade number prefixes
seed priority only when they are unambiguous; `.manna/handoff-order.yaml` and `manna sync`
own presentation after admission. Recovery accepts only the complete before or
complete after board, so a concurrent mutation is never overwritten. Replaying
a completed migration is byte-stable. The annotation records how a legacy row
entered strict mode; it does not prevent later status or type transitions.

Cross-project import is deliberately narrow: the pointer must name a regular,
UTF-8 Markdown file, the file itself cannot be a symlink, and the resolved path
cannot enter Git metadata. This read-only admission exception never makes an
external path authoritative. The resulting row points only at its canonical local handoff.
A row that already carries `handoff_digest` is still strict; a missing or
deleted document binding is tampering and migration refuses it.

Grandfathered done history without pairs is exempt. A done row that owns a
strict pair keeps that sealed pair, but sync removes it from priority and the
generated index and returns its handoff to an unnumbered historical path.

### Status Transitions

```
open → in_progress (via claim)
in_progress → done (via done)
in_progress → open (via abandon)
blocked claim → blocked (via abandon; ownership clears, blockers remain)
* → blocked (when blocked_by is non-empty)
blocked → * (when blocked_by becomes empty)
open dream → done (via done, without a claim)
```

Claim, done, abandon, block, unblock, metadata updates, and deletion re-read
and mutate under one board lock. Exactly one concurrent claimant can win.
`done` revalidates the strict handoff seal and shadow-workflow scan before the
status transition, so an edit made after claim cannot disappear into history.
Once claimed, mutation requires both `claimed_by` and the bearer token whose
digest is stored in `claim_token_hash`. The public owner label alone is not a
credential. Host runtimes may derive that proof from an opaque thread identity
and a machine-local key outside the repository. Plain shells and scripted lanes
provide both `MANNA_SESSION_ID` and `MANNA_SESSION_TOKEN`. `update --status` is
rejected; lifecycle state moves only through the named lifecycle verbs.

Strict pair create, delete, seal, attach, detach, and presentation rename write an HMAC-authenticated
transaction intent before touching either side. The key lives outside the
worktree. Atomic no-clobber installation prevents concurrent intent overwrite;
the signature binds the canonical project root, journal identity, complete rows,
canonical `.handoff/` paths, archive path, document, priority, and index. The next Manna command validates the full
scaffold and completes an interrupted intent idempotently. Delete and
item-to-non-item conversion archive the handoff before removing its live pointer.

### The dream gate

A `type: dream` row has no entry into that diagram. `claim` refuses it — exit
2, nothing written — and names the conversion; the refusal, not hiding, is the
gate. Dreams stay visible in `list` and `context` throughout, every row marked
`[DREAM: not claimable, needs conversion]`, so an agent reads the idea and its
un-actionable status in the same glance.

`update <id> --type item` is the authorization act (Erik's to make) and prints
an explicit `AUTHORIZED:` line saying the row is now claimable work; the
reverse prints `PARKED:`. Every other verb still works on a dream, and
`done <id>` is the explicit unclaimed lifecycle transition for closing a dream.

### ID Format

- Prefix: `mn-` (manna)
- Hash: 6 hexadecimal characters (lowercase)
- Collision handling: Auto-extend to 7, 8, ... characters
- Example: `mn-a1b2c3`, `mn-f4e5d6c`

## sessions.jsonl

Each line is a session event (append-only log).

### Example
```jsonl
{"session_id":"ses_abc123","event":"start","timestamp":"2026-01-29T10:00:00Z","context":{}}
{"session_id":"ses_abc123","event":"claim","timestamp":"2026-01-29T10:01:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"done","timestamp":"2026-01-29T10:05:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"end","timestamp":"2026-01-29T11:00:00Z","context":{}}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | String | Yes | Session identifier (from `$MANNA_SESSION_ID`) |
| `event` | String | Yes | Event type (see below) |
| `timestamp` | String | Yes | ISO8601 timestamp of event |
| `issue_id` | String | Conditional | Required for `claim`, `release`, `done` events |
| `context` | Object | Conditional | Required for `start`, `end` events (can be empty) |

### Event Types

| Event | Description | Required Fields |
|-------|-------------|-----------------|
| `start` | Session begins | `session_id`, `event`, `timestamp`, `context` |
| `claim` | Issue claimed for work | `session_id`, `event`, `timestamp`, `issue_id` |
| `release` | Issue unclaimed (abandoned) | `session_id`, `event`, `timestamp`, `issue_id` |
| `done` | Issue completed | `session_id`, `event`, `timestamp`, `issue_id` |
| `end` | Session ends | `session_id`, `event`, `timestamp`, `context` |

## coordinators.json, managed.json, lifecycle.jsonl

Sidecars for the managed lifecycle, beside the board and written under the
board lock. They never change an `issues.jsonl` row, so older binaries read
the board unchanged and an unmanaged board never has them.

- `coordinators.json`: `{version, grants: [{id, coordinator_id, coordinator_proof,
  scope: {items, tracks}, reason, granted_at, granted_by, revoked?}]}`. The proof
  is the same `sha256:` token digest claims store; a label alone is nothing.
- `managed.json`: `{version, items: {<mn-id>: {id, attempt, required, grant,
  managed_at, managed_by, target?: {reference, sha, kind, pinned_at, pinned_by},
  submission?: {id, attempt, by, at, revision?, report, status, correction?},
  acceptances: [{check, attempt, submission, target_sha, by, authority, at, evidence}],
  releases: [{attempt, by, at, reason, worker?, worker_liveness, basis, isolation?,
  isolation_toplevel?, claim_release}], history: [superseded submissions]}}}`.
  `acceptances[].submission` is the id of the submission the verdict was given
  on; an acceptance counts only while that submission is the current one.
  `releases[].claim_release` is `pending` between the sidecar write and the
  row's claim release, `released` after; a `pending` entry whose worker still
  holds the claim is an interrupted release.
- `lifecycle.jsonl`: one JSON object per line, append-only: `{txn, at, action,
  issue_id, actor, authority, attempt?, reason?, evidence?, detail?}` with
  actions `grant`, `revoke`, `require`, `claim`, `submit`, `correct`, `accept`,
  `release`, `release_resume`, `abandon`, `close`. `txn` names the transaction
  the line belongs to (empty for claim notes, which are not transactions).
- `managed-intent.json` (transient, ignored by Git, absent at rest):
  `{version, intents: [{txn, issue_id, action, started_at, actor, actor_proof,
  record_after?, grants_after?, event}]}`. An intent is written before a
  transaction's state and audit writes and removed after both landed; one
  left behind means those writes did not both land, the item refuses every
  mutation, and `managed recover <id>` applies the recorded outcome.

## drift.yaml

Written atomically (temp + rename) by `reconcile --write-drift`. Shape:

```yaml
generated_at: "<ISO8601 UTC>"
session: "<session id or null>"   # explicit or host-derived identity, else null
findings:
  - kind: landed_open|dead_claim|blocker_desync|stale_dream|dangling_track|doc_reference|prompt_pairing|handoff_presentation|workflow_sprawl|orphan_handoff|skipped
    issue_id: "mn-xxxxxx"   # optional
    detail: "one line"
    evidence: "sha / file:line / pid"   # optional
    proposed_fix: "one line"            # optional
```

Commit trailers feeding the `landed_open` check are body lines of exactly
`Manna: mn-xxxxxx` (key case-sensitive, one ID per line, multiple lines allowed).

## File Format Rules

1. **One JSON object per line** - No pretty printing, no multi-line JSON
2. **Append-first** - New records append; atomic lifecycle rewrites preserve valid JSONL
3. **Explicit deletion** - `manna delete` removes a row and archives a strict handoff
4. **UTF-8 encoding** - All files must be UTF-8
5. **Newline terminated** - Each line ends with `\n`

## Corruption Handling

If a line cannot be parsed as valid JSON:
- Skip the malformed line
- Log a warning to stderr
- Continue processing remaining lines

This allows recovery from partial writes or corruption.
Whole-board migration is deliberately stricter: any malformed line aborts
without writing, because skipping it and rewriting the board would lose data.

## Concurrency

All writes must acquire an exclusive file lock (flock) before modifying JSONL files.

See DESIGN.md for implementation details.
