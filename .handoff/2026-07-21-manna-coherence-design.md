# Manna Coherence: Status From Receipts, Not Testimony

**Date:** 2026-07-21 · **Status:** design v2, generalized to every board; conventions ship now, machinery staged.
**Supersedes:** v1 in place, same file, same day. v1 was agent-do-flavored; its title-prefix grammar is retired as interim scaffolding.
**Origin:** the 2026-07-21 board review: mn-e6c7bd sat "open, unclaimed" while all six of its
commits were landed on its own branch. Not-started and code-complete are opposite poles; the
board could not tell them apart. This document makes that class of drift structurally impossible,
on any board the schema touches.

## Doctrine

Same move as the contracts layer. There, the lexicon generates the inventory, and gate + drift +
audit keep the registry's promises true; nobody hand-trusts a declaration. Here, **board status is
derived from receipts wherever a receipt can exist, and asserted only where no receipt is possible**
("is this still wanted" is the one question only the human can answer). Evidence over testimony,
dogfooded on our own board before any board we hand to someone else.

## The grammar (normative)

Three universal roles, closed set. Everything else is data:

> Every issue is a **track** (a named grouping with intent), an **item** on a track, or a
> **dream** (raw intake, exempt from tracking, converted or closed with a written reason).
> Commits that advance an item cite it with a `Manna: mn-xxxxxx` trailer. The board is the
> only backlog: memories and docs point at mn- IDs, never carry their own checklists.

## The schema (normative)

| Field | Values | Rule |
|---|---|---|
| `type` | `track` \| `item` \| `dream` | Default `item`. Closed set; lint rejects anything else. |
| `track` | `<mn-id>` | Edge on items naming their track row. A trackless item is a lint finding; dreams are exempt. |
| `source` | free citation | Provenance: where the work order came from (e.g. "SPEC §3.2", "audit 2026-06-29", "support ticket #812"). |

Project vocabulary (program names, mythology, numbering schemes) lives in titles and descriptions
only, never in structure. A grep for a project term should hit data, not grammar. Dream routing:
a dream files to the nearest `.manna/` walking up from cwd, else to the global inbox board at
`~/.agent-do/inbox/`.

Four layers, ordered by when they act.

## Layer 1: intake, the filing grammar (write time)

Random big-brained additions cohere because the schema sorts them at creation, not because a
later cleanup finds them.

- New work enters as an item on a track, as a new track (description states the intent), or as
  a dream. Nothing else exists.
- **The dream contract**, for "I want to build this, fr" moments: capture the spark verbatim, add
  a guessed track if one suggests itself (wrong is fine), and one line of what done might look
  like if visible. Dreams are allowed to be wrong; they are not allowed to be lost. The reconcile
  sweep converts dreams into tracks or items, or closes them with a written reason; a killed
  dream keeps its epitaph.
- Enforced by `manna lint` (ships with the schema, mn-2a33a5): unknown `type`, trackless items,
  and `track` edges naming non-track rows are findings. v1 enforced intake by convention and
  title prefixes; the typed fields replace both.

## Layer 2: binding, receipts (work time)

- **Commit trailer:** any commit advancing an item carries `Manna: mn-xxxxxx` (same mechanic as
  `Co-Authored-By`). This is the edge that makes status computable; the whole design hangs on it.
- **Claims are already receipts:** coord v2 anchors sessions to pid + start time, so a claim held
  by a dead session is detectable, not just suspicious.
- Derivation table (the poles get names):

| Signal | Derived state |
|---|---|
| No claim, no trailer commits | open (truly not started) |
| Claimed by live coord session | in_progress |
| Trailer commits landed, branch unmerged | code-complete-unmerged (today: open + drift flag; a real `in_review` status may follow) |
| Trailer commits merged to main | close candidate; reconcile proposes `done` |
| Claimed by dead session | stale claim; reconcile proposes abandon |

## Layer 3: reconcile, the drift trinity (audit time)

`agent-do manna reconcile [--fix]`, mirroring gate/drift/audit from contracts. Reports:

1. Open items with landed trailer commits (the mn-e6c7bd class).
2. Claims held by dead coord sessions.
3. Blocked issues whose blockers are all resolved. `manna done` releases dependents inline
   in the same atomic board write (tools/agent-manna/src/store.rs). Reconcile remains the
   backstop for deleted blockers and stale boards written by older binaries or manual edits.
4. Dreams older than N days, unconverted.
5. Track edges naming rows that do not exist or are not tracks; tracks with no live items
   (retire or refill).
6. **Memory/doc drift:** scan project memory + `.handoff/` for `mn-[a-f0-9]{6}` references and
   checklist marks that disagree with board status. A backlog living inside a memory file is
   itself a finding (Layer 4's single-truth rule).

Wiring: SessionEnd hook runs it advisory (work dying unwritten IS a board that no longer matches
reality). Weekly schedule + nightly CI run it as a report with notify on findings, exactly like
the contracts audit. Advisory in-session, binding at the gate.

## Layer 4: ambient dissemination (read time)

- SessionStart hook injects `manna context --max-tokens N` so every session, including a random
  train-of-thought one, begins knowing the tracks, the open items, and where the work is heading.
  Dreams get filed under the right sky because the sky is visible.
- Stop-hook nudge (lite form of auto-claim, shippable early): "this session's commits touch the
  scope of open unclaimed mn-X; claim it or say why not."
- **Single-truth rule:** the board is the only backlog. Memories and handoff docs carry pointers
  to mn- IDs, never their own checklists.

## Why reconcile stops being needed

Each layer retires a failure mode at its source: the typed schema kills orphan intake, trailers
kill status testimony, liveness kills ghost claims, ambient injection kills blind filing. What
remains for `reconcile` is the residue, and structured metadata plus ambient hooks shrink that
residue further. End state: transitions are computed from claims, trailers, and merges; the only
human input left is priority and desire. Reconcile becomes a green light you glance at, not a
chore you perform.

## Staging

- **Now:** schema fields + lint land in agent-manna (mn-2a33a5); the doctrine lands in three
  documents: the global CLAUDE.md grammar block, this v2, and the repo CLAUDE.md section shrink
  (mn-0302de).
- **Next:** first dogfood migration (mn-0c9eaf, below); `manna reconcile` checks 1-5 (needs only
  git log + coord peers + board); SessionStart board injection; SessionEnd advisory run.
- **Converges with:** structured-metadata trunk mn-807f18 (possible `in_review` status, GitHub
  sync), ambient-hooks trunk mn-f1604f (subsumes the lite nudges), and the SessionEnd organ
  mn-2ac590 (reconcile-advisory and the session-death sweep are one build).

## First dogfood board (non-normative)

agent-do's own board migrates first: two track rows (mn-b7a0cc "Agentic Work OS", mn-69368a
"Companion / Second Chair"), items re-pointed with `--track`, provenance recorded with `--source`.
Existing titles keep their program names and mythology; structure now lives in the fields, so the
display prefixes those titles carry are data only. Migration steps:
`.dev/session-prompts/03-doctrine-migration.md`.
