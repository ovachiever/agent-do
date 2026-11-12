# coord-wake/1 fixtures

Real `agent-do coord` payloads from an isolated board, written by `tests/gen_coord_wake_fixtures.py`.
Session ids, pids, paths and timestamps are the fixture run's own. `tests/test_coord_v2.py::test_wake_fixtures`
checks every file against the contract's required keys. Contract: `docs/COORD-WAKE.md`.

`dispatch-*`, `*-after-dispatch*`, `demands-lapsed-reservation` and `request-superseded-lapsed-reservation` are the
crash-window shapes: a reservation (no dispatch mark) whose holder died is reclaimable; a dispatch-started request
whose holder died reads `unknown` and refuses every new request until a live consumer establishes its outcome.

- `demands-wanted.json`
- `refusal-recipient-is-caller.json`
- `request-requested.json`
- `refusal-held-by-other.json`
- `request-duplicate.json`
- `waiting-pending-readiness.json`
- `demands-held-by-consumer.json`
- `outcome-submitted.json`
- `outcome-submitted-replay.json`
- `refusal-submitted-needs-after.json`
- `demands-acknowledged-held.json`
- `refusal-acknowledged.json`
- `request-new-revision.json`
- `outcome-unknown.json`
- `refusal-unknown-outstanding.json`
- `outcome-failed-after-unknown.json`
- `refusal-no-evidence.json`
- `refusal-dispatching-not-holder.json`
- `dispatch-started.json`
- `dispatch-started-replay.json`
- `refusal-waiting-after-dispatch.json`
- `refusal-released-after-dispatch.json`
- `demands-dispatching-held.json`
- `demands-unknown-after-dispatch-crash.json`
- `refusal-unknown-after-dispatch-crash.json`
- `outcome-established-after-crash.json`
- `demands-lapsed-reservation.json`
- `request-superseded-lapsed-reservation.json`
- `refusal-dispatch-demand-moved.json`
- `demands-stale-reassigned.json`
- `refusal-stale.json`
