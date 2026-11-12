---
workflow: 2
manna: mn-67ea8d
track: null
source: Erik's approval 2026-11-12 17:14; counterpart of holy-ghostty mn-705d1f
base_commit: 7c61cf4c51de1be54f92ed00605aa509b3c1cd3b
scope: 'manna locate <id> --json: every registered board that holds an id, and every board that could not be read'
inputs:
- Erik's approval 2026-11-12 17:14; counterpart of holy-ghostty mn-705d1f
binding: sha256:770533cb48e1049eff76d0d077ec6570aa436b9c1652d78c1eff6b56f5889ecf
---

# Handoff: manna locate <id> --json: every registered board that holds an id, and every board that could not be read

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-67ea8d
```

## Scope

manna locate <id> --json: every registered board that holds an id, and every board that could not be read

## Inputs

- Erik's approval 2026-11-12 17:14; counterpart of holy-ghostty mn-705d1f

## Work order

Approved by Erik 2026-11-12 17:14 as a new read-only manna verb (taxonomy gate satisfied for this verb only). Need: Holy's cross-board link lookup (holy-ghostty mn-705d1f) must open the board that holds a clicked mn- id at once, show a chooser when several boards hold it, and report unreadable boards beside the result without letting them block a match. Today the only cross-board answer is the prose pointer in 'manna show' (tools/agent-manna/src/main.rs:1027, 'it lives on <board>'), which names one board, lists no other holders, and hides read failures. Build: 'agent-do manna locate <id> --json' reads the machine registry and returns success, the id, 'matches' (one row per board holding the id: board name, slug, root, and the item's type, status and title), 'unreadable' (root and reason for each registered board that could not be read), 'absent' or equivalent for registered roots with no board, and the count of boards examined. It must locate by reading each board's issue rows directly, never by deriving full board state: measured 2026-11-12, 'manna state --json' on aldebaran-group took 25.31 s while a plain scan of every issues.jsonl under Custom-Coding found the holder in 0.054 s. Exit 0 when the lookup completed (zero, one or many matches), nonzero only for an invalid id or an unreadable registry. An unreadable board never fails the command. No writes. The 'show' pointer should call the same lookup so there is one implementation. Registry entry with contracts (snapshot beat, read-only), --help text, docs/TOOLS.md regenerated, and tests: one holder, two holders, no holder, one unreadable board with a match elsewhere, an absent root, an invalid id, and a timing assertion against a fixture estate of 35 boards. Verification: those tests executed; contracts validate and drift clean; from the agent-do checkout 'agent-do manna locate mn-705d1f --json' names holy-ghostty.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-67ea8d`.
4. Commit with `Manna: mn-67ea8d` and run `agent-do manna done mn-67ea8d` only after the work is verified.

## Verified return: 2026-11-12

Implemented in `b9e9ce6` (`de603d8` on isolated branch `mn-67ea8d-locate`), with the exact Manna trailer. The shared `locate.rs` scanner reads issue rows directly, reports all holders, unreadable and absent roots, deduplicates canonical roots, refuses malformed registries/ids, and never derives board state. The existing human wrong-board pointer calls this scanner. The registry snapshot contract, help, README and regenerated `docs/TOOLS.md` are included. No other agent-do command was added. Other workers' README and board changes were preserved.

Executed receipts in `.dev/verification/mn-67ea8d/`:
- `cargo test --manifest-path tools/agent-manna/Cargo.toml`: 213 library + 54 binary + 7 initial lookup tests passed, zero failures. After adding the non-regular-registry guard, `cargo test --manifest-path tools/agent-manna/Cargo.toml --test locate -- --nocapture`: all 8 final lookup tests passed. The 267 existing tests were not repeated after that isolated guard addition.
- 35-board fixture, including a broken ledger and FIFO derivation inputs that lookup never opens: one holder in 0.328526 seconds, no holder in 0.016910 seconds, both below 2 seconds. These measure the CLI lookup, not Holy click-to-item latency.
- `PATH=/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH ./agent-do harness contracts validate --json`: zero errors and warnings. `... contracts drift --tool manna --json`: zero declared-only/help-only drift. Existing virtualenv used; no dependencies installed.
- `python3 bin/gen-tools-doc --check`, `rustfmt --edition 2021 --check tools/agent-manna/src/locate.rs tools/agent-manna/tests/locate.rs`, and `git diff --check`: passed.
- `cargo build --release --manifest-path tools/agent-manna/Cargo.toml`: passed in the isolated worktree and primary checkout. The primary wrapper now uses the built release binary.
- From `/Users/erik/Custom-Coding/agent-do`, `agent-do manna locate mn-705d1f --json`: exit 0 in 0.299956 seconds, 35 boards examined, one holder `holy-ghostty`, one absent root `fritsch-food`, no unreadable boards. Exact JSON in `live-locate.json`.

Initial tests exposed fixture-only errors: macOS canonical `/private/var` roots differed from `/var` assertions, and the show fixture lacked `sessions.jsonl`. Fixtures now use canonical roots and the actual initialized-store marker. First contracts invocation used a Python without PyYAML; selecting the existing owning virtualenv resolved it. Failed attempts are retained. No push or pull request.

All acceptance requirements of this counterpart are verified. Holy integration and click-to-item acceptance belong to mn-705d1f and are still pending. Lessons logged: 3 (new): les-efb65a, les-f18ecb, les-776508. Decisions logged: 1 (new): dec-278955, recording Erik's explicit taxonomy approval.
