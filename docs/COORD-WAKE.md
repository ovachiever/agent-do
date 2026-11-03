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

## The three verbs

| Call | Who | What it does |
|---|---|---|
| `agent-do coord drops --wake --json` | host | Read the wake demands: actionable first, held ones with reasons, each with its notification state. |
| `agent-do coord drop wake <drop-id> [--revision <n>] [--after <request-id> --evidence <text>] --json` | host | Claim the demand for this consumer. Returns a request id, the recipient's harness facts and the fixed instruction. |
| `agent-do coord drop wake <drop-id> --request <request-id> --waiting <reason> --json` | host | Record why the held request is waiting (busy, needs the user, draft present). |
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
A consumer that crashes leaves a lapsed request that any live consumer may
supersede; a consumer that restarts under the same id is the same consumer.
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
  "notification": {"state": "wanted", "demand_id": "…", "request": null, "lapsed": null, "attempts": 0, "requests": 0},
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

## Notification states

| `notification.state` | Meaning | How it moves |
|---|---|---|
| `wanted` | actionable, no live holder | `drop wake` by a consumer |
| `requested` | a live consumer holds it | `--waiting`, `--outcome` |
| `pending readiness` | the holder is waiting for the session to be input-ready, with a reason | `--outcome` |
| `submitted` | the holder recorded that the instruction was submitted, with evidence | the recipient's own `drop ack` (leaves `demands`); or a further `drop wake --after <request-id> --evidence` |
| `unknown` | the holder could not tell whether it submitted | `--outcome submitted` or `--outcome failed` on the same request, with evidence; every new request is refused meanwhile |

`failed` and `released` outcomes return the demand to `wanted` (`failed`
counts an attempt, `released` does not). A holder's death never releases an
`unknown` outcome: when the holder of an unknown request is no longer active,
any live consumer may record the establishing `submitted` or `failed` outcome
on that request (the recorder is journaled), and only then may anyone request
again. A lapsed request (holder no longer
active) also reads `wanted`, with `notification.lapsed` naming it; the next
request supersedes it and journals the supersession.

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
             "evidence": null, "waiting": null, "outcome": null, "supersedes": null,
             "history": [{"event": "requested", "at": "…", "by": "session-…"}]},
 "demand": {…the demand record, now notification.state requested…},
 "instruction": "The ledger has entries concerning you; run `agent-do coord interrupts` and `agent-do coord drops --for-me`."}
```

`change` is `requested`, `superseded` (a lapsed holder's request was closed
out, named in `supersedes`) or `unchanged` with `duplicate: true` (the same
consumer asked again; the same request comes back, nothing is written).

Outcome (`--outcome` or `--waiting` success):

```json
{"success": true, "tool": "coord", "contract": "coord-wake/1", "change": "recorded", "duplicate": false,
 "holder_presence": "active",
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
| outcome on a request another live consumer holds | the holder | `held_by` |
| outcome on a superseded request | the superseding request | `superseded_by` |
| `--outcome` without `--evidence`, both or neither of `--outcome`/`--waiting` | the usage | |

A reconnect or a timeout is never grounds to submit again: an `unknown`
outcome holds the demand until the consumer establishes what happened.

## Where the receipts live

On the drop record, `wake[<demand_id>].requests[]`, in the coord store
(`<git-dir>/agent-do/coord/drops.json`); the events journal carries
`wake_request`, `wake_waiting` and `wake_outcome` lines that `drop history <id>`
lists. Every `drops`, `worker <mn-id>` and `drop history` view shows
`delivery.notification`. The owner's `interrupts` awaiting notice says
`wake <state>` beside the delivery stage. Nothing is deleted.

## Standalone behavior

With no host adapter present, nothing changes: drops ring the bell, hooks
deliver the fixed context at the worker's next boundary, `drops --wake` lists
the demands as `wanted`, and no request ever exists. The host adapter is
optional by construction.
