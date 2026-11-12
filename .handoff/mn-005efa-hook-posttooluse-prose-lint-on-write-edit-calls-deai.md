---
workflow: 2
manna: mn-005efa
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'hook: PostToolUse prose lint on Write/Edit (calls deai)'
inputs: []
binding: sha256:6c0fd71036b91f8387eb4c42f48f6edee72c43b18dac9faf4508165652d0a62b
---

# Handoff: hook: PostToolUse prose lint on Write/Edit (calls deai)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-005efa
```

## Scope

hook: PostToolUse prose lint on Write/Edit (calls deai)

## Inputs

- None declared.

## Work order

Option C. Sibling of agent-do-quantity-check.py, registered the same way: fires on Write/Edit of prose files (.md and friends; path-based register detection — drafts/ gets essay pack, code files skipped), runs deai, injects flags as additionalContext so the writing agent fixes before finishing. Proven feedback pattern (quantity check demonstrates the loop). Blocked by the deai tool.

## Completion

Build acceptance verified on 2026-09-20 (America/Chicago).

### Authority and delivery

- Claimed successfully as `codex-01a0c1a320437852`; no foreign claim was taken.
- The initial handoff's normalized binding matched canonical Manna and the
  requested `sha256:3d7c39858a74c696e3f57f09da1166a2711c6051796cd2692cb2294e970c45fd`.
- Source work used `/Users/erik/Custom-Coding/agent-do-mn-005efa` on
  `codex/mn-005efa-prose-hook`; Manna and coordination stayed in the primary
  checkout. Focus and exact path claims preceded edits.
- Verified source commit: `9338e92` in the worktree, integrated into primary
  `main` as `1904787` (`feat(hooks): lint prose after write and edit calls`).
  Both contain the exact trailer `Manna: mn-005efa`.
- An initial cherry-pick refused while the sibling guard worker had staged
  changes. Their index was preserved; integration proceeded after their
  commit and an empty-index check. No foreign source changes were absorbed.

### Delivered behavior

- `hooks/claude/agent-do-prose-lint.py` runs canonical
  `agent-do deai lint <saved-file> --register <pack> --json` after Write,
  Edit, and MultiEdit. It lints the full saved file for correct rates,
  code-fence masking, and original file locations.
- Prose extensions: `.md`, `.markdown`, `.txt`, `.rst`. Source code and
  dependency/build directories are skipped. The closest named directory
  selects the register: `drafts`/`essays` -> essay; `email`/`emails` -> email;
  `product-answers`/`product_answers` -> product-answer; otherwise default.
- Findings become advisory PostToolUse `additionalContext`. Every revision
  is checked, clean files are silent, and failures remain explicitly
  unchecked. The hook never rewrites files or emits a blocking decision.
- Output shows six rules with explicit omitted counts and the complete CLI
  command. The linter's three-second timeout fits the five-second host
  registration and kills/reaps its own process group. `AGENT_DO_PROSE_LINT=0`
  disables the hook.
- `install.sh` includes matching registration, wrapper, and uninstall
  entries. `test.sh` includes the focused suite. `docs/INTEGRATION.md`
  documents pack routing, activation, and failure behavior.

### Executed validation

The owning root runner dispatches Python suites as `python3 tests/<suite>.py`.
The following commands ran in the isolated worktree with
`PATH=/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH`:

| Command | Actual result |
| --- | --- |
| `python3 tests/test_prose_lint_hook.py` | 17 passed, 0 failed; final isolated run 7.164s |
| `python3 tests/test_deai.py` | 28 passed, 0 failed; 3.763s, before the sibling guard integration |
| `python3 tests/test_install_specs.py` | 5 passed, 0 failed |
| `python3 tests/test_quantity_write_check.py` | All 13 cases passed |
| `bash -n install.sh test.sh` | Exit 0; shell syntax check |
| `git diff --check` and `git diff --cached --check` | Exit 0; no whitespace errors |

After integration into primary `main`, the hook suite executed again against
the sibling's integrated deai code: **17 passed, 0 failed, 6.940s**. Fixtures
exercise real deai CLI calls, saved-file Edit behavior, clean revisions,
register selection, code exclusions, relative and quoted paths, malformed
host input, unavailable files, failure injection, bounded output, and the
installer's actual settings serializer. The serializer test executes only
the pure function and writes no wrappers or host configuration.

These are executed CLI/unit regressions, not compiled app-hosted tests.
No app was launched, installed, or screenshotted; no live host session was
spawned. The root all-tools suite was intentionally not run under the
focused-suite constraint. The normal staged secret scan and pre-commit
file-size gate passed for the source commit. Nothing was pushed and no PR
was created.

### Remaining acceptance

Installed-host acceptance is tracked separately as **mn-0e3716**, owner Erik:
`.handoff/mn-0e3716-field-check-observe-mn-005efa-prose-feedback-in-claude.md`.
It requires a coordinated, permitted hook installation and live Claude
Write/Edit check. This text-only hook has no screenshot or visual gate.
Per the repository closing rule, the build item can close on its verified
synthetic receipts and trailer commit. Installed activation is not claimed.

Lessons logged: 3 (new) | Decisions logged: 0 (new).
Lessons: `les-3c21a6`, `les-0e6384`, `les-317ec7`.

Seal this updated handoff with `agent-do manna handoff seal mn-005efa`, then
mark done through `agent-do manna done mn-005efa`. Commit the sealed receipts
and owned board changes with the same Manna trailer.
