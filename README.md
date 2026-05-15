# agent-do

<p align="center">
  <img src="assets/agent-do-logo.png" alt="agent-do logo" width="720" />
</p>

<p align="center"><strong>The outer harness for AI coding agents.</strong></p>

AI coding agents are strong inside a repository. They read files, write code, run
tests, and reason through local changes.

The hard part is everything outside that loop: browsers, authentication, cloud
services, databases, screenshots, design review, project memory, PR triage,
notifications, and the local machine itself.

`agent-do` gives agents one durable command contract for that outer world:

```bash
agent-do <tool> <command> [args...]
```

It looks like a CLI because the shell is the simplest contract every coding
agent can already use. But it is not primarily a human productivity CLI.

Humans install it, configure credentials, approve local-machine permissions, read
outputs, and occasionally run commands directly for debugging. In normal use, the
caller is the AI agent or its harness. The agent calls `agent-do` to browse,
authenticate, inspect services, review PRs, query data, coordinate with other
agents, and verify work without inventing one-off shell glue.

It is not a replacement for Claude Code, Codex, Cursor, or any other inner agent.
It is the operating layer around them: structured tools, shared credentials,
discoverability, readiness checks, hooks, and stateful workflows that make good
agent behavior easier to repeat.

## Why It Exists

Agents can improvise. That is useful until the session becomes a pile of custom
curl calls, one-off Playwright scripts, raw vendor CLIs, copied secrets, and
half-remembered setup steps.

`agent-do` narrows that surface.

- One command shape
- One registry of tools
- One readiness and bootstrap path
- One credential layer
- One discoverability layer
- One hook surface for nudges without hard-blocking work

The goal is not abstraction for its own sake. The goal is repeatable agency:
the agent should be able to inspect the world, act on it, verify the result, and
leave behind enough structure for the next agent to continue.

## Mental Model

Mature `agent-do` tools follow the same rhythm:

```text
Connect -> Snapshot -> Interact -> Verify -> Save
```

Snapshot is the hinge. An agent cannot reason well about a browser page, a
database schema, a cloud service, or an iOS screen unless it can first see the
current state in a structured way.

Example:

```bash
agent-do db connect mydb
agent-do db snapshot
agent-do db query "SELECT * FROM orders LIMIT 10"
agent-do db disconnect
```

Some tools are deep systems. Some are thin adapters. All of them aim at the same
outer contract.

## Install

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
```

The installer can symlink `agent-do` into `PATH`, install dependencies, and copy
agent hooks into place.

See [INTEGRATION.md](INTEGRATION.md) for Claude Code and Codex hook wiring.

## First Run

```bash
agent-do --health
agent-do bootstrap --recommend
agent-do bootstrap
```

`--health` checks whether the harness is usable. `bootstrap --recommend` shows
what stateful tools should be initialized for the current machine or repository.
`bootstrap` initializes the pieces that are actually needed.

## Core Commands

The examples below are the commands agents are expected to call. Humans can run
the same commands, but the design center is agentic execution.

When the agent knows the tool:

```bash
agent-do <tool> <command> [args...]
```

When the agent knows the goal but not the tool:

```bash
agent-do suggest "deploy this service"
agent-do suggest --project
agent-do find playwright
```

When setup needs credentials:

```bash
agent-do creds required render
agent-do creds store RENDER_API_KEY --stdin
agent-do creds check --tool render
```

When a human or harness wants natural-language routing:

```bash
agent-do -n "take an iOS screenshot"
agent-do --offline "check render logs"
agent-do --how "review PRs waiting for me"
```

## Common Workflows

These workflows are written as shell commands because that is the contract agents
can execute, log, and verify. They are examples of agent calls, not an expectation
that humans manually operate every tool.

### Browser Automation

```bash
agent-do browse open https://app.example.com
agent-do browse snapshot -i
agent-do browse fill @e3 "admin@example.com"
agent-do browse click @e7
agent-do browse wait --stable
```

For authenticated sessions:

```bash
agent-do browse login https://app.example.com
agent-do browse login done --save mysite
agent-do browse session load mysite
```

### External Docs And Project Memory

Use `context` for external reference material. `retrieve` is the agent-facing
entry point because it returns bounded snippets with freshness, version
currency, trust, and provenance metadata:

```bash
agent-do context retrieve "Stripe idempotency docs" --fresh --max-tokens 8000
agent-do context retrieve "TanStack Query v5 migration" --require-fresh --require-official
agent-do context retrieve "latest Next.js routing docs" --fresh --prefer-latest --max-tokens 8000
agent-do context fetch-llms stripe.com
agent-do context fetch-repo vercel/next.js docs/
agent-do context crawl https://nextjs.org/docs --limit 25
agent-do context search "payments api"
```

Register high-value sources when agents should be able to keep them current:

```bash
agent-do context add-source stripe https://stripe.com/llms.txt --kind llms --trust official --ttl 7d
agent-do context add-source next-docs https://github.com/vercel/next.js/tree/canary/docs --kind github-dir --trust official
agent-do context add-source next-web https://nextjs.org/docs --kind html-site --trust official --ecosystem npm --package next --doc-version latest
agent-do context sources sync --all
agent-do context maintain --limit 10
agent-do context versions sources
agent-do context versions outdated
```

HTML sources are first-class: raw HTML is preserved in the cache for provenance,
while extracted readable content is indexed and returned to agents. Version
currency is separate from HTTP freshness, so a cached page can be fresh but still
warn if it points at old major-version docs.
Use `versions sources` to check the configured source registry itself, including
sources that have not been crawled yet. Use `versions outdated` to check the
already indexed docs that agents can retrieve.

Background maintenance is opt-in. Print the launchd job before installing it:

```bash
agent-do context maintain schedule print
```

For a local visual status page:

```bash
agent-do context serve --port 8765
```

Use `zpc` for lessons learned in real work:

```bash
agent-do zpc init
agent-do zpc learn "deploying" "missing env var" "added .env.example" "always ship env templates" --tags "deploy,env"
agent-do zpc decide "Which DB?" --options "postgres,sqlite" --chosen postgres --rationale "team expertise" --confidence 0.9
```

### Cloud And Service Operations

```bash
agent-do render services
agent-do render logs my-service --since 1h
agent-do vercel deployments my-project
agent-do supabase projects
agent-do cloudflare dns example.com
```

### GitHub Review Work

```bash
agent-do gh inbox
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova
agent-do gh audit owner/repo#123 --reply --probe-deploys
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova --audit --replies --probe-deploys
```

`gh audit` inspects PR metadata, checks, unresolved threads, changed files, diff
content, lockfile blast radius, deployment hints, and optional Render/Vercel env
presence. It can draft engineering review text with concrete fix guidance.

### Visual QA

```bash
agent-do browse screenshot /tmp/ui.png
agent-do dpt score /tmp/ui.png
```

`dpt` scores a screenshot across perception rules and returns concrete UI
critique for agents doing frontend work.

### Multi-Agent Coordination

```bash
agent-do coord touch
agent-do coord focus set "private Render networking" --path recognition-oracle/render.yaml
agent-do coord claim recognition-oracle/render.yaml --reason "private Render blueprint wiring"
agent-do coord interrupts
```

`coord` is a shared state board, not an agent chat system. It tracks presence,
focus, claims, needs, publishes, and derived interruptions across parallel agents
working in the same project.

### Notifications

```bash
agent-do notify set-recipient me --sms +15551234567 --email me@example.com --prefer sms,email
agent-do notify me "Deploy complete" --via sms
agent-do notify templates
agent-do notify apply-template build_failed --recipient me
```

For visible desktop control, use the explicit live modifier:

```bash
agent-do +live(scope=desktop,ttl=15m) macos click @g5
```

## Tool Surface

There are 91 tools in the current catalog. Use `agent-do --list` for the complete
inventory and `agent-do <tool> --help` for command details.

| Category | Tools | What They Do |
|---|---|---|
| Browser | `browse`, `unbrowse` | Browser automation, auth sessions, API capture |
| Context | `context`, `zpc` | External docs, project memory, lessons, decisions |
| Credentials | `creds`, `auth` | Secure secrets and authenticated site state |
| GitHub | `gh`, `git`, `ci` | PR triage, review, merge, local git, checks |
| Cloud | `render`, `vercel`, `supabase`, `cloudflare`, `gcp`, `docker`, `k8s` | Service and infrastructure operations |
| Visual | `dpt`, `screen`, `vision`, `ocr` | Screenshots, UI critique, OCR, perception |
| Devices | `ios`, `android`, `macos`, `hardware` | Simulators, desktop automation, device control |
| Data | `db`, `excel`, `sheets`, `pdf`, `pdf2md` | Databases, spreadsheets, PDF workflows |
| Communication | `notify`, `email`, `sms`, `slack`, `meetings`, `resend` | Human notifications, inboxes, meetings, email ops |
| Agent Support | `coord`, `harness`, `spec`, `manna`, `sessions` | Coordination, observability, specs, issue tracking |

See [docs/TOOLS.md](docs/TOOLS.md) for a fuller tool map and workflow examples.

## Hooks And Nudges

Hooks are optional, but useful. They help agents choose structured `agent-do`
tools before falling back to raw shell glue.

The hook model is intentionally non-blocking by default:

- suggest relevant tools at session start
- route fuzzy user prompts to likely `agent-do` commands
- remind agents to check completion before drifting into optional polish
- surface coordination context when another active agent is in the same project
- record hook outcome telemetry so nudges can be measured instead of guessed

See [INTEGRATION.md](INTEGRATION.md) for installation and hook behavior.

## Architecture

At runtime, the core is plain:

```text
agent-do <tool> <command>
        |
        v
tools/agent-<name>
```

The supporting layers are:

- `registry.yaml` for tool metadata and routing hints
- `tools/` for tool implementations
- `lib/` for shared helpers
- `hooks/` for Claude Code and Codex integration
- `bin/` for routing, health, bootstrap, and harness commands

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system map.

## Requirements

- Python 3.10+
- Node.js 18+ for browser tooling
- Rust for `manna`
- `tmux` for terminal-session tooling
- Optional API keys for providers you want to use

Install Python dependencies with:

```bash
pip install -r requirements.txt
```

## Security

Do not put secrets in repos, logs, screenshots, or review comments.

Use `agent-do creds` for API keys and tokens:

```bash
agent-do creds store RENDER_API_KEY --stdin
agent-do creds store VERCEL_ACCESS_TOKEN --stdin
agent-do creds check --tool render
```

`agent-do context` fetches public reference material without browser cookies or
saved auth state. HTML sources are cached locally with raw provenance plus
extracted searchable text. Agent-facing context output redacts common token, key,
secret, signature, password, auth, and credential query parameters.

See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Development

Run the root smoke suite:

```bash
./test.sh
```

Selected deeper checks:

```bash
cd tools/agent-browse && npm test
cd tools/agent-manna && cargo test
bash tools/agent-context/test/integration.sh
bash tools/agent-manna/test/integration.sh
```

Contribution guidance lives in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
