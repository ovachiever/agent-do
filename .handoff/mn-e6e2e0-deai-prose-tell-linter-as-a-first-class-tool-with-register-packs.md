---
workflow: 2
manna: mn-e6e2e0
track: null
source: null
base_commit: 0d42ea467b9f57e356e1fb80e0f15ae71e42f9d1
scope: 'deai: prose-tell linter as a first-class tool with register packs'
inputs: []
binding: sha256:dd0f128e79799b3d66fc10f66c44de38dfffe6779e01a2363ab6b92718ddf51a
---

# Handoff: deai: prose-tell linter as a first-class tool with register packs

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-e6e2e0
```

## Scope

deai: prose-tell linter as a first-class tool with register packs

## Inputs

- None declared.

## Work order

Erik-approved 2026-09-13 (the de-AIer global hookup, option B — the keystone the hook and guard call). Migrate the canonical rulebook from substack-writings (scripts/lint-ai-speak.py + voice/ai-speak-lexicon.md, ceilings measured on Erik's 120k-word certified corpus) into an agent-do tool: agent-deai lint <file> [--register essay|email|default|product-answer]. Register packs are the design center — essay pack strict; default pack must NOT flag literal technical usage (structural, robust, architecture in code docs) or it cries wolf and dies; each pack carries its own ceilings and whitelists with provenance. Contracts gate stays green; substack-writings keeps a thin wrapper or migrates its draft gate to call this. New tells keep arriving from Erik's ear (three in three days: tour-guide, costume, wink) — design for cheap rule addition with a measured-ceiling requirement (no bare literals).

### Delivery and verification (2026-09-18)

The scoped implementation is verified. The first claim succeeded for
`codex-01a0b62545397b13`. The original normalized binding was verified against
both the canonical Manna row and the requested
`sha256:0ec382bff8f40b6333a4f36cf1850405d0059d3d68c710e5c5f1d6d416802033`.
The starting agent-do commit was `70252358f99256c7ab5a03719c43b0db4906dcda`.

- New domain: prose lint, exposed through `agent-do deai lint`, `packs`,
  `measure`, and `validate`. No other registered tool owned this domain.
- Canonical rules and four register packs live under `tools/agent-deai/`.
  There are 107 rules: 47 migrated bans, 46 word ceilings, 12 constructions,
  and the two existing essay house bans structural and architecture, omitted
  by the old script. Default, email, and product-answer explicitly permit
  ambiguous literal technical words. The strict essay pack retains house policy.
- Every statistical ceiling resolves to a source measurement, pattern, and
  denominator. The original 110,977-word baseline and later 120,102-word
  baseline stay distinct. Each pack discloses that its ceilings are inherited;
  independent email/product-answer calibration is not claimed.
- `measure` returns counts, exact denominator, pattern, date, and file hashes.
  Adding a rate rule needs data and measured evidence, not an engine edit.
  Validation rejects missing evidence, changed patterns, and bare ceilings.
- Lint has complete JSON results and original line/column locations, preserves
  input files, excludes declared Markdown nonprose, normalizes curly
  apostrophes, and uses a stable Poisson tail calculation. Exit codes are
  0 clean, 1 findings, 2 input/configuration error.
- The Substack script delegates to the real CLI's essay pack and retains the
  word-hunt `TIER3` import and optional advisory feed. Its verified local commit
  is `61a1054e74efd1092566a2bb3476ecbc5814f6ce`, with `Manna: mn-e6e2e0`.
  Source migration is pinned to Substack commit
  `71c1c20b768dfbaa921fdcedf6b2620959dd1c98` and exact file hashes in `rules.json`.
- Registry discovery, generated tool reference, the root test runner, and tool
  counts are updated. The complete discovery catalog is 39,536 characters:
  optional command-list spaces were removed without dropping information.
  The index test's stale GitHub help heading now matches committed production.

Executed focused validation, all final runs successful:

| Working directory | Command | Actual result |
| --- | --- | --- |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_deai.py` | 28 tests passed |
| substack-writings | `python3 scripts/test-lint-ai-speak.py` | 6 real-CLI integration tests passed |
| substack-writings | `python3 voice/word_hunt/test_word_hunt.py` | 24 tests passed |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_contracts_gate.py` | suite passed |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_v11_routing.py` | suite passed |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" bash tests/test_index_generation.sh` | passed |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" agent-do harness contracts validate --json` | 104/104 tools declared, zero missing, errors, warnings; bounds errors zero |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" agent-do harness contracts drift --tool deai --json` | no phantom or undeclared verbs |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" agent-do harness bounds drift --tool deai --json` | no findings; role coverage passes |
| agent-do | `agent-do deai validate` | 107 rules and 4 packs valid |
| agent-do | `agent-do find deai` and `AGENT_DO_SUGGEST_AI=off agent-do suggest 'lint an essay for prose tells'` | discovers deai and selects lint |
| agent-do | `PATH="$PWD/.venv/bin:$PATH" bin/gen-tools-doc --check` | no generated-doc drift |
| both repos | `git diff --check` | clean |

Compile-only checks: `python3 -m py_compile` on the new engine/entrypoint/tests,
`lib/registry.py`, and the Substack wrapper/tests; `bash -n test.sh
tests/test_index_generation.sh`. These are syntax checks, separate from the
executed tests above. There is no app-hosted test component.

A read-only comparison ran both engines over all 10 current `drafts/*.md`
files (including `covers.md`). Both leave the same eight clean. The already
flagged son essay additionally raises the existing architecture house ban.
The cover file's three em-dash occurrences are retained in one grouped finding.
No draft was edited.

Initial integration failures were resolved, not skipped: the new catalog
entry exceeded the existing size gate, and the index assertion still named
GitHub's previous help heading. Final suites pass. Test logs, initial/final
contract receipts, and the draft comparison are in `.dev/mn-e6e2e0/`.

No full-root suite was run, per the focused-only instruction. No app launch,
installation, screenshot, or live session spawn occurred. Live/visual
acceptance is not applicable to this offline CLI lane; its consumer checks
execute the real command path. No push or pull request was made. Other workers'
board rows, generated handoff changes, and untracked assets were preserved.

Lessons logged: 9 (new) | Decisions logged: 1 (new).
Needed next: no remaining feature acceptance. Non-essay calibration remains
explicitly inherited evidence, not a claim of newly measured register rates.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-e6e2e0`.
4. Commit with `Manna: mn-e6e2e0` and run `agent-do manna done mn-e6e2e0` only after the work is verified.
