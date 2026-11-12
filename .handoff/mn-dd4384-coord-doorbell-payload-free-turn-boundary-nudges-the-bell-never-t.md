---
workflow: 2
manna: mn-dd4384
track: null
source: null
base_commit: 51982db3f382c1e6403b3b977f51cb9c0adbfcb8
scope: 'coord doorbell: payload-free turn-boundary nudges — the bell, never the letter'
inputs: []
binding: sha256:62c8a22a85bc479d2c463cb976e893f814b338877a4c000eaf27b26744b276b5
---

# Handoff: coord doorbell: payload-free turn-boundary nudges — the bell, never the letter

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-dd4384
```

## Scope

coord doorbell: payload-free turn-boundary nudges — the bell, never the letter

## Inputs

- None declared.

## Work order

Ratified with Erik 2026-09-21 (holy-ghostty AIO session). The estate's coordination stays LEDGER-ONLY — no inboxes, no DMs, no message payloads in transit; that refusal is the differentiator (private agent mail is the design that always fails: hidden pairwise state, records dying with sessions, unauditable side channels). The one honest gap is attention latency: an agent learns the board changed only when it next looks. The doorbell closes it: (1) BELL — a payload-free nudge fired to a named session at its next turn boundary, saying only 'the ledger has entries concerning you; read coord'. No content, ever, so nothing can route around the board; the recipient reads the same public record everyone reads. (2) ROUTING — coord need add / drop add --for already address agents; the bell rides those writes: when the target is a live session, ring it. (3) DELIVERY — runtime-neutral via the lifecycle hooks agent-do already installs (claude, codex, opencode): a turn-boundary hook checks for pending rings and surfaces the nudge as context where the harness supports injection; where it only supports notification, surface it there; where neither, degrade silently to today's poll-at-pause behavior — the bell may only remove latency, never add a failure mode. VERIFY the codex hook surface against its live docs/config before choosing the mechanism — do not assume injection exists. (4) GUARDRAILS (doctrine, enforce in code where cheap): bells carry no payload (refuse a bell with content); workers may request contract changes via need but never self-amend acceptance criteria; a bell exchange is never a close — done still requires executed receipts. USE CASE that motivated it: a worker hits an easy-fix failure mid-claim, rings the orchestrator, they coordinate ON THE LEDGER (drops/needs), the item progresses under its original claim — replacing Erik hand-pasting failure reports between sessions. The no-reopen law is untouched: this serves LIVE claims only. Tests: ring lands at next turn boundary per harness; content-bearing bell refused; dead-session ring degrades silently; ledger entries remain the only substance. Acceptance: a worker in one session rings a coordinator in another on a real mid-claim blocker and the item progresses with zero human relay, all substance visible in coord for a third session.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-dd4384`.
4. Commit with `Manna: mn-dd4384` and run `agent-do manna done mn-dd4384` only after the work is verified.

## Builder verification, 2026-09-22

Outcome: local implementation and focused verification complete. Required
installed-host, real-session acceptance is still pending. Keep this item
`in_progress`; do not run `manna done` based on these offline fixtures.
The work order and its acceptance criteria above are unchanged.

Claim owner: `codex-01a0cb76199774d0`. Initial binding verified against the
canonical `manna state --json --cached-drift` item and the repository's
`workflow.rs::binding_material` normalization:
`sha256:88012d583e6f6c1f0681901ac73b27625b34145088a9883e5b4590d58f8ab5ef`.
Implementation started at `51982db3f382c1e6403b3b977f51cb9c0adbfcb8`.
Exact Coord path claims were established before edits; the unrelated
`mn-481318` board row and handoff are preserved and excluded from this commit.

### Changes

- `tools/agent-coord`: addressed need/drop writes set only a recipient bit in
  the existing Coord store, under its shared lock. Explicit `bell ring --for`
  refuses content arguments without echoing their contents. Dead, stopped,
  stale, and unknown recipients degrade to polling. Ring failures cannot fail
  committed ledger writes or renew recipient presence.
- `bell check --from-hook` and the shared Claude/Codex doorbell hook: match
  exact event session identities, emit one fixed nudge, coalesce rings, and
  consume atomically. Prompt context and one Stop continuation are supported;
  `stop_hook_active` prevents continuation loops. A two-second hook deadline
  expires silently before the five-second harness timeout.
- Addressed incoming needs are now visible in the recipient's public
  `coord interrupts` view. All request/response substance stays in needs and
  drops, available to an observer. No Manna lifecycle or acceptance mutation
  is performed by the bell.
- Updated Claude/Codex install and uninstall specifications, the Codex
  registration template, registry contracts, and generated reference docs.
  No installer, app, screenshot tool, or live agent-session launcher was run.

### Executed verification

All commands ran from `/Users/erik/Custom-Coding/agent-do`. Python dependency
commands used `PATH="$PWD/.venv/bin:$PATH"`.

| Command | Actual result |
| --- | --- |
| `python3 tests/test_coord.py` | Exit 0, `coord tests passed` |
| `python3 tests/test_coord_v2.py` | Exit 0, `coord v2 tests passed`, including offline worker/coordinator/observer fixtures, payload refusal, identity matching, dead/stopped/stale/reused-process fallback, corrupt/unwritable/busy stores, hung lookup deadline, concurrent writes/consumption, and hook registration |
| `python3 tests/test_install_specs.py` | Exit 0, 5 tests passed |
| `agent-do harness contracts validate` | Exit 0, 103/103 tools declared, 0 errors, 0 warnings; bounds: 15 gated sites, 0 errors (156 units remain inventoried under the existing authority, plus 8 shared-code caps without a declaration home) |
| `agent-do harness contracts drift --tool coord` | Exit 0, 0 declared-but-unimplemented verbs, 0 undocumented verbs |
| `bin/gen-tools-doc --check` | Exit 0, generated reference matches registry |
| `bash -n install.sh` | Exit 0, shell syntax valid; installer NOT executed |
| `python3 -m py_compile tools/agent-coord hooks/claude/agent-do-coord-doorbell.py tests/test_coord_v2.py` | Exit 0, Python syntax compiled; this is separate from executed suites above |
| `git diff --check` | Exit 0, no whitespace errors |

No app-hosted tests were compiled or executed. No root-wide test runner or
live/visual acceptance was run. No push or pull request was made.

### Runtime capability receipts and remaining acceptance

Official Codex documentation fetched on 2026-09-22 confirms
[UserPromptSubmit context injection](https://learn.chatgpt.com/docs/hooks#userpromptsubmit)
and [Stop continuation](https://learn.chatgpt.com/docs/hooks#stop).
[Claude's reference](https://code.claude.com/docs/en/hooks#stop) documents the
same Stop fields and loop guard. Local `~/.codex/config.toml` enables hooks,
but read-only inspection of `~/.codex/hooks.json` and
`~/.claude/settings.json` found no doorbell registration on either boundary.
Host configuration was not changed and the existing Codex `notify` chain was
not touched.

Contrary to the staging assumption, this checkout has no OpenCode hook/plugin
installer. OpenCode remains poll-only under the work order's degradation
rule; no automatic OpenCode delivery has been verified or claimed. The bell
does not wake or start idle sessions. A ring after the last hook waits until
the next supported turn boundary.

Needed next: coordinate hook installation/registration and one real
worker/coordinator/observer acceptance pass at close. The worker must hit a
real mid-claim blocker, put its substance in Coord, ring the coordinator,
receive the public ledger response, and progress under the original claim
with zero human relay. The observer must verify that all substance is visible
in Coord. Preserve original acceptance, claim ownership, and no-reopen rules.
Attach those executed receipts, reseal, and only then mark done. No
independent active coordinator was identified on this project's current Coord
board; the other active record belongs to this worker's same pane. The public
Coord need `mn-dd4384-live-acceptance` and a handoff drop addressed to the
`overseer` role now carry this closing dependency.

Lessons logged: 5 (new): `les-78edb1`, `les-470d17`, `les-969c59`,
`les-4206fb`, and `les-c1b0f4`. Decisions logged: 1 (new):
`dec-f03f56`. ZPC harvest was run; no automatic pattern rewrites were requested.
