# coord-wake/1 fixtures

Real `agent-do coord` payloads from an isolated board, written by `tests/gen_coord_wake_fixtures.py`.
Session ids, pids, paths and timestamps are the fixture run's own. `tests/test_coord_v2.py::test_wake_fixtures`
checks every file against the contract's required keys. Contract: `docs/COORD-WAKE.md`.

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
- `demands-stale-reassigned.json`
- `refusal-stale.json`
