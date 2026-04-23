# agent-do coord

Current design for `agent-do coord`.

`coord` is not an agent mailbox. It is a project-local state and interrupt broker for parallel agent work inside one repo.

## Product Thesis

The useful coordination signals are:

- contention: two active agents are touching overlapping paths
- dependency: one agent is waiting on an artifact another agent published
- novelty: something relevant changed since the current agent last checked

If none of those are true, agents should keep working and `coord` should stay quiet.

## Scope

`coord` owns:

- short-lived presence leases
- current focus declarations
- advisory claims
- dependency declarations
- published artifacts
- derived interrupts

`coord` does not own:

- issue tracking (`manna`)
- durable lessons (`zpc`)
- human notifications (`notify`)
- tmux control (`agent`)
- agent chat or transcript history

## Storage

Canonical storage prefers git-local state:

```text
.git/agent-do/coord/
```

Fallback for non-git directories:

```text
~/.agent-do/projects/<project-hash>/coord/
```

Current files:

```text
coord/
├── agents.json
├── focus.json
├── claims.json
├── needs.json
├── publishes.json
└── events.jsonl
```

## Command Surface

Identity and presence:

```bash
agent-do coord touch
agent-do coord whoami
agent-do coord alias <name>
agent-do coord aliases
agent-do coord peers [--all]
agent-do coord status
agent-do coord interrupts [--mark-seen] [--limit N]
```

State:

```bash
agent-do coord focus set "<goal>" --path <path> [--path ...]
agent-do coord focus show [peer]
agent-do coord focus clear

agent-do coord claim <path> [--reason <text>] [--strength soft|strong]
agent-do coord release <path>
agent-do coord claims

agent-do coord need add <key> --why "<reason>" [--from <peer>]
agent-do coord need list [--all]
agent-do coord need clear <key>

agent-do coord publish add <key> --status <status> --summary "<text>" [--ref <ref> ...]
agent-do coord publish clear <key>
agent-do coord publishes
```

## Presence Model

Presence is lease-based:

- `active`: lease has not expired
- `idle`: lease expired, but the agent was seen recently enough to keep in project history
- `stale`: old enough to hide by default

Defaults:

- `AGENT_DO_COORD_ACTIVE_SECONDS=900`
- `AGENT_DO_COORD_IDLE_SECONDS=1209600`

## Hooks

SessionStart:

- renews coord presence
- checks interrupts
- injects `Coord Interrupts` only if there is a real interrupt
- otherwise injects `Coord Focus Reminder` only if active peers exist and current focus is empty

UserPromptSubmit:

- keeps existing tool routing
- adds coord context when the prompt explicitly concerns other agents or conflicts
- if `cwd` is available, renews presence and prefers real interrupts over generic peer reminders

## Success Criteria

`coord` is doing its job when:

- agents can declare focus without human copy/paste
- overlapping work produces a contention interrupt
- a published artifact satisfies another agent’s need
- relevant changes surface as novelty instead of forcing agents to poll transcripts
- hooks stay quiet when there is no real interrupt
