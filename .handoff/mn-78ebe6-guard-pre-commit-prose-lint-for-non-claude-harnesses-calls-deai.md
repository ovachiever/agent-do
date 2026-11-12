---
workflow: 2
manna: mn-78ebe6
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'guard: pre-commit prose lint for non-Claude harnesses (calls deai)'
inputs: []
binding: sha256:422eac189842226c035288edaa6ccd11aef8da0cddcdadf5b2bcb076e3f9417b
---

# Handoff: guard: pre-commit prose lint for non-Claude harnesses (calls deai)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-78ebe6
```

## Scope

guard: pre-commit prose lint for non-Claude harnesses (calls deai)

## Inputs

- None declared.

## Work order

Option E. Warn-only pre-commit guard (coord guard pattern) linting changed prose files at commit time — catches codex/droid/cursor output that never passes through Claude hooks. Blocked by the deai tool.

## Implementation and verification

Verified 2026-09-21 UTC in `/Users/erik/Custom-Coding/agent-do`.
The initial claim succeeded for `codex-01a0c1a346dc7c21`. The canonical pointer,
owner, frontmatter binding, and recomputed binding all matched the dispatched
`sha256:558b77dedbf1a931a0620fce37f2356d5d6277218921f53ed8e9209373a4a6ce`.
Binding was recomputed using `tools/agent-manna/src/workflow.rs` normalization.

Acceptance invariant: committing changed prose invokes the canonical deai
rules against the Git index, emits advisory findings, preserves existing commit
gates, and never rewrites prose or staged content. This operates independently
of the coding harness and requires no Claude hook.

Delivered:

- `agent-do deai guard check [--register NAME] [--json]` checks staged Markdown,
  reStructuredText, and plain text using immutable Git blob IDs. It defaults to
  the technical-safe `default` register, with an explicit register override.
  Findings and check failures are visible but advisory. Partial staging,
  alternate indexes, unusual filenames, rename destinations, and subdirectories
  are handled; deletions, symlinks, and binary content are not linted.
- `agent-do deai guard install [--register NAME] [--json]` manages one shell
  pre-commit block after the shebang. Existing hook content and exit status are
  preserved, including hooks that end early. Setup is idempotent, respects
  `core.hooksPath` and linked worktrees, and refuses unsupported hooks unchanged.
- Shared CLI dispatch, registry contracts, contract lexicon, generated catalog,
  tool documentation, and focused regression coverage are updated. No new
  package was installed; the guard uses the repository's existing Git runtime.

Executed focused checks:

| Command | Actual result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 python3 tests/test_deai.py` | PASS: 37 tests, zero failures or skips. Includes actual Git commits with generated fixture hooks, advisory findings, and rejection by an existing gate. |
| `PYTHONDONTWRITEBYTECODE=1 PATH="$PWD/.venv/bin:$PATH" python3 tests/test_contracts_gate.py` | PASS: contracts gate tests. |
| `PYTHONDONTWRITEBYTECODE=1 PATH="$PWD/.venv/bin:$PATH" ./agent-do harness contracts validate` | PASS: 103/103 tools declared, zero errors or warnings; 15 gated bounds sites pass. Existing ungated bounds inventory remains reported by the command. |
| `PYTHONDONTWRITEBYTECODE=1 PATH="$PWD/.venv/bin:$PATH" ./agent-do harness contracts drift --tool deai --json` | PASS: no declared-only or help-only commands. |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python bin/gen-tools-doc --check` | PASS: generated catalog matches registry. |
| `git diff --check` | PASS. |

Resolved verification failures: the first test run passed 36/37, with one
fixture comparing macOS `/var` and `/private/var` aliases; resolved path
comparison fixed it. The first contracts-suite invocation gave its subprocess
the host Python without PyYAML; placing the existing `.venv/bin` on `PATH` fixed
the environment. No dependency installation or test bypass was used.

Validation boundaries: these tests were executed, not merely compiled. There
are no compiled or app-hosted tests for this change. Hook installation occurred
only inside isolated Git fixtures. No live checkout hook activation, app launch,
screenshot, or live harness session was performed. This CLI-only work order has
no visual acceptance requirement. Live activation is a separate operation via
the documented install command, outside this lane's no-install boundary.

Coord focus and path claims protect this lane. The parallel `mn-005efa` worker
was given the guard interface and path policy through Coord; its hooks,
installer, test runner, and Manna claim are preserved.

Lessons logged: 3 (new) | Decisions logged: 0 (new).
Lesson IDs: `les-afb62b`, `les-718cbe`, `les-8300f2`.

## Completion

Acceptance is verified. Implementation commit: `b74b5c7` (`feat(deai): add
advisory staged prose guard`), with the exact `Manna: mn-78ebe6` trailer.
The guarded commit passed the staged secret scan and existing pre-commit gate.
No push or pull request was performed. No required acceptance remains for this
CLI work order; live hook activation remains separate from implementation.

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-78ebe6`.
4. Commit with `Manna: mn-78ebe6` and run `agent-do manna done mn-78ebe6` only after the work is verified.
