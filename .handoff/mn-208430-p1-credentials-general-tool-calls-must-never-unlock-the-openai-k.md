---
workflow: 2
manna: mn-208430
track: null
source: Erik request in Codex session 01a19d92-c373-7de1-b5eb-926992e5e1b1, 2026-11-03
base_commit: 4227aed0a551631cf4acecb03b1b839565777862
scope: 'P1 credentials: general tool calls must never unlock the OpenAI key'
inputs:
- Erik request in Codex session 01a19d92-c373-7de1-b5eb-926992e5e1b1, 2026-11-03
binding: sha256:86e2b40cfca51241795992e7af46b903510819e1920ab5c0063b023c19f5aa28
---

# Handoff: P1 credentials: general tool calls must never unlock the OpenAI key

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-208430
```

## Scope

P1 credentials: general tool calls must never unlock the OpenAI key

## Inputs

- Erik request in Codex session 01a19d92-c373-7de1-b5eb-926992e5e1b1, 2026-11-03

## Work order

Routine Manna, Obsidian, help, status, and automatic credential resolution must not retrieve OPENAI_API_KEY or open Keychain prompts. Only a named explicit OpenAI credential read may prompt, once; denial must return failure without retries. Keep other credential behavior and the existing protected Keychain item intact. Verify with synthetic credentials and focused local tests; no paid API calls.

## Repo

`/Users/erik/Custom-Coding/agent-do`

## Project memory

The compact command exceeded the documented bound; this is a literal bounded excerpt of `agent-do zpc patterns`.

```text
# Patterns

No patterns yet. Run `agent-do zpc harvest` after accumulating 3+ lessons with shared tags.

## testing
- A background daemon must detach every inherited pipe as well as its process group or synchronous callers can hang.
- Interpreter choice is part of the test environment: dependency tests use the virtualenv, but macOS framework integration uses host Python.
- ZPC project selection is working-directory based; isolated tests must change cwd instead of inventing a path flag.
- Derived discovery artifacts must be generated from the canonical registry and tested for complete set equality.
- Validation commands must use the dependency-owning environment, while platform-framework tests may intentionally use the host interpreter.

## hooks
<!-- zpc:auto -->
- Never pipe captured JSON through echo in zsh; use printf %s. A reproducible failure across two versions is still not evidence the code is wrong when both runs share one harness
- two independent tests for any side-system: does Erik have to remember it exists (fail = adopt into agent-do or delete), and does the wrapper machinery act on a property the content actually has (methods don't rot)
- A red test only blocks a merge after it fails without the change too — reproduce on clean base before blaming the PR, and check the process tree before calling a slow test slow
- A gate that nags must derive its evidence from the agent's own actions, never from ambient state it did not cause - and when it must fall back to ambient state, the advisory has to say its evidence is weak
- For any hook-fed identity, the payload names the session; inherited env is a hazard, not a source

## manna
<!-- zpc:auto -->
[remaining project patterns omitted to keep this work order bounded]
```

## Mission

Remove implicit OpenAI Keychain requests from routine tool activity. Preserve the protected credential and deliberate named reads. This is a repair to the existing credential domain, not a new tool or provider.

## Owned paths

- `agent-do`
- `bin/intent-router`
- `lib/creds-helper.sh`
- `tools/agent-creds`
- `tests/test_creds.py`
- `README.md`
- `CHANGELOG.md`
- This generated handoff.

Non-owned neighbors: `registry.yaml`, `lib/psql_keychain_store.py`, `tools/agent-manna/`, other handoffs and other workers' changes. No changes to global shell files or Keychain permissions in this lane.

## Ground truth (verified 2026-11-03)

- `agent-do:142`: the dispatcher previously loaded every tool-declared credential before invoking any verb, including help.
- `bin/intent-router:107`: the alternate router independently preloaded credentials through explicit `creds get --reveal` subprocesses.
- `lib/creds-helper.sh:72`: macOS secret retrieval uses `security find-generic-password -w`; metadata-only probes omit `-w` and `-g`.
- `tools/agent-creds`: status/source/value lookups previously repeated secret reads. Presence metadata now remains separate from authorization to use a key.
- `test.sh:147`: `python3 tests/test_creds.py` is the focused credential validation command. The repository `.venv/bin` supplies the dependencies and supported Python version for the contract checks.
- The user's actual OpenAI key remains in the existing protected Keychain item. No provider calls or secret-value output are authorized by this repair.

## Integration contract

- `OPENAI_API_KEY` is excluded from both automatic tool credential loaders.
- macOS generic helper reads of this key refuse unless the named creds command explicitly requests secret retrieval.
- `creds get OPENAI_API_KEY --reveal` and `creds export OPENAI_API_KEY` perform one secret lookup. A denial returns failure immediately, with no internal retry or fallback.
- macOS status/source/check operations inspect attributes, never secret data.
- Bulk `creds export --tool ...` refuses an implicit OpenAI key export before retrieving any values.
- Other automatic credential loading and explicitly supplied environment values remain supported.

## Executed verification receipts

1. `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY PATH="$PWD/.venv/bin:$PATH" python3 tests/test_creds.py`: PASS, `credential tests passed`. Includes production Manna/Obsidian help dispatch with a synthetic Keychain, local tool state/help, metadata checks, implicit-helper refusal, explicit get/export, a single denied lookup without retry, bulk refusal, other-key regression, and the intent-router path.
2. `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY PATH="$PWD/.venv/bin:$PATH" python3 tests/test_routing_contracts.py`: PASS, `routing contracts tests passed`.
3. `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY python3 tests/test_health_probes.py`: PASS, `health probe tests passed`.
4. `PATH="$PWD/.venv/bin:$PATH" agent-do harness contracts validate`: PASS, 103/103 tools declared, zero errors and zero warnings; bounds gate also passed. Existing inventoried nongated bounds were reported by the validator.
5. `bash -n agent-do lib/creds-helper.sh tools/agent-creds`: PASS.
6. `git diff --check` restricted to owned paths: PASS.
7. `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY agent-do creds get OPENAI_API_KEY --source`: PASS, actual protected item returned `store` immediately using metadata only. No key was revealed and no prompt was requested.

Initial system-Python contract attempts failed because Python 3.15 lacked PyYAML and removed `SourceFileLoader.load_module`. Rerunning those checks in the already installed repository virtual environment passed; no dependency or runtime was installed or changed.

## Out of scope

Session-specific native prompt identity, arbitrary direct calls to macOS `security`, credentials other than the OpenAI-specific read gate, and clearing keys already inherited by old processes. Already queued dialogs belong to processes started before the repair. No paid API validation, other workers' changes, pushes, or pull requests.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-208430`.
4. Commit with `Manna: mn-208430` and run `agent-do manna done mn-208430` only after the work is verified.
