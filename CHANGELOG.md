# Changelog

## Unreleased

- `coord focus set --phase building` now warns a writer when another active writer is already building in the same checkout, even when their source paths are disjoint. The advisory explains that dirty compile state and build artifacts are checkout-wide, points the joining lane to `agent-do git worktree add <branch>`, preserves the primary-board caveat, remains visible through `coord interrupts` and `status`, and stays silent for lone builders, read-only roles, non-building phases, and `AGENT_DO_COORD_ISOLATION_NUDGE=0`. (mn-6a43ba)
- New tool `agent-substack`: draft and publish Substack essays through the editor's own JSON endpoints (Substack publishes no write API). Converts a Markdown subset — headings, marks, links, lists, blockquotes, fenced code, rules, images with local-file upload — to Substack's ProseMirror document; auth rides the shared agent-browse session (`browse login https://substack.com`, `session save substack --shared`), so no second login exists anywhere. Five beats: `connect` verifies cookies and pins the publication, `snapshot`/`drafts`/`posts`/`get` read, `draft`/`update` write DRAFTS ONLY, `verify` reads the draft back and compares against the receipt or the source file, and every write appends a receipt with the editor URL. `publish` is the one outward-facing verb — destructive+sensitive in its contract, runs only on explicit command, and never emails subscribers unless `--email` is passed. Offline `convert` emits the ProseMirror JSON for inspection; tests drive the full loop against a fixture server, cookies asserted on every request. (mn-386f70)

- `coord pulse record` now accepts a timestamped six-state verdict from an external supervisor under the target harness session ID. An identity-free write path merges into the hook-fed row under the same lock without minting caller bookkeeping or renewing or impersonating the target session, preserves hook-owned prompt/todo/counters, and reports duplicate writes as unchanged. This gives Holy's roster orb and Manna's attention surface one record to read. (mn-86a41b)
- `manna estate --json` exposes every board in the machine registry through the exact `/api/boards` derivation without starting or contacting the serve daemon. Each row carries its root, slug, effective status counts, dreams, decisions, drift timestamp and count, latest update, and coord attention rollup; missing registered roots remain visible. YAML is the human default, JSON is the native-client contract. (mn-7ef12d)
- install.sh installs the Claude wrapper for the touch ledger: the hook was registered in settings.json, listed for Codex, and covered by uninstall, but absent from the wrapper-install list, so clean installs registered a file that never existed and the stop-time quality gate silently fell back to git-status inference (found by Chris). A new test holds registration and wrapper installation coherent so the class dies.
- agent-browse: `ws` 8.19.0 → 8.21.3, clearing two high advisories on the runtime WebSocket dependency (memory disclosure fixed 8.20.1; fragment-flood DoS fixed 8.21.0); 47/47 browse tests pass on the bump (also flagged by Chris).
- The `agent-psql` macOS Keychain helper subprocesses no longer receive raw or hex-encoded passwords through argv or inherited password-holder variables: writes send one bounded add-or-update command to `/usr/bin/security -i -q` over stdin, and framed reads preserve terminal newlines while decoding SecurityTool's binary-password representation. Within `agent-psql`, profile-add URIs reach the private helper only over bounded stdin, with percent-encoded userinfo password bytes decoded exactly. Profile inputs fail closed for non-PostgreSQL URI forms, authorities unsupported by agent-psql's existing hostname/single-port path, and decoded `password` or `sslpassword` query keys; the same checks and size bound apply to legacy profile records. Profile mutations now share a bounded lock and publish explicit credential-requirement metadata, so concurrent updates or an orphaned credential cannot pair a password with the wrong endpoint; the `session-` namespace is reserved to prevent cross-kind credential collisions. On macOS, session and credentialed-profile records publish only after storage succeeds. Existing profile names still require removal before replacement, and the historical non-macOS masked-profile no-op remains unchanged. Remaining non-Keychain parsing subprocesses are tracked separately.
- `creds list` on macOS no longer reports an empty store when Keychain items exist. Enumeration now parses each `dump-keychain` record (acct lives *before* svce; a `grep -A4` window after svce never saw the account) and errors if `security dump-keychain` itself fails instead of treating a failed query as "No stored secrets." Every remaining silent exit-1 in `creds list` is gone: an empty Linux store is a valid outcome again (grep's zero-match exit no longer kills the pipeline under pipefail), unknown platforms and Windows-without-powershell refuse loudly on stderr, and a mktemp failure explains itself.
- Cockpit pages never wait on reconcile: live drift computes in a background thread per board (reconcile serializes on the board lock; measured 40s+ of convoy on a busy 242-row board), the page ships the last finished findings with the drift file's age beside them, and the stream pushes the fresh result when it lands. A board's full state on the worst measured board: 47s → 1.6s.
- The daemon watches its own source and restarts in place when the code on disk changes; previously only a CLI touch noticed, and an untouched daemon served day-old code indefinitely (observed).
- Column fitting measures real pixels with the header label as a floor (inline labels get a box; a stretched header span reports its column width, which ratcheted columns wider on every fit). Fixes clipped AGE cells, the sliver horizontal scrollbar, empty columns collapsing under their labels, and the ragged STATE column on sparse boards.
- The coordination sheet paints from the fast state too, with presence included whenever the daemon's bundle is warm.
- Cockpit columns behave on boards with long track names: track and state columns clamp with ellipsis (full text in the tooltip), leading `[TRACK]`-style markers are stripped from display, and a boundary drag between two fixed columns transfers width across that boundary so the divider you grab is the divider that moves. Long blocker lists no longer crush the digest column.
- The cockpit resolves coord state through the coord tool script instead of the agent-do dispatcher, cutting each presence refresh from 1.5-2s (worse under load) to ~0.4s; the two serve HTTP tests that flaked under machine load pass again.
- `manna serve` no longer assumes port 7777: the first run asks the OS for a free port and keeps it in `$AGENT_DO_HOME/manna/serve/config.json`, so printed URLs stay stable without colliding with whatever another machine already runs there; `--port` and `MANNA_SERVE_PORT` override one invocation. README screenshots retaken at full resolution and linked to their originals so a click zooms.
- README rewritten as one essay for the human reader (the workshop, the vessel, the dharma of receipts): every institution presented with its evidence, no agent commands beyond the install, logo plus cockpit and coordination screenshots placed in the sections they depict. Chosen from fifteen candidates across three clean-room rounds.
- `manna serve`: a `recent` chip on the board sheet renders every entry (items, dreams, done, blocked) as one flat list sorted by last activity with an age column, linkable at `#board/recent`; the inspector now shows `filed` (created) beside `touched` (updated) for every item.
- UserPromptSubmit hooks no longer time out under load: the prompt router invokes the coord tool script directly instead of paying the dispatcher's per-call interpreter tax twice, defers the provider SDK import until an AI routing call actually happens, and the four UserPromptSubmit hook ceilings rise 5s→10s in the registration spec (lesson les-2a750a).
- zpc-trigger telemetry carries the trigger value again (prompt/command/path) through telemetry's central policy — stable hash plus redacted 160-char excerpt — restoring nudge debuggability; ruled by Erik 2026-08-26, recorded as dec-ef3bbd.
- DPT: remaining canon false-positives retired across four perception layers, with controlled fixtures under `tools/agent-dpt/fixtures/`. (mn-55530d)
- Stop-time quality gates now read a per-session touch ledger (`lib/touch_ledger.py`, PostToolUse-fed) instead of inferring agent action from `git status`, so another lane's edits or human-dropped files no longer trigger false "design work without a browser" advisories; Claude and Codex hooks ship wired, Codex stop gate updated to match.

## v1.5 (2026-08-25)

The Agentic Work OS release. Everything since v1.4, grouped by program.

### The cockpit (manna serve)

- One local daemon at `127.0.0.1:7777` renders every registered board: an estate index whose counts link to what they count, and per-board sheets for inbox, board, and coordination, live over server-sent events. Loopback-only with Host and Origin checks (DNS-rebinding refused). Agents keep the command line; the page is a window, never a source. (mn-613088, mn-1e71e2)
- Every item row carries a one-line digest written by the fast model (hash-keyed cache, byte-bounded batches, measured per-call cap, title as fallback); the inspector holds a collapsible summary under 450 characters; an ask bar answers questions from the board's own rows on the deep role and cites the item ids it used.
- Reconcile by click: drift appears in the inbox as asks whose verbs are buttons, each click running exactly one manna verb under the daemon's own authenticated identity. Refusals print verbatim; delete asks twice; nothing edits a file directly.
- Coordination is on the page: claimed rows carry the claimant's live pulse, a per-board sheet shows who is present, what they hold, and claim contention, and the estate index shows needs-you / working / here per board.
- Hardening: provider exceptions never reach a client (fixed error codes only), the daemon restarts itself when its source changes on disk, and no personal names ship in the code (decision markers are a machine setting).

### Work boards (manna)

- One transactional spine: board identity pinned in `board.yaml`, status moved only by lifecycle verbs under a board-wide mutation lock, HMAC-authenticated write-ahead journals, and `lint` / `reconcile` / `claim` failing closed on broken pairs or shadow work orders anywhere in the repository.
- `init` is crash-atomic and byte-stable on re-run; `migrate` converges legacy and mixed boards (multiple rounds, sealed content preserved, external projects untouched); legacy boards are detected and pointed at migration before their first failed write.
- Ordered handoffs: `.manna/handoff-order.yaml` owns priority, filenames derive from it (past 99 items without lying), a generated README indexes the plan, and sealed content bindings refuse edits without an explicit reseal.
- Ownership is restart-durable: Claude, Cursor, and Codex sessions re-derive the same claim proof under a machine-local key after a restart, and an orphaned claim whose work provably landed is released by evidence, not by request.
- Dreams are visible and inert: they appear in every listing, and `claim` refuses them (exit 2, nothing written) until the owner converts one; `dream --description` carries the idea's substance.
- Portable federation: every board carries a tracked identity that survives cloning, items can declare typed relations across repositories (counterpart, depends_on, informed_by, supersedes), a missing counterpart resolves to "unavailable," and no relation changes another board's state. Boards auto-enroll.

### Memory (zpc)

- Positions: a verdict is filed with its falsifier, and a flip that names no new evidence is refused; the refusal spawns a clean-context `counsel` run (a fresh model that never saw the argument) whose verdict lands beside the position.
- Memory can change its mind: lessons carry identity, `retract` appends a correction with a receipt (nothing edited or deleted), and delivery is anti-dogma: entries arrive as dated claims a live observation outranks, with exposure-ranked re-litigation of what memory repeats most.
- Corrections cost one keystroke (`w` too wordy, `d` deeper, `s` subtraction) and are mined into receipted preference lessons that travel to every session via `inject --preferences`; `inject --compact` fits memory into a lane prompt.
- Machine-wide lessons earn entry (rule + why + `when` trigger, or exit 2) and fire on their trigger during the session instead of flooding session start.
- Every read leaves a receipt in an access log, and the store walk is bounded to the project and owner (a committed symlink could previously read arbitrary files).

### Numbers from an authority (harness)

- A quantity is a claim about the world: `harness quantity` answers bounding numbers (token ceilings, page sizes, retry counts) from published, provenanced records, and an unknown key exits nonzero instead of guessing.
- A command that caps its output declares where the cap came from (`bounds:` beside `contracts:`), and the build fails on a bare bounding literal the authority could have answered; a PostToolUse hook flags one at the moment it is written.
- The fix that motivated it: zpc's delivery bound was derived from the authority instead of typed, ending a bug where 197 of 197 memory claims were silently dropped.

### Coordination (coord)

- Hook-fed pulse: every harness event (prompt, tool call, turn end) updates a per-session pulse (working / needs-you / failed / finished, and what it last touched) with no model call; `peers` sorts attention-first so whoever needs you sits on top.
- Contention interrupts name the remedy (split ownership before isolating), a declared branch mismatch names worktree isolation as mandatory, and a worktree binds its memory to the checkout that outlives it.

### The estate brief (brief)

- New tool: joins `gh` inbox rows, manna items (trailers and title ids), live coord sessions, and last commits into ranked threads whose reasons ride with the score. Verifies that a trailer's commits actually touched the claimed work (trailer is not landed), degrades every dead source to an annotation carrying its reason, and self-calibrates its GitHub sweep budget from its last measured duration.

### GitHub (gh)

- `inbox` derives waiting-on-us from maintainer role, not just review-request ceremony, sweeps a declared portfolio, and reports every unswept repo loudly.
- Stage awareness: every inbox row knows whose move it is. The sweep runs as two concurrent GraphQL documents: 30 seconds down to 3.7.

### New tools

- `sentry` (error tracking), `betterstack` and `cronitor` (uptime and scheduled-job monitoring), all with declared contracts and `--json` throughout.
- `ci triage`: deterministic classification of a failed GitHub Actions run into five causes, secrets scrubbed from quoted logs, validated 24 for 24 against two weeks of real failures.

### Runtimes and the installer

- Cursor adapter hooks translate Cursor's hook JSON into the canonical Claude hooks and back; `install.sh --cursor` installs them atomically (a failed upgrade leaves the previous working install in place). Cursor sessions persist their conversation id, so board ownership survives a restart.
- Codex session start embeds project memory directly instead of inviting the agent to go read it.
- The installer registers its own hooks (an unregistered hook silently never fires), session start runs under 4 seconds, and every turn opens with a stamp of the real current time and the gap since the last one.
- The launcher, installer, health checker, and test runner enforce GNU Bash 4.4+ (macOS ships 3.2) with a clean promotion to Homebrew Bash.

### Fixed

- dpt visual scoring made honest: a deliberately broken page scores broken, and the scorer's limits are written down beside it.
- Interactive browser logins update the canonical saved-session name instead of forking it.
- The zpc trigger hook never logs the raw command; auto-harvest detaches so a hook timeout cannot kill it mid-write.
- Hook annotations defer imports so hooks load under whichever Python the harness picks.

## v1.4 (2026-07-22)

### TL;DR
- The board can no longer lie. Manna grows a universal grammar as schema — every issue is a `track`, an `item` on a track, or a `dream` (raw intake with a nearest-board-else-global-inbox router); `source:` records provenance as citation. Status is derived from receipts: `Manna: mn-xxxxxx` commit trailers bind work to items, `manna lint` enforces the grammar (wiring the long-dormant `validate()`), and `manna reconcile [--fix]` catches the drift classes that receipts expose — landed-but-open items, dead-session claims, blocker desync (`done` never auto-unblocked; reconcile clears the residue), stale dreams, dangling track edges, and doc references to nonexistent issues. v1 boards round-trip byte-identical and upgrade lazily on write; `context` renders the track tree on typed boards and is unchanged on untyped ones.
- The board is ambient. SessionStart injects `manna context` in repos with a board (byte-identical output elsewhere) plus a drift greeting from `.manna/drift.yaml`; SessionEnd runs the reconcile advisory that writes it (bounded, always exit 0). SessionStart pins `MANNA_SESSION_ID` beside the coord pin, so claims anchor to sessions instead of transient CLI pids that always probe dead. Fixed on the way: the session-start tooling reminder had been silently truncated mid-line by unquoted quotes in every session, and the project-scoped tools section had never rendered once (live backticks in an f-string); both now render complete with zero stderr. Registry truth repaired: six real manna verbs the commands map omitted are now declared with contracts, and manna's cargo + integration suites run in `./test.sh`.
- Issues carry their work orders. Manna issues gain `prompt:` (`--prompt` on create/update; a `PROMPT:` first description line is honored as the interim form, field wins). `manna lint` flags pointers to missing files; reconcile's `prompt_pairing` check verifies both directions — the pointed-at file must contain the issue's id, and any prompt file whose claim commands (`manna claim mn-xxxxxx`, any invocation prefix) target a live local issue demands a back-pointer. Bare id mentions are data, never pairing promises. Also fixed: the id matchers sliced 9-byte windows without char-boundary guards, so multibyte content (astrology glyphs, U+FFFD) panicked reconcile; guarded with regression tests.
- Documentation is current-state and partly generated. README, ARCHITECTURE, INTEGRATION, CONTRIBUTING, SECURITY, and AGENTS describe the system as it is (no delta framing; this changelog is the only diff document), and docs/TOOLS.md is now a build product: `bin/gen-tools-doc` renders it from the bundled registry with contracts-derived safety notes, and a `--check` gate in `./test.sh` fails the build if it drifts.
- coord v2: presence can no longer lie. Identities are session UUIDs anchored to the long-lived agent process (a recycled tmux pane never inherits a dead session), peers are liveness-verified (kill -0 + start-time match) into active/idle/dead/stopped/stale with last-seen ages, and territory is data — roles declare exclusive write-domains whose overlaps interrupt both writers. Every v1 CLI form and record keeps working; v1 records upgrade lazily on write.
- Contracts are now load-bearing, not just declared. The registry's promises are enforced four ways: a weekly behavioral audit probes every safe read verb and pings on failures; a drift gate fails the build if the registry promises a command a tool doesn't implement; concurrency is derived from contracts (a `read` tool cannot hold world-write verbs); and natural-language routing asks before executing destructive commands unless `AGENT_DO_AUTO_DESTRUCTIVE=1`.
- Every one of the 23 previously phantom registry commands is now real: built (`manna update/delete`, `slack read`, `discord read`, `clipboard history`, `calendar delete`, `cloud deploy/logs`, `debug backtrace`, `sheets create`, `jupyter kernel`, `dns list`, `logs filter`, `macos tree`, and more), documented where they already worked, or removed with a filed issue where the promise was infeasible (`dns update`, `discord join`).
- New `own_state` contract attribute: tools whose only writes touch their own cache stay parallel-safe instead of being over-serialized.

### Added
- The installed `~/.factory/agent-do-index.yaml` is now a deterministic build artifact generated from canonical `registry.yaml` plus small presentation overrides, so every tool is discoverable without hand-maintaining a second inventory.
- `agent-do git` now refuses implicit staging, scans staged additions for redacted secret findings, manages env-seeded worktrees, exposes `refs/auto` snapshot recovery, reports conflicts and read-only recovery evidence, and keeps branch sweeping dry-run-only until `--apply`.
- Browser daemon self-heal is now session-safe: lifecycle signals require PID/argv identity, raw `ping` distinguishes healthy-idle from wedged daemons without launching a page, `browse doctor` diagnoses the current session, and the live two-session gate proves one session's recovery cannot disturb another.
- ZPC global lessons now participate in bounded agent injection, status counts, and opt-in `query --global` reads; absent global state remains silent and all regression tests use isolated `AGENT_DO_HOME` directories.
- Capability-aware cross-provider fallback for internal LLM roles: OpenAI GPT-5.6 Responses API candidates, bounded model-list doctor checks, 404-only runtime fallback with telemetry, and warn-only handling for absent optional provider keys.
- Central capability-aware model roles for agent-do's own internal LLM calls (`models.yaml`, `agent-do models list|resolve`), replacing scattered retired defaults while preserving generated templates and explicit eval model choices.
- coord v2 (`tools/agent-coord`) — the state board rebuilt around real incidents from multi-session builds:
  - Liveness-verified presence: records carry pid + process start time; `peers` renders active/idle/**dead**/stopped/stale with last-seen ages, plus `--active-only`/`--writers` filters for hook consumption. Idle retention default dropped 14d → 2d; dead/stopped tombstones age out after 24h and verifiably-gone records sweep on the same TTL.
  - Session-UUID identity anchored to the nearest agent-runtime ancestor (`claude`/`codex`, extensible via `AGENT_DO_COORD_ANCHOR_NAMES`) — per-call harness shells no longer mint an identity per command, and a pane reused by a new process mints a fresh identity while the old record tombstones DEAD. `AGENT_DO_COORD_SESSION` pins identity explicitly; records carry `runtime` and optional `model`.
  - `role set <builder|auditor|researcher|overseer> [--mode] --territory <path>...` — exclusive-writer territories; overlapping writers get a contention interrupt on both sides, auditors on a writer's paths emit a courtesy notice, and `territory show` renders the ownership map with overlap callouts.
  - `guard check [<paths>] [--staged]` / `guard install` — warn-only detection (never blocks) when staged paths intersect a live peer's claim or territory, installable as a pre-commit hook that appends without clobbering existing hooks.
  - Structured focus: goal + phase (building|gating|watching|quiet|blocked|stopped) + note + blocking_on + last_ship; omitted flags preserve, empty string clears; v1 `focus set <goal> --path` unchanged.
  - `drop add <path> --for <agent|role|any> [--key]` / `drops --for-me` — file-pointer handoffs on the board (never content); drops addressed to you or matching a need key raise dependency interrupts. `publish add` gains `--file`.
  - `stop [--note]` / `bye` — clean session retirement (idempotent, Stop-hook safe) instead of writing "stopped" into focus prose; `history [peer] [--limit]` reads the events journal without grepping.
  - `touch` returns `peer_counts` so hooks render live writers first with phase + age, auditors marked read-only, and dead/stale collapsed to a count (session-start + prompt-router updated accordingly).
  - v1 compatibility: every v1 CLI form works, v1 records read as-is and upgrade lazily on write, and `tests/test_coord.py` passes unchanged; new coverage in `tests/test_coord_v2.py` (pane reuse, dead detection via pid/start-time mismatch, both-ways territory contention, migration, anchor walk, tombstone aging).
- SessionEnd hook `hooks/claude/agent-do-coord-stop.sh` retires coord presence at session teardown (only in repos with an existing board); session-start pins `AGENT_DO_COORD_SESSION` from the session_id so retirement hits the identity the session actually used.
- Hook hardening: every `agent-do` spawn inside the Claude hooks now runs under a hard wall-clock bound that SIGKILLs the whole process group on expiry (bash `bounded_run` via perl setpgrp+alarm; python `run_bounded` via `start_new_session` + `killpg`) — a slow or wedged spawn degrades to "no coord context" instead of eating the hook's timeout and discarding its output. Budgets: prompt-router 2s per coord call, session-start 3+3+2+2s under its 10s limit.
- `agent-do harness contracts audit [--include-network] [--out FILE] [--notify]` — bounded behavioral probe of the declared read surface with tri-state grading (ok / clean-skip / fail); `--install-schedule [weekly|daily]` writes a launchd agent that audits automatically and notifies only on failures via `notify emit contracts_audit`. First run found 69 verbs violating their declared shape (mostly snapshot verbs ignoring `--json`) — filed for class-by-class fixes.
- `agent-do harness contracts drift [--tool X]` — diffs registry command promises against each tool's `--help` (zero false positives across all 95 tools); the declared-but-unimplemented channel gates `./test.sh`.
- `agent-do harness contracts surface --json` — machine-readable safety surface for orchestrators: read_only/write/destructive/sensitive/long_running/passthrough/own_state verb lists over the merged registry.
- Routing consumes contracts: the LLM catalog carries per-tool `Safety:` lines; both routers annotate resolved routes with the verb's beats and attributes (after cache writes, so route memory never replays stale safety data); read-leaning intents resolving to write verbs log `route_intent_mismatch` telemetry.
- `AGENT_DO_AUTO_DESTRUCTIVE=1` — natural-language routes to destructive/sensitive verbs ask first (exit 2 clarification) by default; auto mode executes with annotation and telemetry.
- `AGENT_DO_AI_MODEL` now reaches the natural-language router (previously hardcoded).
- Concurrency-from-contracts validator rule: `concurrency: read` with world-write verbs is a gate error; `own_state` writes are exempt.

### Changed
- `dns`, `usb`, `creds`, `clipboard` corrected `read` → `mixed` (their writes hit provider records, the OS mount table, the keychain, the clipboard); `dns` returned to `read` after its phantom `update` verb was removed.
- `figma` emits JSON-safe errors and bounded requests; `sheets` create/write pass user input via argv instead of interpolating into python source (injection fix, plus write's double-nested values bug).

### Fixed — the audit's day-one findings (69 → 0)
- The read surface honors `--json` everywhere: 33 tools gained or repaired JSON output on their snapshot/verify verbs (agent, api, browse api list, ci, clipboard, creds, dpt, eval, gcp, gh doctrine, git log, hardware, homekit, ios, lab, latex, learn, memory, metrics, printer, prompt, repl, serial, ssh, swarm, tail, tui, unbrowse, usb, vm, and more). Plain-text output is unchanged everywhere; `--json` is additive.
- No read verb can hang anymore: `calendar list` (TCC/Automation stalls), `docker ps` (dead daemon socket), `db tables` (no connection), `meetings active/snapshot` (provider probes), and `vision count/faces/ocr/snapshot` (missing source, stalled camera) all gained bounded execution with structured fail-fast errors.
- `manna list --json` and `manna context --json` work (clap previously rejected the flag with empty output); `metrics processes` no longer dies of SIGPIPE (exit 141).
- The weekly scheduled audit now guards all of this: behavioral failures went 69 → 0, with 125 verbs probing clean.
- No network call can hang anymore: every `curl` and `urllib` request across the cloud tools (`clerk`, `cloudflare`, `gcp`, `namecheap`, `okta`, `render`, `resend`, `supabase`, `vercel`) and `discord` now carries `--max-time`/`--connect-timeout` (or `urlopen(timeout=)`), including the requests hidden inside embedded-Python helpers — closing the same hang class that froze CI for 40 minutes, now on a flaky connection instead of a dead daemon.

## v1.3 (2026-06-12)

### TL;DR
- The five-beat mental model (Connect → Snapshot → Interact → Verify → Save) is now machine-readable and enforced. Every one of the 94 tools declares a `contracts:` block in `registry.yaml` mapping each command verb to its beats, with attribute flags for the shapes a single beat cannot express.
- Agents and schedulers can now read per-verb truth from the registry: 890 verbs classified, 469 read-only (safe to parallelize), 51 destructive, 24 secret-emitting, 11 arbitrary-code passthroughs, 26 long-running.
- A gate blocks any new tool from merging without contracts, enforced by `./test.sh` and GitHub Actions CI (the repo's first).

### Added — contracts layer
- `contracts:` blocks on all 94 registry tools (890/890 command verbs classified). Beats stay five; verbs that resist a single beat carry orthogonal attributes instead: `destructive`, `long_running`, `polymorphic`, `composite`, `sensitive`, `passthrough`. Validated against a fixed vocabulary in `lib/registry.py`; a verb declared under multiple beats must explain itself with `polymorphic` or `composite`, and only `passthrough`/`long_running` verbs may stand beat-less.
- `lib/contracts-lexicon.yaml` — the canonical verb→beat/attribute mapping with documented principles (Verify is purposive, not contextual; transforms are interact; destruction is an attribute, not a beat) plus per-tool overrides. `lib/contracts-lexicon-learned.yaml` carries agent-derived classifications with confidence and evidence; the hand lexicon always wins on merge.
- `agent-do harness contracts validate [--strict]` — the gate: registry shape errors plus full-coverage enforcement. `agent-do harness contracts propose [--tool X] [--out FILE]` — regenerates draft declarations and a reviewable inventory whose header aggregates the safety surface (destructive/sensitive/passthrough/long-running verbs across all tools).
- `tests/test_contracts_gate.py` in `./test.sh`: schema validation, attribute vocabulary, full-coverage enforcement, lexicon merge precedence, and a duplicate-YAML-key guard (PyYAML silently keeps the last duplicate mapping key, which can swallow override blocks).
- GitHub Actions CI: `contracts-gate.yml` (registry gate + harness inventory on ubuntu) and `ci.yml` (bash/python syntax sweep on ubuntu; full `./test.sh` on macOS).
- The new-tool rule in `CLAUDE.md`/`README.md`: no tool merges without a contracts declaration.

### Changed
- Concurrency classifications corrected where per-verb review exposed lies: `screen` (drives real mouse/keyboard), `resend` (`add`/`verify` are POSTs), and `harness` (`evidence`/`manifest` write files) moved `read` → `mixed`. Distribution is now 57 mixed / 20 read / 17 write.
- The `metrics` registry entry described a fictional tool (`query`/`alert`/`dashboard`); it now declares the real surface (`cpu`/`memory`/`disk`/`network`/`processes`/`load`/`uptime`/`all`). Phantom `slack react` (declared, never implemented) removed.
- Sensitive-blind reads now flagged: `render secret get`, `render kv connect-info`, `render db` (DSN reveal), `browse auth get-creds`, `sms code`/`link` all carry `sensitive`.

### Fixed
- `agent-do --health` could hang forever when the Docker daemon was dead: `bin/health` now bounds external daemon probes (`docker info`, `kubectl cluster-info`) with a 10-second python-backed timeout, since macOS ships no `timeout(1)`. Regression-tested with a shimmed blocking docker (`tests/test_health_probes.py`).

### Added — pre-existing unreleased work
- `agent-do notion` has been rebuilt from a stub into a contract-real Notion team operating layer. It now uses Notion API `2025-09-03`, resolves credentials through `agent-do creds`, supports `doctor`, `snapshot`, workspace/users/search/read/blocks/data-source commands, verified saves for team notes/tasks/decisions/handoffs/comments, local SQLite/FTS cache sync, schema adoption via `bootstrap-team`, webhook ingestion, and optional semantic cache commands.
- The Notion registry entry now documents the required `NOTION_TOKEN`, optional semantic keys, routing keywords, recommended entrypoints, and the team-workspace setup model. `tests/test_notion.py` covers the Notion contract with mocked API responses and is included in `./test.sh`.
- `agent-do obsidian` is now release-ready for local vault usage: `doctor --json` reports local-index mode, note/chunk/embedding counts, feature readiness, and credential readiness without exposing secret values. `agent-do --health obsidian` now treats a readable vault path as ready even when the Obsidian CLI is not installed.
- `agent-do creds required <tool>` now supports feature-level credential presentation from `registry.yaml`, so tools can explain which API keys are required, optional, or only needed for specific capabilities. The Obsidian registry entry now documents no-key vault operations plus `VOYAGE_API_KEY`, `OPENAI_API_KEY`, and `COHERE_API_KEY` setup.
- The README now documents Obsidian local-index setup, semantic vault search setup, vault chat setup, and the public credential-discovery contract through `agent-do creds required <tool>`.
- `lib/snapshot.sh` `snapshot_field` now encodes string values via `python3`'s `json` module when available, covering the full RFC 8259 control range (`U+0000`–`U+001F` plus `\\` and `\"`); a manual fallback covering the named C0 controls is used when `python3` is unavailable. `snapshot_error` now routes its message through the same encoder so error JSON is consistent with snapshot JSON.
- `lib/snapshot.sh` `snapshot_end` now bounds invalid-UTF-8 failures to the offending value: each string is tried with strict UTF-8 decode and, on failure, re-decoded with `errors="replace"` so its bad bytes become U+FFFD. Sibling string fields keep full encoder semantics, snapshot output remains valid UTF-8 and valid JSON, and the helper no longer silently downgrades the whole snapshot to manual fallback when one value contains invalid bytes.

## v1.2 (2026-05-14)

### TL;DR
- `agent-do` is now a stronger default agent layer. It helps agents fetch fresh docs, handle auth, work GitHub PRs, coordinate with other agents, and send status updates.
- For current docs, the main command is now `agent-do context retrieve "<question>" --fresh --max-tokens 8000`.
- Local skills now show `local skill - no versioning` instead of looking like broken web docs.
- The public repo is cleaner. Local notes and non-release material belong under `.dev/`.

### Added
- `agent-do psql` for PostgreSQL CLI operations via the native `psql`/`pg_dump`/`pg_restore` binaries. Connection management with macOS Keychain-backed profiles, schema exploration (snapshot, tables, views, describe, schemas, extensions, sizes, relations), data operations (query with auto-LIMIT, sample, count, exec), admin commands (connections, locks, stats, indexes, version), and backup/restore. All output is structured JSON. Complementary to `agent-db` (which uses Python drivers for multi-database support). Table name validation prevents SQL injection in identifier interpolation. Schema-qualified table references (`schema.table`) are parsed correctly across all table commands. Snapshot integration on connect, query, and exec for audit trail.
- Fresh docs support in `agent-do context`, including refresh, stale checks, HTML docs, local docs serving, source version checks, and last-good fallback when the network fails.
- GitHub PR work commands in `agent-do gh`, including inbox, awaiting review, diffs, review threads, checks, audits, replies, approvals, merge work, checkout, ready, and draft.
- Auth flow support in `agent-do auth`, with encrypted auth bundles, browser import, SSO, TOTP, email codes, SMS codes, recovery codes, passkeys, and checkpoint advance.
- Secure credential support in `agent-do creds`, plus registry metadata so tools can say which secrets they need.
- Agent coordination in `agent-do coord`, with focus, claims, needs, published outputs, presence, and interrupt checks.
- Notification support in `agent-do notify`, with SMS, email, Slack, Messenger, local pipes, rules, templates, groups, cooldowns, and delivery history.
- Harness and hook observability in `agent-do harness`, with telemetry, evidence bundles, manifest checks, and nudge outcome tracking.
- New tool families for Resend, hardware, meetings, email, SMS, and repo-local specs.
- `+live(...)` approval support for direct visible-machine actions.

### Changed
- Docs prompts now route agents toward `agent-do context retrieve ... --fresh` instead of weak generic search hints.
- The README is now a front door for agents, with detailed tool workflows moved to docs.
- Browser sessions are isolated per agent by default so parallel agents do not overwrite each other's saved state.
- Browser session import now carries more state, including cookies, localStorage, sessionStorage, and IndexedDB where possible.
- Auth flows can keep working in a real visible browser when a site blocks headless login.
- Email lookup now uses Apple Mail's local index for faster message and mailbox search.
- Structured dispatch now ignores unregistered `agent-*` binaries on `PATH`.
- `agent-do --health` now reports credential readiness from tool metadata.
- `agent-do macos` and `agent-do screen` now require explicit live approval for direct control actions.
- Public release files were cleaned so generated files, local handoffs, and private working notes stay out of the repo.

### Fixed
- Render service lookup by name works again.
- DPT scoring now checks the right agent-scoped browser socket before scoring.
- GitHub awaiting-review output no longer reports bad `[null]` reviewers.
- Browser `get text|html|value|attr` now sends the right protocol actions.
- Namecheap DNS writes no longer crash after a successful add.

## v1.1 (2026-04-11)

### Added
- `agent-do suggest "<task>"`, `agent-do suggest --project`, and `agent-do find <keyword>` for non-LLM discovery on top of shared registry routing metadata.
- `agent-do nudges stats|recent|clear` for local hook telemetry under `~/.agent-do/telemetry/`.
- Shared `routing` metadata in `registry.yaml` for the first high-value tool set, including discover keywords, raw CLI equivalents, readiness hints, and project signals.

### Changed
- SessionStart hook context is now project-aware and can recommend likely tools for the current repo instead of only a static key-tool list.
- Prompt-submit and PreToolUse hooks now use shared registry routing metadata for more exact hard nudges and concrete replacement commands.
- Offline matching now consumes shared registry routing metadata before falling back to legacy regex patterns.
- Natural-language cache memory is now project-scoped and weighted by route success/failure instead of treating all prior matches equally.

## v1 (2026-04-10)

### Fixed
- Natural-language routing now resolves directory-backed tools correctly instead of trying to execute tool directories directly.
- `agent-do --health` is now a real top-level command rather than an installer-only expectation.
- Offline routing preserves arguments correctly and surfaces clarification questions instead of failing silently.
- Stale `gui` routing no longer leaks into current `macos` flows.
- Missing `PyYAML` on common paths now produces actionable errors instead of Python tracebacks.
- `agent-context` source management now works without `PyYAML`, including the previously failing `sources` fallback path.
- `agent-dpt` is now repo-local instead of depending on an absolute symlink outside the repository.
- `agent-manna` health checks and binary resolution now match the actual `manna-core` build output.

### Added
- `agent-do bootstrap` for idempotent project setup of stateful tools.
- Session-start bootstrap detection that tells Claude to ask once when a project needs `context`, `zpc`, or `manna` initialization.
- Runnable browse tests via `vitest` in `tools/agent-browse`.
- Repo-local DPT source, install script, wrapper binaries, and documentation.

### Changed
- README, integration docs, architecture docs, and project CLAUDE guidance now document `--health`, bootstrap, and current first-run verification.
- Root smoke tests now validate bootstrap behavior in addition to direct, offline, and health-check flows.
- Claude Code hook guidance now reflects the real non-interactive SessionStart model: hooks inject context, Claude asks in conversation.

### Validation
- `./test.sh`
- `bash tools/agent-context/test/integration.sh`
- `cd tools/agent-browse && npm test`
- `bash tools/agent-manna/test/integration.sh`

## v0.9 (2026-03-17)

### Added
- **agent-context**: Curated docs and context for AI agents (tool #76), 22 commands:
  - `fetch <url>`: fetch markdown from any URL
  - `fetch-llms <domain>`: fetch llms.txt / llms-full.txt from any domain
  - `fetch-repo <owner/repo>`: fetch docs from GitHub via gh CLI
  - `scan-local`: index project context files (CLAUDE.md, .cursorrules, etc.)
  - `scan-skills`: index ~/.claude/skills/ as searchable context
  - `search <query>`: FTS5 BM25 search with keyword expansion, trust-tier boosting, feedback weighting
  - `get <id>`: retrieve cached doc with annotations, incremental fetch (--file, --full)
  - `list`: list all indexed packages with trust badges
  - `budget <tokens> <query>`: token-aware greedy knapsack context assembly
  - `inject --max-tokens N`: structured context blob for spawned agents
  - `annotate <id> <note>`: persistent notes displayed inline on future gets
  - `feedback <id> up|down`: ratings that influence search ranking
  - `build <dir>`: validate and package private content with registry.json
  - `cache list|clear|pin|stats`: full cache management with pinning
  - `sources` / `add-source` / `remove-source`: multi-source config management
  - `status` / `init`: storage management
  - Full `--json` support via `lib/json-output.sh` + `lib/snapshot.sh`
  - SQLite FTS5 index with 50-entry keyword expansion table
  - Trust tiers: official, maintainer, community, local
  - 31 integration tests (tools/agent-context/test/integration.sh)
- Registry entry for context in `registry.yaml` (22 commands, 8 examples)
- Exceeds Context Hub (chub): any-source fetching, token budgets, skills indexing, no Node.js dependency

### Changed
- Tool count: 75 → 76 across all documentation
- Updated README, CLAUDE.md, ARCHITECTURE.md, PLAN.md, TOOL_AUDIT.md, INTEGRATION.md, CHANGELOG.md, install.sh

---

## v0.8 (2026-02-27)

### Added
- **agent-zpc**: Structured project memory for AI coding agents (tool #75), 13 commands:
  - `learn`: capture validated lessons with tags (writes to `lessons.jsonl`)
  - `decide`: log decisions with rationale, confidence, bias detection (writes to `decisions.jsonl`)
  - `decide-batch`: batch-log decisions from planning phase via stdin or file (pipe-delimited)
  - `harvest`: consolidation scan with format health, pattern drafting, auto-write for 5+ lesson tags
  - `query`: search by tag, date, text, or type (lessons/decisions/all)
  - `patterns`: view established patterns, score effectiveness
  - `promote`: promote lessons to team (git-tracked) or global scope with dedup
  - `inject`: emit agent context blob for spawned agents (baseline counts for self-report grounding)
  - `init`: initialize `.zpc/` with stack auto-detection and platform-specific instructions
  - `status`: memory snapshot with health check (human + JSON output)
  - `checkpoint`: swarm phase boundary with memory inventory, agent compliance, format health, consolidation gaps
  - `review`: post-sprint lesson extraction from git history, draft lessons/decisions from commits
  - `profile`: view/update project profile, auto-detect stack
  - 4 platform templates: Claude Code, Cursor, Codex, Generic
  - Full `--json` support via `lib/json-output.sh` + `lib/snapshot.sh`
  - Per-project memory (`.zpc/`) + global memory (`~/.agent-do/zpc/`)
  - Team scope (`.zpc/team/`) for git-tracked shared memory
- Registry entry for zpc in `registry.yaml` (13 commands, 10 examples)
- zpc patterns in prompt router hook
- zpc in PreToolUse skip patterns
- zpc in SessionStart key tools list
- zpc entry in runtime index and catalog
- Frontend/design intent detection in prompt router (two-stage: UI keywords + action keywords)
- Frontend project detection at session start (monorepo-aware: apps/\*, packages/\*)
- ZPC project detection at session start (.zpc/ directory → memory reminder)

### Changed
- Tool count: 74 → 75 across all documentation
- Updated README, CLAUDE.md, AGENTS.md, ARCHITECTURE.md, PLAN.md, TOOL_AUDIT.md, INTEGRATION.md, install.sh
- Session-start hook: auto-detects agent-do location (3-tier fallback), no hardcoded paths
- Session-start hook: added macos, gcp, zpc to key tools list
- Prompt router: tightened iOS/Android patterns to prevent false positives (bare "ios" no longer matches)
- Prompt router: added design toolkit injection for frontend/visual prompts

---

## v0.7 (2026-02-06)

### Added
- **agent-sessions**: AI coding session history search with FTS5 full-text search
- **agent-supabase**: Data access (REST queries, SQL via agent-db bridge)
- **install.sh**: Idempotent installer with Claude Code hooks distribution
- Claude Code hook trinity: SessionStart, UserPromptSubmit, PreToolUse

### Changed
- Tool count: 68 → 72
- Full repo audit: fix stale counts, symlink references, agent-gui→agent-macos renames

---

## v0.6 (2026-01-28)

### Added
- **agent-gcp**: Google Cloud Platform management (projects, APIs, secrets, service accounts, OAuth)
- **agent-render**: Render.com service management via REST API
- **agent-vercel**: Vercel project/deployment management via REST API
- **agent-dpt**: Design Perception Tensor (65 rules, 0-100 visual quality score)
- **agent-pdf2md**: PDF-to-Markdown converter with tabular/prose auto-detection
- **agent-tail**: Dev command wrapper with log capture for AI agents
- **agent-vision**: Visual perception CLI (YOLO, OCR, face detection, Vision LLM)
- **agent-screen**: Multi-display vision (24fps capture, OCR, element detection)

### Changed
- P0-P3 tool audit: 20 tools upgraded with snapshot commands
- lib/snapshot.sh and lib/json-output.sh shared framework libraries
- bin/health dependency checker

---

## v0.5 (2026-01-15)

### Added
- Initial public structure with 60+ tools
- Structured API mode (`agent-do <tool> <command>`)
- Natural language mode (`agent-do -n "intent"`)
- Offline pattern matching (`agent-do --offline "intent"`)
- 3-tier fallback: SQLite cache → Jaccard fuzzy → Claude API
- Gold standard tools: browse, db, excel, unbrowse
