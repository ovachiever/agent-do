---
workflow: 2
manna: mn-0364a0
track: null
source: null
base_commit: b51d3dc26ae38ccfce2d6dbf4e1a20dc1d91a428
scope: '[P1][MANNA] done releases its dependents inline — a satisfied blocker never leaves an item showing blocked'
inputs: []
binding: sha256:a2d736e7ee0f8007e60f97f11104760f44ad52142cf4d6aff0d87aab56fdf1b8
---

# Handoff: [P1][MANNA] done releases its dependents inline — a satisfied blocker never leaves an item showing blocked

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-0364a0
```

## Scope

[P1][MANNA] done releases its dependents inline — a satisfied blocker never leaves an item showing blocked

## Inputs

- None declared.

## Work order

Erik 2026-09-10 (holy-ghostty board, live failure): mn-5a26f9 stayed status=blocked behind mn-9b5b5b after mn-9b5b5b closed, so the Holy board's Claim & build refused it until a manual unblock — the human-facing button lied for the gap between done and the next reconcile --fix. The code already defines resolved: reconcile.rs check_blocker_desync says 'a blocker counts as resolved when it is done or no longer exists on the board' and calls the stale status routine drift. Make done perform the release inline: when an item transitions to done, remove its id from every dependent's blocked_by and flip any dependent whose list empties to open, reporting the released ids in done's output (success payload lists released: [mn-...]) so agents and Holy see the cascade. Deletion/nonexistence stays reconcile's job (the sweep remains as backstop and its check stays for boards mutated by older binaries). Update README unblock/done sections and the grammar text ('done does not auto-unblock' doctrine line dies everywhere it is quoted, including the CLAUDE.md snippet Erik carries). Tests: done with one dependent (releases to open), dependent with two blockers (stays blocked until both done), done output lists released ids, reconcile still heals a hand-edited stale board. Contract gate stays green: agent-do harness contracts validate 95/95.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-0364a0`.
4. Commit with `Manna: mn-0364a0` and run `agent-do manna done mn-0364a0` only after the work is verified.

## Verification receipts

Implementation complete. Every required work-order acceptance check passed.
Canonical lifecycle state remains in `.manna/`.

- Initial claim succeeded for `codex-01a08e8183f07bc1`. The complete document's
  normalized binding, its frontmatter, and canonical Manna state all matched
  `sha256:657cb4a0bbd0b864b13c015bde0d9577a80f77751dcd22b2ef60206ff8f85247`
  before editing.
- Implementation commit: `e367942f31b163b071d2bb78e4731f8817b9c2cf`
  (`fix(manna): release dependents when completing blockers`), with the exact
  trailer `Manna: mn-0364a0`.
- `complete_issue_checked` removes the completed ID from every dependent in the
  same board lock and atomic write as completion. Its `released` result names
  only dependents that became unblocked, in board order; the CLI always emits
  the list, including `released: []`.
- The existing status rule remains authoritative: an unclaimed dependent becomes
  `open`, an already claimed dependent resumes `in_progress` with its owner and
  proof preserved, a dependent with other blockers remains `blocked`, and a
  completed dependent stays `done`.
- Reconcile retains its existing repair behavior for missing/deleted blockers
  and stale boards. README command help, architecture grammar, the portable
  CLAUDE conventions, the older coherence-design quotation, and release notes
  describe the new completion behavior.

| Command | Actual result |
| --- | --- |
| `cargo test --manifest-path tools/agent-manna/Cargo.toml` | Executed: 176 library tests and 46 binary tests passed (222 total), zero failed or ignored. Zero doc tests. |
| `PATH="$PWD/.venv/bin:$PATH" bash tools/agent-manna/test/integration.sh` | Executed: 399 assertions passed, zero failed. The canonical runner built the release CLI with `cargo build --release --quiet` first. |
| `PATH="$PWD/.venv/bin:$PATH" agent-do harness contracts validate` | PASS: current catalog 102/102 declared tools, zero errors and zero warnings. The work order's 95-tool denominator was historical. |
| `cargo fmt --manifest-path tools/agent-manna/Cargo.toml -- --check` | Passed. |
| `bash -n tools/agent-manna/test/integration.sh` | Passed. |
| `git diff --check` and `git diff --cached --check` | Passed. |

The regression checks execute single-dependent release, partial and final
release with two blockers, exact release payloads, immediate claiming without
reconcile or sync, preserved dependent ownership, closed-row preservation,
refused-completion rollback, concurrent blocker completion, and reconcile's
repair of an explicitly hand-edited isolated fixture. Duplicate satisfied edges
are removed; unrelated missing blockers remain for reconcile.

Raw logs and source/log hashes: `.dev/mn-0364a0/verification.json`,
`.dev/mn-0364a0/cargo-test.log`, `.dev/mn-0364a0/integration.log`, and
`.dev/mn-0364a0/contracts-validate.log`.
The contracts command also reports its existing non-gated bounds inventory
(176 ceilings owed and 8 shared-code caps). Those are outside this item's scope.
The root suite was not run, following the instruction to run focused suites only.

## Acceptance and coordination boundary

- Required acceptance remaining: none. Tests above were executed; there are no
  compiled-only or unexecuted required tests.
- No app launches, installs, screenshots, or live session spawning occurred.
  This CLI work order has no app-hosted or visual acceptance requirement.
- Optional field observation for the coordinating Holy Board owner after this
  lane closes: observe a real last-blocker completion make its dependent
  immediately claimable. Coordinate that pass separately; it does not gate
  this item's verified CLI acceptance.
- Foreign work was preserved. The overlapping design-planning session explicitly
  declared read-only planning with no implementation or tracker mutation; this
  lane retained exact file ownership and published its handoff boundary.
- Lessons logged: 4 (new), `les-e3b143`, `les-b03bad`, `les-42de14`,
  plus the final YAML timestamp receipt-serialization lesson.
  Decisions logged: 0 (new). `agent-do zpc harvest --since last` completed with
  zero format issues and zero consolidation gaps.
