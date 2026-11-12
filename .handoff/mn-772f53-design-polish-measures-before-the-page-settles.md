---
workflow: 2
manna: mn-772f53
track: null
source: null
base_commit: 630640e73afe7081ae34b79d7e4f09b90d27f703
scope: design polish measures before the page settles
inputs: []
binding: sha256:77bf065bc74bac0d7c17ec143eb400ad6d74debde0555b8f44f6ea294e2e0717
---

# Handoff: design polish measures before the page settles

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-772f53
```

## Scope

design polish measures before the page settles

## Inputs

- None declared.

## Work order

agent-do design polish opens the URL and evaluates polish.js immediately (design_browser.py polish()). On a client-rendered page that assembles for several seconds after load, the audit judges the loading skeleton (observed 2026-09-22 on the Palingenesis Today page: 'Assembling', 'unavailable', 'Offline' captured). Needs a settle condition: network idle plus a caller-supplied ready predicate or text marker, with the wait recorded in the audit.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-772f53`.
4. Commit with `Manna: mn-772f53` and run `agent-do manna done mn-772f53` only after the work is verified.

## Implementation and verification receipts (2026-09-23)

Claim owner: `codex-01a0ce84839c7d83`. Initial binding independently verified against
canonical Manna state and the source binding algorithm:
`sha256:90f59411f3dcaa64e6fd0dc8c9482392959b494c60dc6b92d5810b52dbe42e23`.
Isolated implementation checkout:
`/Users/erik/Custom-Coding/agent-do-mn-772f53`, base
`630640e73afe7081ae34b79d7e4f09b90d27f703`. Canonical board operations remain in
`/Users/erik/Custom-Coding/agent-do`.

Implemented behavior:

- `design polish` waits for native browse network idle after navigation and viewport setup.
- `--ready-text` or `--ready-js` adds an application readiness condition. The tool waits
  for network idle again and rechecks readiness before measuring. A single
  `--settle-timeout-ms` budget covers all phases (default 60000 ms).
- `--config` accepts the same options under `settle`; CLI options override them.
- Successful audits include the requested condition, timeout, elapsed time, and
  native wait outcomes. Failed readiness exits 2, skips measurement/rendering,
  and saves a failed receipt to `--out`. Dry runs perform no browser operations.
- The supported browse CLI exposes `wait --fn` and per-condition `--timeout-ms`,
  safely encodes literal markers, and passes the native predicate timeout in the
  correct Playwright options position.

Executed focused checks:

| Command (implementation checkout unless noted) | Actual result |
| --- | --- |
| `python3 tools/agent-design/test/test_settle.py` | 18 passed; explicit transport fixtures, no browser |
| `cd tools/agent-browse && npm test -- wait.test.js protocol.test.js` | 32 passed; no browser launch |
| `python3 tools/agent-design/test/test_contract.py` | 13 passed |
| `python3 tools/agent-design/test/test_settle_browser.py` | Closing pass: 5 passed in 21.338s; real headless browse path, session closed |
| `python3 -m py_compile tools/agent-design/design.py tools/agent-design/design_browser.py tools/agent-design/test/test_settle.py tools/agent-design/test/test_settle_browser.py` | Passed; syntax compilation only |
| `bash -n test.sh tools/agent-browse/agent-browse` | Passed |
| `node --check tools/agent-browse/actions.js` | Passed |
| `git diff --check` | Passed |
| `PATH=/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH ./agent-do harness contracts drift --tool design --json` | Exit 0; zero declared-only verbs |
| Same drift command with `--tool browse` | Exit 0; zero declared-only verbs; existing help-only verbs remain advisory |
| `./agent-do design polish https://example.com/today --viewport 800x600 --ready-js 'window.todayReady === true' --settle-timeout-ms 45000 --dry-run` | Exit 0; requested readiness plan returned, no browser |

The first new protocol test supplied an object to a JSON-text parser and failed.
It now exercises serialized input, matching the production protocol; the rerun
passed all 32 tests. Vitest reports missing legacy source maps for existing JS
files; these are nonfatal and remain outside this lane. Existing node dependencies
were reused through a worktree symlink; no install occurred.

## Coordinated closing acceptance

No browser or app launched mid-lane. At the closing phase, after implementation
and offline verification, Coord reserved `.dev/design-polish-live-acceptance`
and published the active window. The native readiness suite ran in the isolated
checkout through a dedicated browse UUID session. It closed its session and
released the slot. No screenshots, installs, pushes, or pull requests occurred.
The full root suite was not run because it exceeds the focused validation scope.

The first native run passed 4/5 and the targeted diagnostic rerun reproduced the
failure. A JavaScript expression had been wrapped as an arrow-function string,
which Playwright treated as a truthy function rather than executing. The final
readiness recheck still prevented incorrect measurement, but the native ready
wait and receipt phase were wrong. The implementation now passes the boolean
expression directly and records every recheck explicitly. The no-browser suites
passed again, followed by **5/5 executed native fixtures** in 21.338 seconds.
Initial failure evidence and the diagnostic audit remain in `.dev/mn-772f53/`.

Final real-browser receipts:
`.dev/mn-772f53/design-readiness-ae48467eed5841e2b24a7d843f9f9f8d/`.

| Fixture | Measured result | Recorded wait |
| --- | --- | --- |
| Delayed boolean predicate | `Ready now.` | 2542 ms; all four phases passed |
| Delayed text marker | `Ready now.` | 2623 ms; all four phases passed |
| Missing marker | Measurement not run | 3060 ms; text wait failed |
| Pending network fetch | `Complete.` | 1520 ms; network idle passed |
| Invalid predicate | Measurement not run | 1110 ms; predicate wait failed |

Each native wait receives the remaining deadline budget. The receipt includes
CLI transport overhead, so failure reporting can occur after the configured
browser-wait budget. It never authorizes measurement after that deadline.

These fixtures are executed receipts, not compilation evidence. The separate
syntax-compilation row above remains a syntax check only. Companion `mn-17c022`
owns its geometry suite and lifecycle, and its own requested acceptance boundary
is preserved. The combined Today field check is tracked as **mn-0eff4d**, owner
Erik, under the repository's separate field-check closing rule. It calls for:

```bash
python3 tools/agent-design/test/test_settle_browser.py
python3 tools/agent-design/test/test_polish.py
```

Then auditing the Palingenesis Today page using a confirmed application-ready text
marker or boolean expression, and inspect the retained `settle` receipt and
rendered text. No known Today URL or ready signal is invented here. These live
page receipts remain pending on the field item. This build's required readiness
acceptance is verified; its local commit and canonical Manna closure are recorded
by the `Manna: mn-772f53` trailer and board state.

Lessons logged: 5 (new) | Decisions logged: 0 (new).
