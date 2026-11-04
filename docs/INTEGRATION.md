# Integrating agent-do with an Agent Harness

agent-do works with any coding agent that can execute shell commands. Two integration depths exist:

1. **Instructions only**: document the CLI in the harness's instruction file (CLAUDE.md, .cursorrules, AGENTS.md). No hooks, no state; the agent simply knows the tools exist.
2. **The ambient loop**: install the shipped Claude Code (and optionally Codex) hooks. Sessions then start with the project's work board and drift report injected, prompts get high-confidence tool routing, raw commands get nudged toward native equivalents, and session teardown retires coordination presence and writes the reconcile report the next session greets with.

Everything below is presence-gated: repos without a `.manna/` board or a coord board see none of the board machinery, and the hooks degrade to the plain tooling reminder.

## Coordination doorbell

Coord remains a public ledger, not a mailbox. An addressed dependency
(`coord need add <key> --why <text> --from <agent>`, also spelled `--for`) or
file drop (`coord drop add <path> --for <agent>`) sets a pending bit for a live
named session. Exact IDs and existing aliases route the bell; role/`any` drops
remain ordinary ledger entries, and a direct `--for` that names no registered
session, alias, or role is refused rather than written to nobody. A drop for
the worker on an item (`coord drop add <path> --for-item <mn-id>`) rings the
session whose bound Manna proof equals the board's claim proof, exactly; with
no such live session the drop is recorded as pending, no bell is set, and the
worker's next `coord touch` resolves and rings it. The drop's `delivery` view
says which of these happened; a queued bell is never an acknowledgment.
Repeated rings coalesce. An explicit
`agent-do coord bell ring --for <agent>` can repeat the nudge after a ledger
write, but accepts no content, message, note, or file payload.

`bells.json` in the existing project-local coord store contains only recipient
IDs mapped to `true`. The shared coord lock serializes ledger writes, rings,
and consumption. Dead, stopped, stale, or unknown targets do not ring. Bell
I/O failure cannot fail a committed need/drop; a busy or unavailable hook
degrades silently to ordinary polling. Hook work has a two-second local
deadline inside the five-second harness timeout. A ring never renews target presence,
revives a session, changes a Manna claim, or edits a sealed work order.

The shared `hooks/claude/agent-do-coord-doorbell.py` hook is included in both
Claude and Codex install bundles. Register it on `UserPromptSubmit` and `Stop`:

- `UserPromptSubmit` adds the fixed context: "The ledger has entries concerning you; read coord."
- `Stop` requests one continuation with that same fixed sentence, only when
  `stop_hook_active` is explicitly false. Already-continuing turns retain any
  new ring for the next prompt, preventing a stop-hook loop.
- Other events produce no output and leave the pending bit untouched.

The hook resolves the payload's exact `session_id` and `cwd`, including legacy
thread identities, without trusting an inherited foreign session pin. It
never reads a transcript or forwards the prompt, need, drop, or bell sender.
Recipients read `agent-do coord interrupts`, `agent-do coord need list --all`,
and `agent-do coord drops --for-me`; observers can read the same ledger. An
informational drop is a notice: it leaves a reader's interrupts once that reader
acknowledges it (`agent-do coord drop ack <id>`, per reader, per revision) and
never blocks the prompt router. An action drop (`drop add --action`) is an
obligation: acknowledging it means "read", it stays listed as a dependency and
the router keeps reminding at work boundaries until an authorized party resolves
it (`agent-do coord drop resolve <id> --reason ...`). Both leave the record and
its history in place, and a changed drop resurfaces. The session-start and
prompt-router hooks read coord under the session id the shell was given, so an
acknowledgment from the shell quiets the hook.
Workers may request contract changes there, but cannot self-amend acceptance.
A bell exchange never closes an item: `done` still requires executed receipts.

Runtime capability check, 2026-09-22: current [Codex hook documentation](https://learn.chatgpt.com/docs/hooks#userpromptsubmit)
defines `hookSpecificOutput.additionalContext` for prompt submission and
[one-shot Stop continuation](https://learn.chatgpt.com/docs/hooks#stop) via
`decision: "block"` and `reason`. [Claude's hook reference](https://code.claude.com/docs/en/hooks#stop)
documents the same continuation fields and loop guard. This implementation
uses those lifecycle hooks, not Codex's separate `notify` command, so existing
notification chains are unchanged. Features/hooks and the registrations must
be enabled in the host; editing this repo does not install or enable them.

This checkout has no OpenCode hook/plugin installer. OpenCode and other
unintegrated harnesses therefore retain poll-at-pause behavior; no automatic
delivery is claimed for them. A notification-only host can surface only the
same fixed nudge through its supported adapter; no alternative message path
is part of this implementation. The bell does not launch, resume, or wake an
idle agent process. A ring after its last hook waits for its next supported
boundary.

Focused verification is `python3 tests/test_coord_v2.py` (offline ledger,
hook-protocol, failure, concurrency, and registration fixtures), alongside
`python3 tests/test_coord.py` and `python3 tests/test_install_specs.py`.
These are executed CLI/hook tests, not live harness acceptance. Closing this
lane additionally requires a coordinated worker/coordinator exchange on a
real mid-claim blocker with a third session able to read all substance on
Coord, without human relay.

## Installation (install.sh)

GNU Bash 4.4 or newer is a runtime requirement. On macOS, install it with
`brew install bash`; the system Bash 3.2 is intentionally rejected. The
installer and public launcher share one runtime selector, so sparse agent
environments still execute the dispatcher and every child tool under the same
supported Bash.
Set `AGENT_DO_BASH=/absolute/path/to/bash` only when the supported interpreter
lives outside the standard paths searched by the selector.
Python-backed Manna commands similarly bind to one verified Python 3.10+
interpreter with PyYAML. Installation records it at
`~/.agent-do/python-path`; set `AGENT_DO_PYTHON=/absolute/path/to/python` to
select a different runtime deliberately.

```bash
./install.sh                # Install; auto-installs Codex hooks if ~/.codex/ exists
./install.sh --codex        # Force Codex hook install even without ~/.codex/
./install.sh --no-codex     # Skip Codex install even when ~/.codex/ is present
./install.sh --uninstall    # Remove symlink, breadcrumb, generated index, and hook wrappers
```

What the installer actually does, in order:

1. Symlinks `agent-do` into `~/.local/bin` (warns if that directory is not on `PATH`)
2. Writes the repo path to `~/.agent-do/install-path` (the breadcrumb wrappers and hooks resolve)
3. Generates the discovery index from `registry.yaml` via `bin/gen-index`
4. Writes the Claude hook **wrappers** to `~/.claude/hooks/`; `CLAUDE_HOOK_SPECS` in `install.sh` lists the sources, including `agent-do-quantity-check.py` and `agent-do-prose-lint.py`
5. Optionally writes five Codex wrappers to `~/.codex/hooks/` (the three event hooks plus `stop-quality-gate.sh`/`.py`)
6. Installs Python dependencies through one Python 3.10+ interpreter and records that exact runtime at `~/.agent-do/python-path`
7. Interactively offers `npm install` for browse/unbrowse and `cargo build --release` for manna
8. Runs `agent-do --health`
9. Prints the Claude `settings.json` snippet, the Codex `hooks.json` template when Codex install ran, and a project CLAUDE.md snippet

Claude registration is required: **Claude Code does not auto-discover hooks**.
The installer asks before merging `settings.json` in an interactive terminal;
`--register-hooks` authorizes that merge and `--print-only` leaves settings
untouched while printing the complete snippet. Both options still install
wrappers and dependencies. A wrapper does nothing until it is registered.

## Registering the Claude hooks (settings.json)

Merge into `~/.claude/settings.json` (into the existing arrays if you already have hooks for these events):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-session-start.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-prompt-router.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-pretooluse-check.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-prose-lint.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/agent-do-coord-stop.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

The example above shows selected registrations; `CLAUDE_SETTINGS_SPECS` in
`install.sh` generates the complete set. The prose hook allows three seconds
for the linter inside its five-second registration, leaving time to report a
failure before the host deadline.

agent-do registers nothing at `Stop`. Claude Code fires `Stop` every turn; session retirement belongs on `SessionEnd`. Auto-commit, formatters, notifications, and other turn-end behavior are personal workflow for your own dotfiles.

## Prose feedback after writing

`agent-do-prose-lint.py` runs after Claude `Write`, `Edit`, and `MultiEdit`
calls. The installer registers one `PostToolUse` matcher (`Edit|Write|MultiEdit`)
with a five-second timeout and installs its Python wrapper alongside the
quantity hook. Existing installations need the new wrapper and registration;
adding source code alone does not activate a new hook.

The hook calls `agent-do deai lint <saved-file> --register <pack> --json`.
It checks `.md`, `.markdown`, `.txt`, and `.rst` files, skips source code and
dependency/build directories, and uses the closest named directory to select
a pack: `drafts/` or `essays/` selects `essay`, `email/` or `emails/` selects
`email`, and `product-answers/` or `product_answers/` selects `product-answer`.
Other prose uses `default`. Relative paths resolve from the tool event's
working directory, including sessions started inside `drafts/`.
The entire saved file is checked so rates, frontmatter,
and code fences retain their context.

Findings arrive as advisory `additionalContext` with rule IDs and file
locations. The hook reports up to six rules, explicitly counts omitted rules
and repeated occurrences, and includes the command for the complete report.
Every edit is checked again; a clean result is silent. A timeout or linter
failure reports an unchecked file. Nothing rewrites text or blocks the edit.
`AGENT_DO_PROSE_LINT=0` disables the hook. The hook writes no prose or receipt
files; the dispatcher retains its normal invocation telemetry.

Focused checks: `python3 tests/test_prose_lint_hook.py`,
`python3 tests/test_deai.py`, and `python3 tests/test_install_specs.py`.
These exercise local CLI fixtures and registration coherence without
installing hooks or opening a host session.

## The wrapper upgrade model

Installed hooks are not copies. Each is a small version-tagged wrapper (`WRAPPER_VERSION` in install.sh, currently 2) that resolves the repo and delegates to the canonical hook at `<repo>/hooks/claude/<file>` or `<repo>/hooks/codex/<file>`:

- Python wrappers use `runpy.run_path` and insert `<repo>/lib/` into `sys.path` first, so hook imports (`from registry import ...`) resolve
- Bash wrappers `exec` the canonical file
- Repo resolution order: `AGENT_DO_REPO` env var, then the `~/.agent-do/install-path` breadcrumb; if neither resolves, the wrapper writes one stderr line and exits 0 (hooks fail open, never block a session)

Consequences:

- `git pull` updates flow through automatically; the next hook event runs the current repo code
- Re-run `install.sh` only when the wrapper format version bumps, a hook file is added, or the repo moves (rewriting the breadcrumb)

## Codex registration (hooks.json)

Codex reads `~/.codex/hooks.json`. The full template lives at `hooks/codex/hooks.json.example` and registers SessionStart (`matcher: "startup|resume"`, 10s), UserPromptSubmit (5s), PreToolUse (`matcher: Bash`, 10s), and Stop (`stop-quality-gate.sh`, 30s). The Codex wrappers under `~/.codex/hooks/` delegate exactly like the Claude ones.

Codex supports `hookSpecificOutput.additionalContext` on PreToolUse (May 2026 hooks release), so the same PreToolUse hook serves both runtimes. Codex parses but does not enforce `permissionDecision: "deny"`, so block mode is effectively Claude-only. The Codex Stop hook is advisory DPT scoring of the active `agent-do browse` session; no Claude equivalent ships, though nothing in the script is Codex-specific beyond its install path.

## Environment the hooks establish

SessionStart writes three exports to `CLAUDE_ENV_FILE`, which Claude Code sources for every subsequent Bash call in the session:

| Export | Purpose |
|--------|---------|
| `PATH=<agent-do dir>:$PATH` | Every Bash call can invoke `agent-do` without installation assumptions |
| `AGENT_DO_COORD_SESSION=<session_id>` | Coord identity anchors to the Claude session; every Bash call derives the same agent id, and SessionEnd retires exactly that identity |
| `CLAUDE_SESSION_ID=<session_id>` | Manna derives a stable private ownership proof under the machine-local key, so separate shell calls and restarted processes recover the same authority without storing a bearer token in the board |

Coord identity and a complete pre-existing Manna identity pair are respected.
An incomplete Manna pair is neutralized so derivation can take over. Cursor's
SessionStart adapter persists its conversation id as `CLAUDE_SESSION_ID`, using
the same proof path as Claude. An orchestrator that pins one identity per lane
must set both Manna variables. Codex has no hook environment export channel, so
Manna derives the same private proof on each invocation from `CODEX_THREAD_ID`
and a mode-0600 key under `$AGENT_DO_HOME/manna/`; plain shells without a host
identity fail closed.

## Presence gating

The hooks decide what to inject by looking at the repo, not configuration:

| Signal | Effect |
|--------|--------|
| `$CWD/.manna/` exists | SessionStart injects the Manna board (`manna context --max-tokens 1500`) and, when `.manna/drift.yaml` contains findings, the drift greeting; SessionEnd runs `manna reconcile --fix --only dead_claim,blocker_desync --write-drift` (the only two repairs `--fix` has: claims coord positively verified dead or stopped abandoned, resolved blockers cleared; `landed_open` is advisory in every path, so a landed row is only ever reported with its next step; mn-880173) |
| `<git-dir>/agent-do/coord/` exists | SessionEnd runs `coord stop`; SessionStart injects coord interrupts or a focus reminder when active peers exist |
| `$CWD/.zpc/` exists | SessionStart mentions the experience journal and its status commands |
| Frontend markers (package.json frameworks, `.tsx`/`.vue`/`.svelte` files, Flutter) | SessionStart injects the design-toolkit workflow |
| `bootstrap --recommend` reports pending setup | SessionStart raises the bootstrap prompt (native macOS dialog by default, context ask otherwise; `AGENT_DO_BOOTSTRAP_PROMPT_MODE=native|context|disabled` overrides). A nonempty board without strict identity/config surfaces `legacy board: run agent-do manna migrate` |

A repo with none of these gets the tooling reminder and project-scoped suggestions only.

## Output conventions an orchestrator can rely on

- **`--json` everywhere it matters**: tools built on `lib/json-output.sh` accept `--json` and emit a `{"success": true|false, ...}` envelope (`json_success` / `json_error` / `json_result` / `json_list`). Snapshot-style reads built on `lib/snapshot.sh` emit a JSON object opening with `tool` and `timestamp` fields; `AGENT_DO_SNAPSHOT_COMPACT=1` forces single-line output.
- **agent-manna** prints YAML by default (a `success:` envelope) and JSON with `--json`. Its own exit codes are 0 success, 1 user error, 2 system error; `lint` exits 1 on findings, `reconcile` exits 0 on findings (advisory) and nonzero only when `--fix` fails.
- **agent-coord** emits JSON with `--json` on every verb.
- **Natural-language mode** (`agent-do --json "intent"`) returns structured status objects: `success`, `tool_error` (with `exit_code`, `stdout`, `stderr`), `needs_input` (with the question), or `error`, plus the resolved route's contract `beats` and `attributes`.

## Natural-language exit codes and the clarification loop

| Code | Meaning |
|------|---------|
| `0` | Routed and executed successfully |
| `1` | Error: no matching tool, tool failure, missing dependency |
| `2` | Needs input: ambiguous intent, or a destructive/sensitive route that requires confirmation |

On exit 2 the orchestrator answers the question and retries with context:

```bash
agent-do -n "restore the database"
# ? Which database session should I target? ... (exit 2)
agent-do --context "the staging postgres session" -n "restore the database"
```

Routes that resolve to a verb marked `destructive` or `sensitive` in its contract also return exit 2 with an explanatory question unless `AGENT_DO_AUTO_DESTRUCTIVE=1` is set. The structured API (`agent-do <tool> <verb>`) is never gated; the gate exists because natural language adds interpretation risk.

## Contracts surface for orchestrators

Before scheduling parallel agents, read the safety surface once:

```bash
agent-do harness contracts surface --json
```

Alongside the standard success envelope, the payload is bucket lists of `{tool, verb}` objects: `read_only` (beat union ⊆ {snapshot, verify}; safe to run concurrently), `write` (serialize), and one bucket per attribute (`destructive`, `sensitive`, `long_running`, `passthrough`, `polymorphic`, `composite`, `own_state`). Policy that follows directly:

- schedule `read_only` verbs freely in parallel; queue `write` verbs per shared resource
- treat `own_state` writes as parallel-safe (they touch only the tool's own cache)
- require confirmation or explicit intent for `destructive` and guard the output of `sensitive`
- expect `long_running` verbs not to return; run them detached
- classify `polymorphic`/`passthrough` calls by their payload, not their verb

The coarse per-tool `concurrency: read|write|mixed` field in `registry.yaml` summarizes the same data and is validated against it. `agent-do harness contracts validate --json` is the machine-readable gate result if you want to assert the declarations are intact before trusting them.

## Credential resolution

Tools declare their secrets in `registry.yaml` (`credentials: required/optional/one_of`). Resolution order everywhere (dispatcher, intent router, health checker):

1. the current process environment
2. the OS secure store via `agent-do creds` (macOS Keychain, Linux Secret Service, Windows per-user store)

```bash
agent-do creds store RENDER_API_KEY --stdin   # store once
agent-do creds check --tool render            # verify a tool's declared credentials
agent-do creds required namecheap             # list what a tool expects
```

Secrets never belong in command arguments, docs, or committed files; store them once and let resolution find them.

## Board conventions for agent teams

These are the conventions the manna tooling checks mechanically; teams that follow them get drift detection for free.

**The grammar.** Every issue is a **track** (a named grouping with intent), an **item** on a track, or a **dream** (raw intake, exempt from tracking, converted or closed with a written reason). Commits that advance an item cite it with a `Manna: mn-xxxxxx` trailer. The board is the only backlog.

**Commit trailers.** A trailer is a commit-body line that is exactly `Manna: mn-xxxxxx` (key case-sensitive, one id per line, multiple lines allowed). `manna reconcile` scans the last 500 commits for trailers and reports issues that landed but are still open (`landed_open`).

**Session identity.** Claude and Cursor SessionStart hooks persist stable host
session ids; Codex supplies its opaque thread id. Manna derives ownership from
those ids plus a machine-local secret. Scripted lanes set both explicit values,
for example:
`MANNA_SESSION_ID=lane6-internals MANNA_SESSION_TOKEN=<32+-character-secret> agent-do manna claim mn-133ad6`.
Claims made under an identity that coord later reports dead or stopped
surface as `dead_claim` findings (a stale record is an aged lease, not death;
an unbound claimant is unseen, not dead), and `reconcile --fix` releases only
when the complete inspected row still matches.

**Generated handoff pairing.** `agent-do bootstrap` runs `manna init` for new
boards and strict-scaffold repair, and `manna migrate` for a detected nonempty
legacy board. New boards receive `.manna/workflow.yaml` and a tracked
`.handoff/` root. `manna create` generates one initial work order for each
actionable item and stores the same repository-relative path in the issue's
`prompt` field. `.manna/handoff-order.yaml` owns priority. `manna sync`
transactionally derives dense `.handoff/<NN>[b<MM>]-<mn-id>-<slug>.md` names
and the README index from board state. A bare filename is safe to launch;
`bMM` names the highest-numbered still-open blocker. Tracks and dreams remain
board-only.

The handoff contains exactly one claim target for its item. `manna claim`
checks the file, pointer, claim command, canonical root, and Git visibility
before it writes any state; a broken pair exits 2. `manna lint` checks the same
contract as a board gate. It also reports `workflow_tracking` with
`git-tracked: no` for each canonical board file that exists outside the Git
index. `manna reconcile` checks both directions under
`.handoff/` and reports `workflow_sprawl` when active local work appears under
`.handoffs/`, `.dev/session-prompts/`, or nested `handoff-prompts/` roots. Bare
id mentions are data, not claims; only `manna claim <id>` command lines bind.
`manna lint` and `manna reconcile` also report filename/index drift with
`agent-do manna sync` as the repair. A live claimed handoff is never renamed;
its number stays reserved until release.

Nonempty boards created before workflow version 1 remain legacy until an
explicit `agent-do manna migrate`. The migration creates sealed handoffs for
active items, grandfathers done rows, exempts tracks and dreams, releases
claims without ownership proofs, and publishes strict identity last in one
recoverable transaction. Their absolute pointers, `PROMPT:` description fallback,
and `.dev/session-prompts/` reverse scan keep working. This compatibility path
prevents an agent-do upgrade from rearranging a live campaign silently.
An identityless nonempty board directs every caller to this migration command;
an empty identityless board and an authenticated pending init journal direct
the caller to `manna init`.

**The loop.** Claim before working, `done` only after verification (done requires the claim), file stray ideas with `agent-do manna dream "<spark>"` (routes to the nearest board walking up from cwd, else the global inbox under `~/.agent-do/inbox`), and let SessionEnd's reconcile write `.manna/drift.yaml` so the next session starts by reconciling the board against reality.

## CLAUDE.md snippet (hookless integration)

For harnesses without hooks, or as reinforcement alongside them, add to the project's instruction file:

```markdown
## agent-do (Universal Automation CLI)

BEFORE using raw commands (xcrun, adb, osascript, curl for APIs, etc.),
CHECK if agent-do has a tool:

    agent-do <tool> <command> [args...]   # Structured API (AI/scripts)
    agent-do -n "what you want"           # Natural language (humans)
    agent-do suggest "task"               # Likely tool/command for a task
    agent-do suggest --project            # Likely tools for this repo
    agent-do find <keyword>               # Keyword search across tools
    agent-do --list                       # List all registered tools
    agent-do <tool> --help                # Per-tool help
    agent-do --health                     # Dependency readiness
    agent-do creds check --tool <tool>    # Check declared credentials
```

Other harnesses follow the same pattern in their own config surface (`.cursorrules`, `.aider.conf.yml`, `.continue/config.json`): document the API, and enforce with hooks where the harness supports them.

## Nudge vs block mode

PreToolUse defaults to nudge mode: `additionalContext` reminders, command still runs. Nudges are session-state-gated (an observed `agent-do` invocation suppresses further nudges for that tool this session) and telemetry-recorded (`agent-do nudges stats`, `agent-do harness nudges effectiveness`). Safe commands are skipped entirely: git, npm, python and friends, file utilities, localhost curl, `--help`/`--version`, and agent-do invocations themselves (which instead get an advisory heads-up when the verb is contract-marked destructive or sensitive).

To block instead of nudge, edit `hooks/claude/agent-do-pretooluse-check.py` to emit `permissionDecision: "deny"`. Claude Code enforces it; Codex does not. Do not block coord focus reminders; the agent must see them to act on them.

## Uninstalling

```bash
./install.sh --uninstall
```

Removes the symlink, breadcrumb, generated index (only when it carries the generator marker), and the agent-do hook wrappers from both `~/.claude/hooks/` and `~/.codex/hooks/`, touching nothing else in those directories. Hook entries in `~/.claude/settings.json` and `~/.codex/hooks.json` must be removed manually.
