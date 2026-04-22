# agent-do coord

Design for a native agent-to-agent coordination tool inside `agent-do`.

This is a forward design document. It describes a proposed tool and storage model. It does not describe current shipped behavior.

## Purpose

`agent-do` already has nearby surfaces:

- `agent` can spawn and control agent sessions in tmux
- `swarm` can orchestrate multi-agent runs from the top down
- `manna` can coordinate issue execution and dependency blocking
- `zpc` can store durable lessons and decisions
- `notify` can alert humans across channels

What is still missing is a simple, local-first way for agents already running in separate sessions to coordinate directly about active work:

- hand off findings
- ask another agent a scoped question
- reply with structured review notes
- acknowledge receipt
- avoid touching the same file blindly

Today that often degenerates into humans copy-pasting large blocks between agents. `agent-do coord` should absorb that.

## Product Thesis

The tool should be:

- project-scoped
- local-first
- deterministic
- structured
- scriptable with `--json`
- transport-agnostic at the core

It should not be a chat app. It should be an engineering coordination mailbox.

## Why This Belongs In agent-do

This is a strong fit for `agent-do` because it extends the same outer-harness pattern:

- convert improvised operator glue into a stable CLI contract
- keep state local and reviewable
- reduce brittle dependence on tmux scraping or human copy/paste
- make coordination explicit enough that hooks and future tooling can reason about it

Without a native coordination surface, agents can still talk indirectly through humans, shared notes, or prompt injection into each other’s tmux sessions. That is useful, but it is not reliable.

## Current Repo Boundary

Today:

- `agent-do agent` is manager-style control of tmux-backed agent sessions
- `agent-do swarm` is orchestration, not peer mailboxing
- `agent-do notify` is outbound communication to humans and external providers
- `agent-do manna` is issue tracking, not conversational handoff state

The missing layer is peer coordination between active sessions in the same project.

## Non-Goals

`agent-do coord` should not:

- replace `agent-do agent` as the tmux control surface
- replace `manna` as the issue tracker
- replace `zpc` as durable memory
- require Telegram, Slack, Discord, or any networked service in v1
- use prompt injection into another agent terminal as the canonical delivery model
- become an always-on daemon in v1

## Lessons From OpenClaw

OpenClaw is useful here for architecture lessons, not for transport choice.

Useful lessons:

- separate `agent identity` from `transport`
- keep routing deterministic and host-controlled
- make session keys and queue behavior explicit
- treat external messaging surfaces as untrusted and optional

Important anti-lesson:

- do not make Telegram or any external chat system the source of truth for local coordination

Why not Telegram as the coordination backend:

- it is external and internet-dependent
- it adds credentials, bot/account setup, and policy overhead
- it couples message semantics to a third-party transport
- it makes project-scoped local handoff harder, not easier
- it creates unnecessary privacy and security exposure for repo details

So the correct design is:

- local canonical mailbox first
- external bridges later

## Core Model

The core unit should be a project-local coordination mailbox.

Each project mailbox contains:

- agent identities
- aliases
- messages
- threads
- acknowledgements
- optional claims

This is not “messages between terminals.” It is “structured coordination events inside one project.”

## Storage Model

Canonical storage should prefer git-local state when available:

```text
.git/agent-do/coord/
```

Fallback for non-git directories:

```text
~/.agent-do/projects/<project-hash>/coord/
```

Proposed layout:

```text
coord/
├── config.json
├── agents.json
├── inbox/
│   ├── 2026-04-22T16-34-10Z_handoff_01.json
│   ├── 2026-04-22T16-35-02Z_question_02.json
│   └── ...
├── threads/
│   ├── thread_abc123.json
│   └── ...
├── claims.json
└── state.json
```

Why this root:

- same project folder naturally shares the same mailbox
- state stays local to the work, not global to the machine
- nothing lands in tracked repo files by default
- agents in separate tmux sessions can coordinate without extra setup

## Identity Model

Each active agent needs a stable local identity.

Identity derivation order:

1. `CODEX_THREAD_ID`
2. Claude-style thread/session variables when present
3. `TMUX_PANE`
4. hostname + pid fallback

Examples:

- `codex-019d79125a477c01`
- `tmux-58`
- `host-mbp-42191`

Optional aliases should be supported:

```bash
agent-do coord alias reviewer
agent-do coord alias infra
```

That lets humans and peer agents target `reviewer` instead of opaque IDs.

## Message Model

Messages should be structured JSON, not only freeform text.

Minimum schema:

```json
{
  "id": "msg_2026-04-22T16:34:10Z_01",
  "thread_id": "thread_abc123",
  "kind": "handoff",
  "from": "codex-019d79125a477c01",
  "to": ["infra"],
  "subject": "generation cutover local verification",
  "body": "Local verification is done...",
  "refs": [
    "recognition-oracle/app/api/generate/route.ts",
    "commit:78541cf"
  ],
  "checks": [
    "cd recognition-oracle && RESEND_API_KEY=re_dummy npm run build"
  ],
  "next": [
    "publish dm-sdk 1.2.2",
    "wire private Render networking"
  ],
  "created_at": "2026-04-22T16:34:10Z",
  "acked_at": null,
  "reply_to": null
}
```

Suggested message kinds:

- `handoff`
- `question`
- `reply`
- `status`
- `review`
- `claim`
- `release`
- `broadcast`

These are closer to real engineering coordination than generic “chat.”

## Command Surface

### Identity and Discovery

```bash
agent-do coord whoami
agent-do coord peers
agent-do coord alias <name>
agent-do coord aliases
```

### Messaging

```bash
agent-do coord send <peer> --subject <text> --body <text>
agent-do coord send <peer> --subject <text> --body-file <path>
agent-do coord handoff <peer> --summary <text>
agent-do coord ask <peer> --question <text>
agent-do coord reply <message-id> --body <text>
agent-do coord broadcast --subject <text> --body <text>
```

### Inbox

```bash
agent-do coord inbox
agent-do coord read <message-id>
agent-do coord wait
agent-do coord ack <message-id>
agent-do coord threads
agent-do coord thread <thread-id>
```

### Claims

```bash
agent-do coord claim <path-or-key>
agent-do coord release <path-or-key>
agent-do coord claims
```

### Hygiene

```bash
agent-do coord archive <message-id>
agent-do coord gc
```

## Output Shape

Every read-oriented command should support `--json`.

Human output should stay concise and mailbox-like:

```text
INBOX
msg_01  handoff  from:infra  subject:generation cutover local verification
msg_02  question from:reviewer subject:does render.yaml branch need hotfix?
```

Structured output should preserve:

- ids
- thread relationships
- ack status
- timestamps
- refs/checks/next lists

## Routing and Delivery Rules

Routing must stay deterministic.

- direct send to one peer -> one mailbox event
- broadcast -> one event per recipient, or one multi-recipient event with explicit fanout metadata
- replies inherit `thread_id`
- `ack` only changes acknowledgement state; it does not mutate original body content

The model should not choose the destination implicitly. The host CLI and arguments should.

## Queue and Concurrency Model

The coordination store should not have one global shared lane.

V1 should support at least:

- append-only message creation
- concurrent readers
- safe ack/update semantics

This can be done with simple per-message JSON files plus file-locking around:

- alias updates
- claim updates
- state/index writes

Important design rule:

- per-thread coordination should not block unrelated threads

This is one of the main lessons from systems that tie everything to one transport queue.

## Claims

Claims are not identical to messages, but they belong in the same tool.

Purpose:

- reduce accidental overlap on files, paths, or work items
- make “I am touching this” explicit

Suggested claim shape:

```json
{
  "key": "recognition-oracle/render.yaml",
  "owner": "infra",
  "reason": "private Render blueprint wiring",
  "created_at": "2026-04-22T16:40:00Z",
  "expires_at": null
}
```

Claims should be advisory by default, not hard locks.

That matches how engineering work actually flows:

- warn first
- let humans decide when overlap is acceptable

## Relationship To Existing Tools

### `agent`

`coord` should not require that the peer was spawned by `agent-do agent`, but it should integrate cleanly when it was.

Useful future integrations:

- map `agent-do agent list` sessions to coord peers
- show `coord` alias next to session name
- optional “new message” poke in tmux

### `swarm`

`swarm` remains top-down orchestration.

`coord` becomes the peer mailbox a swarm can rely on for:

- phase handoffs
- reviews
- findings
- claims

### `manna`

`manna` tracks issues and dependencies.

`coord` tracks conversational engineering state between active agents.

The two should complement each other, not merge.

### `notify`

`notify` is for human-facing alerts.

`coord` is for agent-facing coordination.

One useful future bridge:

- `coord --notify` or rule-based escalation when an unread message is blocking work

## tmux Integration

tmux integration should be secondary, not canonical.

Good:

- show a short tmux message that a new coord message arrived
- resolve a peer alias to a known tmux-backed agent session

Bad:

- inject the full handoff directly into another agent terminal as the only delivery path

Reason:

- tmux prompt injection is brittle
- prompt state is not deterministic
- delivery and acknowledgement become hard to reason about

So v1 should store to mailbox first. Any tmux poke is just a convenience.

## External Bridges

External messaging systems can be useful later, but only as bridges.

Possible phase-two bridges:

- Telegram
- Slack
- Discord
- email

Bridge principle:

- canonical truth remains local
- bridges mirror or notify
- bridges do not become the source of truth

So a future Telegram integration should look like:

```bash
agent-do coord bridge telegram enable ...
agent-do coord send infra --bridge telegram
```

not:

- “Telegram is where coord messages live”

## v1 Success Criteria

`agent-do coord` is successful in v1 if:

- two agents in separate tmux sessions can exchange structured handoffs without human copy/paste
- each agent can discover its own identity and inbox
- messages support refs, checks, and next steps
- acknowledgements and replies work
- advisory claims reduce accidental overlap
- the system works fully offline and locally

## v1 Non-Requirements

These are explicitly not required for the first shipped version:

- Telegram or Slack bridge
- remote machine federation
- live streaming chat UI
- hard locks on files
- daemonized background worker
- end-to-end encryption beyond local filesystem permissions

## Suggested Implementation Shape

Likely tool home:

```text
tools/agent-coord
```

Likely language:

- Python for data model, file locking, and JSON handling
- small Bash wrapper if needed for consistency with other tools

Tests should cover:

- identity derivation
- project-root mailbox resolution
- send/read/reply/ack lifecycle
- claim/release semantics
- concurrent write safety
- alias resolution

## Recommendation

Build `agent-do coord` as a real tool.

Do not build Telegram-first coordination.
Do not build prompt-injection-first coordination.

The correct order is:

1. local canonical mailbox
2. structured handoff and claim model
3. tmux convenience integration
4. optional external bridges later
