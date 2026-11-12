# Coord wake contract (`coord-wake/1`)

The contract a host adapter (Holy, or any other process that can reach a
worker's terminal) consumes to notify an idle worker about its pending Coord
action without agent-do depending on that host. Everything here is a read of
the coord ledger or a transport receipt written beside it. Nothing here
acknowledges a drop, resolves one, extends an approval, or moves a claim.

Source: `tools/agent-coord` (`wake_list`, `wake_request`, `wake_outcome`).
Executed coverage: `tests/test_coord_v2.py::test_wake_contract` and
`test_wake_fixtures`. Fixtures a consumer can replay: `tests/fixtures/coord-wake/`
(generated from the real CLI by `tests/gen_coord_wake_fixtures.py`).

## The verbs

| Call | Who | What it does |
|---|---|---|
| `agent-do coord drops --wake --json` | host | Read the wake demands: actionable first, held ones with reasons, each with its notification state. |
| `agent-do coord drop wake <drop-id> [--revision <n>] [--after <request-id> --evidence <text>] --json` | host | Claim the demand for this consumer. Returns a request id, the recipient's harness facts and the fixed instruction. |
| `agent-do coord drop wake <drop-id> --request <request-id> --waiting <reason> --json` | host | Record why the held reservation is waiting (busy, needs the user, draft present). |
| `agent-do coord drop wake <drop-id> --request <request-id> --dispatching <evidence> --json` | host | Enter dispatch-started: the durable fence written immediately before the transport is touched, with the terminal and the session incarnation just re-checked. Send only after it succeeds; a refusal means do not send. |
| `agent-do coord drop wake <drop-id> --request <request-id> --outcome submitted\|unknown\|failed\|released --evidence <text> --json` | host | Record what the transport did, with what established it. |

Every call exits 0 with `success: true` or exits 2 with `success: false`,
`error` and the structured reason (`demand`, `held_by`, `outstanding`,
`submitted`, `superseded_by`). Nothing is written on a refusal.

## Consumer identity

A consumer is an ordinary coord participant. It runs the commands with:

```
AGENT_DO_COORD_SESSION=<stable consumer id, e.g. holy:<host>:<server-epoch>>
AGENT_DO_COORD_PID=<the consumer's own long-lived pid>
AGENT_DO_COORD_PID_START=<ps -o lstart= of that pid>   # optional; coord reads it when absent
```

Its coord presence is the lease: a demand is held while the holder's presence
is `active` (the presence window `AGENT_DO_COORD_ACTIVE_SECONDS`, renewed by
every coord call the consumer makes) and its process is not verifiably gone.
A consumer that crashes before it entered dispatch leaves a lapsed reservation
that any live consumer may supersede; one that crashes after dispatch-started
leaves an unknown outcome that only evidence settles (see Reservation and
dispatch-started); a consumer that restarts under the same id is the same
consumer and settles its own open requests first.
Declare a read-only role once so the consumer never counts as a writer:
`agent-do coord role set overseer --territory .` (overseer defaults to
read-only).

## What is a wake demand

An open drop is a demand when all of these hold, read fresh at every call:

- `kind` is `action` (an informational drop is a notice; it is never a wake)
- it addresses one exact recipient (an item drop resolved by claim proof, or a
  direct `--for <session>`); roles and `any` are broadcasts and never wakes
- the recipient's coord session is live (`active` or `idle`)
- the recipient has not acknowledged the current revision
- for an item drop, the assignment is not stale (no reassignment, new claim,
  attempt change, work-order revision or closure since the drop pinned it)

Everything else that is an open action drop is listed under `held` with its
reason, so a human surface can say why nothing is being sent.

A demand's deduplication identity is `demand_id`:
`<drop-id>:r<revision>:<assignment-key>`, where the assignment key is a digest
of the pinned board path, claim proof, claim timestamp, managed flag, attempt
and work-order digest (item drops), or the recipient session id (direct drops).
A new revision is a new demand (the owner re-pinning a drop against a moved
assignment bumps the revision too): earlier receipts stay in history and do not
carry over, and an acknowledged action re-added at a new revision is a demand
again. A board that moves underneath an unchanged pin (reassignment, a new
claim or attempt, a revised work order, closure) does not make a new demand: it
makes the same demand stale, and stale demands are held, never requested.

## Demand record

```json
{
  "demand_id": "drp-5b1c…:r1:9f3e…",
  "actionable": true,
  "reason": null,
  "wake_wanted": true,
  "drop": {"id": "drp-5b1c…", "revision": 1, "kind": "action", "status": "open", "path": ".dev/approval.md",
           "note": "…", "owner": "session-…", "owner_label": "…", "created_at": "…", "updated_at": "…",
           "approval": {"allows": [], "excludes": [], "authorized_by": "…", "work_order": {"prompt": "…", "digest": "sha256:…"}}},
  "addressing": "item",
  "assignment": {"id": "mn-…", "title": "…", "status": "in_progress", "board": "/…/.manna", "board_root": "/…",
                 "via_worktree": false, "claimant": "claude-…", "claim_proof": "sha256:…", "claimed_at": "…",
                 "attempt": null, "managed": false, "work_order": {"prompt": "…", "digest": "sha256:…"},
                 "observed_at": "…", "source": "manna show --json; …"},
  "recipient": {"state": "resolved", "agent_id": "session-…", "presence": "idle",
                "session": {"agent_id": "session-…", "presence": "idle", "harness": {"runtime": "claude",
                            "identity_source": "AGENT_DO_COORD_SESSION", "session": "<harness session id>",
                            "pid": 4242, "pid_start": "…", "host": "…", "pane": "%5", "process": "alive"},
                            "bound": {"manna_session": "claude-…", "proof": "sha256:…", "bound_at": "…"},
                            "pulse": {"status": "idle", "updated_at": "…"}}},
  "stage": "bell queued",
  "acknowledged": null,
  "stale": null,
  "bell": {"state": "queued", "at": "…"},
  "notification": {"state": "wanted", "demand_id": "…", "request": null, "lapsed": null, "unknown": null, "attempts": 0, "requests": 0},
  "next": "a host adapter may claim it: agent-do coord drop wake drp-5b1c…"
}
```

`recipient.session.harness` is the coord record the worker's own process
wrote: `session` is the harness session id (`CLAUDE_SESSION_ID` or the pinned
coord session), `pane` is its `TMUX_PANE` when it had one, `pid`/`pid_start`
anchor liveness, `process` is `alive`, `gone` or `unverifiable`. A host maps
these to the terminal it owns and re-checks the session's incarnation
immediately before it submits anything. Coord never says a session is
input-ready; that is the host's evidence to gather.

## Reservation and dispatch-started

A request has two phases, and the difference is what a crash means.

A **reservation** is the request as `drop wake` creates it (`request.dispatch`
is `null`, `phase: reservation`). It is the consumer's intent, nothing more.
While it stands the holder may record `--waiting`, may step back with
`--outcome released`, and may lose it: when the holder's coord presence lapses
nothing can have been sent, so the demand reads `wanted` with
`notification.lapsed.reclaimable: true`, and the next `drop wake` supersedes
the reservation (`change: superseded`; the old request is frozen with its
`lapsed` record).

**Dispatch-started** is entered with
`drop wake <drop-id> --request <request-id> --dispatching <evidence>`, by the
holder, immediately before it touches the transport. The evidence is what the
host re-checked at that moment: the terminal it will type into and the
recipient's session incarnation (`pid`, `pid_start`, `session`, `pane` from the
demand record). Under its lock coord revalidates the demand (same `demand_id`,
still actionable), pins the recipient incarnation it saw into
`request.dispatch.recipient`, journals `wake_dispatch`, and returns
`phase: dispatch-started` with the demand in state `dispatching`. The host
sends only after this call returned success. A refusal means **do not send**:
`demand_moved` (the revision or the assignment changed since the reservation),
the demand's `reason` (acknowledged, stale, resolved, recipient not live), or
the caller is not the holder. A replayed `--dispatching` is `unchanged`,
`duplicate: true`; the first mark stands.

From the mark on, a missing receipt proves nothing. If the holder's presence
lapses with no outcome recorded, the demand reads `unknown` with
`notification.unknown.how: "lapsed after dispatch-started"` and
`notification.lapsed.reclaimable: false`. Nothing supersedes it, no consumer
may request it, `released` is refused on it, and nobody may enter dispatch on
the dead holder's behalf. The only way forward is evidence: a live consumer
(the restarted holder, or any other) records `--outcome submitted` or
`--outcome failed` on that same request with what it found in the transport
(scrollback, the host's own send journal keyed by request id, the composer
state), or `--outcome unknown` with why it still cannot tell. The demand then
moves as any established outcome does: `failed` reopens it, `submitted` waits
for the recipient's ack or an explicit `--after` request.

The three crash windows and what the ledger says afterwards:

| Crash | Record | Demand reads | Next |
|---|---|---|---|
| before `--dispatching` | reservation, no mark | `wanted`, `lapsed.reclaimable: true` | any consumer's `drop wake` supersedes it |
| after `--dispatching`, before the transport call | mark, no outcome | `unknown`, `lapsed.reclaimable: false` | a live consumer establishes `failed` (nothing in the terminal); the demand reopens |
| after the transport call, before `--outcome` | mark, no outcome | `unknown`, `lapsed.reclaimable: false` | a live consumer establishes `submitted` from the terminal; the demand waits for the ack |

Coord cannot tell the last two apart, by construction, and does not pretend
to: both read the same and both are settled by evidence, never by reclamation.
What coord promises is at most one open request per demand and no new request
while an earlier one may have landed. Exactly-once terminal input is not
promised and needs the transport's own support: a host whose transport cannot
confirm a submission treats its own receipt gap as `unknown`, never as
`failed`.

### Host obligations: deduplication and reconciliation

1. Keep a local send journal keyed by `request.id` with the steps `reserved`,
   `dispatch recorded` (after `--dispatching` returned success), `sent` (after
   the transport returned) and `receipt recorded`. Never send for a request id
   the journal does not show as `dispatch recorded`.
2. Immediately before sending, re-check the terminal and the recipient's
   incarnation against `request.dispatch.recipient`. A mismatch is
   `--outcome failed` with the mismatch as evidence, never a send to whatever
   is there now.
3. Send at most once per request id. A transport timeout or a reconnect after
   the send is `--outcome unknown`, then reconciliation, never a second send.
4. On start or restart, before claiming anything, list `drops --wake` and
   settle every demand in state `unknown` or `dispatching` whose request this
   consumer id holds, from the journal and the terminal: `submitted`, `failed`,
   or `unknown` with why. A dead peer's `unknown` that this host can read
   evidence for may be settled the same way; the recorder is journaled.
5. Never infer `failed` from the absence of a receipt. The absence of a receipt
   is `unknown`.

## Notification states

| `notification.state` | Meaning | How it moves |
|---|---|---|
| `wanted` | actionable, no live holder | `drop wake` by a consumer |
| `requested` | a live consumer holds a reservation | `--waiting`, `--dispatching`, `--outcome` |
| `pending readiness` | the holder is waiting for the session to be input-ready, with a reason | `--dispatching`, `--outcome` |
| `dispatching` | the holder entered dispatch-started; the transport call is in flight | `--outcome submitted\|failed\|unknown` |
| `submitted` | the instruction was submitted, with evidence | the recipient's own `drop ack` (leaves `demands`); or a further `drop wake --after <request-id> --evidence` |
| `unknown` | the holder recorded that it could not tell whether it submitted, or it entered dispatch and its presence lapsed with no outcome (`notification.unknown.how` says which) | `--outcome submitted` or `--outcome failed` on the same request, with transport evidence, by any live consumer; every new request is refused meanwhile |

`failed` and `released` outcomes return the demand to `wanted` (`failed`
counts an attempt, `released` does not; `released` applies to a reservation
only and is refused after dispatch-started). A holder's death never releases
a dispatch-started request or a recorded `unknown`: when the holder is no
longer active, any live consumer may record the establishing `submitted` or
`failed` outcome on that request with transport evidence (the recorder is
journaled), and only then may anyone request again. A lapsed reservation
(holder no longer active, no dispatch mark) reads `wanted`, with
`notification.lapsed` naming it and `reclaimable: true`; the next request
supersedes it and journals the supersession.

The delivery stage of the drop (`recorded`, `recipient resolved`,
`bell queued`, `acknowledged`, `completed`) never moves on any of these. Only
the recipient's `drop ack` and `drop resolve` do. A demand with
`notification.state: submitted` and `stage: bell queued` is the normal shape
after a successful wake and before the worker reads coord.

## Receipts

Request (`drop wake <id>` success):

```json
{"success": true, "tool": "coord", "contract": "coord-wake/1", "change": "requested", "duplicate": false,
 "supersedes": null,
 "request": {"id": "wrq-…", "demand_id": "…", "drop_id": "drp-…", "revision": 1, "consumer": "session-…",
             "consumer_label": "…", "requested_at": "…", "recipient": "session-…", "after": null,
             "evidence": null, "waiting": null, "dispatch": null, "outcome": null, "supersedes": null,
             "history": [{"event": "requested", "at": "…", "by": "session-…"}]},
 "demand": {…the demand record, now notification.state requested…},
 "instruction": "The ledger has entries concerning you; run `agent-do coord interrupts` and `agent-do coord drops --for-me`."}
```

`change` is `requested`, `superseded` (a lapsed holder's request was closed
out, named in `supersedes`) or `unchanged` with `duplicate: true` (the same
consumer asked again; the same request comes back, nothing is written).

Dispatch-started (`--dispatching` success):

```json
{"success": true, "tool": "coord", "contract": "coord-wake/1", "change": "recorded", "duplicate": false,
 "phase": "dispatch-started", "holder_presence": "active",
 "request": {…, "dispatch": {"at": "…", "by": "session-…",
                             "evidence": "tmux pane %5, server epoch 12, worker pid 4242 alive, composer empty",
                             "instruction": "The ledger has entries concerning you; …",
                             "recipient": {"agent_id": "session-…", "presence": "idle", "session": "<harness session id>",
                                           "pid": 4242, "pid_start": "…", "pane": "%5", "process": "alive"}}},
 "demand": {…notification.state dispatching…}, "demand_moved": null, "demand_actionable": true, "delivery_stage": "bell queued"}
```

`change` is `recorded`, or `unchanged` with `duplicate: true` for a replay (the
first mark stands). The pinned `recipient` is what the host compares against
immediately before it sends.

Outcome (`--outcome` or `--waiting` success):

```json
{"success": true, "tool": "coord", "contract": "coord-wake/1", "change": "recorded", "duplicate": false,
 "phase": "dispatch-started", "holder_presence": "active",
 "request": {…, "outcome": {"state": "submitted", "evidence": "tmux pane %5, server epoch 12, composer empty", "at": "…", "by": "session-…"}},
 "demand": {…}, "demand_moved": null, "demand_actionable": true, "delivery_stage": "bell queued",
 "note": "a transport receipt is never the recipient's acknowledgment; …"}
```

`change` is `recorded`, `corrected` (a different state replaced an earlier
one; `outcome.corrects` keeps the earlier outcome and the request history has
both) or `unchanged` with `duplicate: true` (the same state replayed; nothing
written). `demand_moved` is set when the drop's revision or assignment changed
after the request: the receipt is kept as a fact against the old demand and the
current demand needs fresh attention. `demand_actionable: false` with the
demand's `reason` says the work no longer wants a wake (acknowledged, stale,
resolved).

`--evidence` is required for every outcome, including `unknown` (why it is
unknown) and `released` (why the consumer stepped back).

## Refusals (exit 2, nothing written)

| Situation | `error` names | Extra field |
|---|---|---|
| the drop is informational, broadcast, resolved, acknowledged, stale, or its recipient is pending, ambiguous or not live | the reason | `demand` |
| the caller is the recipient | `drop ack` | `demand` |
| another live consumer holds the demand | the holder and its request | `held_by` |
| the last request's outcome is unknown | the request and the exact `--outcome` command | `outstanding` |
| the last request was submitted and the recipient has not acked | `--after <request-id> --evidence` | `submitted` |
| `--revision` does not match | the current revision | `demand` |
| a new request while a dead holder's dispatch-started request has no outcome | the holder, its dispatch time, `may have occurred`, and the exact `--outcome` command | `outstanding` |
| outcome on a request another live consumer holds | the holder | `held_by` |
| outcome on a superseded request | the superseding request | `superseded_by` |
| `--dispatching` by a session that is not the holder, live or dead | the holder's own act | `held_by` |
| `--dispatching` after the revision or the assignment moved | `do not send` and both demand ids | `demand_moved`, `demand` |
| `--dispatching` when the demand is no longer actionable (acknowledged, stale, resolved, recipient not live) | `do not send` and the reason | `demand` |
| `--waiting` or `--outcome released` after dispatch-started | the dispatch time and the outcomes that apply | `dispatch` |
| `--outcome` without `--evidence`, `--dispatching` without evidence, or not exactly one of `--outcome`/`--waiting`/`--dispatching` | the usage | |

A reconnect, a timeout or a missing receipt is never grounds to submit again:
an `unknown` outcome, recorded or inferred from a holder that died after
dispatch-started, holds the demand until a live consumer establishes what
happened with transport evidence.

## Where the receipts live

On the drop record, `wake[<demand_id>].requests[]`, in the coord store
(`<git-dir>/agent-do/coord/drops.json`); the events journal carries
`wake_request`, `wake_waiting`, `wake_dispatch` and `wake_outcome` lines that `drop history <id>`
lists. Every `drops`, `worker <mn-id>` and `drop history` view shows
`delivery.notification`. The owner's `interrupts` awaiting notice says
`wake <state>` beside the delivery stage. Nothing is deleted.

## Standalone behavior

With no host adapter present, nothing changes: drops ring the bell, hooks
deliver the fixed context at the worker's next boundary, `drops --wake` lists
the demands as `wanted`, and no request ever exists. The host adapter is
optional by construction.
