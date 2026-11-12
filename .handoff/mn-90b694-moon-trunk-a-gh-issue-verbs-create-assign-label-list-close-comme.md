---
workflow: 2
manna: mn-90b694
track: mn-b7a0cc
source: null
base_commit: d6bad082a06b9c64f472151f399e3d576108ca38
scope: 'Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare'
inputs: []
binding: sha256:c3298a7f54aff9075d716abf5f105f50d3c9b8f569f2cd522c90dea3c32c0e72
---

# Handoff: Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-90b694
```

## Scope

Moon trunk A: gh issue verbs (create/assign/label/list/close/comment) + pr create --declare

## Inputs

- None declared.

## Work order

Claim mechanism needs issue verbs; gh tool is PR-only today. House pattern: registry+contracts+tests+docs.

## Delivery receipts (2026-09-15)

- Claim accepted for `codex-01a0a68550877930` in the primary checkout.
- Initial canonical item digest, frontmatter binding, and independently
  normalized handoff SHA-256 all matched
  `sha256:3d1b649e41a3fb4eec411dc8ca9d3e76cbbe20dd932d258c4af4b2c24624e644`.
- Implementation base observed: `f158189`; implementation commit:
  `e2cdcf43e113a19461e1af7cfc5c2afa7cc5dea8`,
  `feat(gh): add issue commands and declared PR creation`, with exact trailer
  `Manna: mn-90b694`. The staged secret scan and normal pre-commit hook passed.
- Owned implementation: `tools/agent-gh`, `tests/test_gh.py`, `registry.yaml`,
  `docs/GITHUB.md`, generated `docs/TOOLS.md`, `CLAUDE.md`, and `CHANGELOG.md`.
  Coord focus and path claims preceded edits; foreign changes were preserved.

### Accepted implementation

1. `gh issue create/list/assign/unassign/label/close/comment` uses the existing
   GitHub CLI transport, validates issue targets before mutation, supports
   JSON output, preserves body-file/stdin text, and returns read-back receipts.
   Additive assignment preserves other assignees; it is not Manna arbitration.
2. Issue listing fetches every page and excludes PR objects before counting
   or display limits. Empty collections, malformed responses, transport
   failures, wrong target kinds, and successful writes with failed read-back
   have executed coverage. Writes are never retried automatically.
3. `gh pr create --declare` preserves every base-to-head commit's Work-Item
   (or Manna), Model, Effort, and Session trailers in a versioned declaration.
   It refuses missing/ambiguous stamps and mismatched published heads.
   It checks the created PR's head/body and retains its URL on partial success.
4. Local `--dry-run` never calls GitHub. Actual PR creation always passes
   `--head`, preventing the native CLI's implicit push/fork behavior. Existing
   `gh pr <reference>` inspection and review commands retain their syntax.
5. Registry commands, routing, five-beat contracts, generated tool reference,
   and detailed `docs/GITHUB.md` document the complete surface and boundaries.

### Focused verification

All commands below ran from `/Users/erik/Custom-Coding/agent-do` with
`PATH="$PWD/.venv/bin:$PATH"` for the repository's Python dependencies.

| Command | Actual result |
| --- | --- |
| `python3 tests/test_gh.py` | PASS: existing GH regressions and 52 new command scenarios executed |
| `python3 tests/test_contracts_gate.py` | PASS: contracts gate tests executed |
| `./agent-do harness contracts validate` | PASS: 103/103 tools declared, zero errors and warnings; bounds gate zero errors |
| `./agent-do harness contracts drift --tool gh --json` | PASS: no declared-only or help-only verbs |
| `python3 -m py_compile tools/agent-gh tests/test_gh.py` | PASS: Python modules compiled; separate from executed tests above |
| `./bin/gen-tools-doc --check` | PASS: generated reference matches registry |
| `git diff --check` | PASS |

The contracts suite initially caught routing catalog growth to 40,010
characters (baseline 39,953; gate requires fewer than 40,000). Tightening
only new GH discovery prose reduced it to 39,935; the suite then passed.
No test threshold or capability was removed. Logs and source-hash receipts
are under `.dev/mn-90b694/`.

### Acceptance and continuation boundary

The scoped build requirements are verified by executed isolated CLI/Git
fixtures. No app-hosted tests apply. No app launch, installation, screenshot,
live session spawn, push, live GitHub issue mutation, or live PR creation ran.
An optional provider field check needs a separately authorized disposable
GitHub target; no visual acceptance applies to this CLI-only lane.

Harness-derived stamping and authentication of provenance remain the separate
trunk C work order; GitHub/Manna synchronization remains trunk B; policy floors
remain trunk D. This lane consumes committed stamps and never invents them.

Canonical completion also removed `mn-90b694` from `mn-404dd7`'s blockers.
That dependent remains blocked by `mn-807f18` and `mn-c3145f`. The completion
payload's `released: []` lists newly unblocked rows, not every updated row;
the dependent's automatic update is included in the closure commits.

Lessons logged: 5 (new) | Decisions logged: 0 (new).
Lesson receipts: `les-d902eb`, `les-b0473b`, `les-156c66`, `les-ab5c33`, and
`les-0f67fb` (corrected with the exact canonical dependency-release diff).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-90b694`.
4. Commit with `Manna: mn-90b694` and run `agent-do manna done mn-90b694` only after the work is verified.
