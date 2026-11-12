---
workflow: 2
manna: mn-e6e1a8
track: mn-b7a0cc
source: independent review of mn-5cdd6e, 2026-11-03, probe P1
base_commit: 7096b00c4668e3a51d1d39a5a8e1d84a2b061aaa
scope: 'coord: stale item-approval interrupts name a refused remedy'
inputs:
- independent review of mn-5cdd6e, 2026-11-03, probe P1
binding: sha256:5e5b28f040ff0c187f9e5b857c66cf53e5ed0c18d2811e841715d4175da4bf87
---

# Handoff: coord: stale item-approval interrupts name a refused remedy

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e6e1a8
```

## Scope

coord: stale item-approval interrupts name a refused remedy

## Inputs

- independent review of mn-5cdd6e, 2026-11-03, probe P1

## Work order

Found in the independent review of mn-5cdd6e (receipt .dev/mn-ed4353-review/acceptance-mn-5cdd6e.md, probe P1). Since 7096b00, coord correctly refuses ack and resolve by the recipient of a STALE item-addressed approval (claim changed, attempt changed, reassigned, item closed, unverified); only the owner may retire it. But the interrupt/hook text for that drop still prints the ordinary remedy: 'resolve when done: agent-do coord drop resolve <id> --reason <text>' or 'ack when read: agent-do coord drop ack <id>'. An agent following the hint gets exit 2. Fix: when for_item staleness is set, the remedy names the real path (the owner retires it or explicitly readdresses; the recipient needs a fresh approval). Since the recipient can never ack a stale drop, decide whether it should stay in their interrupts at all, or show once as a notice. Regression: extend test_assignment_turnover to assert the stale hook text names no refused command. Low severity: enforcement is correct, only the guidance is wrong.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e6e1a8`.
4. Commit with `Manna: mn-e6e1a8` and run `agent-do manna done mn-e6e1a8` only after the work is verified.

## Verification receipts (2026-11-03, worker claude-3f2a6552e3b94bf2, Claude Fable 5.1)

Fix commit: `e408409541c33bdc66c96ee5a74725dfe61cd7c0` — `fix(coord): stale assignment drops name a remedy that works`, trailer `Manna: mn-e6e1a8`, on base 7096b00. Files: `tools/agent-coord`, `tests/test_coord_v2.py`, `registry.yaml`, `docs/TOOLS.md` (regenerated), `ARCHITECTURE.md`, `CHANGELOG.md`.

Decision (zpc dec-6b461b): a stale item-addressed drop is an **info notice** for its recipient until the owner retires or readdresses it. Never a router-blocking dependency (the worker cannot clear it), never hidden after one showing (that needs new per-reader state and the fact stays true until the owner acts). The owner's own awaiting notice names the two commands that run as the owner: retire (`drop resolve`) or an exact readdress (`drop add` of the same absolute path with its recorded flags). Lesson les-496f00: guidance and enforcement branch on the same predicate, and a remedy string is only verified when the test runs it.

Executed, all passing:

- `python3 tests/test_coord_v2.py` → `coord v2 tests passed` (3m56s wall; holds the extended `test_assignment_turnover`)
- `python3 tests/test_coord.py` → `coord tests passed`
- `python3 bin/gen-tools-doc --check` → exit 0 (TOOLS.md in sync with the registry)
- `PATH=.venv/bin:$PATH ./agent-do harness contracts validate` → Gate PASS, 103/103 declared, 0 errors, 0 warnings
- `PATH=.venv/bin:$PATH ./agent-do harness contracts drift` → 0 declared-but-unimplemented
- `.venv/bin/python tests/test_contracts_drift.py` → `contracts drift tests passed`
- Discrimination: the extended `test_assignment_turnover`, with only the test's coord CLI helper redirected to 7096b00's `tools/agent-coord` (manna and the real prompt-router hook unchanged, the mn-5cdd6e reviewer's method), fails at its first new assertion: `a stale approval is an info notice: {'kind': 'dependency', 'severity': 'warning', ... 'stale': {'reason': 'claim changed', ...}}`.
- Live CLI probe of the review's P1 sequence in a throwaway board (worker acks a live approval, then abandons and reclaims): the worker's `coord interrupts` prints `notice: Approval for the worker on <item> ... [STALE: claim changed: this is a different claim, even if the same worker reclaimed it; reported 1s ago, not re-verified; void for you: its recipient can neither acknowledge nor resolve a stale approval; only its owner (<owner>) retires it or readdresses it, and you need a fresh approval before relying on it; re-check: agent-do coord worker <item>]`; the worker's `drop resolve` and `drop ack` exit 2 as before; the worker's prompt-router context does not name the drop; the owner's `coord interrupts` prints `Stale approval <id> for the worker on <item> (<session>, active): claim changed: ...; its recipient can neither acknowledge nor resolve it [retire: agent-do coord drop resolve <id> --reason <text>; or readdress: agent-do coord drop add <absolute path> --for-item <item> --allows '...' --excludes '...' --authorized-by '...'; re-check: agent-do coord worker <item>]`; running the named retirement as the owner exits 0 and both sides then print `No interrupts.`

Not run: the full `./test.sh` (focused suites only, per the lane); Rust and manna suites (no manna change). No app launches, installs, screenshots, or live session spawning.

Observations outside this item: the prompt router's generic footer still reads `drop resolve ... (owner or recipient)`; it is never paired with a stale drop because notices do not reach the hook. `coord interrupts` sorts notices before dependencies and truncates to `--limit` before the router filters blocking kinds with `--limit 5`, so five notices hide every dependency from the hook; filed as its own item.
