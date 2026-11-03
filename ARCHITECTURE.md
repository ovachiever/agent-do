# agent-do Architecture

## Overview

agent-do is a universal automation layer for AI coding agents. One bash dispatcher fronts 95 registered tools and five cross-cutting layers:

1. **Structured CLI API**: direct tool invocation, no LLM in the path
2. **Contracts layer**: machine-readable per-verb safety declarations, validated and audited
3. **Natural language mode**: LLM-routed intent resolution for humans, with cached route memory
4. **Credential resolution**: secure-store and env-var loading driven by registry metadata
5. **Internal model roles**: capability-driven model selection for agent-do's own LLM calls
6. **Discovery, nudges, and hooks**: task suggestions, project-scoped ranking, and an ambient Claude Code / Codex hook loop

## Routing Flow

```
                          agent-do <arg>
                               │
               ┌───────────────┼───────────────┐
               │               │               │
         Structured API   Natural Language   Offline
         is_tool()?       -n / --natural     --offline
               │               │               │
               │         ┌─────┴─────┐    bin/pattern-matcher
               │         │  3-tier   │    (registry routing +
               │         │ fallback: │     regex + keywords)
               │         │ 1. cache  │
               │         │ 2. fuzzy  │
               │         │ 3. LLM    │
               │         └─────┬─────┘
               └───────────────┼───────────────┘
                               │
                               ▼
                      credential preload
                               │
                               ▼
                       tools/agent-<name>
```

### Mode Selection (agent-do main script)

The bash entry point first consumes at most one `+live(...)` runtime modifier (explicit approval for live desktop/browser control, exported via `lib/live.sh`), then switches on the next argument:

| First arg | Mode | Path |
|-----------|------|------|
| Known tool name | Structured API | `exec_tool()` → `tools/agent-<name>` |
| `suggest` / `find` | Discovery | `bin/suggest` (optional AI rerank via `lib/ai_router.py`) |
| `notify` | Root notification contract | `bin/notify` + `lib/notify.py` |
| `nudges` | Hook telemetry | `bin/nudges` |
| `bootstrap` | Project setup | `bin/bootstrap` |
| `--status` / `--health` | State and readiness | `bin/status`, `bin/health` |
| `-n` / `--natural` | Natural language | `bin/intent-router` |
| `--json "intent"` | Natural language, JSON envelope | `bin/intent-router --json` |
| `--offline` | Offline NL | `bin/pattern-matcher` |
| `--dry-run` / `--how` | Preview / explain | `bin/intent-router --dry-run` / `--explain` |
| `--raw <tool>` | Explicit direct execution | `exec_tool()` bypassing NL routing |

Every structured execution is wrapped in telemetry (`lib/telemetry.py:record_tool_call` / `record_tool_result`) unless `AGENT_DO_TELEMETRY_SUPPRESS=1`.

### Credential Resolution

Before running a tool, the dispatcher loads any secret env vars the registry declares for it (`credentials:` block) from:

1. the current process environment
2. the OS secure store via `tools/agent-creds` (`lib/creds-helper.sh`)

`bin/intent-router` and `bin/health` read the same registry metadata, so structured execution, natural-language execution, and readiness checks agree on what a tool needs.

### Natural Language Fallback Chain

`bin/intent-router` tries three strategies in order:

1. **SQLite route memory** (`lib/cache.py:check_cache`): exact match on the normalized intent, keyed `project_scope::intent`, preferring project-scoped rows
2. **Weighted fuzzy match** (`lib/cache.py:fuzzy_match`): Jaccard word overlap (threshold 0.6) plus a project-scope bonus, success-rate bonus, and failure penalty from recorded route outcomes
3. **LLM call**: `lib/ai_router.py:llm_call("fast", ...)` with the registry catalog and session state in context

Successful LLM routes are cached; every execution then feeds `note_route_outcome`, so the router learns which route actually works in the current repo. If the LLM call errors, the router retries fuzzy matching at a lower threshold (0.4) before giving up. Route source labels (`cache` / `fuzzy` / `registry` / `llm`) travel with each outcome record.

After the route resolves (and strictly after cache writes, so safety data is never persisted and replayed stale), the router annotates the result with the verb's contract beats and attributes, logs a telemetry event when a read-leaning intent lands on a write-shaped route, and applies the destructive gate described under Contracts below.

### Discovery AI

`bin/suggest` is registry-first: it builds candidate tools and commands from `registry.yaml` routing metadata, then can optionally ask the configured fast model role to choose the best first command from those candidates. The model cannot invent tools or shell pipelines; if the call is unavailable or returns an unsafe command, `suggest` falls back to deterministic local matching. `AGENT_DO_SUGGEST_AI=auto|on|off` controls the AI path.

### Offline Pattern Matching

`bin/pattern-matcher` needs no API key. It tries cached fuzzy matches, then shared registry routing metadata (`match_prompt_tools`), then legacy regex patterns, then keyword matching. Each resolved route gets the same contract annotation and destructive gate as the LLM path, expressed through the clarification mechanism (exit 2).

## Tool Resolution

### Shell Runtime Invariant

`agent-do`, `install.sh`, `bin/health`, and `test.sh` source
`lib/bash-runtime.sh` before using the repository's modern Bash surface. The
bootstrap remains parseable by macOS Bash 3.2, but execution requires GNU Bash
4.4 or newer. An old shell is replaced with a verified supported interpreter,
then a private directory containing only a `bash` symlink is prepended to
`PATH`. Every `#!/usr/bin/env bash` child uses the same runtime without
reordering Python, GitHub, or other caller-provided shims. Missing or invalid
runtimes fail before dispatch.

Tools live in `tools/agent-*`. The dispatcher (`resolve_tool_exec()`) checks in order:

1. `tools/agent-<name>/agent-<name>` (directory with nested executable, e.g. agent-browse)
2. `tools/agent-<name>` (standalone executable)
3. `agent-<name>` on `$PATH`, only when `<name>` is declared in the merged registry

Most tools are standalone bash scripts. Some are directory-based with Python, Node.js, or Rust backends. `--list` auto-discovers by filesystem scan of `tools/agent-*`.

## Key Components

```
agent-do                    # Main entry (bash): mode selection + tool dispatch
├── bin/
│   ├── intent-router       # NL router (Python): cache → fuzzy → LLM, contract-aware
│   ├── pattern-matcher     # Offline router (Python): registry routing + regex + keywords
│   ├── suggest             # Discovery CLI: task/project → likely tools, optional AI rerank
│   ├── notify              # Root notification contract: routing, aliases, rules
│   ├── nudges              # Local telemetry summary for hook nudges
│   ├── bootstrap           # Stateful-tool bootstrap recommender/executor
│   ├── gen-index           # Generated discovery index from registry.yaml
│   ├── health              # Per-tool dependency and credential checker
│   └── status              # Session status display
├── lib/
│   ├── registry.py         # Registry loader, routing helpers, contract validation
│   ├── contracts.py        # Lexicon-driven proposal engine + gate + safety surface
│   ├── contracts_drift.py  # Registry-vs---help drift detection
│   ├── contracts_audit.py  # Bounded behavioral audit of the read surface
│   ├── contracts-lexicon.yaml          # Canonical verb → beat/attribute rules (hand-written)
│   ├── contracts-lexicon-learned.yaml  # Agent-derived classifications (hand lexicon wins)
│   ├── models.py           # Internal model roles: resolution, capabilities, doctor
│   ├── ai_router.py        # llm_call over model roles; JSON helpers for suggest/hooks
│   ├── cache.py            # Project-aware route memory + fuzzy matching (SQLite)
│   ├── state.py            # Session state CRUD (~/.agent-do/state.yaml)
│   ├── telemetry.py        # JSONL telemetry for nudges, routes, tool calls
│   ├── bash-runtime.sh     # Bash 3.2-safe selector enforcing GNU Bash 4.4+
│   ├── snapshot.sh         # Shared JSON snapshot helpers for bash tools
│   ├── json-output.sh      # Shared --json flag support for bash tools
│   ├── retry.sh            # Shared API retry/backoff for curl-based tools
│   ├── live/ + live.sh     # +live(...) runtime gating for desktop/browser control
│   └── capture/            # Shared capture pipeline (browse + unbrowse)
├── hooks/
│   ├── claude/             # Canonical Claude Code hooks (SessionStart through SessionEnd)
│   └── codex/              # Canonical Codex hooks + Stop quality gate
├── tools/agent-*           # 102 tools (standalone scripts + directory-based tools)
├── models.yaml             # Internal model roles: chains, capabilities, retired list
├── registry.yaml           # Master tool catalog with contracts
└── test.sh                 # Test suite (gate inventory below)
```

### Registry (registry.yaml)

The master catalog defines every tool with:

- `description`: what the tool does
- `capabilities`: list of actions it supports
- `commands`: subcommands with descriptions (a curated subset for some tools)
- `examples`: intent-to-command mappings (used by the LLM router and pattern matcher)
- `routing`: optional discovery metadata (keywords, prompt patterns, raw CLI equivalents, readiness hints, project signals, recommended entrypoints)
- `credentials`: secret env vars resolvable from env or secure storage (`required` / `optional` / `one_of`)
- `concurrency`: `read` | `write` | `mixed`, validated against the contracts write surface
- `contracts`: required; maps each command verb to its five-beat roles plus per-verb attributes

### Registry Loading Order (lib/registry.py)

Registries merge with higher priority overwriting lower:

1. `~/.agent-do/registry.yaml` (user overrides, highest priority)
2. `./registry.yaml` (bundled)
3. `~/.agent-do/plugins/*.yaml` (plugin extensions, lowest priority)

`load_registry()` loads them in reverse order so later (higher-priority) entries win per tool.

## Contracts Layer

The five-beat mental model (Connect → Snapshot → Interact → Verify → Save) is machine-readable. All 102 tools declare `contracts:` blocks (`./agent-do harness contracts validate` prints `Tools: 102 Declared: 102` with zero errors and zero warnings). Snapshot/verify verbs are reads; connect/interact/save verbs are writes. Seven orthogonal attributes cover the shapes beats cannot express (`lib/registry.py:CONTRACT_ATTRIBUTES`):

| Attribute | Meaning |
|-----------|---------|
| `destructive` | irreversible data loss; confirm before auto-running |
| `long_running` | daemon/stream/session verb; may never return |
| `polymorphic` | beat decided by payload or flag at call time (sql, query) |
| `composite` | one call performs several beats internally (ensure, doctor) |
| `sensitive` | emits or persists secret material |
| `passthrough` | arbitrary-code escape hatch (shell/eval); belongs to no beat |
| `own_state` | writes confined to the tool's own cache/state; parallel-safe |

Only `passthrough` and `long_running` may stand alone without beat membership.

### The pipeline, end to end

**1. Lexicon** (`lib/contracts-lexicon.yaml`). The canonical verb → beat/attribute mapping: exact verbs, single-wildcard patterns, and per-tool `overrides:`. `lib/contracts-lexicon-learned.yaml` holds agent-derived classifications with confidence and evidence; `lib/contracts.py:load_lexicon` merges it underneath, and the hand lexicon always wins. Rule resolution per verb: override → exact → first matching pattern; anything unresolved lands in the exceptions report for human review. A gate test rejects duplicate YAML keys in either file.

**2. Propose** (`agent-do harness contracts propose [--tool X] [--out FILE] [--json]`). Applies the lexicon mechanically to each tool's commands map (extracting `a|b|c` subcommand tokens from descriptions when the bare verb does not classify), preserves already-declared blocks verbatim, and renders the reviewable inventory. The inventory is a regenerable build product, never hand-edited: to change a classification, change the lexicon and regenerate.

**3. Gate** (`agent-do harness contracts validate`, enforced by `tests/test_contracts_gate.py` in `./test.sh` and CI). Rules, all in `lib/registry.py:validate_tool_contracts`:

- unknown beats and unknown attributes are errors; the vocabulary is closed
- every contract verb must match a declared command; multi-word verbs ("embed status") match by first token (`_contract_command_exists`)
- a verb under multiple beats warns unless marked `polymorphic` or `composite`
- an attribute on a verb with no beat warns unless the attribute is `passthrough` or `long_running`
- concurrency must agree with the write surface: `concurrency: read` with world-write verbs is an error (`own_state` writes are exempt); `write`/`mixed` with zero write verbs warns as overdeclared
- full coverage: every registry tool must declare contracts and warnings must be zero (the grandfather baseline emptied on 2026-06-11 and was deleted; `lib/contracts.py:validate_gate` still honors a baseline file if one ever reappears, and fails on stale entries so the ratchet only tightens)

**4. Drift** (`agent-do harness contracts drift [--tool X]`, `lib/contracts_drift.py`). Diffs registry command promises against each tool's live `--help` output. Two asymmetric channels: `declared_only` (registry promises a verb the help lacks) fails `./test.sh`; `help_only` is advisory only, because registry command maps are intentionally curated subsets. Help that yields no parseable commands is reported as a runtime-dependency error, not N phantom verbs.

**5. Behavioral audit** (`agent-do harness contracts audit [--include-network] [--schema-check] [--out F] [--notify]`, `lib/contracts_audit.py`). Bounded live probe of the declared read surface: only verbs whose beat union is a subset of {snapshot, verify}, with no attributes, needing no arguments. Credentialed tools sit behind `--include-network` (default off). Outcomes are tri-state: `ok` (ran clean; `--json` output parsed), `clean-skip` (refused with a structured or explanatory error: the contract held, the host didn't), `fail` (hung, crashed, emitted nothing, or lied about `--json`). `--schema-check` calls each ok JSON-object verb twice and flags top-level key drift as a warning, never a failure. `--install-schedule [weekly|daily]` writes a launchd agent (weekly = Monday 09:00) that runs the audit and notifies on failures only; CI also runs it nightly (see Test/CI surface).

**6. Safety surface for orchestrators** (`agent-do harness contracts surface --json`). Aggregates the merged registry into machine-readable buckets: `read_only` (beat union ⊆ {snapshot, verify}), `write`, plus one bucket per attribute, each a list of `{tool, verb}` objects. This is the scheduling contract: read_only verbs parallelize freely; write verbs serialize; attribute buckets drive confirmation and guarding policy.

**7. Routing consumers.** `build_registry_context` emits a compact per-tool `Safety:` line (write verbs plus destructive/sensitive/passthrough flags) into the LLM router catalog. `bin/intent-router` and `bin/pattern-matcher` annotate resolved routes with the verb's beats and attributes, after cache writes so route memory never persists safety data. Natural-language routes to `destructive` or `sensitive` verbs ask first via exit 2 unless `AGENT_DO_AUTO_DESTRUCTIVE=1`; the structured API is never gated. `bin/suggest`'s AI rerank picks only from registry candidates, and the PreToolUse hook reads the same attributes to emit an advisory safety heads-up when an agent invokes a destructive or sensitive agent-do verb directly.

No tool merges without a contracts declaration: the gate runs in `./test.sh` and in the `contracts-gate` GitHub workflow on every push and pull request.

### Bounds: the second property the machine holds (`lib/bounds.py`)

Contracts hold "which beats does this verb perform" across 102 tools without anyone remembering to. Bounds hold the next one: **a command that caps its output declares where the cap came from.** Same registry, same gate, same run — a doc line fixes nothing, and this repo measured what instructions are worth (518 lessons, zero structural readers).

**Declaration** (`bounds:` beside `contracts:`), keyed by verb, or `*` for caps in shared library code that belong to no single verb. Four sources, and the source picks which enforcement applies:

| `source` | `ref` is | Drift enforces | Audit enforces |
|----------|----------|----------------|----------------|
| `registry` | an authority key | the shipped literal equals it exactly — a copy that differs is stale by definition | output carries its total |
| `derived` | an expression over authority keys | the literal equals what the expression computes; the factor in it is the explanation | output carries its total |
| `measured` | a census expression | **no literal may ship at all** — a counted quantity is true only now | output carries its total |
| `none` | nothing (a ref here is an error) | nothing: no ceiling is claimed | output carries its total, and any truncation marker carries magnitude |

**Detection is evidence-based, never prose-based.** A command is bounding because a numeric literal sits in a bounding position in its implementation, at a file and line the gate prints — not because its description sounded like it returns a lot of rows. `BOUND_PARAMETERS` maps ~30 curated names to units; six syntaxes recognize the literal (kwarg/object assignment including quoted shell locals, shell `${X:-N}` defaults, `|| N` / `?? N` fallbacks, SQL `LIMIT N`, argparse `default=N`, `head -n` / `.slice(0, N)`). Comment and help-text lines are classified `doc` and never gated: a bound quoted in help documents a cap, it is not one. Test files are excluded — a bound asserted in a test is the test's fixture. Verb attribution walks up to the nearest enclosing definition or `case` arm and returns `None` rather than guessing, because a wrong attribution sends a reviewer to the wrong verb.

**Gate reach equals authority reach** (`mark_gate_eligible`). The gate demands a receipt only for units the authority currently holds a ceiling in — `{unit for entry in authority_entries()}`, computed every run, listed nowhere. Demanding a citation the authority cannot supply would push the next agent toward inventing one, which is the defect, not the fix. Today that is `tokens` and `records`: 15 sites gate, and 164 caps in `rows`/`levels` are **inventoried on every run, never suppressed** — there is no grandfather file, nothing to empty, and nothing to forget. When lane-27's authority learns a unit, every site in it gates the same day with no change to this code.

**What the gate cannot reach, it names.** The declaration surface is a tool's registry entry, so caps in `lib/` and `bin/` (8 today, including `lib/ai_router.py:DEFAULT_MAX_TOKENS`) belong to no tool and have nowhere to declare. They are counted and printed on every gate run rather than skipped: naming what the gate cannot reach is the difference between a boundary and a blind spot.

**Drift** (`agent-do harness bounds drift [--tool X]`). Resolves each declared `ref` (longest-match key substitution, then arithmetic with no names, calls, or attribute access) and compares. The only tolerances in the module, both derived rather than chosen:

- **Integer rounding: 0.5.** Rounding a real to an integer moves it by at most 0.5, so 0.5 is the unique tolerance that admits exactly the rounding a correct expression performs and no second number beyond it.
- **The authority delivery floor: `min(max_tokens / max_input_tokens)` over every model record**, today 0.128 from `anthropic/claude-opus-4-8`. Every model record pairs a capacity with a delivery ceiling; that pair is a published statement, by the people who built the system, about how small one delivery may be relative to the space it is drawn from. A bound that *claims a ceiling governs it* (`registry` or `derived`) and lands below the tightest such ratio in the authority is smaller than any delivery ceiling any provider considered worth publishing, so its stated factor is doing no work and the number came from somewhere other than the ceiling it cites. That is the `inject at 6000 chars against a 200k-token window` shape. The number is **read, never written**: recomputed each run, stored nowhere, and it moves when the authority moves. It applies only to bounds asserting a ceiling relationship — `source: none` claims none, so there is no ratio to judge and the audit holds it to totals instead. With no record publishing both numbers there is no floor at all, because a checker with no evidence must not invent one.

Same command checks **router coverage**: every model a `roles.*.chain` can select must have an authority record (mn-b7cb18). Reachability is exactly what the chains declare — a model no chain names cannot be selected, so nothing is owed for it — which keeps the check inside what the registry can prove and leaves the data fix with `models.yaml`'s maintainer.

**Audit** (`agent-do harness bounds audit [--tool X]`). Probes declared bounding verbs and grades what comes back: a payload returning rows with no total fails, because a caller cannot tell a complete set from a capped one; a payload declaring `has_more`/`truncated` with no total fails as the bare fact of a cut; text output fails when a truncation marker carries no magnitude (`[truncated: 30 of 197 shown]` passes, `... output truncated` does not). Probes reach only verbs the registry already declares read-only, through `quantities._read_only_verb` — the same safety source the census uses, so a probe can never reach a write. Like `contracts audit`, the live run is on demand and its fixtures are what `./test.sh` enforces.

**Outward scan** (`agent-do harness bounds scan <path> [--out FILE]`). The same detector, aimed at any project, because the pollution is already shipped and there is no map of it. Outward the context signal is a precondition rather than corroboration: a literal counts only in a file that references an LLM, DB, or HTTP client, since nothing else establishes that the number bounds a fetched set. The signal is file-scoped because imports are file-scoped in every language it reads. Each finding carries the published ceiling when the file names a model the authority knows, and names the missing authority record when it does not — the honest half of the same refusal `quantity lookup` makes. Report-only: it never rewrites a file.

## Internal Model Roles

agent-do's own LLM calls (intent routing, suggest rerank, hook routing) never hardcode a model. `models.yaml` is the source of truth; `lib/models.py` resolves it; `lib/ai_router.py:llm_call(role, ...)` executes it. Generated templates and user-selected engines are out of scope by design.

- **Roles**: `fast`, `vision`, `deep`. Each declares a provider-qualified candidate `chain` (Anthropic and OpenAI models interleaved), an env override (`AGENT_DO_MODEL_FAST` / `_VISION` / `_DEEP`; `fast` also honors the older `AGENT_DO_AI_MODEL`), and a role-level `generation` policy (effort + thinking mode).
- **Resolution** (`models.resolve(role)`): env override first, then the chain in order, skipping anything on the `retired` list. `models.candidates(role)` returns the full usable chain.
- **Capability records**: per-model entries pin provider, endpoint (`messages` vs `responses`), modalities, token ceilings, and capability maps (thinking types, effort values). `generation_params` maps the role policy onto what the model actually advertises, so an unsupported effort or thinking type is silently dropped rather than sent. Requested `max_tokens` is capped to the model's recorded ceiling.
- **Cross-provider fallback**: `llm_call` filters the chain to providers whose SDK and API key are both present, then walks it, crossing providers only on model-not-found (HTTP 404). Every fallback is reported to stderr and recorded as a `model_fallback` telemetry event. Other errors propagate; a 404 chain exhaustion raises.
- **`agent-do models doctor`**: fetches each provider's complete model listing (Anthropic paginated to the end; pagination that claims more without a cursor fails loud), then classifies configured models: present in the listing = available; missing models get an individual probe where 404 = retired, 403 = unavailable-to-these-credentials (never auto-retired), anything else = error. `--fix` persists only verified retirements and Anthropic-published capability refreshes, atomically. `agent-do models list` and `agent-do models resolve <role>` expose the resolved state.

## Quantity Authority (lib/quantities.py, `harness quantity` / `harness census`)

Agents invent numbers because measuring costs a tool call and guessing costs nothing. This layer inverts that trade: one place to read a published number from, one place to measure a present one, so typing a literal is the more expensive option. Two kinds, and the distinction is load-bearing.

- **LOOKED_UP** — a static, versioned ceiling somebody else published (a model's `max_tokens`, an API's page limit). Lives in `models.yaml` and is answered with the record it came from, so a caller can cite it.
- **MEASURED** — how many exist *right now* (lines, directory entries, rows behind a read command). Computed on demand, never cached into a literal, because it is true only now.

**Key grammar.** `<namespace>.<subject>.<quantity>`, e.g. `anthropic.claude-sonnet-5.max_tokens`. Parsed from the ends, never by splitting on every dot: subjects carry dots of their own (`openai.gpt-5.6-sol.max_tokens`), while namespace and quantity never do. Consumers reference a key; they never copy the value into code.

**Two storage shapes in `models.yaml`, because they have two maintainers.** `models:` records are rewritten wholesale by `agent-do models doctor` from the provider's `/v1/models` response, so they carry no per-field provenance — the record is the citation and the doctor is the maintainer. `limits:` entries (page ceilings, quotas) are hand-maintained and each carries `value` + `unit` + `source` + `verified` **in data**, not in a comment: `models doctor --fix` round-trips the file through a YAML dumper and comments do not survive that.

**Output shape (pinned; downstream lanes code against it).**

Every `--json` payload also carries `ok` and `tool:"harness"`; successes add `command` and a timestamp (`generated_at` for lookups, `measured_at` for a census).

| Verb | Bare stdout | `--json` payload |
|------|-------------|------------------|
| `quantity lookup <key>` | the number alone, newline-terminated (shell-substitutable) | `key`, `value`, `unit` (may be `null`), `kind:"looked_up"`, `provenance{file,record,field,maintained_by[,source,verified]}` |
| `quantity keys [--prefix P]` | one key per line, sorted | `prefix`, `total`, `keys[]` — each entry `{key,value,unit,kind,provenance}` |
| `census lines` | the total alone | `target`, `total`, `unit:"lines"`, `kind:"measured"`, `exact:true`, `method:"newline-count"`, `method_detail`, `final_line_unterminated`, `bytes_scanned` |
| `census entries` | the total alone | …`unit:"entries"`, `method:"dir-scan"`, `glob`, `recursive` |
| `census rows` | the total alone | …`unit:"rows"`, `method:"json-array"`, `verb`, `json_path` |
| any refusal | nothing on stdout | `{ok:false, exact:false, refused:true, reason, detail}` — **no `total` key at all** |
| any caller error | nothing on stdout | `{ok:false, error}` — **no `value` or `total` key at all** |

**Exit codes.** `0` answered exactly · `1` the request could not run as asked (unknown or malformed key, unreadable target, non-read or undeclared verb, a `--path` that is not there) · `2` it ran but no exact count exists (payload not JSON, no array, ambiguous array, paginated, command failed, timed out). Refused and crashed must never look alike, and neither ever carries a number. Absence is the contract: a consumer that reads `payload["value"]` or `payload["total"]` on a failure gets a `KeyError`, not a silent `None`.

**Census methods**, each self-reported in `method` (stable id) and `method_detail` (prose): `newline-count` counts `0x0A` bytes to match `wc -l` exactly and reports an unterminated final line in `final_line_unterminated` rather than silently adding it; `dir-scan` enumerates glob matches (`--recursive` for the whole tree); `json-array` runs an agent-do read command through argv (never a shell) and counts one JSON array.

**`census rows` refuses more often than it answers, by design.** It runs only verbs the registry already declares read-only (beat union ⊆ `{snapshot, verify}`) — safety comes from the contracts layer, not a list kept alongside it, and an *undeclared* verb is refused because unknown safety is not safe. It then refuses when the payload is not JSON, contains no array, contains more than one array (name it with `--path`), or shows any sign of being one page of a larger set: `has_more`/`truncated`/`is_truncated` true, a `next_page`/`next_cursor`/`next_page_token`/`next_offset` present, or a declared `limit` exactly equal to the row count — at the page boundary a complete count and a capped one are the same number, which is precisely the failure this layer exists to prevent.

**Consumers, not just producers.** `lib/ai_router.py:_cap_tokens` clamps requested output to the model's recorded ceiling, and `lib/models.py:fetch_provider_models` reads the Anthropic list-endpoint page size from `limits.anthropic/models_list.page_limit` instead of a literal. Both fail loud on absence: a guessed page size can silently return a truncated listing, and a truncated listing is how `models doctor` would decide a live model was retired.

## Manna Subsystem (tools/agent-manna, Rust)

Git-backed issue tracking with a typed board grammar. Every issue is a **track** (a named grouping with intent), an **item** on a track, or a **dream** (raw intake, exempt from tracking, converted or closed with a written reason). Commits that advance an item cite it with a `Manna: mn-xxxxxx` trailer. The board is the only backlog.

### Storage and locking (src/store.rs)

- `.manna/issues.jsonl` (issue records), `.manna/sessions.jsonl` (session event log), `.manna/board.yaml` (independent strict or legacy identity), `.manna/workflow.yaml` (strict workflow version and canonical handoff root), and `.manna/handoff-order.yaml` (first-class ordered item priority)
- `.manna/transactions/` is an ignored write-ahead journal. Each intent is HMAC-authenticated by a private key outside the worktree, installed with atomic no-clobber semantics, and bound to the canonical project root, filename, complete rows, canonical handoff, archive path, and document payload
- `legacy-board-migration.yaml` is the one whole-board journal: it binds exact before and after rows plus every generated handoff and scaffold file, then publishes strict identity last
- `.handoff/README.md`, `.handoff/<NN>[b<MM>]-mn-xxxxxx-<slug>.md`, and `.handoff/.archive/` are durable Git state, not scratch space
- Every mutation takes the board-wide `fs2` lock across re-read, validation, state change, temp write, fsync, and atomic rename. File locks alone are insufficient because the JSONL rewrite replaces the inode
- Malformed lines are skipped with a stderr warning, never fatal
- Output is YAML by default (`success:` envelope), JSON with `--json`. Exit codes: 0 success, 1 user error, 2 system error (I/O, lock)

### Schema (src/issue.rs)

`id` (`mn-` + 6 lowercase hex), `title` (1-500 chars), `status`, `description`, timestamps, `blocked_by`, `claimed_by`/`claimed_at`, `claim_token_hash`, plus the typed fields:

- `type`: `track` | `item` (default, omitted on disk so v1 rows round-trip byte-identical) | `dream`
- `track`: edge to a `type: track` issue; tracks cannot themselves carry a track edge (tracks don't nest)
- `source`: where the issue came from (vault note, conversation, commit)
- `prompt`: repository-relative `.handoff/` path paired with an actionable item on strict boards; legacy boards may retain older absolute pointers
- `handoff_digest`: `sha256:<64 lowercase hex>` binding the canonical handoff document, with its self-referential binding field normalized, to the row

### Workflow scaffold (src/workflow.rs)

`manna init` classifies the board once in `.manna/board.yaml`. New or empty
boards are strict; pre-workflow nonempty boards are explicitly legacy. Strict
boards install workflow version 2, `.manna/handoff-order.yaml`, and
`.handoff/README.md`, and narrowly unignore both YAML authorities, both JSONL
files, and `.handoff/`.
Removing `workflow.yaml` cannot downgrade the board because identity is stored
separately; init restores it. Existing version-2 digests are monotonic markers:
restoration or a forged version downgrade validates them and never re-enters
the binding-creating migration path. The runtime lock and transaction journal
stay ignored.

An identityless board is routed by its rows: empty means `manna init`, while
nonempty means `manna migrate`. `bootstrap --recommend` uses the same boundary
and SessionStart surfaces `legacy board: run agent-do manna migrate` before a
normal write reaches the fail-closed gate. A pending authenticated board-init
journal stays on the init recovery path.

After workflow convergence, both `manna init` and `manna migrate` converge the
tracked `.manna/federation.yaml` identity under the same board lock and its
separate authenticated federation journal. Command success is withheld until
both phases are valid. A stop between phases leaves a complete local workflow
that the next invocation safely enrolls without changing issue or handoff
bytes. Bootstrap treats a missing federation manifest as incomplete setup, and
the global inbox receives the same identity before its first dream is written.

`manna migrate` is the explicit bridge for a nonempty legacy board, including
a board left behind a premature strict identity. Under one board lock, its
authenticated transaction generates sealed handoffs for all active items,
records done rows as grandfathered history, records tracks and dreams as
exempt, and releases ownership state that has no valid token proof. Recovery
accepts only the exact before or exact after board. Strict identity is the
commit point, and a completed migration replays as a no-op. Ordinary strict
commands cannot enter this path or use it to reseal a damaged pair.

On strict boards, creating an item writes a transaction intent, generates
`.handoff/<id>-<slug>.md`, and installs the bound row under the board lock. A
crash at any point leaves the authenticated intent for idempotent completion by
the next Manna command. Recovery verifies the scaffold first, accepts only an
exact complete-row replay, and cannot write outside `.handoff/`. Delete and item conversion archive the live handoff before
clearing its pointer. Tracks and dreams never receive live handoffs.

Ordered presentation is a derived build product over board truth. The ordered
ID list in `.manna/handoff-order.yaml` is the priority authority; every
dependency remains an explicit `blocked_by` edge. `manna sync` assigns dense,
board-wide fixed-width priorities with a two-digit minimum, expanding the
whole plan to three digits at 100 items, and derives one same-width blocker
marker from the highest-numbered still-open blocker. It repoints rows and
regenerates `.handoff/README.md` from the same snapshot. A bare name is the
launch signal. `manna order <id>
<position>` changes the ordered list and performs that sync immediately.
Claimed handoffs are immovable and keep their current numbers reserved until
release. The `Rename` pair transaction stages all moves before installing any
destination, so swaps and longer cycles cannot clobber files; exact before and
after boards, priority YAML, README bytes, and all source/destination paths are
HMAC-bound for idempotent crash recovery. Content bindings exclude paths, so a
native rename preserves the seal without authorizing any document edit.
Completed pairs leave the launch plan on the next sync: their sealed handoffs
return to unnumbered paths, while the board and Git history retain provenance.

### Portable federation

Cross-repository relations sit beside the issue state machine in the tracked
`.manna/federation.yaml`. They are not fields on `Issue`. Every canonical board
receives a public identity (`mb-` plus 32 lowercase hex characters), while
relations remain optional. An outbound edge names a local source, a closed
relation kind, and a portable
`manna://<board_id>/<issue_id>` target. Normal clones and worktrees retain the
ID as replicas. `manna federation fork --reason <text>` is the only identity
split: it journals exact bytes, archives the inherited manifest, generates a
new ID, and clears active relations.

The authority boundary is asymmetric by design:

1. The source repository's manifest is the only durable authority for its
   outbound declaration.
2. The machine-local serve registry is a resolver cache. It can explain a
   declaration, but cannot create, remove, or become the only copy of one.
3. Every claim, block, done, handoff, ownership, landed-evidence, lint, and
   reconcile decision remains local to the board that owns the issue.
4. Missing counterpart boards degrade to `unavailable` and never invalidate
   the source board.

`relate` and `unrelate` share the board-wide lock with issue writes, re-read the
strict board and manifest, and require the exact owner proof when a source is
actively claimed or blocked. Open and done sources accept authenticated
lineage declarations without rewriting issue JSONL or handoff bytes. Manifest
init, relation changes, and fork use a project-bound HMAC journal with exact
before and after bytes. A fork additionally binds the archive path and bytes.

`manna relations` is a local declaration read. `--resolve` joins only the
private serve registry and returns:

- `resolved`: every registered replica agrees on the exact target row bytes;
- `unavailable`: no registered board carries the target board ID;
- `missing`: an unambiguous registered board lacks the issue ID;
- `ambiguous`: cached identity disagrees with live identity, a candidate is
  unreadable, or replicas disagree on target presence or exact row bytes.

`--check` exits nonzero for `missing` and `ambiguous`, but not `unavailable`.
Counterpart edges separately render `confirmed`, `one_way`, `unavailable`, or
`ambiguous` reciprocity. Two reciprocal declarations remain two autonomous
writes. No cross-board mutation is atomic or implied.

Lint and reconcile inspect only tracked local authority: manifest shape,
deterministic order, local source existence, same-board and duplicate refusal,
Git tracking, archive validity, and transaction convergence. Remote state does
not enter `landed_open`, `dead_claim`, `blocker_desync`, prompt pairing, or
handoff presentation. Serve adds derived relations to issue drawers without
changing NOW, NEXT, WAITING, NEEDS DECISION, or DRIFT placement.

Handoff frontmatter binds workflow version, item, track, source, base commit,
scope, inputs, and a SHA-256 of the canonical document with the binding field
normalized. The same digest lives in
the issue. `manna handoff seal <id>` is the only path that authorizes an edit.
Metadata updates first verify the old seal, and config restoration never
recomputes one.
`claim` validates Git visibility, every path component (no symlinks), structured
metadata, Claim section, and both digests after taking the board lock. Loose
comments and claim-like strings have no authority. Broken continuity exits 2
with no claim.

### The human window (`manna serve`)

`agent-do manna serve` is the read cockpit for humans: one daemon on
a stable loopback port, picked free on first run and kept in `$AGENT_DO_HOME/manna/serve/config.json` (Python, `tools/agent-manna/serve/`, beside the Rust core)
renders every registered board at `/` — effective counts per board, each number
linking to the exact section it counts — and each project at `/<name>` with
three sheets (inbox · board · coordination), an inspector, a ⌘K jump/ask bar,
and a status strip whose `debug ▸` opens live reconcile findings and the
daemon's own numbers. Rows carry model-written one-line digests and each item a
collapsible summary (fast role, hash-keyed cache under
`$AGENT_DO_HOME/manna/serve/digests/`, outside the board, title as fallback);
`manna state --json` resolves the board through the serve registry and attaches
only hash-current cached values to its repeated rows. The core never generates
or writes presentation state. Any human-facing client can therefore render the
same cached words, while agents ignore these optional presentation fields and
continue to reason from durable board facts. Serve itself only schedules cache
gaps after derivation. The bar's Enter asks the deep role a question answered
from board rows only,
citing ids. Two-clock cache: board+git state re-derives on file signature
(that is where live `reconcile --json` and the trailer-commit log run);
coord presence refreshes on a ten-second cadence with a content digest so
streams push only on real change; both pages paint instantly from cheap reads
and backfill. Loopback-only (Host and Origin checked), agents never read from
it — `context|list|show` remain the contract — and `claim_token_hash` never
leaves the board directory. Writes exist only as reconcile-by-click: inbox
asks carry verb buttons (`close`, `promote`/`delete`, `sync`, `apply`) that
POST one action each, guarded by a per-process page token, and the daemon runs
exactly that manna verb under its own pinned identity
(`$AGENT_DO_HOME/manna/serve/identity.json`, mode 600); manna's refusals
surface verbatim. The page never edits a file.

### State machine

- `claim` requires status `open` and no claimant; validation and transition are one locked operation, so concurrent claimers have exactly one winner
- Once claimed, mutations require both the exact `claimed_by` session and its bearer-token proof. The board stores only `claim_token_hash`, so the visible owner string cannot impersonate the claim
- `done` closes on receipts, strongest authority first. `evidence`: a commit in the last 500 carrying `Manna: <id>` that touched a path outside `.manna/` and `.handoff/` closes the item from any live status over any claimant (the claim stays on the row as history; the commits ride in `evidence`). `operator`: the human's terminal identity closes any live item. `owner`: otherwise the claim-holder's proof plus `in_progress`, as before. An unclaimed dream closes through its own transition. Handoff pairing and shadow-workflow drift are observed after the close and returned as `warnings`; they never hold it (mn-4061c8)
- `claim` resolves the id before demanding an identity, so the wrong checkout answers with the board that holds the id (from the estate registry) instead of an identity error; the item's own handoff pointer is the exact gate, and shadow-workflow findings ride along as `warnings`
- `abandon` requires the owner plus an active claim (`in_progress` or `blocked`); it returns to `open` when clear or remains `blocked` while dependencies remain
- `block`/`unblock` maintain `blocked_by` and derive `blocked` status. `done` removes the completed ID from every dependent in the same locked, atomic board write and reports newly unblocked IDs as `released`. A dependent with no blockers returns to `open`, or `in_progress` if already claimed; other blockers keep it `blocked`, and completed dependents stay `done`. `reconcile` retains `blocker_desync` as the backstop for deleted blockers, older binaries, and hand-edited boards; `reconcile --fix` repairs those through the existing state machine
- `update --status` is rejected. Status moves only through lifecycle verbs
- Validation invariants: `in_progress` requires `claimed_by`; `claimed_by`, `claimed_at`, and `claim_token_hash` come and go together; handoff digests use the pinned SHA-256 shape

### Lint (`manna lint`)

Board-grammar gate: findings exit 1, clean exits 0. Rules:

- per-issue `validate()` invariants
- `untracked_item`: items need a track once the board has any tracks (young boards don't nag)
- `dangling_track`: track edges must point at existing track rows
- `dream_status`: dreams only carry `open` or `done`
- `prompt_file`: a prompt pointer on a non-done issue must resolve to a file
- `workflow_tracking`: every existing canonical board file must be present in
  the Git index; a visible but untracked file reports `git-tracked: no`
- strict workflow rules: the scaffold exists, each active item has a canonical
  `.handoff/` pointer, the canonical document matches its authoritative digest,
  no handoff-shaped symlink aliases a root, no shadow workflow exists, and no
  canonical handoff is orphaned
- ordered presentation rules: board priority is normalized, each filename
  matches its derived priority and launch gate, and the generated index matches
  the board. A live-claim hold is reported until release rather than renamed

### Reconcile (`manna reconcile [--fix] [--write-drift] [--dream-age-days N]`)

Drift detection between the board and reality. Informational findings are
advisory. `workflow_sprawl`, `orphan_handoff`, `prompt_pairing`,
`handoff_presentation`, and `--fix` failures exit nonzero because they change
which work order is authoritative or whether its filename is a safe launch
signal.
Checks run in a fixed order, and a check that cannot run records a `skipped`
finding with the reason:

1. `landed_open`: issues cited by `Manna:` trailers in the last 500 commits but not yet done (report-only; merge judgment stays human)
2. `dead_claim`: claims held by provably-gone sessions. A `--fix` release is compare-and-swap against the inspected complete row, so stale evidence cannot release a newer claim
3. `blocker_desync`: `blocked` status out of sync with `blocked_by` (all blockers done or missing, or an empty list)
4. `stale_dream`: open dreams strictly older than the threshold (default 14 days)
5. `dangling_track`: track edges to missing or non-track issues
6. `doc_reference`: `mn-` ids mentioned in `.handoff/`, `.dev/`, `.zpc/`, and the per-project Claude memory directory that do not exist on this board (files ≤ 1MB, symlinks skipped, deduplicated per file+id)
7. `prompt_pairing`, in both directions. Forward: an issue's prompt pointer resolves to a file that never mentions the issue's id. Reverse: every board id that a work-order file *claims* (a line containing `manna claim <id>`, any invocation prefix; bare id mentions are data, not claims) must belong to an issue whose prompt pointer resolves back to that same file. Strict boards scan `.handoff/**/*.md`; legacy boards retain the `.dev/session-prompts/` scan. A missing directory is a successful empty scan, and foreign-board ids are ignored
8. `handoff_presentation`: priority state, numbered filename, launch-gate marker, or generated README index differs from the board-derived plan. The proposed repair is `agent-do manna sync`; live claimed files remain held until release
9. `workflow_sprawl` on strict boards: any live claim-bearing Markdown appears outside `.handoff/`. The walk is what Git would carry (`git ls-files` tracked plus untracked-not-ignored; a plain filesystem walk outside Git), so ignored state such as `.zpc/.state`, `.dev/`, and dependency stores is never a work order. No symlink is followed; a handoff-shaped one (named like a handoff, a legacy root name, or resolving into `.handoff/`) is reported without an item. Advisory in `claim` and `done`
10. `orphan_handoff`: a structured Manna work order under `.handoff/` has no live actionable row, or does not match that row's pointer. Freeform research and continuation Markdown is not a work order; `.handoff/.archive/` is excluded intentionally

The prompt pointer itself comes from the `prompt` field, or as a blessed interim convention, a description whose first line is `PROMPT: <path>`.

`--fix` applies only the safe subset through the existing state machine: releasing dead claims and removing resolved blockers. `--write-drift` serializes the findings to `.manna/drift.yaml` (atomic temp + rename, `generated_at` quoted so YAML 1.1 parsers keep it a string, `session` from the explicit or host-derived Manna identity). The SessionEnd hook writes this file; the next SessionStart greets with it.

### Managed lifecycle (`manna identity | coordinator | managed | submit | accept | assess`, `done --assessment`)

Coordinator-owned closure for items whose completion is not the worker's to declare. A worker submits; an authorized coordinator verifies integration and acceptance and closes, or releases the assignment, without the worker's session ever being resumed or impersonated. Storage is three sidecars beside the board, written under the same board lock and never touching `issues.jsonl` rows (older binaries keep working and strip nothing; an unmanaged board never acquires the files): `.manna/coordinators.json` (grants), `.manna/managed.json` (per-item records), `.manna/lifecycle.jsonl` (append-only audit that survives any restart). All three are durable Git state, tracked like the board.

- **Authority is explicit and proof-bound.** `manna identity` prints a session's public label and its ownership proof (the SHA-256 token digest claims already store; the token never prints). Only the operator (a human terminal) runs `coordinator grant --session <id> --proof <sha256> --item/--track ... --reason`; the grant binds label + proof + scope. A coord role, a pulse row, a claimed label, or a worker's secret is never authority, and a grant cannot be self-issued. `coordinator revoke` keeps the record. `Authority::resolve` yields `operator` > `coordinator` > `owner` > `none`.
- **Submission is not acceptance.** `managed require <id> --check <name>...` (coordinator) names the checks closure needs and starts attempt 1. The claim-holder runs `submit <id> --report <file|-> [--revision <ref>]`; the report lands on the record verbatim under a fresh submission id and the item stays `in_progress`. `managed correct --reason` sends it back; a sent-back submission cannot be accepted until it is resubmitted.
- **Acceptance binds to the exact submission and pins the integration target.** `accept <id> --check <name> --target <ref> --evidence <text>` resolves the reference without fetch or checkout, records its kind (`head`, `local_branch`, `remote_tracking`, `tag`, `commit`), pins the SHA on first acceptance, refuses a different SHA unless `--repin`, and records the submission id it reviewed. An acceptance counts only for the same attempt, the pinned target, and the submission currently on the record: a resubmission needs a fresh verdict, a superseded attempt's acceptances never count, and a pre-binding acceptance that names no submission never counts.
- **Every mutation is one locked, recoverable transaction.** The row and the grants are reloaded under the board lock, authority re-derived against that row (a revoked grant or changed scope refuses), the expected owner and attempt compared, and only then does anything move: the transaction's intent (its complete outcome: the record after, the audit line, a `txn` id) is written to `.manna/managed-intent.json` first, then the sidecar, then the audit line, then the intent is retired. A failure after the intent is durable leaves the item refusing every mutation with the transaction named until `managed recover <id>` applies the recorded outcome idempotently (operator, a granted coordinator, or the session that started it). Recovery is itself decided under the board lock: the pending transactions, the board's own pending transaction, and the grants are reloaded there, authority and transaction ownership are re-derived against them, and only the transactions that look authorized are replayed; a grant revoked while recovery waited for the lock refuses with nothing written. `accept` names what the coordinator reviewed (`--submission`, `--attempt`) and refuses under the lock when either moved. Release and abandon write the sidecar's `pending` phase first, then release the row's claim, then mark `released`; a process that dies between leaves an interrupted release that `assess` reports, every other mutation refuses, and the coordinator's next `managed release` completes. The close's audit line is a transaction too: the intent is durable before the row changes, so an unwritable audit leaves the close durable and the audit recoverable; the command then fails (exit 2) with the durable row, the transaction, and `managed recover <id>` named, so no caller reads an incomplete close as clean. A grant or revocation is a board-level transaction (`issue_id: board`): while one is incomplete the grants file is not the truth, so every managed mutation and every further grant or revocation refuses naming it, and only the operator (or the session that started it) finishes it with `managed recover board`, since a coordinator cannot finish the transaction that decides its own authority.
- **Assessment is the one read-only answer, and says where each fact came from.** `assess <id> [--target <ref>] [--deployed <sha>]` reports status, the claimant's liveness as coord classified it with its source and whether that is a verified stop (`dead`/`stopped`; `stale`/`idle` are an aged lease, `unknown` stays unknown), required/accepted/outstanding checks and the superseded acceptances with the reason they no longer count, the caller's authority, the requested vs pinned target, whether the pinned reference name still points at the pinned commit, whether the target is this checkout's HEAD, every commit on any ref carrying the item's trailer classified as `in_target`, `patch_equivalent`, or `elsewhere` (receipts, never acceptance), a deployed revision only when the caller asserts one, an `observations` block naming the source and time of the git and coord reads and marking the sidecar content as recorded claims, incomplete transactions, the blockers, the exact next command, and an `assessment` token: `assess:v2:<requested sha|->:<pinned reference now|->:<hex>` only for a closable verdict, `blocked:v2:<hex>` otherwise. `done --assessment` refuses a blocked or old-format token outright and, for a closable one, recomputes its conditions under the lock (the pinned reference still points where it pointed, a requested target is still the pinned commit and still resolves, the row and acceptance state unchanged).
- **Closure revalidates under the lock.** `done` on a managed item ignores the trailer-evidence path entirely: it needs coordinator/operator/owner authority, a current submission, a pinned target, and every required check accepted for the current attempt at that target. With `--assessment <digest>` the close refuses when any of that moved since the look, re-checked inside the same locked write that releases dependents. `reconcile --fix` refuses `dead_claim` and `landed_open` repairs on managed items and names the coordinator path instead.
- **Release needs a verified stop or a validated isolation.** `managed release <id> --reason` advances the attempt and releases the claim only when coord (read with stale peers included) reports the worker `dead` or `stopped`, or when `--isolated-checkout <path>` names an existing directory inside a git working tree whose toplevel differs from this checkout's. A stale or idle lease, an unknown peer, and a bare path all refuse: an old lease is not death, and a replacement never becomes a second writer in the old files. The superseded worker can no longer submit or close. A worker's own `abandon` ends its attempt in the same locked transaction that releases the row.
- **Adoption is checked, not assumed.** `managed doctor` reports three things apart: command availability (this binary's `managed_lifecycle`; the installed `agent-coord`'s `drop ack`/`drop resolve`/`--action`), hook registration in `~/.claude/settings.json`, and verified behaviour, which exists only when `--probe` ran the managed lifecycle, the drop lifecycle, and the prompt-router hook through the real binaries in a throwaway fixture. `live` is `null` without a probe, never inferred from registration. `manna state` carries a `managed` summary per row for human windows.

### Trailer grammar

A trailer is a commit-body line that is exactly `Manna: <id>` (key case-sensitive, one id per line, multiple lines allowed). `mn-` ids embedded in longer hex runs do not match.

### Dream routing (`manna dream "<spark>" [--track id] [--source ref]`)

Walks up from the current directory to the first `.manna/` board; falls back to the global inbox at `$AGENT_DO_HOME/inbox` (auto-created on first use). The response names the receiving board and notes when it was the inbox.

### Context (`manna context [--max-tokens N]`)

Boards with track rows render a track tree: one section per track, then Untracked (including items whose track edge dangles, so no work line ever vanishes), then Dreams; done items excluded. Zero-track boards keep the by-status render. Output truncates to roughly 4 chars per token against the budget.

## Coord v2 (tools/agent-coord, Python)

Project-local state-and-interrupt broker for parallel agents. State lives under `<git-dir>/agent-do/coord/` (JSON files plus an `events.jsonl` journal, one flock-guarded lock file); outside a git repo it falls back to `$AGENT_DO_HOME/projects/<path-hash>/coord/`.

- **Identity anchoring**: precedence is `AGENT_DO_COORD_SESSION` (pinned by the SessionStart hook from the Claude session id) → thread env vars (`CODEX_THREAD_ID`, `CLAUDE_THREAD_ID`, `CLAUDE_SESSION_ID`, `CLAUDE_AGENT_ID`) → a session UUID minted at first contact, keyed to the anchoring process (tmux pane or host + pid + process start time). A recycled pane therefore never inherits a dead session's identity; the previous occupants of a re-anchored pane are tombstoned dead.
- **Liveness classification**: presence is verified, not assumed. `kill -0` plus a `ps lstart` start-time match distinguishes a live process from a recycled pid. Peers render as `active` (lease current), `idle` (seen within the idle window, default 48h), `dead` (process gone or tombstoned), `stopped` (retired via `stop`/`bye`), or `stale`. `peers --active-only` and `--writers` filter; `stop` and `bye` are Stop-hook-safe lifecycle verbs.
- **Roles and territories**: `role set builder|auditor|researcher|overseer [--mode writer|read-only] --territory <path>...` declares exclusive write domains (builder defaults to writer; the rest to read-only). Overlapping writers generate a contention interrupt on both sides; an auditor on a writer's paths generates a courtesy notice.
- **Structured focus**: goal, phase (`building|gating|watching|quiet|blocked|stopped`), note, `blocking_on`, `last_ship`.
- **Board primitives**: advisory `claims` on paths, `needs` (declared dependencies), `publishes` (produced artifacts), and `drops` (file pointers handed to a peer, role, or anyone; pointers, never content). Interrupts are computed from this state (contention/notice/dependency/novelty), not delivered as chat.
- **Drop lifecycle**: every drop carries a stable `drp-` id, a `kind` (`info`, the default: a delivery, surfaced as a `notice` that never blocks the prompt router; `action` via `drop add --action`: an obligation, surfaced as a `dependency`), a `revision`, a `status` (`open`/`resolved`), per-reader `acks`, and a `history`; a drop written by an older coord is read as open, `info`, revision 1 with a deterministic id and `legacy: true` (age, a pruned owner, or a missing file is an observation, never completion). `drop ack <id>` is per reader and per revision and means "read", never "done": an info drop leaves that reader's interrupts; an action drop stays listed, no longer `new`, with the resolve command in its summary, until resolved. One reader can never hide a broadcast (`any` or a role) from the others. A drop that answers one of the reader's declared needs is a dependency whatever its kind. `drop resolve <id> --reason [--evidence] [--for-everyone]` settles it for every reader (owner or addressed recipient; a broadcast needs the explicit flag) and keeps the record, its original `created_at`, and the journal lines (`drop_add`/`drop_ack`/`drop_resolve` with the drop id). Re-adding changed content bumps the revision, so acknowledged readers see it again and a resolved drop reopens. The interrupt summary labels the note as a dated report (`reported <age> ago, not re-verified`) and names the ack command. Nothing deletes a drop; `drops --all` and `drop history <id>` read the retired ones.
- **Assignment addressing** (mn-ed4353, after the mn-261c29 incident where an approval was dropped to two guessed labels and reached nobody): `drop add <path> --for-item <mn-id> [--action] [--allows … --excludes … --authorized-by …]` addresses *the worker on an item* without copying, shortening, or translating a session id. The binding is the claim proof: `manna claim` stores the claimant's ownership proof as `claim_token_hash`, and `coord touch` (also `whoami`, and first contact of any coord command) asks the manna binary for `manna identity --json` in the worker's own process and records `manna.session` and `manna.proof` on the coord record. A drop for an item reads the canonical board (`manna show --json` from the common git dir's checkout, so a worktree reads the primary board, plus `manna assess --json` for the managed attempt), pins the claimant, proof, attempt, and work-order digest, and resolves the recipient as the one live coord record whose proof equals the row's: equality only, never a label, a prefix, or a first match; two live records of one harness session (a hook pinned to the session id beside a shell deriving from the thread id share `identity_raw`) are one recipient, two live records with different anchors are `ambiguous` and nothing is picked. With no live bound session the drop is written `pending` (`for_agent_id` null, bell not queued) and the worker's next `touch` resolves it, journals `recipient_resolved`, and rings once; a replacement claimant or a revised work order is read from the board at view time and marked `STALE` (`reassigned`, `work-order revised`, `item closed`) rather than forwarded, and the replacement never sees it (its proof differs). An unknown direct `--for` is refused (exit 2, naming the live sessions, roles, and `--for-item`); roles and `any` remain broadcasts. Every drop view carries `delivery`: `recorded`, `recipient` (resolved/pending/ambiguous/unassigned/broadcast with presence), `bell` (queued or why not), `acknowledged` (the exact recipient's ack at the current revision; a broadcast lists readers), `completed` (the resolution), a `stage`, and `stale`; a ledger write or a queued bell is never acknowledgment. The owner's `interrupts` carry an `awaiting` notice for each of its own open action drops that nobody has acknowledged (never blocking). An approval record names the item, work-order digest, `allows`, `excludes`, and `authorized_by` (all required) and states that routing confers no authority and that local implementation approval is not deployment approval; approvals are actions. `worker <mn-id>` answers who the worker is: the exact session with its binding provenance, the board assignment beside the session's declared focus title (with whether the focus predates the claim), liveness evidence (lease, `kill -0`/`ps lstart`, pulse), and open obligations with their stages. No idle-worker resumption or terminal retirement exists: an unreachable worker is shown pending, honestly.
- **Guard**: `guard install` drops a warn-only pre-commit hook that flags staged paths hitting live claims or foreign territories; `guard check` runs the same check ad hoc.
- **History**: `history [peer] [--limit N]` reads the events journal newest-first.
- **Pulse** (`pulse record --from-hook`; `pulse record --session <harness-session-id> --status <working|needs-user|finished|failed|idle|ended> --updated-at <RFC3339> [--activity <note>|--clear-activity]`; `pulse show [peer]`): shared per-session telemetry with latest prompt, current activity, and TodoWrite progress. Harness events and external supervisor verdicts merge through the same flock-guarded store. Explicit writes replace status and observation time, touch activity only when asked, preserve hook-owned prompt/todo/counters, and use an identity-free store path that neither mints caller bookkeeping nor creates or renews the target's presence lease. Repeating the same timestamped verdict is a no-op; concurrent writers are serialized and the last locked write wins for each field it owns. `peers` sorts the six-state pulse attention-first (needs-you > failed > working > present > idle > finished > ended) and renders pulse columns beside separately verified presence. Telemetry is never custody: a pulse row may route attention but is never evidence of what the board records.

## Hooks Architecture

Canonical hooks live in the repo (`hooks/claude/`, `hooks/codex/`); installed hooks under `~/.claude/hooks/` and `~/.codex/hooks/` are thin version-tagged wrappers written by `install.sh` (`WRAPPER_VERSION` 2). Each wrapper resolves the repo root via `AGENT_DO_REPO`, then the `~/.agent-do/install-path` breadcrumb, adds `<repo>/lib/` to `sys.path` for Python hooks, and delegates (bash `exec`, Python `runpy.run_path`). `git pull` on the repo changes hook behavior on the next event with no reinstall. See docs/INTEGRATION.md for registration.

Every Claude hook is advisory: they inject context or run cleanup, and never block.

### SessionStart (`hooks/claude/agent-do-session-start.sh`)

Resolves agent-do (PATH → `~/.local/bin` symlink → breadcrumb → script-relative repo fallback for bare checkouts), then:

- **PATH**: appends an export line to `CLAUDE_ENV_FILE` so every Bash call finds `agent-do`
- **Identity pins**: exports `AGENT_DO_COORD_SESSION` and `CLAUDE_SESSION_ID` into `CLAUDE_ENV_FILE`. Manna derives the private ownership proof from the stable host session id under a mode-0600 machine-local key, so process restarts recover the same authority without storing a bearer token in the board. Cursor's adapter persists its conversation id through the same derivation input. Complete explicit `MANNA_SESSION_ID` plus `MANNA_SESSION_TOKEN` pins still win for scripted lanes
- **Injected context sections**, each independently gated:
  - the tooling reminder (prefer agent-do over raw CLI; discovery commands)
  - project-scoped tooling (`suggest --project`, 3s bound): top likely tools with readiness fixes
  - a bootstrap prompt when `bootstrap --recommend` (3s bound) reports pending setup; legacy boards carry the explicit `legacy board: run agent-do manna migrate` notice. On macOS this defaults to a native dialog that can run `bootstrap --yes` directly and notify with a log, otherwise it becomes a context ask
  - coord context (2s bounds): active interrupts if any exist, else a focus reminder when active peers exist and this agent has no focus
  - the **Manna Board**: gated on `$CWD/.manna` existing; injects `manna context --max-tokens 1500` (2s bound) plus claim/done working instructions
  - the **drift greeting**: if `.manna/drift.yaml` exists and contains findings, its first 30 lines are injected with instructions to reconcile before claiming new work
  - additional gated blocks for always-active skill loading and frontend/zpc project detection (the presence signals are tabulated in docs/INTEGRATION.md)

Subprocess calls run under `bounded_run`, a perl wrapper that sets a process group and SIGKILLs the whole group on alarm expiry, so a wedged spawn degrades to a missing section instead of eating the hook's registered 10s timeout.

Both Claude hooks that read coord (`agent-do-session-start.sh`, `agent-do-prompt-router.py`) pin `AGENT_DO_COORD_SESSION` to the payload's `session_id` for their coord spawns, so they read as the same identity the shell was given through `CLAUDE_ENV_FILE`; a shell acknowledgment therefore quiets the hook (mn-812cd9).

### UserPromptSubmit (`hooks/claude/agent-do-prompt-router.py`)

Classifies each prompt and emits high-confidence context only. Claude Code kills the hook at its registered 5s and discards all output, so the hook works against a 4.2s internal safety line: base stages (registry, coord state, models config) spend their share first, the optional AI call gets what remains capped at 1.75s, and is skipped entirely below 0.9s. With `AGENT_DO_HOOK_AI` on/auto and a key present, the AI path receives the compact full catalog (not a deterministic shortlist) and returns tool suggestions, coord assessments, and context-retrieval pointers; weak matches stay silent. `Coord Focus Required` context is emitted, non-blocking, when active peers exist, this agent has no focus, and the prompt starts workspace work. Deterministic fallbacks (completion-check context, design-quality path) still fire without AI.

### PreToolUse, matcher Bash (`hooks/claude/agent-do-pretooluse-check.py`)

Nudge mode: emits `hookSpecificOutput.additionalContext`; the command always runs. Per-session state (keyed by session id) gates repetition: an observed `agent-do <tool>` invocation is recorded as a demonstration that suppresses future nudges for that tool, and emission frequency decays. The cascade per command:

1. skip-patterns (git, npm, python, localhost curl, and other safe commands); an `agent-do` invocation additionally gets an advisory safety heads-up when the verb is marked `destructive` or `sensitive` in its contract
2. docs-fetch nudge toward `agent-do context`
3. registry-driven hard nudge via `routing.raw_cli_equivalents` (closest replacement command plus readiness fix)
4. legacy friendly-reminder patterns

Every decision (emit or suppress, with reason) lands in telemetry; `agent-do nudges stats` and `agent-do harness nudges effectiveness` summarize it. Block mode (changing the output to `permissionDecision: "deny"`) is a documented opt-in edit, not the default.

### SessionEnd (`hooks/claude/agent-do-coord-stop.sh`)

Presence-gated cleanup, always exit 0. In repos whose git dir already has a coord board, it re-exports `AGENT_DO_COORD_SESSION` from the payload's `session_id` and runs `coord stop --note "session ended"` (5s bound). In repos with `.manna/`, it pins `MANNA_SESSION_ID` the same way and runs `manna reconcile --fix --write-drift --json` (4s bound), discarding the exit code. `--fix` applies only the two repairs the tool itself labels safe (abandon dead claims, unblock resolved blockers); every judgment finding stays a finding for the drift file. The budget arithmetic is deliberate: 5s + 4s stays inside the hook's registered 10s timeout. Claude Code's `Stop` event fires every turn; session retirement belongs on `SessionEnd`, and agent-do registers nothing at `Stop`.

### Codex

`hooks/codex/` carries SessionStart/UserPromptSubmit/PreToolUse equivalents plus an advisory Stop quality gate (`stop-quality-gate.sh` + `.py`) that DPT-scores the active `agent-do browse` page and reports it as `additionalContext`. Codex supports `hookSpecificOutput.additionalContext` on PreToolUse (May 2026 hooks release); it parses but does not enforce deny decisions, so block mode is effectively Claude-only.

Codex does not expose a persistent environment-export channel from SessionStart.
Manna therefore derives a stable ownership proof from `CODEX_THREAD_ID` under
`$AGENT_DO_HOME/manna/session-identity.key`, a mode-0600 machine-local secret.
The board stores only the compact coord-compatible owner label and a digest of
that proof. The raw thread id and key never enter repository state.

## Framework Libraries

**`lib/snapshot.sh`**: JSON snapshot output for bash tools:

```bash
source lib/snapshot.sh
snapshot_begin "tool-name"
snapshot_field "key" "value"
snapshot_json_field "data" '{"nested": true}'
snapshot_end
# → {"tool": "tool-name", "timestamp": "...", "key": "value", "data": {"nested": true}}
```

Values round-trip the full RFC 8259 control range; invalid UTF-8 in one field is replaced without poisoning sibling fields; `AGENT_DO_SNAPSHOT_COMPACT=1` emits single-line JSON.

**`lib/json-output.sh`**: `--json` flag support:

```bash
source lib/json-output.sh
parse_output_format "$@"     # Detects --json
json_success "result"        # {"success": true, "result": "..."}
json_error "message"         # {"success": false, "error": "..."}
json_result '{"key": "v"}'   # Pass-through raw JSON
json_list ...                # JSON array output
```

**`lib/retry.sh`**: shared error recovery for API tools. `api_request METHOD URL [curl args]` retries per error class (429 respects `Retry-After`, 5xx backs off exponentially, network errors retry immediately, max 3 attempts); `with_retry N cmd` wraps arbitrary commands; `stall_detect` guards streaming; `AGENT_DO_PERSISTENT=1` retries 429/5xx indefinitely for CI.

**`lib/capture/`**: shared browse/unbrowse capture pipeline: `CaptureSession` (request/response correlation), `filterEntries` (static/CDN noise removal, dedup), `extractAuth` (auth pattern detection), `generateSkill` (skill package writer → `~/.agent-do/skills/`).

**`lib/state.py`**: session state CRUD in `~/.agent-do/state.yaml`: TUI/REPL sessions, iOS/Android simulator state, Docker containers, SSH connections, tail sessions. The intent router includes this state in LLM context so "my python session" resolves.

**`bin/health`**: verifies each tool exists and `--help` works, checks tool-specific dependencies plus declared credential metadata, and reports OK / WARN (missing dependency) / CONF (needs config or credentials) / MISS (not found).

## Tool Concurrency Classification

Every tool declares `concurrency: read|write|mixed` in `registry.yaml`; the counts in the current registry are 17 read, 17 write, 62 mixed (96 total). The field is a coarse summary validated against the contracts write surface; per-verb truth lives in the contracts blocks, and `harness contracts surface --json` is the machine-readable form orchestrators should consume. Read-only tools parallelize freely; write tools serialize; mixed tools require per-command inspection.

## Exit Codes

| Code | Meaning | When |
|------|---------|------|
| `0` | Success | Command executed successfully |
| `1` | Error | Tool error, missing dependency, invalid arguments, no matching tool |
| `2` | Needs clarification | Natural language and offline modes: ambiguous intent, or a destructive/sensitive route without `AGENT_DO_AUTO_DESTRUCTIVE=1` |

Exit 2 tells the orchestrator to answer the question and retry with `--context "answer"`. Individual tools may define their own conventions (agent-manna uses 2 for system errors; `harness census` uses 2 for a principled refusal to estimate, and `zpc position` for a refused flip); the 0/1/2 contract above is the dispatcher's natural-language surface.

## Test/CI Surface

`./test.sh` runs the whole gate inventory against an isolated `AGENT_DO_HOME`: dispatcher smoke checks (`--help`, `--list`, `--status`, `--health`, `--raw`, `--offline` routes), the Python suites under `tests/` (routing, models, suggest/prompt-hook AI, contracts gate + drift + audit + routing-contracts, coord v1 + v2, auth family, email/sms, browse isolation and session defaults, harness, hooks non-blocking, nudge telemetry, tool regressions, and the service tools), a live `harness contracts drift` run that must come back empty, the manna Rust unit tests (`cargo test`) and its shell integration suite, `lib/snapshot.sh` encoding checks, and a bootstrap end-to-end flow.

GitHub workflows:

- **ci.yml** (push to main, PRs): bash/python syntax sweep, then the full `./test.sh` suite on macOS 14 with GNU Bash 4.4+ shadowed in
- **contracts-gate.yml** (push to main, PRs): `tests/test_contracts_gate.py` plus the harness inventory test; a tool without contracts cannot merge
- **nightly-audit.yml** (daily 08:00 UTC, manual dispatch): `harness contracts audit --schema-check` on macOS, network probing off; any `fail` outcome fails the job, schema drift is surfaced but non-fatal, and the report uploads as an artifact

## Design Principles

1. **Structured > natural language for AI.** Agents call `agent-do ios tap 200 400`, not `agent-do -n "tap the button"`. Natural language is a human convenience layer.
2. **Snapshot = AI vision.** The `snapshot` verb gives agents structured understanding of current state.
3. **Session = memory.** Persistent sessions (database connections, browser state, TUI sessions) give agents context across commands.
4. **Declarations must be checkable.** Contracts are validated in shape (gate), against the help surface (drift), and against live behavior (audit). A safety claim no machine can check is a comment, not a contract.
5. **Tools are composable.** Each tool is standalone, callable directly or via agent-do, with the same interface for AI and humans.

Per-tool depth lives in docs/TOOLS.md; harness integration lives in docs/INTEGRATION.md.
