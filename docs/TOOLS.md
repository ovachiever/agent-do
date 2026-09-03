# agent-do Tool Reference

GENERATED FILE. Edit registry.yaml, not this file.
Regenerate with: `bin/gen-tools-doc`

Every tool shares one command shape:

```bash
agent-do <tool> <command> [args...]
```

Discovery: `agent-do --list`, `agent-do <tool> --help`,
`agent-do find <keyword>`, `agent-do suggest "task"`.

Concurrency: `read` tools are safe to run in parallel, `write` tools
mutate state and run serially, `mixed` tools carry both kinds of
commands. Per-verb truth lives in each tool's safety note, derived
from its `contracts:` block: verbs touching only the snapshot and
verify beats are read-only; connect, interact, and save verbs write.

## Summary (103 tools)

| Tool | Description | Concurrency | Commands |
|------|-------------|-------------|----------|
| [3d](#3d) | 3D modeling and rendering control | mixed | 4 |
| [agent](#agent) | Control AI coding agent sessions (Claude, OpenCode, Droid, Amp) | mixed | 10 |
| [android](#android) | Control Android Emulator | mixed | 5 |
| [api](#api) | API testing plus canonical API integration templates for agents | mixed | 13 |
| [appleevents](#appleevents) | Control scriptable macOS apps through AppleEvents, AppleScript, and JXA | mixed | 9 |
| [audio](#audio) | Audio processing | mixed | 3 |
| [auth](#auth) | Site-level authentication orchestration over encrypted session bundles, browser import, and secure credentials | mixed | 13 |
| [betterstack](#betterstack) | Better Stack Uptime monitoring, incidents, heartbeats, status pages, and on-call | mixed | 14 |
| [bluetooth](#bluetooth) | Bluetooth control | mixed | 3 |
| [brief](#brief) | Estate briefing engine — joins GitHub PRs, the manna board, live coord sessions, and git into ranked threads, a delta since last look, one-tap suggestions carried as data, and a receipts-grounded paragraph | mixed | 10 |
| [browse](#browse) | AI-first headless browser automation with @ref element selection, SSO/MFA login handoff, persistent sessions | mixed | 20 |
| [burp](#burp) | Burp Suite automation | mixed | 4 |
| [cad](#cad) | CAD file operations | mixed | 4 |
| [calendar](#calendar) | Control calendar | mixed | 3 |
| [ci](#ci) | Control CI/CD pipelines | write | 4 |
| [clerk](#clerk) | Clerk authentication platform — users, organizations, sessions, OAuth apps, enterprise SSO, JWT templates, roles | mixed | 14 |
| [clipboard](#clipboard) | Cross-app clipboard management | mixed | 4 |
| [cloud](#cloud) | Control cloud providers (AWS, GCP, Azure) | mixed | 3 |
| [cloudflare](#cloudflare) | Cloudflare account management — zones, analytics (GraphQL), DNS, Workers, Pages, R2, security events | mixed | 18 |
| [coderabbit](#coderabbit) | Local AI diff review via CodeRabbit CLI — review uncommitted changes, staged diffs, or branch diffs before opening a PR | mixed | 6 |
| [colab](#colab) | Google Colab notebook management | mixed | 4 |
| [context](#context) | Knowledge library — fetch, index, and serve external reference docs. Complementary to zpc (experience journal). | mixed | 27 |
| [coord](#coord) | Project-local agent state and interrupt broker | mixed | 23 |
| [creds](#creds) | Secure credential storage and resolution for agent-do tools | mixed | 8 |
| [cronitor](#cronitor) | Cronitor scheduled job and uptime monitoring | mixed | 11 |
| [datadog](#datadog) | Datadog observability — monitors, logs, metrics, incidents, dashboards, and SLOs with cross-tool incident response | mixed | 23 |
| [db](#db) | Control database clients | mixed | 5 |
| [debug](#debug) | Control debuggers | read | 5 |
| [discord](#discord) | Control Discord | mixed | 2 |
| [dns](#dns) | DNS lookups and resolution diagnostics (read-only; record writes live in namecheap/cloudflare) | read | 2 |
| [docker](#docker) | Control Docker containers | write | 7 |
| [dpt](#dpt) | Design Perception Tensor - automated design quality scoring | read | 7 |
| [email](#email) | Control email | mixed | 12 |
| [eval](#eval) | LLM output evaluation and testing | read | 4 |
| [excel](#excel) | AI-first Excel CLI for workbook automation | mixed | 11 |
| [figma](#figma) | Control Figma | read | 3 |
| [gcp](#gcp) | Google Cloud Platform management — REST API for projects, APIs, secrets, service accounts + Console automation for OAuth credentials | mixed | 19 |
| [gh](#gh) | GitHub repository, pull request, review, and merge work-state across accessible repos | mixed | 24 |
| [ghidra](#ghidra) | Ghidra reverse engineering automation | read | 4 |
| [git](#git) | Guarded local Git operations for staged commits, worktrees, snapshots, conflicts, and recovery | mixed | 19 |
| [handbrake](#handbrake) | Convert ripped video (MKV) to Plex-ready MP4 via HandBrakeCLI — probe a file's titles and streams, list encode presets, transcode single files or whole directories with skip/overwrite handling, and verify .mp4 outputs | mixed | 7 |
| [hardware](#hardware) | Unified hardware device control across serial, bluetooth, USB, printers, and MIDI | mixed | 6 |
| [harness](#harness) | Observable agent-do harness inventory, evidence, and change-manifest front door | mixed | 8 |
| [homekit](#homekit) | HomeKit/smart home control | mixed | 3 |
| [ide](#ide) | Control VS Code/Cursor editor | read | 5 |
| [image](#image) | Image processing | mixed | 3 |
| [ios](#ios) | Control iOS Simulator | mixed | 10 |
| [jupyter](#jupyter) | Control Jupyter notebooks | mixed | 4 |
| [k8s](#k8s) | Control Kubernetes clusters | write | 5 |
| [lab](#lab) | JupyterLab management | mixed | 4 |
| [latex](#latex) | LaTeX document compilation | write | 4 |
| [learn](#learn) | Learning and pattern improvement | write | 4 |
| [linear](#linear) | Control Linear | mixed | 3 |
| [logs](#logs) | Control log aggregation | read | 3 |
| [macos](#macos) | Control native macOS desktop applications via accessibility APIs | mixed | 6 |
| [manna](#manna) | Git-backed issue tracking with generated, bidirectionally linked handoff work orders | write | 27 |
| [meet](#meet) | Google Meet control | mixed | 4 |
| [meetings](#meetings) | Unified enterprise meeting orchestration across Zoom, Google Meet, and Microsoft Teams | mixed | 14 |
| [memory](#memory) | Persistent memory and context | mixed | 4 |
| [metrics](#metrics) | System metrics and monitoring (CPU, memory, disk, network, processes) | read | 8 |
| [midi](#midi) | MIDI control | mixed | 3 |
| [models](#models) | Capability-aware model roles for agent-do's internal LLM calls | mixed | 3 |
| [namecheap](#namecheap) | Namecheap domain and DNS management — domains, DNS records (safe upsert with exact verification), nameservers, SSL, availability | write | 13 |
| [network](#network) | Network diagnostics | read | 4 |
| [notion](#notion) | Notion team operating layer for pages, data sources, tasks, decisions, handoffs, comments, cache, and webhooks | mixed | 22 |
| [obsidian](#obsidian) | Obsidian vault integration with a local SQLite vault index plus official Obsidian CLI fallback | mixed | 31 |
| [ocr](#ocr) | Screen text extraction | read | 4 |
| [okta](#okta) | Okta tenant management — applications (OIDC/SAML), SSO configuration, users, groups, authorization servers, system logs | mixed | 14 |
| [pdf](#pdf) | Control PDF operations | mixed | 4 |
| [pdf2md](#pdf2md) | Convert PDF files to Markdown | read | 3 |
| [printer](#printer) | Printer control | write | 3 |
| [prompt](#prompt) | Prompt management and templating | read | 4 |
| [psql](#psql) | PostgreSQL CLI wrapper for AI agents over the native psql binary | mixed | 24 |
| [render](#render) | Full-surface Render.com control — services (create/update/delete/lifecycle), deploys (trigger/show/cancel/rollback), one-off jobs, cron runs, env vars + secret files, env groups, postgres lifecycle + creds + recovery, key value, blueprints, custom domains + headers + routes, persistent disks + snapshots, dedicated IPs, registry credentials, projects + environments, webhooks, notifications, maintenance, audit logs, owners, observability (logs + metrics) | write | 46 |
| [repl](#repl) | Control interactive REPLs (Python, Node, psql, etc.) | mixed | 5 |
| [resend](#resend) | Resend domain management and DNS verification — exact records, verification state, and public DNS checks | mixed | 7 |
| [screen](#screen) | Vision-based screen perception and control (macOS) | mixed | 9 |
| [sentry](#sentry) | Sentry error tracking, issue management, alerts, and releases | mixed | 12 |
| [serial](#serial) | Serial port communication | mixed | 3 |
| [sessions](#sessions) | Search and retrieve AI coding session history | read | 9 |
| [sheets](#sheets) | Control Google Sheets | mixed | 3 |
| [slack](#slack) | Control Slack | mixed | 5 |
| [sms](#sms) | SMS messaging | write | 8 |
| [spec](#spec) | Repo-local specifications and change artifacts for intended behavior, change deltas, and archive readiness | mixed | 5 |
| [ssh](#ssh) | Control remote server sessions | write | 5 |
| [substack](#substack) | Draft and publish Substack essays through the editor API — markdown to ProseMirror drafts, auth rides a saved agent-browse session | mixed | 11 |
| [supabase](#supabase) | Supabase project lifecycle + management + data access (full Management API, REST API, SQL, and agent-db) | write | 64 |
| [swarm](#swarm) | Multi-agent orchestration | write | 4 |
| [tail](#tail) | Wrap dev commands, capture output to log files for AI agents | read | 11 |
| [teams](#teams) | Microsoft Teams control | mixed | 4 |
| [transcribe](#transcribe) | Source-to-transcript ingestion pipeline (YouTube URLs, authenticated downloads, Whisper API + local Whisper + caption fallbacks, batch, cost preflight, structured JSON) | mixed | 4 |
| [tui](#tui) | Control any terminal/TUI application via tmux | mixed | 7 |
| [unbrowse](#unbrowse) | Standalone API traffic capture → reusable curl-based skills. For SSO/MFA → headless handoff, use browse login instead. | mixed | 9 |
| [usb](#usb) | USB device management | mixed | 3 |
| [vector](#vector) | Operate Versova Vector portfolio command center | write | 16 |
| [vercel](#vercel) | Control Vercel projects, deployments, domains, and env vars | write | 14 |
| [video](#video) | Video processing | mixed | 3 |
| [vision](#vision) | AI-first visual perception with object detection, OCR, and face detection | read | 7 |
| [vm](#vm) | Control virtual machines | write | 4 |
| [voice](#voice) | Voice synthesis and recognition | write | 4 |
| [wireshark](#wireshark) | Network packet capture and analysis | read | 4 |
| [zoom](#zoom) | Zoom meeting control | mixed | 5 |
| [zpc](#zpc) | Experience journal — structured lessons, decisions, patterns per project. Complementary to context (knowledge library). | mixed | 16 |

## Tools

### 3d

3D modeling and rendering control

Concurrency: `mixed`

**Capabilities**

- view 3D files
- convert between formats
- render to image
- get model info

**Commands**

- `view`: Open 3D file in viewer
- `convert`: Convert between formats
- `render`: Render to image
- `info`: Show model information

**Examples**

```bash
# view model.obj
agent-do 3d view model.obj
# convert model.stl to obj
agent-do 3d convert model.stl model.obj
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `info`
- Write (connect/interact/save): `convert`, `render`, `view`

### agent

Control AI coding agent sessions (Claude, OpenCode, Droid, Amp)

Concurrency: `mixed`

**Capabilities**

- spawn agent sessions in tmux
- send prompts to agents
- monitor agent status (ready/busy)
- accept/reject changes
- capture screen output

**Commands**

- `spawn`: Start agent: spawn \<type> [--session \<name>] [--dir \<path>]
- `list`: List active agent sessions
- `send`: Send prompt: send \<prompt> [--session \<name>] [--nowait]
- `snapshot`: Capture screen: snapshot [--session \<name>] [--json]
- `status`: Check status: status [--session \<name>]
- `accept`: Accept changes (press y)
- `reject`: Reject changes (press n)
- `cancel`: Cancel operation (Ctrl+C)
- `kill`: Kill session: kill [--session \<name>]
- `attach`: Get tmux attach command

**Examples**

```bash
# start Claude in my project
agent-do agent spawn claude --dir ~/myproject
# send a task to the agent
agent-do agent send 'fix the login bug'
# check if the agent is done
agent-do agent status
# accept the agent's changes
agent-do agent accept
# list running agents
agent-do agent list
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `snapshot`, `status`
- Write (connect/interact/save): `accept`, `attach`, `cancel`, `kill`, `reject`, `send`, `spawn`
- destructive (irreversible data loss; confirm before auto-running): `kill`

### android

Control Android Emulator

Concurrency: `mixed`

**Capabilities**

- tap/swipe gestures
- take screenshots
- install/launch apps
- send intents

**Commands**

- `tap`: Tap at coordinates
- `screenshot`: Capture emulator screen
- `launch`: Launch an app
- `install`: Install APK
- `shell`: Run adb shell command

**Examples**

```bash
# screenshot the Android emulator
agent-do android screenshot
# launch Chrome on Android
agent-do android launch com.android.chrome
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `screenshot`
- Write (connect/interact/save): `install`, `launch`, `tap`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `shell`

### api

API testing plus canonical API integration templates for agents

Concurrency: `mixed`

**Capabilities**

- make HTTP requests
- inspect API state
- list canonical API templates
- show canonical API template source
- scaffold project API clients from templates
- save project integrations as canonical templates

**Commands**

- `list`: List canonical API templates
- `show`: Show template metadata and source
- `scaffold`: Write a project integration from a template
- `save`: Save a project integration as canonical
- `get`: HTTP GET request
- `post`: HTTP POST request
- `put`: HTTP PUT request
- `patch`: HTTP PATCH request
- `delete`: HTTP DELETE request
- `head`: HTTP HEAD request
- `snapshot`: Show API environments and request history
- `history`: Show recent request history
- `env`: Set or show base URL environments

**Examples**

```bash
# build a canonical Anthropic client
agent-do api scaffold anthropic --target ./lib/llm.py
# save this Anthropic client as the standard
agent-do api save anthropic --from ./lib/llm.py
# GET /api/users
agent-do api get /api/users
# POST to /api/login
agent-do api post /api/login
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `env`, `history`, `list`, `show`, `snapshot`
- Write (connect/interact/save): `delete`, `get`, `head`, `patch`, `post`, `put`, `save`, `scaffold`

### appleevents

Control scriptable macOS apps through AppleEvents, AppleScript, and JXA

Concurrency: `mixed`

**Capabilities**

- inspect app scripting dictionaries
- compile AppleScript and JXA safely before running
- run live-gated AppleEvent scripts
- diagnose macOS Automation permission state with explicit live probes

**Commands**

- `apps`: List scriptability hints from installed app bundle metadata
- `probe`: Resolve an app and inspect static scriptability and dictionary metadata
- `dictionary`: Show an app scripting dictionary as JSON, Markdown, or raw SDEF XML
- `terms`: Search commands, classes, and properties from an app dictionary
- `compile`: Compile-check AppleScript or JXA without running it
- `permissions`: Live-gated Automation permission probe by sending a benign event
- `run`: Live-gated AppleScript or JXA execution
- `tell`: Terse target-app sugar over the shared run path
- `cache`: Inspect or clear cached scripting dictionaries

**Examples**

```bash
# inspect Finder scripting support
agent-do appleevents probe Finder
# show Xcode's scripting dictionary
agent-do appleevents dictionary Xcode --format markdown
# compile-check AppleScript from stdin
agent-do appleevents compile --language applescript --stdin
# test Automation permission for Finder
agent-do +live(scope=desktop,ttl=5m) appleevents permissions Finder
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `apps`, `compile`, `dictionary`, `permissions`, `probe`, `terms`
- Write (connect/interact/save): `cache`
- destructive (irreversible data loss; confirm before auto-running): `cache`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `run`, `tell`
- polymorphic (beat decided by payload or flag at call time): `cache`
- composite (one call performs several beats internally): `permissions`

### audio

Audio processing

Concurrency: `mixed`

**Capabilities**

- convert formats
- trim/merge
- transcribe

**Commands**

- `convert`: Convert format
- `trim`: Trim audio
- `transcribe`: Transcribe audio (local file, local Whisper only — for URL/API/batch use agent-transcribe)

**Examples**

```bash
# transcribe recording.mp3
agent-do audio transcribe recording.mp3
```

**Safety (from contracts)**

- Write (connect/interact/save): `convert`, `transcribe`, `trim`
- long_running (daemon/stream/session; may never return): `transcribe`
- composite (one call performs several beats internally): `transcribe`

### auth

Site-level authentication orchestration over encrypted session bundles, browser import, and secure credentials

Concurrency: `mixed`

**Capabilities**

- create site auth profiles with validation rules and strategy ladders
- reuse saved authenticated browser state before trying fresh login
- import cookies and storage from a real authenticated browser profile
- drive provider-aware site login with secrets resolved from env or agent-do creds
- handle GitHub and Google login shapes before falling back to generic form fill
- resolve TOTP secrets from agent-do creds when login flows require one-time codes
- consume provider backup codes from secure storage when recovery-code branches appear
- wait for mailbox-delivered verification codes or magic links through agent-do email
- wait for SMS-delivered verification codes or magic links through agent-do sms
- validate whether saved authenticated state is still usable
- inspect the live auth branch and classify checkpoints before retrying
- return next-step auth guidance for agents
- reuse upstream GitHub or Google auth to complete SSO into another site
- inherit upstream GitHub or Google TOTP and backup-code config when a provider-backed site hits those checkpoints
- step through provider account choosers and consent screens with persisted checkpoint metadata
- surface passkey or security-key checkpoints as explicit action-required states
- open a real system browser for anti-bot or remote human-visible login flows, then import validated state back into auth storage

**Commands**

- `init`: Initialize a site profile: init \<site> [--domain D] [--login-url URL] [--provider generic|github|google] [--email-code|--magic-link|--sms-code|--sms-link]
- `list`: List configured auth profiles: list
- `show`: Show one auth profile: show \<site>
- `status`: Show auth state: status \<site> [--name default]
- `probe`: Inspect the current auth checkpoint branch: probe \<site> [--load]
- `advance`: Advance one safe checkpoint step and re-probe, preferring visible in-browser alternate methods: advance \<site> [--action ACTION] [--timeout 60]
- `ensure`: Run the strategy ladder: ensure \<site> [--strategy saved-session|browser-import|site-creds|provider-refresh|interactive] [--timeout 180]
- `save`: Save current authenticated browser state: save \<site> [--name default]
- `load`: Load saved browser auth state: load \<site> [--name default]
- `import-browser`: Import cookies and browser storage from a real browser: import-browser \<site> [--browser comet] [--domain .example.com] (cookies, local/session storage, and best-effort IndexedDB)
- `clear`: Clear saved auth state: clear \<site> [--all]
- `validate`: Validate signed-in state: validate \<site>
- `instructions`: Next-step guidance: instructions \<site>

**Examples**

```bash
# create a github auth profile
agent-do auth init github
# create a github sso profile for another site
agent-do auth init widgethub --domain app.example.com --provider github
# reuse saved github auth
agent-do auth ensure github
# reuse github auth to sign into another app
agent-do auth ensure widgethub --strategy provider-refresh
# open the real browser for a cloudflare login and import the authenticated state
agent-do auth ensure cloudflare --strategy interactive --timeout 300
# initialize a site that sends email verification codes
agent-do auth init widgethub --domain app.example.com --email-code --email-from WidgetHub --email-subject "verification code" --email-account Work --email-mailbox Inbox
# initialize a site that texts verification codes
agent-do auth init widgethub --domain app.example.com --sms-code --sms-from WidgetHub --sms-contains "verification"
# log into github with saved creds and totp
agent-do auth ensure github --strategy site-creds
# log into google with saved creds and totp
agent-do auth ensure google --strategy site-creds
# import cookies from comet for github
agent-do auth import-browser github --browser comet --domain .github.com
# check if we are still signed in
agent-do auth validate github
# inspect auth state for a site
agent-do auth status github
# inspect the current auth checkpoint
agent-do auth probe github
# advance a live auth checkpoint
agent-do auth advance github
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `instructions`, `list`, `probe`, `show`, `status`, `validate`
- Write (connect/interact/save): `advance`, `clear`, `ensure`, `import-browser`, `init`, `load`, `save`
- destructive (irreversible data loss; confirm before auto-running): `clear`
- sensitive (emits or persists secret material; guard output): `import-browser`
- long_running (daemon/stream/session; may never return): `ensure`
- composite (one call performs several beats internally): `advance`, `ensure`, `import-browser`, `probe`

### betterstack

Better Stack Uptime monitoring, incidents, heartbeats, status pages, and on-call

Concurrency: `mixed`

**Capabilities**

- list and inspect uptime monitors
- view monitor availability and response times
- pause and resume monitors
- list and manage incidents (acknowledge, resolve)
- list heartbeats
- list status pages
- view on-call schedules
- full account snapshot as JSON

**Commands**

- `monitors`: List all monitors with status
- `show`: Detailed monitor info
- `availability`: Monitor availability summary
- `response-times`: Monitor response time data
- `pause`: Pause a monitor
- `resume`: Resume a monitor
- `incidents`: List incidents (--active for unresolved)
- `incident`: Detailed incident info
- `ack`: Acknowledge an incident
- `resolve`: Resolve an incident
- `heartbeats`: List all heartbeats
- `status-pages`: List all status pages
- `on-call`: List on-call schedules
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my betterstack monitors
agent-do betterstack monitors
# show betterstack monitor details
agent-do betterstack show vms-web
# check active incidents in betterstack
agent-do betterstack incidents --active
# check uptime availability
agent-do betterstack availability versova-chat
# pause a betterstack monitor
agent-do betterstack pause vms-web
# acknowledge a betterstack incident
agent-do betterstack ack 12345
# get betterstack account snapshot
agent-do betterstack snapshot
```

**Credentials**

- Required: `BETTERSTACK_API_TOKEN`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `availability`, `heartbeats`, `incident`, `incidents`, `monitors`, `on-call`, `response-times`, `show`, `snapshot`, `status-pages`
- Write (connect/interact/save): `ack`, `pause`, `resolve`, `resume`
- composite (one call performs several beats internally): `ack`, `pause`, `resolve`, `resume`

### bluetooth

Bluetooth control

Concurrency: `mixed`

**Capabilities**

- scan devices
- connect/disconnect
- send data

**Commands**

- `scan`: Scan devices
- `connect`: Connect device
- `disconnect`: Disconnect device

**Examples**

```bash
# scan for bluetooth devices
agent-do bluetooth scan
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `scan`
- Write (connect/interact/save): `connect`, `disconnect`

### brief

Estate briefing engine — joins GitHub PRs, the manna board, live coord sessions, and git into ranked threads, a delta since last look, one-tap suggestions carried as data, and a receipts-grounded paragraph

Concurrency: `mixed`

**Capabilities**

- join gh inbox rows to manna items to live coord sessions to last commits to claim state
- rank threads with reasons that explain every score (heuristic today, learned as the behavior journal fills)
- compute the delta since the caller's last look (explicit --since, read-state, or first look)
- carry manna reconcile desyncs as one-tap suggestions whose commands are data, never executed
- speak a paragraph grounded in receipts (model voice when configured; deterministic fallback, annotated)
- answer estate questions with a receipt id on every claim
- versioned full-shape JSON contract for the Holy panel; consumers fail closed on drift
- pin, snooze (until a timestamp or until the thread changes), record observed behavior
- honest degradation — a failed source is an annotation, never a guess and never silence

**Commands**

- `now`: Human-readable estate brief; model voice when configured, deterministic sentence annotated otherwise
- `threads`: Joined thread objects — gh PR ↔ manna item ↔ live session ↔ last commit ↔ claim state
- `ask`: Answer a question over the estate (sessions, git log, board, zpc); every claim carries a receipt id
- `holy`: Full composite contract JSON for the Holy panel — versioned, full shape, honest degradations
- `pin`: Pin a thread (rank boost, survives restarts)
- `unpin`: Remove a pin
- `snooze`: Snooze a thread until a timestamp or until it changes (refuses an unbounded snooze)
- `unsnooze`: Clear a snooze
- `observe`: Record observed behavior on a thread (acted|ignored|snoozed|pinned|opened) — feeds the ranker
- `state`: Show the read-state store and journal size

**Examples**

```bash
# what needs me right now
agent-do brief now
# full contract for the Holy panel
agent-do brief holy --focused-repo ~/Custom-Coding/holy-ghostty --since 2026-08-11T14:00:00Z
# joined threads as data
agent-do brief threads --json
# ask the estate a question
agent-do brief ask "who touched the auth flow last week"
# snooze a thread until it changes
agent-do brief snooze mn-53da2c --until-changed
# record that I acted on a thread
agent-do brief observe ovachiever/agent-do#23 acted
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `state`, `threads`
- Write (connect/interact/save): `ask`, `holy`, `now`, `observe`, `pin`, `snooze`, `unpin`, `unsnooze`
- long_running (daemon/stream/session; may never return): `ask`, `holy`, `now`, `threads`
- polymorphic (beat decided by payload or flag at call time): `now`, `snooze`
- composite (one call performs several beats internally): `ask`, `holy`
- own_state (writes only its own cache/state; parallel-safe): `holy`

### browse

AI-first headless browser automation with @ref element selection, SSO/MFA login handoff, persistent sessions

Concurrency: `mixed`

**Capabilities**

- navigate web pages
- interact with elements via @ref snapshots
- fill forms, click buttons, upload files
- SSO/MFA login via headed browser with automatic handoff to headless
- persistent session save/load with cookies, browser storage, and IndexedDB injected at context creation when available
- capture API traffic and generate reusable curl skills
- extract text, HTML, attributes from elements
- read browser clipboard contents after clicking UI copy buttons
- credential management via OS keychain
- tab management (new, switch, close, list)
- vision-powered element finding and page description
- autonomous goal execution and page exploration

**Commands**

- `open`: Navigate to URL: open \<url>
- `snapshot`: Get page structure with @refs: snapshot [-i] [-c] [--csv] [--md]
- `click`: Click element: click \<@ref>
- `fill`: Clear and fill input: fill \<@ref> \<text>
- `type`: Append text: type \<@ref> \<text>
- `press`: Press key: press \<key>
- `get`: Read data: get text|value|attr|title|url \<@ref>
- `clipboard`: Browser clipboard: clipboard read|copy|paste
- `wait`: Wait for condition: wait \<ms|selector|--text|--stable>
- `login`: SSO/MFA auth: login \<url> opens headed browser; login done [--save \<name>] transfers auth to headless; login status; login cancel
- `session`: Persistent auth: session save|load|list|delete|export|import \<name>
- `capture`: API traffic capture: capture start|stop \<name>|status
- `api`: Replay captured API: api \<name> \<function>|list|show|test|delete
- `auth`: Credentials: auth check-creds|store-creds|login|get-creds \<domain>
- `tab`: Tab management: tab list|new|close|\<n>
- `viewport`: Set viewport size: viewport \<width> \<height>
- `screenshot`: Capture screenshot: screenshot [path] [--full]
- `vision`: AI vision: vision describe|find|click|analyze|explain|compare
- `agent`: Autonomous: agent goal|explore|explain|recover
- `doctor`: Diagnose the current session daemon, verified PID identity, socket, ping, and page state

**Examples**

```bash
# open a website
agent-do browse open https://example.com
# get interactive elements
agent-do browse snapshot -i
# click a button
agent-do browse click @e3
# fill in a form field
agent-do browse fill @e5 'hello world'
# login with SSO
agent-do browse login https://app.example.com
# finish SSO login and save session
agent-do browse login done --save mysite
# restore a saved session
agent-do browse session load mysite
# capture API traffic
agent-do browse capture start
# wait for page to load
agent-do browse wait --stable
# read the copied value from the page
agent-do browse clipboard read
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `api list`, `api show`, `api test`, `auth check-creds`, `auth get-creds`, `clipboard read`, `doctor`, `get`, `screenshot`, `session list`, `snapshot`, `tab list`, `vision analyze`, `vision compare`, `vision describe`, `vision explain`, `vision find`, `wait`
- Write (connect/interact/save): `agent`, `api delete`, `auth login`, `auth store-creds`, `capture`, `click`, `clipboard copy`, `clipboard paste`, `fill`, `login`, `open`, `press`, `session delete`, `session export`, `session import`, `session load`, `session save`, `tab close`, `tab new`, `type`, `viewport`, `vision click`
- destructive (irreversible data loss; confirm before auto-running): `api delete`, `session delete`
- sensitive (emits or persists secret material; guard output): `auth get-creds`, `auth store-creds`
- long_running (daemon/stream/session; may never return): `agent`, `capture`
- composite (one call performs several beats internally): `agent`

### burp

Burp Suite automation

Concurrency: `mixed`

**Capabilities**

- control proxy
- scan targets
- view issues

**Commands**

- `launch`: Launch Burp Suite
- `proxy`: Control system proxy
- `scan`: Scan target URL
- `issues`: List found issues

**Examples**

```bash
# enable burp proxy
agent-do burp proxy on
# scan example.com
agent-do burp scan https://example.com
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `issues`
- Write (connect/interact/save): `launch`, `proxy`, `scan`

### cad

CAD file operations

Concurrency: `mixed`

**Capabilities**

- view CAD files
- convert formats
- measure dimensions

**Commands**

- `view`: Open CAD file
- `convert`: Convert between formats
- `measure`: Get measurements
- `info`: Show file information

**Examples**

```bash
# view drawing.dxf
agent-do cad view drawing.dxf
# convert part.step to stl
agent-do cad convert part.step part.stl
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `info`, `measure`
- Write (connect/interact/save): `convert`, `view`

### calendar

Control calendar

Concurrency: `mixed`

**Capabilities**

- create events
- list events
- manage invites

**Commands**

- `create`: Create event
- `list`: List events
- `delete`: Delete event

**Examples**

```bash
# show today's events
agent-do calendar list --today
# create meeting at 3pm
agent-do calendar create 'Meeting' --time 15:00
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `create`, `delete`
- destructive (irreversible data loss; confirm before auto-running): `delete`

### ci

Control CI/CD pipelines

Concurrency: `write`

**Capabilities**

- trigger builds
- view status
- manage pipelines

**Commands**

- `trigger`: Trigger build
- `status`: View status
- `logs`: View build logs
- `triage`: Classify a failed run and draft a triage summary (dry-run)

**Examples**

```bash
# trigger deploy pipeline
agent-do ci trigger deploy
# triage a failed CI run
agent-do ci triage 12345 --repo owner/repo
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `logs`, `status`, `triage`
- Write (connect/interact/save): `trigger`

### clerk

Clerk authentication platform — users, organizations, sessions, OAuth apps, enterprise SSO, JWT templates, roles

Concurrency: `mixed`

**Capabilities**

- user CRUD with ban/lock/unlock lifecycle
- organization CRUD with memberships, invitations, and roles
- session management (list, revoke)
- OAuth application management with secret rotation
- enterprise SSO connections (SAML, OIDC)
- JWT template management
- invitation and allowlist/blocklist management
- JWKS retrieval

**Commands**

- `users`: List/search users: users [--query q]
- `user`: User details: user \<id-or-email>
- `user-create`: Create user: user-create --email \<e> --first \<f> --last \<l>
- `orgs`: List organizations: orgs [--query q]
- `org`: Organization details: org \<id-or-slug>
- `org-members`: List org members: org-members \<org>
- `org-add-member`: Add member: org-add-member \<org> \<user> [--role admin]
- `roles`: List organization roles
- `sessions`: List sessions: sessions [--user-id u] [--status s]
- `oauth-apps`: List OAuth applications
- `oauth-app-create`: Create OAuth app: oauth-app-create \<name> --callback \<url>
- `enterprise-connections`: List enterprise SSO connections
- `jwt-templates`: List JWT templates
- `snapshot`: Full instance state as JSON

**Examples**

```bash
# list Clerk users
agent-do clerk users
# search for a user
agent-do clerk users --query "erik"
# list organizations
agent-do clerk orgs
# add member to organization
agent-do clerk org-add-member my-org user_abc --role admin
# create an OAuth app in Clerk
agent-do clerk oauth-app-create "My App" --callback "http://localhost:3000/callback"
# Clerk instance overview
agent-do clerk snapshot
```

**Credentials**

- Required: `CLERK_SECRET_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `enterprise-connections`, `jwt-templates`, `oauth-apps`, `org`, `org-members`, `orgs`, `roles`, `sessions`, `snapshot`, `user`, `users`
- Write (connect/interact/save): `oauth-app-create`, `org-add-member`, `user-create`

### clipboard

Cross-app clipboard management

Concurrency: `mixed`

**Capabilities**

- copy/paste text
- copy images
- clipboard history

**Commands**

- `copy`: Copy to clipboard
- `paste`: Paste from clipboard
- `history`: Show clipboard history
- `clear`: Clear clipboard

**Examples**

```bash
# copy hello to clipboard
agent-do clipboard copy 'hello'
# show clipboard history
agent-do clipboard history
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `history`, `paste`
- Write (connect/interact/save): `clear`, `copy`
- destructive (irreversible data loss; confirm before auto-running): `clear`

### cloud

Control cloud providers (AWS, GCP, Azure)

Concurrency: `mixed`

**Capabilities**

- manage resources
- deploy services
- view metrics

**Commands**

- `list`: List resources
- `deploy`: Deploy service
- `logs`: View logs

**Examples**

```bash
# list EC2 instances
agent-do cloud list ec2
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `logs`
- Write (connect/interact/save): `deploy`

### cloudflare

Cloudflare account management — zones, analytics (GraphQL), DNS, Workers, Pages, R2, security events

Concurrency: `mixed`

**Capabilities**

- list and inspect zones (domains)
- visitor analytics via GraphQL (uniques, page views, countries, top pages)
- request and bandwidth analytics with cache ratios
- threat and security event analysis
- DNS record management (list, add, update, delete)
- Workers script listing and inspection
- Pages project listing and deployment details
- R2 bucket and object listing
- firewall event queries (WAF, rate limit, bot)
- full account snapshot as JSON

**Commands**

- `zones`: List all zones (domains)
- `zone`: Zone details: zone \<domain>
- `visitors`: Visitor summary: visitors \<zone> [--since 24h|7d]
- `top-pages`: Top pages by requests: top-pages \<zone> [--since 24h]
- `top-countries`: Top countries: top-countries \<zone> [--since 7d]
- `requests`: Request summary (total, cached, threats): requests \<zone>
- `bandwidth`: Bandwidth summary: bandwidth \<zone>
- `threats`: Security threats: threats \<zone> [--since 24h]
- `analytics`: Raw GraphQL: analytics \<zone> '\<query>'
- `dns`: List DNS records: dns \<zone>
- `dns-add`: Add record: dns-add \<zone> \<type> \<name> \<content>
- `dns-del`: Delete record: dns-del \<zone> \<record-id>
- `dns-update`: Update record: dns-update \<zone> \<record-id> \<content>
- `workers`: List Workers scripts
- `pages`: List Pages projects
- `r2-buckets`: List R2 buckets
- `firewall-events`: Firewall events: firewall-events \<zone> [--since 24h]
- `snapshot`: Full account state as JSON

**Examples**

```bash
# who visited my site today
agent-do cloudflare visitors recognitionoracle.com
# what pages get the most traffic
agent-do cloudflare top-pages recognitionoracle.com --since 7d
# show DNS records
agent-do cloudflare dns recognitionoracle.com
# list my cloudflare zones
agent-do cloudflare zones
# any security threats
agent-do cloudflare threats recognitionoracle.com --since 7d
# add a DNS record
agent-do cloudflare dns-add recognitionoracle.com CNAME www target.example.com
# cloudflare account overview
agent-do cloudflare snapshot
```

**Credentials**

- One of: `CLOUDFLARE_API_TOKEN`
- One of: `CLOUDFLARE_EMAIL` | `CLOUDFLARE_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `analytics`, `bandwidth`, `dns`, `firewall-events`, `pages`, `r2-buckets`, `requests`, `snapshot`, `threats`, `top-countries`, `top-pages`, `visitors 24h`, `visitors 7d`, `workers`, `zone`, `zones`
- Write (connect/interact/save): `dns-add`, `dns-del`, `dns-update`
- destructive (irreversible data loss; confirm before auto-running): `dns-del`

### coderabbit

Local AI diff review via CodeRabbit CLI — review uncommitted changes, staged diffs, or branch diffs before opening a PR

Concurrency: `mixed`

**Capabilities**

- review tracked local changes against a base branch, with optional committed, uncommitted, or untracked scopes
- replay findings from the most recent local review without an API call
- check auth and connectivity via doctor command
- support free-tier browser OAuth or API key for unlimited headless use

**Commands**

- `review`: Review tracked local changes against the base branch; forwards CodeRabbit review flags like --light, --committed, --uncommitted, --include-untracked, and --dir
- `findings`: Re-read results from the most recent local review (no API call)
- `doctor`: Verify installation, authentication, git state, and service connectivity
- `snapshot`: Auth status, cr version, and last doctor summary
- `auth login`: Authenticate via browser and update local CodeRabbit auth state (free tier, 3 reviews/hour)
- `auth org`: Switch active CodeRabbit organization and update local CLI state

**Examples**

```bash
# review my changes before opening a PR
agent-do coderabbit review
# review changes against develop branch
agent-do coderabbit review --base develop
# review untracked local files before a PR
agent-do coderabbit review --include-untracked
# get structured JSON review output for agent processing
agent-do coderabbit review --json
# replay last review results without an API call
agent-do coderabbit findings
# check coderabbit auth and connectivity
agent-do coderabbit doctor
# coderabbit status and auth summary
agent-do coderabbit snapshot --json
```

**Credentials**

- Optional: `CODERABBIT_API_KEY`
- Note: Free tier (3 reviews/hour): run 'agent-do coderabbit auth login' for browser OAuth. The CodeRabbit CLI saves that login locally, so later reviews work without an API key.
- Note: Unlimited reviews: store CODERABBIT_API_KEY with 'agent-do creds store CODERABBIT_API_KEY --stdin'. CodeRabbit CLI 0.7.0 does not read this env var directly for headless review; agent-coderabbit only passes it as --api-key when AGENT_DO_CODERABBIT_ALLOW_ARGV_API_KEY=1 because argv can expose the key while cr is running.

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `findings`, `snapshot`
- Write (connect/interact/save): `auth login`, `auth org`, `doctor`, `review`

### colab

Google Colab notebook management

Concurrency: `mixed`

**Capabilities**

- open notebooks in Colab
- convert notebooks
- run locally

**Commands**

- `open`: Open notebook in Colab
- `convert`: Convert to/from ipynb
- `run`: Execute notebook
- `new`: Create new notebook

**Examples**

```bash
# open notebook in colab
agent-do colab open analysis.ipynb
# convert script.py to notebook
agent-do colab convert script.py
```

**Safety (from contracts)**

- Write (connect/interact/save): `convert`, `new`, `open`, `run`

### context

Knowledge library — fetch, index, and serve external reference docs. Complementary to zpc (experience journal).

Concurrency: `mixed`

**Capabilities**

- fetch documentation from markdown/text URLs, HTML pages/sites, llms.txt, or GitHub repos
- search across all indexed content with FTS5 BM25 + trust-tier ranking
- retrieve query-specific context with freshness, provenance, trust, and version-currency metadata
- refresh stale WAN-backed packages with conditional HTTP, ETag/Last-Modified, and last-good cache preservation
- preserve raw HTML while indexing extracted readable content
- check package documentation currency against npm, PyPI, crates.io, pub.dev, or GitHub releases
- serve a local read-only HTML dashboard for agents and humans
- index local project files and Claude skills
- token-aware context budgeting for agents (knapsack packing)
- persistent annotations and feedback-influenced search ranking
- build and validate private content packages
- multi-source registry with trust-tier resolution
- global storage at ~/.agent-do/context/ (per-user, not per-project)

**Commands**

- `search`: Search across all indexed content
- `retrieve`: Return token-budgeted context for agents: retrieve \<query> [--fresh|--require-fresh|--require-official|--prefer-latest|--require-current|--offline]
- `get`: Fetch doc/skill by ID: get \<id> [--file F] [--full]
- `list`: List available packages: list [--source S] [--tags T]
- `fetch`: Fetch markdown/text or single HTML page from URL: fetch \<url> [--register-source]
- `crawl`: Crawl bounded same-origin HTML docs: crawl \<url> [--limit N]
- `fetch-llms`: Fetch llms.txt from domain: fetch-llms \<domain> [--register-source]
- `fetch-repo`: Fetch docs from GitHub: fetch-repo \<owner/repo> [path] [--register-source]
- `refresh`: Refresh WAN-backed packages: refresh \<id|name> | --due | --all
- `scan-local`: Index project files: scan-local [path]
- `scan-skills`: Index ~/.claude/skills/
- `sources`: List/sync configured content sources: sources [sync \<name|--all>]
- `add-source`: Register a source: add-source \<name> \<url|path> [--kind K] [--trust T] [--ttl 7d] [--ecosystem npm --package name --doc-version latest]
- `remove-source`: Unregister a source: remove-source \<name>
- `cache`: Cache management: cache [list|clear|pin|stats]
- `annotate`: Attach note: annotate \<id> \<note>
- `feedback`: Rate a package: feedback \<id> up|down
- `budget`: Best content within token limit: budget \<tokens> \<query>
- `inject`: Context blob for agents: inject [--max-tokens N]
- `build`: Package content directory: build \<dir> [-o output]
- `validate`: Check frontmatter + structure: validate \<dir>
- `status`: Sources, cache stats, index freshness
- `stale`: Show stale or failed packages
- `versions`: Check/list version currency: versions check [--all|--due|id] | versions outdated
- `serve`: Serve local context dashboard: serve [--port N]
- `maintain`: Run bounded maintenance: maintain [--limit N] [--max-mb N]
- `init`: Initialize ~/.agent-do/context/

**Examples**

```bash
# fetch stripe documentation
agent-do context fetch-llms stripe.com
# search for authentication docs
agent-do context search authentication
# retrieve fresh context for latest auth docs
agent-do context retrieve "latest auth docs" --fresh --prefer-latest --max-tokens 8000
# crawl an HTML docs site
agent-do context crawl https://docs.example.com --limit 25
# get the supabase docs
agent-do context get supabase-llms
# what docs do I have
agent-do context list
# give me 4000 tokens of react context
agent-do context budget 4000 react
# index my claude skills
agent-do context scan-skills
# fetch docs from a github repo
agent-do context fetch-repo vercel/next.js docs/ --register-source
# keep docs fresh
agent-do context maintain --limit 10
# show outdated docs
agent-do context versions outdated
# sync configured docs sources
agent-do context sources sync --all
# add a note to a doc
agent-do context annotate stripe-llms 'Use idempotency keys for POST'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `budget`, `cache list`, `cache stats`, `get`, `inject`, `list`, `search`, `sources`, `stale`, `status`, `validate`, `versions`
- Write (connect/interact/save): `add-source`, `annotate`, `build`, `cache clear`, `cache pin`, `crawl`, `feedback`, `fetch`, `fetch-llms`, `fetch-repo`, `init`, `maintain`, `refresh`, `remove-source`, `retrieve`, `scan-local`, `scan-skills`
- destructive (irreversible data loss; confirm before auto-running): `cache clear`, `maintain`, `remove-source`
- long_running (daemon/stream/session; may never return): `serve`
- polymorphic (beat decided by payload or flag at call time): `retrieve`
- composite (one call performs several beats internally): `crawl`, `maintain`

### coord

Project-local agent state and interrupt broker

Concurrency: `mixed`

**Capabilities**

- mint session-UUID identities anchored to process pid + start time (pane reuse never inherits a dead session)
- verify peer liveness (kill -0 + start-time match) and classify peers as active, idle, dead, stopped, or stale
- declare structured focus (goal, phase, note, blocking_on, last_ship, branch) with project-relative paths
- declare roles with exclusive-writer territories and compute overlap contention for both writers
- name the isolation remedy in contention interrupts (split ownership first, worktree second) and flag a declared branch this checkout is not on as mandatory isolation
- proactively warn concurrent active building writers to use separate worktrees because compile state and build artifacts remain shared even when source paths are disjoint
- manage advisory claims and a warn-only pre-commit guard over live claims and territories
- point peers at files via drops, declare dependencies, publish artifacts with file pointers
- compute contention, notice, dependency, and novelty interrupts and expose the event journal as history
- merge harness hook observations and timestamped external supervisor verdicts into shared six-state pulse telemetry without renewing target liveness, then rank live peers attention-first

**Commands**

- `touch`: Renew current agent presence lease and report active peers
- `whoami`: Show current coordination identity, session, pid, and runtime
- `alias`: Assign a friendly alias: alias \<name>
- `aliases`: List known aliases in this project
- `peers`: List known peers with liveness-verified status and age: peers [--all] [--active-only] [--writers]
- `stop`: Retire this session cleanly (Stop-hook safe): stop [--note \<text>]
- `bye`: Delete this agent's own board records
- `role`: Declare role and territory: role set \<builder|auditor|researcher|overseer> [--mode read-only|writer] --territory \<path>
- `territory`: Render the ownership map: territory show
- `guard`: Advisory commit guard: guard check [\<path> ...] [--staged] | guard install
- `status`: Show current focus, needs, publishes, and interrupt counts
- `interrupts`: Show current interrupts: interrupts [--mark-seen] [--limit \<n>]
- `focus`: Manage structured focus and report a warn-only concurrent-builder isolation nudge: focus set \<goal> [--path \<p>] [--phase \<phase>] [--note \<t>] [--blocking-on \<ref>] [--last-ship \<t>] [--branch \<name>] | show | clear
- `pulse`: Shared session telemetry: pulse record --from-hook (stdin JSON, always exit 0) | pulse record --session \<harness-session-id> --status \<working|needs-user|finished|failed|idle|ended> --updated-at \<RFC3339> [--activity \<note>|--clear-activity] | pulse show [peer|harness-session-id]
- `claims`: List advisory claims
- `claim`: Claim a file/path: claim \<path> [--reason \<text>] [--strength soft|strong]
- `release`: Release a claim you own: release \<path>
- `need`: Manage dependencies: need add|list|clear
- `publishes`: List published artifacts
- `publish`: Manage published artifacts: publish add [--file \<path>]|clear
- `drop`: Point a peer at a file: drop add \<path> --for \<agent|role|any> [--note \<text>] [--key \<need-key>]
- `drops`: List drops: drops [--for-me]
- `history`: Read the coordination event journal: history [peer] [--limit \<n>]

**Examples**

```bash
# see who I am in this project
agent-do coord whoami
# refresh my coordination presence
agent-do coord touch
# declare my role and exclusive write territory
agent-do coord role set builder --territory dm-ephemeris --territory shared/schema.json
# declare what I am working on
agent-do coord focus set "private Render networking" --path recognition-oracle/render.yaml --phase building
# go quiet while another agent audits
agent-do coord focus set "private Render networking" --phase quiet --note "QUIET while auditor runs"
# declare the branch this lane needs so a mismatch with this checkout surfaces
agent-do coord focus set "private Render networking" --branch feat/render-networking
# claim a file to avoid overlap
agent-do coord claim recognition-oracle/render.yaml --reason "private Render blueprint wiring"
# declare that I am waiting on a package
agent-do coord need add dm-sdk@1.2.2 --why "switch off tarball dependency"
# publish something another agent may care about
agent-do coord publish add dm-sdk@1.2.2 --status ready --summary "private package published"
# hand another agent a research file
agent-do coord drop add .dev/research-drops/report.md --for builder-a --note "ephemeris findings"
# see whether anything should interrupt me
agent-do coord interrupts
# see what a session is observably doing right now
agent-do coord pulse show session-3f2a91
# record an external supervisor's evidence-backed session verdict
agent-do coord pulse record --session 019d8abc-dead-7eef-9000-aabbccddeeff --status needs-user --activity "pane is waiting for input" --updated-at 2026-09-01T03:00:00Z
# retire this session at the end of work
agent-do coord stop --note "lane 14 shipped"
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `aliases`, `claims`, `drops`, `history`, `need list`, `peers`, `publishes`, `status`, `territory`, `whoami`
- Write (connect/interact/save): `alias`, `bye`, `claim soft`, `claim strong`, `drop`, `focus`, `guard`, `interrupts`, `need add`, `need clear`, `publish add`, `publish clear`, `pulse`, `release`, `role`, `stop`, `touch`
- destructive (irreversible data loss; confirm before auto-running): `bye`, `need clear`, `publish clear`
- polymorphic (beat decided by payload or flag at call time): `guard`, `interrupts`, `pulse`
- composite (one call performs several beats internally): `touch`

### creds

Secure credential storage and resolution for agent-do tools

Concurrency: `mixed`

**Capabilities**

- store secrets in the OS secure credential store
- resolve tool credentials from env vars or secure storage
- check which credentials a tool needs
- export resolved credentials for debugging
- list and delete stored secrets

**Commands**

- `store`: Store a secret: store \<KEY> [VALUE] [--stdin]
- `get`: Show secret status: get \<KEY> [--reveal|--source]
- `delete`: Delete a secret: delete \<KEY>
- `list`: List stored secret keys
- `check`: Check secrets: check \<KEY...> | --tool \<tool>
- `required`: Show declared tool credentials: required \<tool>
- `export`: Print export lines: export \<KEY...> | --tool \<tool>
- `platform`: Show detected secure-store backend

**Examples**

```bash
# store a render API key securely
agent-do creds store RENDER_API_KEY --stdin
# check what namecheap needs
agent-do creds required namecheap
# verify vercel credentials
agent-do creds check --tool vercel
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `check`, `get`, `list`, `platform`, `required`
- Write (connect/interact/save): `delete`, `export`, `store`
- destructive (irreversible data loss; confirm before auto-running): `delete`
- sensitive (emits or persists secret material; guard output): `delete`, `store`

### cronitor

Cronitor scheduled job and uptime monitoring

Concurrency: `mixed`

**Capabilities**

- list and inspect monitors (jobs, heartbeats, checks)
- view monitor details including schedule and assertions
- create and delete monitors
- pause and resume monitors for maintenance windows
- send telemetry events (run, complete, fail, ok)
- list and inspect issues (incidents)
- list notification lists
- full account snapshot as JSON

**Commands**

- `monitors`: List all monitors with status
- `show`: Detailed monitor info by key
- `create`: Create a monitor (JSON from stdin)
- `delete`: Delete a monitor by key
- `pause`: Pause a monitor (indefinitely or for N hours)
- `resume`: Resume a paused monitor
- `issues`: List issues (--open for unresolved only)
- `issue`: Detailed issue info by key
- `ping`: Send telemetry event (--state run|complete|fail|ok)
- `notifications`: List notification lists
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my cronitor monitors
agent-do cronitor monitors
# show cronitor monitor details
agent-do cronitor show TuoCU3
# check open cronitor issues
agent-do cronitor issues --open
# send a cronitor telemetry ping
agent-do cronitor ping my-job --state complete
# pause a cronitor monitor for maintenance
agent-do cronitor pause my-job 4
# resume a paused cronitor monitor
agent-do cronitor resume my-job
# get cronitor account snapshot
agent-do cronitor snapshot
# create a new cronitor monitor
echo '{"type":"job","key":"my-job","schedules":["0 * * * *"]}' | agent-do cronitor create
```

**Credentials**

- Required: `CRONITOR_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `issue`, `issues`, `monitors`, `notifications`, `show`, `snapshot`
- Write (connect/interact/save): `create`, `delete`, `pause`, `ping`, `resume`
- destructive (irreversible data loss; confirm before auto-running): `delete`
- composite (one call performs several beats internally): `create`, `pause`, `ping`, `resume`

### datadog

Datadog observability — monitors, logs, metrics, incidents, dashboards, and SLOs with cross-tool incident response

Concurrency: `mixed`

**Capabilities**

- list, inspect, mute, unmute, create, and delete monitors
- query monitor alert state summary (alerting/warn/ok breakdown)
- search logs with service, status, and time range filters
- query metric timeseries and list available metrics
- list and post events
- create, update, resolve, and inspect incidents (JSON:API v2)
- list and inspect dashboards
- list SLOs and retrieve error budget history
- list service catalog definitions
- observability snapshot combining monitors, events, and SLOs
- dry-run mode for all write commands (exit 0; text preview by default, structured JSON preview with --json)
- automation exit codes: monitor-status and snapshot return 1 when monitors are alerting

**Commands**

- `monitors`: List monitors: monitors [--tag env:prod] [--name CPU] [--state Alert]
- `monitor`: Get one monitor: monitor \<id>
- `monitor-status`: Alert state summary: monitor-status [--tag env:prod] (exits 1 when any monitor is alerting)
- `monitor-mute`: Mute monitor: monitor-mute \<id> [--end now+1h] [--scope host:web-01] [--message reason] [--dry-run]
- `monitor-unmute`: Unmute monitor: monitor-unmute \<id> [--dry-run]
- `monitor-create`: Create monitor: monitor-create --name N --type "metric alert" --query Q [--message M] [--tags t1,t2] [--priority 1-5] [--dry-run]
- `monitor-delete`: Delete monitor: monitor-delete \<id> [--dry-run]
- `logs`: Search logs: logs [query] [--from now-1h] [--to now] [--service svc] [--status error|warn|info|debug] [--limit 25] [--cursor TOKEN]
- `metrics`: Query timeseries: metrics "avg:system.cpu.user{*}" [--from now-1h] [--to now]
- `metrics-list`: List metrics: metrics-list [--prefix system]
- `events`: List events: events [--from now-1h] [--priority normal|low] [--tags tag1]
- `event-post`: Post event: event-post --title T --text B [--priority normal] [--tags t1,t2] [--alert-type error|warning|info|success] [--dry-run]
- `incidents`: List incidents: incidents [--state active|stable|resolved]
- `incident`: Get incident: incident \<id>
- `incident-create`: Create incident: incident-create --title T [--severity SEV-1..SEV-5] [--customer-impacted] [--dry-run]
- `incident-update`: Update incident: incident-update \<id> [--title T] [--status active|stable|resolved] [--severity S] [--dry-run]
- `incident-resolve`: Resolve incident: incident-resolve \<id> [--dry-run]
- `dashboards`: List all dashboards
- `dashboard`: Get dashboard: dashboard \<id>
- `slos`: List SLOs: slos [--tags team:platform]
- `slo`: SLO history and error budget: slo \<id> [--from now-30d] [--to now]
- `services`: List service catalog: services [--page-size 100]
- `snapshot`: Observability snapshot: snapshot (exits 1 when any monitor is alerting)

**Examples**

```bash
# check if any monitors are alerting
agent-do datadog monitor-status
# search logs for errors in the api service
agent-do datadog logs "error" --service api --from now-1h
# query cpu metrics for the last hour
agent-do datadog metrics "avg:system.cpu.user{*}" --from now-1h
# list active incidents
agent-do datadog incidents --state active
# create a datadog incident for a production outage
agent-do datadog incident-create --title "Checkout errors" --severity SEV-1 --customer-impacted
# resolve a datadog incident
agent-do datadog incident-resolve inc-001
# mute a monitor during a deploy
agent-do datadog monitor-mute 12345 --end now+1h --message "Deploying v2.4.0"
# get SLO error budget status
agent-do datadog slo slo-001
# get a combined observability snapshot
agent-do datadog snapshot --json
```

**Credentials**

- Required: `DD_API_KEY`, `DD_APP_KEY`
- Optional: `DD_SITE`, `DD_API_BASE_URL`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `dashboard`, `dashboards`, `events`, `incident`, `incidents`, `logs`, `metrics`, `metrics-list`, `monitor`, `monitor-status`, `monitors`, `services`, `slo`, `slos`, `snapshot`
- Write (connect/interact/save): `event-post`, `incident-create`, `incident-resolve`, `incident-update`, `monitor-create`, `monitor-delete`, `monitor-mute`, `monitor-unmute`
- destructive (irreversible data loss; confirm before auto-running): `monitor-delete`

### db

Control database clients

Concurrency: `mixed`

**Capabilities**

- connect to databases
- run queries
- export data
- manage schemas

**Commands**

- `connect`: Connect to database
- `query`: Run SQL query
- `export`: Export query results
- `tables`: List tables
- `describe`: Describe table schema

**Examples**

```bash
# show all tables in postgres
agent-do db tables --db postgres
# run SELECT * FROM users
agent-do db query 'SELECT * FROM users'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `describe`, `tables`
- Write (connect/interact/save): `connect`, `export`, `query`
- polymorphic (beat decided by payload or flag at call time): `query`

### debug

Control debuggers

Concurrency: `read`

**Capabilities**

- set breakpoints
- step through code
- inspect variables
- manage sessions

**Commands**

- `break`: Set breakpoint
- `continue`: Continue execution
- `step`: Step over/into/out
- `print`: Print variable
- `backtrace`: Show call stack

**Examples**

```bash
# set breakpoint at line 42
agent-do debug break 42
# print the value of x
agent-do debug print x
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `backtrace`, `print`
- Write (connect/interact/save): `break`, `continue`, `step`
- own_state (writes only its own cache/state; parallel-safe): `break`, `continue`, `step`

### discord

Control Discord

Concurrency: `mixed`

**Capabilities**

- send messages
- read channels
- manage servers

**Commands**

- `send`: Send message
- `read`: Read channel

**Examples**

```bash
# send hello to #general
agent-do discord send '#general' 'hello'
```

**Credentials**

- Required: `DISCORD_TOKEN`
- Optional: `DISCORD_WEBHOOK_URL`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `read`
- Write (connect/interact/save): `send`

### dns

DNS lookups and resolution diagnostics (read-only; record writes live in namecheap/cloudflare)

Concurrency: `read`

**Capabilities**

- lookup records
- list common record types
- trace resolution paths

**Commands**

- `lookup`: DNS lookup
- `list`: List records

**Examples**

```bash
# lookup DNS for example.com
agent-do dns lookup example.com
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `lookup`

### docker

Control Docker containers

Concurrency: `write`

**Capabilities**

- list/start/stop containers
- view logs
- execute commands
- manage compose stacks

**Commands**

- `ps`: List containers
- `logs`: View container logs
- `exec`: Run command in container
- `shell`: Interactive shell
- `start`: Start container
- `stop`: Stop container
- `compose`: Docker compose operations

**Examples**

```bash
# show running containers
agent-do docker ps
# view logs for postgres container
agent-do docker logs postgres
# run bash in my-container
agent-do docker shell my-container
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `logs`, `ps`
- Write (connect/interact/save): `compose`, `start`, `stop`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `exec`, `shell`
- polymorphic (beat decided by payload or flag at call time): `compose`

### dpt

Design Perception Tensor - automated design quality scoring

Concurrency: `read`

**Capabilities**

- scan any webpage for design quality
- score 0-100 across 5 perception layers
- detect contrast, typography, spacing, hierarchy, coherence violations
- generate prioritized fix lists with CSS selectors
- baseline/diff for before/after comparison

**Commands**

- `scan`: Full-page scan → JSON with all 65 checks
- `score`: Quick score + grade + dimension summary
- `report`: Narrative design critique report
- `violations`: Violations sorted by impact for AI fix loops
- `baseline`: Save a browser-session + project baseline
- `diff`: Compare against that scoped baseline, show deltas
- `build`: Rebuild engine from source

**Examples**

```bash
# check the design quality of this page
agent-do dpt score
# scan stripe.com for design issues
agent-do dpt scan https://stripe.com
# what design violations are on this page
agent-do dpt violations
# save a design baseline before making changes
agent-do dpt baseline
# did my changes improve the design
agent-do dpt diff
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `diff`, `report`, `scan`, `score`, `violations`
- Write (connect/interact/save): `baseline`, `build`
- composite (one call performs several beats internally): `baseline`
- own_state (writes only its own cache/state; parallel-safe): `baseline`, `build`

### email

Control email

Concurrency: `mixed`

**Capabilities**

- send emails
- query inboxes and mailboxes
- search messages with account and mailbox scoping
- wait for matching messages
- fetch exact messages by id
- extract verification codes
- extract magic links

**Commands**

- `send`: Send email
- `read`: Open Mail.app
- `search`: Search emails with structured filters
- `snapshot`: Snapshot scoped mailbox state as JSON
- `latest`: Show latest matching message
- `wait`: Wait for a matching message
- `get`: Fetch one exact message by id
- `export`: Export one exact message as json, txt, html, eml, or pdf
- `code`: Extract verification code from matching email
- `link`: Extract magic link from matching email
- `mailboxes`: List available mailboxes
- `status`: Show feature and provider hydration readiness

**Examples**

```bash
# send email to john@example.com
agent-do email send john@example.com
# read my inbox
agent-do email read
# search archived mail for an invoice
agent-do email search invoice --all-mailboxes --json
# fetch one exact message by id
agent-do email get --id msg-123 --json
# export one exact message as EML
agent-do email export --id msg-123 --format eml --output message.eml
# wait for a verification code email
agent-do email code --from auth@example.com --subject "verification code" --account Work --mailbox Inbox
# get the latest magic link
agent-do email link --from login@example.com --domain app.example.com
```

**Credentials**

- Optional: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `AGENT_EMAIL_PROVIDER`, `AGENT_EMAIL_IMAP_HOST`, `AGENT_EMAIL_IMAP_PORT`, `AGENT_EMAIL_IMAP_USER`, `AGENT_EMAIL_IMAP_PASS`, `AGENT_EMAIL_IMAP_MAILBOX`, `AGENT_EMAIL_IMAP_MAILBOXES`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `code`, `get`, `latest`, `link`, `mailboxes`, `read`, `search`, `snapshot`, `status`, `wait`
- Write (connect/interact/save): `export`, `send`
- sensitive (emits or persists secret material; guard output): `code`, `link`
- composite (one call performs several beats internally): `code`, `link`

### eval

LLM output evaluation and testing

Concurrency: `read`

**Capabilities**

- run evaluation suites
- compare results
- track metrics

**Commands**

- `run`: Run evaluation
- `create`: Create evaluation
- `results`: Show results
- `compare`: Compare runs

**Examples**

```bash
# run math evaluation
agent-do eval run math-test
# show evaluation results
agent-do eval results
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `compare`, `results`
- Write (connect/interact/save): `create`, `run`
- composite (one call performs several beats internally): `run`
- own_state (writes only its own cache/state; parallel-safe): `create`, `run`

### excel

AI-first Excel CLI for workbook automation

Concurrency: `mixed`

**Capabilities**

- open and create Excel workbooks
- read/write cells and ranges
- manage sheets (create, rename, delete, copy)
- set formulas and formatting
- export to CSV and PDF
- insert/delete rows and columns

**Commands**

- `open`: Open workbook: open \<path>
- `new`: Create workbook: new [path]
- `save`: Save workbook: save [path]
- `snapshot`: Sheet overview: snapshot [--range A1:Z50] [--used] [--headers]
- `get`: Read cell/range: get \<cell|range>
- `set`: Write cell/range: set \<cell> \<value>
- `fill`: Fill range: fill \<range> \<value>
- `formula`: Set formula: formula \<cell> \<expr>
- `sheets`: List sheets
- `sheet`: Switch/manage sheets: sheet \<name|new|rename|delete>
- `export`: Export: export csv|pdf \<path>

**Examples**

```bash
# open a spreadsheet
agent-do excel open data.xlsx
# read cell A1
agent-do excel get A1
# set cell B2 to 100
agent-do excel set B2 100
# export sheet to CSV
agent-do excel export csv output.csv
# get sheet overview
agent-do excel snapshot --headers
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `get`, `sheets`, `snapshot`
- Write (connect/interact/save): `export`, `fill`, `formula`, `new`, `open`, `save`, `set`, `sheet delete`, `sheet name`, `sheet new`, `sheet rename`
- destructive (irreversible data loss; confirm before auto-running): `sheet delete`

### figma

Control Figma

Concurrency: `read`

**Capabilities**

- export assets
- read design specs
- manage components

**Commands**

- `export`: Export assets
- `inspect`: Inspect element
- `list`: List components

**Examples**

```bash
# export icons from design
agent-do figma export --icons
```

**Credentials**

- Required: `FIGMA_TOKEN`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `inspect`, `list`
- Write (connect/interact/save): `export`
- own_state (writes only its own cache/state; parallel-safe): `export`

### gcp

Google Cloud Platform management — REST API for projects, APIs, secrets, service accounts + Console automation for OAuth credentials

Concurrency: `mixed`

**Capabilities**

- authenticate via service account key, access token, or gcloud CLI
- list and inspect GCP projects
- enable and disable APIs on a project
- manage service accounts and keys
- create, read, and delete secrets via Secret Manager
- create OAuth consent screen and web app credentials via Console automation
- full account snapshot as JSON

**Commands**

- `auth status`: Current auth state and token validity
- `auth token`: Print access token for piping
- `projects`: List accessible projects
- `project show`: Project details (number, state, labels)
- `apis`: List enabled APIs
- `api-enable`: Enable an API on a project
- `api-disable`: Disable an API on a project
- `service-accounts`: List service accounts
- `sa-create`: Create service account
- `sa-key-create`: Create and download service account key
- `sa-key-list`: List keys for a service account
- `secrets`: List secrets in Secret Manager
- `secret-get`: Read latest secret version
- `secret-set`: Create or update a secret
- `secret-del`: Delete a secret
- `oauth-setup`: Full OAuth workflow: consent screen + client creation (Console automation)
- `oauth-create`: Create OAuth web app client (Console automation)
- `oauth-list`: List OAuth credentials (Console automation)
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my GCP projects
agent-do gcp projects
# show GCP project details
agent-do gcp project show my-project
# check GCP auth status
agent-do gcp auth status
# enable secret manager API
agent-do gcp api-enable my-project secretmanager.googleapis.com
# list enabled GCP APIs
agent-do gcp apis my-project
# list GCP secrets
agent-do gcp secrets my-project
# set a GCP secret
agent-do gcp secret-set my-project GOOGLE_CLIENT_ID my-client-id
# get a GCP secret value
agent-do gcp secret-get my-project GOOGLE_CLIENT_ID
# create GCP service account
agent-do gcp sa-create my-project my-service --display "My Service"
# create Google OAuth credentials
agent-do gcp oauth-setup my-project --name "My App" --redirect "http://localhost:3333/api/auth/callback/google"
# get GCP account snapshot
agent-do gcp snapshot
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `apis`, `auth status`, `auth token`, `oauth-list`, `project show`, `projects`, `sa-key-list`, `secret-get`, `secrets`, `service-accounts`, `snapshot`
- Write (connect/interact/save): `api-disable`, `api-enable`, `oauth-create`, `oauth-setup`, `sa-create`, `sa-key-create`, `secret-del`, `secret-set`
- destructive (irreversible data loss; confirm before auto-running): `secret-del`
- sensitive (emits or persists secret material; guard output): `auth token`, `sa-key-create`, `secret-get`, `secrets`
- long_running (daemon/stream/session; may never return): `oauth-setup`
- composite (one call performs several beats internally): `oauth-setup`

### gh

GitHub repository, pull request, review, and merge work-state across accessible repos

Concurrency: `mixed`

**Capabilities**

- discover accessible GitHub repositories
- list actionable pull requests across repos
- inspect pull request details, diffs, checks, and unresolved review threads
- classify changed files by review-risk tier (critical/elevated/standard)
- audit PR review risks and generate fix-oriented engineering review replies
- surface the built-in review doctrine on every review
- gate merges on failing checks, unresolved threads, dirty merge state, and missing approval
- approve, comment, request changes, close/reopen, edit, check out, update branches, mark ready/draft, and merge pull requests

**Commands**

- `whoami`: Show authenticated GitHub user
- `repos`: List or sync accessible repositories
- `inbox`: Show actionable PR work across repositories — maintainer-role and declared-portfolio sweeps of open third-party PRs plus review-request ceremony (--ceremony-only skips the sweeps)
- `portfolio`: Manage the declared portfolio of swept repos — add/remove owner/repo or owner/* patterns, list current declarations
- `awaiting`: Show open PRs likely awaiting your review by broad review heuristics
- `prs`: Search pull requests
- `pr`: Show PR details
- `diff`: Show PR diff
- `threads`: Show unresolved PR review threads
- `checks`: Show PR checks
- `review`: Summarize a PR for review — state, checks, risk tier, and the review doctrine
- `audit`: Audit a PR for review risks and generate request-changes-ready reply text
- `doctrine`: Print the PR review doctrine
- `approve`: Approve a PR
- `request-changes`: Request changes on a PR
- `comment`: Comment on a PR
- `close`: Close a PR
- `reopen`: Reopen a PR
- `checkout`: Check out a PR locally
- `edit`: Edit PR metadata
- `update-branch`: Update a PR branch from its base branch
- `merge`: Merge a PR (gated on checks, threads, merge state, approval; --force to bypass)
- `ready`: Mark a PR ready for review
- `draft`: Convert a PR to draft

**Examples**

```bash
# show GitHub pull requests that need me
agent-do gh inbox
# show PRs awaiting my review in VID repos
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova
# deeply review PRs awaiting my review and draft replies
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova --audit --replies --probe-deploys
# list open PRs across my repos
agent-do gh prs --state open
# audit a pull request and generate a request-changes reply
agent-do gh audit ovachiever/agent-do#3 --reply --probe-deploys
# review pull request 3 in agent-do
agent-do gh review ovachiever/agent-do#3 --summary
# show unresolved GitHub review comments
agent-do gh threads ovachiever/agent-do#3
# approve this GitHub PR
agent-do gh approve ovachiever/agent-do#3 --body "LGTM"
# close accidental pull request and delete branch
agent-do gh close ovachiever/agent-do#4 --delete-branch --comment "Closing accidental PR"
# check out pull request for local review
agent-do gh checkout ovachiever/agent-do#5 --branch review/pr-5
# add reviewer and label to pull request
agent-do gh edit ovachiever/agent-do#5 --add-reviewer @me --add-label review-needed
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `audit`, `awaiting`, `checks`, `diff`, `doctrine`, `inbox`, `portfolio list`, `pr`, `prs`, `repos`, `review`, `threads`, `whoami`
- Write (connect/interact/save): `approve`, `checkout`, `close`, `comment`, `draft`, `edit`, `merge`, `portfolio add`, `portfolio remove`, `ready`, `reopen`, `request-changes`, `update-branch`
- own_state (writes only its own cache/state; parallel-safe): `portfolio add`, `portfolio remove`

### ghidra

Ghidra reverse engineering automation

Concurrency: `read`

**Capabilities**

- analyze binaries
- decompile functions
- list functions/imports

**Commands**

- `analyze`: Analyze binary
- `decompile`: Decompile function
- `functions`: List functions
- `strings`: Extract strings

**Examples**

```bash
# decompile main from myapp
agent-do ghidra decompile myapp main
# list functions in binary
agent-do ghidra functions program.exe
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `functions`, `strings`
- Write (connect/interact/save): `analyze`, `decompile`
- own_state (writes only its own cache/state; parallel-safe): `analyze`, `decompile`

### git

Guarded local Git operations for staged commits, worktrees, snapshots, conflicts, and recovery

Concurrency: `mixed`

**Capabilities**

- commit explicitly staged changes with heuristic messages and a redacted secret-scan gate
- inspect status, diffs, logs, conflicts, reflog, and unreachable commits
- manage branches, stashes, remotes, and worktrees
- seed named gitignored local files into fresh worktrees without overwriting targets
- bind a new worktree's zpc memory to the primary store and warn that the manna board does not follow it
- inspect and recover files from refs/auto shadow snapshots
- preview safe branch cleanup before explicit apply

**Commands**

- `status`: Show compact working-tree status
- `diff`: Show staged diff, or unstaged diff when the index is empty
- `log`: Show recent commits
- `commit`: Commit staged changes after secret scanning; --no-scan is explicit and logged
- `branch`: List branches or create/switch to a named branch
- `stash`: Push, list, or pop stashes
- `pull`: Pull with rebase
- `push`: Push the current branch and establish upstream when absent
- `sync`: Pull with rebase, then push
- `snapshot`: Emit full repository state as JSON
- `worktree add`: Add a worktree, seed named gitignored files, and bind its zpc memory to this checkout's store
- `worktree list`: List registered worktrees
- `worktree remove`: Remove a clean registered worktree
- `snap list`: List refs/auto shadow snapshots
- `snap diff`: Diff the current branch against its refs/auto snapshot
- `snap restore`: Recover a file to .recovered, or overwrite only with --in-place
- `conflicts`: List unmerged files with conflict-marker counts
- `recover`: Read-only reflog and unreachable-commit report
- `sweep`: Preview safe local branch deletion; mutate only with --apply

**Examples**

```bash
# commit the changes I already staged
agent-do git commit 'fix: describe the staged change'
# show recent commits
agent-do git log
# create an isolated worktree and carry local env files into it
agent-do git worktree add feature/name --path ../repo-feature-name
# recover one file from the automatic shadow snapshot
agent-do git snap restore path/to/file
# preview merged branch cleanup
agent-do git sweep
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `conflicts`, `diff`, `log`, `recover`, `snap diff`, `snap list`, `snapshot`, `status`, `worktree list`
- Write (connect/interact/save): `branch`, `commit`, `pull`, `push`, `snap restore`, `stash`, `sweep`, `sync`, `worktree add`, `worktree remove`
- destructive (irreversible data loss; confirm before auto-running): `snap restore`, `sweep`, `worktree remove`
- polymorphic (beat decided by payload or flag at call time): `branch`, `sweep`

### handbrake

Convert ripped video (MKV) to Plex-ready MP4 via HandBrakeCLI — probe a file's titles and streams, list encode presets, transcode single files or whole directories with skip/overwrite handling, and verify .mp4 outputs

Concurrency: `mixed`

**Capabilities**

- list available HandBrake encode presets by category
- probe a video file's titles, duration, resolution, and audio/subtitle streams
- transcode one file to MP4 with a chosen preset
- batch-transcode every .mkv in a directory, skipping already-converted files
- verify transcoded .mp4 outputs (files and sizes)
- report HandBrake version and a preset-availability snapshot
- structured JSON output parsed from HandBrakeCLI --json scan mode

**Commands**

- `presets`: List available encode presets
- `scan`: Probe a file; list titles, streams, duration: scan \<input>
- `convert`: Transcode one file to .mp4: convert \<input> [output]
- `batch`: Transcode every .mkv in a directory: batch \<indir> \<outdir>
- `verify`: List .mp4 outputs (dir) or check one file: verify \<path>
- `version`: Show HandBrake version
- `snapshot`: Version + preset availability (JSON)

**Examples**

```bash
# list handbrake presets
agent-do handbrake presets
# probe a ripped mkv's streams
agent-do handbrake scan ~/rips/title_t00.mkv --json
# convert an mkv to mp4 for plex
agent-do handbrake convert ~/rips/title_t00.mkv
# convert with a specific preset and destination
agent-do handbrake convert ~/rips/title_t00.mkv ~/plex/movie.mp4 --preset "HQ 1080p30 Surround"
# convert all ripped mkvs in a folder to mp4
agent-do handbrake batch ~/rips ~/plex
# re-encode a folder even if outputs exist
agent-do handbrake batch ~/rips ~/plex --overwrite
# verify transcoded output files
agent-do handbrake verify ~/plex
# show what the convert command would run without executing
agent-do handbrake convert ~/rips/title_t00.mkv --dry-run
# get a HandBrake version and preset snapshot
agent-do handbrake snapshot --json
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `presets`, `scan`, `snapshot`, `verify`, `version`
- Write (connect/interact/save): `batch`, `convert`
- long_running (daemon/stream/session; may never return): `batch`, `convert`
- composite (one call performs several beats internally): `batch`

### hardware

Unified hardware device control across serial, bluetooth, USB, printers, and MIDI

Concurrency: `mixed`

**Capabilities**

- snapshot connected hardware surfaces
- delegate serial port operations through one stable family tool
- delegate bluetooth device operations
- delegate USB device and storage operations
- delegate printer queue and print operations
- delegate MIDI device and message operations

**Commands**

- `snapshot`: Snapshot all supported hardware domains
- `serial`: Serial operations: serial \<list|monitor|send|config> ...
- `bluetooth`: Bluetooth operations: bluetooth \<status|devices|scan|connect|disconnect> ...
- `usb`: USB operations: usb \<list|tree|info|eject|mount|unmount|disks> ...
- `printer`: Printer operations: printer \<list|default|status|print|jobs|cancel|queue> ...
- `midi`: MIDI operations: midi \<snapshot|list|monitor|send|play> ...

**Examples**

```bash
# snapshot connected hardware devices
agent-do hardware snapshot
# list serial ports through the hardware family
agent-do hardware serial list
# list printers through the hardware family
agent-do hardware printer list
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `bluetooth devices`, `bluetooth scan`, `bluetooth status`, `midi list`, `midi snapshot`, `printer jobs`, `printer list`, `printer queue`, `printer status`, `serial config`, `serial list`, `snapshot`, `usb disks`, `usb info`, `usb list`, `usb tree`
- Write (connect/interact/save): `bluetooth connect`, `bluetooth disconnect`, `midi play`, `midi send`, `printer cancel`, `printer default`, `printer print`, `serial send`, `usb eject`, `usb mount`, `usb unmount`
- long_running (daemon/stream/session; may never return): `midi monitor`, `serial monitor`
- polymorphic (beat decided by payload or flag at call time): `printer default`

### harness

Observable agent-do harness inventory, evidence, and change-manifest front door

Concurrency: `mixed`

**Capabilities**

- inspect the editable agent-do harness surface across tools, hooks, instructions, libraries, tests, and state
- summarize hook decisions, nudge emissions, tool calls/results, and followed/ignored/expired outcomes
- build drill-down evidence bundles for sessions, runs, and harness changes
- create and verify falsifiable harness change manifests
- make registry, hook, tool, and memory surfaces visible as one harness instead of adjacent tools
- answer quantity questions from an authority instead of a literal, and refuse to estimate
- fail the build on a cap with no declared provenance, and report bare bounding literals in any project

**Commands**

- `inspect`: Inventory tools, hooks, instructions, libraries, state refs, and tests
- `nudges`: Summarize hook outcome telemetry and nudge effectiveness
- `evidence`: Build local drill-down evidence bundles
- `manifest`: Create and verify harness change manifests
- `contracts`: Contracts gate, lexicon, surface, and drift: contracts validate|propose|surface|drift
- `quantity`: Looked-up ceilings by stable key, with provenance: quantity lookup|keys
- `census`: Measured totals right now, exact or refused: census lines|entries|rows
- `bounds`: Declared caps checked against the authority: bounds drift|audit|scan

**Examples**

```bash
# inspect the agent-do harness
agent-do harness inspect
# show the harness inventory as json
agent-do harness inspect --json
# check whether hook nudges are effective
agent-do harness nudges effectiveness --since 7d
# build harness evidence for this session
agent-do harness evidence build latest-session
# create a falsifiable manifest for an email hydration fix
agent-do harness manifest new email-hydration --component-type tool --file tools/agent-email
# what is this model's max output token ceiling
agent-do harness quantity lookup anthropic.claude-sonnet-5.max_tokens
# how many lines are in this file right now
agent-do harness census lines registry.yaml
# check every declared cap against the ceiling it cites
agent-do harness bounds drift
# find hardcoded token and row limits in a project
agent-do harness bounds scan ~/Custom-Coding/some-project
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `bounds audit`, `bounds drift`, `bounds scan`, `census`, `contracts audit`, `contracts drift`, `contracts surface`, `contracts validate`, `inspect`, `nudges`, `quantity`
- Write (connect/interact/save): `contracts propose`, `evidence`, `manifest`
- polymorphic (beat decided by payload or flag at call time): `contracts propose`, `manifest`
- composite (one call performs several beats internally): `bounds audit`, `contracts audit`, `contracts drift`, `evidence`

### homekit

HomeKit/smart home control

Concurrency: `mixed`

**Capabilities**

- control devices
- run scenes
- check status

**Commands**

- `list`: List devices
- `set`: Set device state
- `scene`: Run scene

**Examples**

```bash
# turn on living room lights
agent-do homekit set 'Living Room' on
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `scene`, `set`

### ide

Control VS Code/Cursor editor

Concurrency: `read`

**Capabilities**

- open files and folders
- run commands
- navigate code
- manage extensions

**Commands**

- `open`: Open file or folder
- `run`: Run editor command
- `goto`: Go to line/symbol
- `search`: Search in files
- `terminal`: Run in integrated terminal

**Examples**

```bash
# open src/main.py in VS Code
agent-do ide open src/main.py
# go to line 42
agent-do ide goto 42
# search for TODO
agent-do ide search TODO
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `search`
- Write (connect/interact/save): `goto`, `open`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `run`, `terminal`
- own_state (writes only its own cache/state; parallel-safe): `goto`, `open`

### image

Image processing

Concurrency: `mixed`

**Capabilities**

- resize/crop images
- convert formats
- apply filters

**Commands**

- `resize`: Resize image
- `crop`: Crop image
- `convert`: Convert format

**Examples**

```bash
# resize image to 800x600
agent-do image resize input.png --size 800x600
```

**Safety (from contracts)**

- Write (connect/interact/save): `convert`, `crop`, `resize`

### ios

Control iOS Simulator

Concurrency: `mixed`

**Capabilities**

- tap/swipe gestures
- take screenshots
- install/launch apps
- get UI hierarchy

**Commands**

- `tap`: Tap at coordinates: tap \<x> \<y>
- `screenshot`: Capture simulator screen: screenshot [path] (saves to path or /tmp/ios-screenshot.png)
- `launch`: Launch an app: launch \<bundle-id>
- `tree`: Get UI element tree
- `swipe`: Swipe gesture: swipe \<x1> \<y1> \<x2> \<y2>
- `type`: Type text: type \<text>
- `boot`: Boot simulator: boot [device-name]
- `shutdown`: Shutdown simulator: shutdown [device-name]
- `list`: List available simulators
- `status`: Show booted simulator status

**Examples**

```bash
# screenshot the iPhone simulator
agent-do ios screenshot
# take a screenshot and save to Downloads
agent-do ios screenshot ~/Downloads/screenshot.png
# save iOS screenshot to /tmp/test.png
agent-do ios screenshot /tmp/test.png
# tap at 100, 200
agent-do ios tap 100 200
# launch Safari
agent-do ios launch com.apple.mobilesafari
# boot the simulator
agent-do ios boot
# boot iPhone 15 Pro
agent-do ios boot 'iPhone 15 Pro'
# shutdown the simulator
agent-do ios shutdown
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `screenshot`, `status`, `tree`
- Write (connect/interact/save): `boot`, `launch`, `shutdown`, `swipe`, `tap`, `type`

### jupyter

Control Jupyter notebooks

Concurrency: `mixed`

**Capabilities**

- run cells
- create notebooks
- manage kernels
- export notebooks

**Commands**

- `run`: Run cell
- `create`: Create notebook
- `export`: Export notebook
- `kernel`: Manage kernel

**Examples**

```bash
# run all cells
agent-do jupyter run --all
# restart kernel
agent-do jupyter kernel restart
```

**Safety (from contracts)**

- Write (connect/interact/save): `create`, `export`, `kernel`, `run`
- destructive (irreversible data loss; confirm before auto-running): `kernel`

### k8s

Control Kubernetes clusters

Concurrency: `write`

**Capabilities**

- manage pods and deployments
- view logs
- port forwarding
- apply manifests

**Commands**

- `pods`: List pods
- `logs`: View pod logs
- `exec`: Execute in pod
- `apply`: Apply manifest
- `port-forward`: Forward port

**Examples**

```bash
# show all pods
agent-do k8s pods
# view logs for api pod
agent-do k8s logs api
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `logs`, `pods`
- Write (connect/interact/save): `apply`, `port-forward`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `exec`
- long_running (daemon/stream/session; may never return): `port-forward`

### lab

JupyterLab management

Concurrency: `mixed`

**Capabilities**

- start/stop server
- manage extensions
- open notebooks

**Commands**

- `start`: Start JupyterLab server
- `stop`: Stop server
- `open`: Open in browser
- `extensions`: List extensions

**Examples**

```bash
# start jupyterlab
agent-do lab start
# open notebook in jupyterlab
agent-do lab open analysis.ipynb
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `extensions`
- Write (connect/interact/save): `open`, `start`, `stop`
- long_running (daemon/stream/session; may never return): `start`

### latex

LaTeX document compilation

Concurrency: `write`

**Capabilities**

- compile documents
- watch for changes
- manage templates

**Commands**

- `compile`: Compile LaTeX to PDF
- `watch`: Watch and auto-compile
- `preview`: Compile and open
- `template`: Create from template

**Examples**

```bash
# compile paper.tex
agent-do latex compile paper.tex
# create article template
agent-do latex template article
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `template`
- Write (connect/interact/save): `compile`, `preview`
- long_running (daemon/stream/session; may never return): `watch`

### learn

Learning and pattern improvement

Concurrency: `write`

**Capabilities**

- correct mistakes
- provide feedback
- view learned patterns

**Commands**

- `correct`: Correct routing mistake
- `feedback`: Rate response
- `patterns`: Show learned patterns
- `stats`: Show learning stats

**Examples**

```bash
# that should have been agent-ios screenshot
agent-do learn correct 'screenshot ios' --should 'agent-ios screenshot'
# that was a great response
agent-do learn feedback 5
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `patterns`, `stats`
- Write (connect/interact/save): `correct`, `feedback`

### linear

Control Linear

Concurrency: `mixed`

**Capabilities**

- create issues
- update status
- manage projects

**Commands**

- `create`: Create issue
- `update`: Update issue
- `list`: List issues

**Examples**

```bash
# create a bug report
agent-do linear create --type bug
# list my issues
agent-do linear list --mine
```

**Credentials**

- Required: `LINEAR_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `create`, `update`

### logs

Control log aggregation

Concurrency: `read`

**Capabilities**

- search logs
- tail logs
- filter by service

**Commands**

- `search`: Search logs
- `tail`: Tail logs
- `filter`: Filter logs

**Examples**

```bash
# search logs for errors
agent-do logs search 'error'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `filter`, `search`
- long_running (daemon/stream/session; may never return): `tail`

### macos

Control native macOS desktop applications via accessibility APIs

Concurrency: `mixed`

**Capabilities**

- click buttons and UI elements
- type text into fields
- read UI element tree
- navigate menus

**Commands**

- `click`: Click an element
- `type`: Type text
- `tree`: Get UI hierarchy
- `find`: Find elements
- `focus`: Focus an application
- `menu`: Navigate menus

**Examples**

```bash
# click the Save button in Photoshop
agent-do macos click Photoshop --title Save
# type hello into the search field
agent-do macos type --role textfield hello
# get the UI tree of Finder
agent-do macos tree Finder
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `find`, `tree`
- Write (connect/interact/save): `click`, `focus`, `menu`, `type`

### manna

Git-backed issue tracking with generated, bidirectionally linked handoff work orders

Concurrency: `write`

**Capabilities**

- track issues and dependencies
- declare portable typed relations between autonomous repository boards
- manage session state
- store context across sessions
- query issue history

**Commands**

- `init`: Initialize .manna plus the tracked .handoff workflow scaffold
- `migrate`: Atomically admit a legacy board into strict paired workflow state
- `status`: Show current session and claimed issues
- `state`: Emit the full derived board model as JSON or YAML, including graph buckets, receipts, federation, drift, and coord attention
- `estate`: Emit every registered board as the /api/boards model without starting or contacting the serve daemon
- `create`: Create an issue; actionable items generate a linked .handoff work order (--type track|item|dream, --track, --source)
- `claim`: Claim an issue for the current session (fails closed on broken handoff pairs; refuses dreams until converted)
- `done`: Mark a claimed issue as done
- `order`: Move a paired item to a dense one-based handoff priority and synchronize generated presentation
- `sync`: Derive numbered handoff filenames, blocker launch gates, and the README index from board state
- `abandon`: Release a claimed issue back to open
- `handoff`: Seal and bind an intentional canonical handoff edit
- `federation`: Initialize, inspect, or explicitly fork a portable Manna federation identity
- `relate`: Add one typed outbound cross-board relation
- `unrelate`: Remove one typed outbound cross-board relation
- `relations`: List local relations and optionally resolve them through registered boards
- `block`: Add a blocker dependency
- `unblock`: Remove a blocker dependency
- `list`: List issues (--status, --type, --track filters)
- `show`: Show issue details
- `update`: Update issue metadata; lifecycle state changes require claim, done, abandon, block, or unblock
- `delete`: Delete issue
- `context`: Get session context
- `dream`: File an idea spark on the nearest board or the global inbox
- `lint`: Check board grammar and strict handoff linkage; findings exit 1
- `reconcile`: Detect board, handoff, and workflow-sprawl drift; --fix applies safe repairs
- `serve`: Read-only human board view on a stable local port (picked free on first run, kept in local config); every registered board indexed at /, this project at /\<name>; always prints the URL

**Examples**

```bash
# initialize manna
agent-do manna init
# migrate a legacy manna board
agent-do manna migrate
# create a new issue
agent-do manna create 'Fix login bug'
# list all issues
agent-do manna list
# read the complete derived board state
agent-do manna state --json
# read every registered manna board
agent-do manna estate --json
# show issue details
agent-do manna show 1
# capture an idea for later
agent-do manna dream 'Unify the auth flows'
# convert a dream into claimable work
agent-do manna update mn-abc123 --type item
# check the board for drift
agent-do manna reconcile --write-drift
# move an item to the top of the handoff plan
agent-do manna order mn-abc123 1
# synchronize handoff filenames after a board change
agent-do manna sync
# show me the board
agent-do manna serve --open
# list every board on this machine
agent-do manna serve --scan ~/Projects
# initialize portable board identity
agent-do manna federation init
# link this item to a sibling board
agent-do manna relate mn-a1b2c3 --kind counterpart --to manna://mb-0123456789abcdef0123456789abcdef/mn-d4e5f6
# inspect cross-board relations
agent-do manna relations --resolve --check
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `context`, `estate`, `lint`, `list`, `relations`, `show`, `state`, `status`
- Write (connect/interact/save): `abandon`, `block`, `claim`, `create`, `delete`, `done`, `dream`, `federation`, `handoff`, `init`, `migrate`, `order`, `reconcile`, `relate`, `sync`, `unblock`, `unrelate`, `update`
- destructive (irreversible data loss; confirm before auto-running): `delete`, `federation`, `migrate`, `unrelate`
- long_running (daemon/stream/session; may never return): `serve`
- polymorphic (beat decided by payload or flag at call time): `federation`, `reconcile`, `relations`
- composite (one call performs several beats internally): `federation`, `migrate`, `order`, `sync`

### meet

Google Meet control

Concurrency: `mixed`

**Capabilities**

- create/join meetings
- control audio/video
- chat

**Commands**

- `new`: Create new meeting
- `join`: Join meeting
- `mute`: Toggle microphone
- `video`: Toggle camera

**Examples**

```bash
# create new google meet
agent-do meet new
# join meet abc-defg-hij
agent-do meet join abc-defg-hij
```

**Safety (from contracts)**

- Write (connect/interact/save): `join`, `mute`, `new`, `video`

### meetings

Unified enterprise meeting orchestration across Zoom, Google Meet, and Microsoft Teams

Concurrency: `mixed`

**Capabilities**

- detect the active meeting provider
- auto-route join links and meeting identifiers to the correct provider
- provide one snapshot for provider readiness and current meeting state
- expose generic meeting controls like mute, video, share, chat, and end
- preserve provider-specific passthroughs under one family tool

**Commands**

- `snapshot`: Snapshot provider availability and active meeting state
- `providers`: List supported providers
- `active`: Show the detected active meeting provider
- `join`: Join a meeting: join \<url|code|id> [--provider \<name>]
- `new`: Start a new meeting: new [provider]
- `schedule`: Schedule a meeting: schedule \<provider> \<topic> [...]
- `mute`: Toggle microphone on the active provider
- `video`: Toggle camera on the active provider
- `share`: Start screen sharing on the active provider
- `chat`: Open or send meeting chat on the active provider
- `end`: End or leave the active meeting
- `zoom`: Zoom passthrough: zoom \<command> [args...]
- `meet`: Google Meet passthrough: meet \<command> [args...]
- `teams`: Teams passthrough: teams \<command> [args...]

**Examples**

```bash
# join a Google Meet link
agent-do meetings join https://meet.google.com/abc-defg-hij
# mute the current meeting
agent-do meetings mute
# start a new Zoom meeting
agent-do meetings new zoom
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `active`, `providers`, `snapshot`
- Write (connect/interact/save): `chat`, `end`, `join`, `meet`, `mute`, `new`, `schedule`, `share`, `teams`, `video`, `zoom`
- long_running (daemon/stream/session; may never return): `chat`
- polymorphic (beat decided by payload or flag at call time): `meet`, `teams`, `zoom`

### memory

Persistent memory and context

Concurrency: `mixed`

**Capabilities**

- store/recall facts
- manage context
- search memories

**Commands**

- `store`: Store memory
- `recall`: Recall memory
- `search`: Search memories
- `list`: List all memories

**Examples**

```bash
# remember that the project uses React
agent-do memory store project 'Uses React'
# what do I know about the project
agent-do memory recall project
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `recall`, `search`
- Write (connect/interact/save): `store`

### metrics

System metrics and monitoring (CPU, memory, disk, network, processes)

Concurrency: `read`

**Capabilities**

- read CPU, memory, disk, and network usage
- list top processes
- report load average and uptime

**Commands**

- `cpu`: CPU usage
- `memory`: Memory usage
- `disk`: Disk usage
- `network`: Network stats
- `processes`: Top processes: processes [n]
- `load`: System load average
- `uptime`: System uptime
- `all`: Summary of all metrics

**Examples**

```bash
# show CPU usage
agent-do metrics cpu
# top processes
agent-do metrics processes 10
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `all`, `cpu`, `disk`, `load`, `memory`, `network`, `processes`, `uptime`

### midi

MIDI control

Concurrency: `mixed`

**Capabilities**

- send MIDI messages
- list devices
- record/playback

**Commands**

- `list`: List devices
- `send`: Send message
- `play`: Play file

**Examples**

```bash
# list MIDI devices
agent-do midi list
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `play`, `send`

### models

Capability-aware model roles for agent-do's internal LLM calls

Concurrency: `mixed`

**Capabilities**

- resolve fast, vision, and deep internal model roles
- expose provider, endpoint, modality, and generation capability records
- preserve explicit user-selected models outside agent-do internals

**Commands**

- `list`: Show configured roles, chains, and resolved models
- `resolve`: Resolve one internal model role
- `doctor`: Verify live provider listings and refresh capabilities with --fix

**Examples**

```bash
# show agent-do's internal model defaults
agent-do models list
# resolve the internal vision model
agent-do models resolve vision --json
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`: Anthropic internal model calls and live capability verification [recommended]
- `OPENAI_API_KEY`: OpenAI Responses API fallback and live model verification
- Note: Provider keys are optional individually; doctor warns and skips an unconfigured provider.

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `resolve`
- Write (connect/interact/save): `doctor`
- composite (one call performs several beats internally): `doctor`

### namecheap

Namecheap domain and DNS management — domains, DNS records (safe upsert with exact verification), nameservers, SSL, availability

Concurrency: `write`

**Capabilities**

- list domains with expiry dates and auto-renew status
- domain details (whois, nameservers, lock status)
- check domain availability
- renew domains
- list and manage DNS records (safe GET-merge-SET pattern)
- reject suspicious masked or truncated DNS values before write
- verify exact provider read-back after DNS writes
- compare expected records against public DNS when requested
- manage nameservers (custom or default)
- list SSL certificates

**Commands**

- `domains`: List all domains: domains [--expiring]
- `domain`: Domain details: domain \<name>
- `domain-check`: Check availability: domain-check \<name> [name2...]
- `domain-renew`: Renew domain: domain-renew \<name> [--years N]
- `dns`: List DNS records: dns \<domain>
- `dns-add`: Add record (safe): dns-add \<domain> \<type> \<host> \<addr>
- `dns-update`: Update record (safe): dns-update \<domain> \<host> \<type> \<addr>
- `dns-verify`: Verify exact record match: dns-verify \<domain> \<type> \<host> \<addr> [--public-verify]
- `dns-del`: Delete record (safe): dns-del \<domain> \<host> [type]
- `nameservers`: Show nameservers: nameservers \<domain>
- `nameservers-set`: Set custom NS: nameservers-set \<domain> \<ns1,ns2>
- `ssl-list`: List SSL certificates
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my domains
agent-do namecheap domains
# check if a domain is available
agent-do namecheap domain-check coolstartup.com
# show DNS records
agent-do namecheap dns example.com
# add a DNS record
agent-do namecheap dns-add example.com A www 1.2.3.4
# verify a DKIM record exactly
agent-do namecheap dns-verify example.com TXT resend._domainkey "p=..."
# domain expiry dates
agent-do namecheap domains --expiring
```

**Credentials**

- Required: `NAMECHEAP_API_USER`, `NAMECHEAP_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `dns`, `dns-verify`, `domain`, `domain-check`, `domains`, `nameservers`, `snapshot`, `ssl-list`
- Write (connect/interact/save): `dns-add`, `dns-del`, `dns-update`, `domain-renew`, `nameservers-set`
- destructive (irreversible data loss; confirm before auto-running): `dns-del`

### network

Network diagnostics

Concurrency: `read`

**Capabilities**

- check connectivity
- trace routes
- scan ports

**Commands**

- `ping`: Ping host
- `trace`: Trace route
- `scan`: Scan ports
- `whois`: WHOIS lookup

**Examples**

```bash
# what's using port 3000
agent-do network scan --port 3000
# ping google.com
agent-do network ping google.com
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `ping`, `scan`, `trace`, `whois`

### notion

Notion team operating layer for pages, data sources, tasks, decisions, handoffs, comments, cache, and webhooks

Concurrency: `mixed`

**Capabilities**

- use Notion API version 2025-09-03 and the databases/data-sources model
- resolve page/database/data-source URLs, IDs, and human names with clarification on ambiguity
- read workspace users, search results, pages, recursive blocks, data sources, schemas, and query results
- save team notes, linked groups, tasks, decisions, handoffs, and comments with read-back verification
- maintain a local SQLite/FTS cache of pages, blocks, users, comments, data sources, and relations
- inspect/adopt existing team workspace structure into a schema mapping file before creating anything
- ingest webhook payloads into a local event store; polling sync remains the baseline freshness path
- optionally build semantic cache embeddings over Notion cache content

**Commands**

- `doctor`: Credential, API, cache, and capability readiness: doctor [--json]
- `snapshot`: Workspace/cache state as JSON: snapshot [--json]
- `auth`: Token identity: auth status [--json]
- `workspace`: Workspace summary: workspace [--json]
- `users`: List users: users [--json]
- `search`: Search pages/data sources: search \<query> [--json]
- `read`: Read a page recursively: read \<page-or-url> [--json]
- `blocks`: Read recursive block tree: blocks \<page-or-url> [--json]
- `data-sources`: Data sources: data-sources list|schema|query
- `save`: Create team page/row: save --title T --content T [--data-source ID|--parent-page ID]
- `save-group`: Create linked hub + children: save-group --title T --child name:body
- `task`: Tasks: task add --title T [--owner ID] [--due YYYY-MM-DD]
- `decision`: Decisions: decision record --title T --content T
- `handoff`: Agent handoffs: handoff create --title T --content T
- `comment`: Comments: comment add \<page> --text T [--mention-user ID]
- `verify`: Read back write target: verify \<page-or-url> [--json]
- `sync`: Poll and refresh local cache: sync [--limit N] [--json]
- `cache`: Cache search/status: cache search \<query> | cache status
- `bootstrap-team`: Inspect/adopt team data sources into schema mapping
- `schema`: Show schema mapping: schema show [--json]
- `webhooks`: Webhook store: webhooks doctor|ingest
- `embed`: Semantic cache: embed status|refresh

**Examples**

```bash
# check notion setup
agent-do notion doctor --json
# search team notion
agent-do notion search "agent-do release" --json
# read this notion page
agent-do notion read https://www.notion.so/example/Page-0123456789abcdef0123456789abcdef --json
# list team data sources
agent-do notion data-sources list --json
# save this as a team decision
agent-do notion decision record --title "Use Notion for team execution" --content "Decision text" --json
# create a task for Chris
agent-do notion task add --title "Review release checklist" --owner "<notion-user-id>" --due 2026-05-22 --json
# build the local Notion cache
agent-do notion sync --limit 100 --json
# find cached team handoffs
agent-do notion cache search "handoff" --json
# adopt existing team workspace structure
agent-do notion bootstrap-team --json
```

**Credentials**

- Required: `NOTION_TOKEN`
- Optional: `VOYAGE_API_KEY`, `OPENAI_API_KEY`
- `NOTION_TOKEN`: Notion workspace read/write, comments, data sources, cache sync, schema bootstrap, and verified team saves [recommended]
- `VOYAGE_API_KEY`: optional semantic cache embeddings for Notion pages and blocks
- `OPENAI_API_KEY`: optional semantic cache fallback embeddings
- Note: Notion requires an internal integration token and pages/data sources shared with that integration.
- Note: Polling sync is the baseline freshness path. Webhooks require a public HTTPS receiver and Notion-side subscription setup.

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `auth`, `blocks`, `cache`, `data-sources list`, `data-sources query`, `data-sources schema`, `embed status`, `read`, `schema`, `search`, `snapshot`, `users`, `verify`, `workspace`
- Write (connect/interact/save): `bootstrap-team`, `comment`, `decision`, `doctor`, `embed refresh`, `handoff`, `save`, `save-group`, `sync`, `task`, `webhooks doctor`, `webhooks ingest`
- composite (one call performs several beats internally): `bootstrap-team`, `doctor`, `webhooks doctor`, `webhooks ingest`

### obsidian

Obsidian vault integration with a local SQLite vault index plus official Obsidian CLI fallback

Concurrency: `mixed`

**Capabilities**

- index, read, keyword search, semantic search, hybrid retrieval, query, relate, summarize, and audit local Obsidian vaults
- build chunked semantic embeddings with Voyage voyage-4-large by default, OpenAI text-embedding-3-large fallback metadata, and Voyage rerank-2.5 reranking when available
- build cited agent context and GPT-5.5 vault chat answers from local chunks
- save individual notes and linked note groups with per-vault conventions
- manage daily, weekly, period, template, graph, tag, backlink, and task workflows
- read and write YAML frontmatter properties, including batch updates
- target a specific vault path with --vault or AGENT_OBSIDIAN_VAULT_PATH, or fall back to obsidian-cli for named live vaults
- emit structured JSON output for every local-index command
- one-time CLI link from the Obsidian.app bundle into ~/.local/bin
- +live-gated eval / dev / plugin surface for plugin and theme development

**Commands**

- `doctor`: Check obsidian-cli wiring: doctor [--fix] [--json]
- `snapshot`: Integration state as JSON: snapshot [--vault V]
- `refresh`: Refresh local SQLite index: refresh [--full] [--json]
- `embed`: Semantic embedding index: embed status|refresh [--full] [--json]
- `read`: Read a note: read \<name> | --path \<path> [--copy] [--vault V]
- `create`: Create a note: create \<name> [--content T] [--template T] [--overwrite] [--open] [--vault V]
- `append`: Append text to a note: append \<name> [\<text>...] [--content T] [--path] [--vault V]
- `search`: Search notes: search \<query> [--mode keyword|semantic|hybrid] [--limit N] [--total] [--vault V]
- `context`: Build cited retrieval context: context build \<query> [--mode keyword|semantic|hybrid]
- `chat`: Answer from vault context with citations: chat \<question> [--mode hybrid]
- `connections`: Find related notes by semantic/hybrid retrieval: connections \<name>
- `query`: Safe DQL subset over local index: query "FROM #tag WHERE status=active SORT due ASC"
- `relate`: Rank backlink candidates: relate \<name-or-content> [--limit N]
- `summarize`: Summarize matching notes with cited sources: summarize \<topic>
- `save`: Save content with conventions frontmatter: save --content T [--related auto] [--scope local|team|public]
- `save-group`: Save linked note group: save-group \<hub> --child name:body [--scope S]
- `daily`: Daily notes: daily read | daily append | daily list
- `weekly`: Weekly notes: weekly read | weekly append | weekly list
- `period`: Period notes: period read --from YYYY-MM-DD --to YYYY-MM-DD
- `prop`: Frontmatter properties: prop get|set|list|batch
- `tasks`: Unified tasks: tasks list|add|complete|update|next
- `tags`: List or manage tags: tags [--counts] [--sort name|count]
- `backlinks`: Backlinks for a note: backlinks \<name>
- `graph`: Vault graph: graph orphans|broken-links|clusters|cluster|tag-usage
- `templates`: Vault templates: templates list|show|apply|register
- `audit`: Vault hygiene ledger: audit [--scope folder] [--json]
- `move`: Move note with journaled link rewrite: move \<from> \<to> [--update-links]
- `delete`: Move note to .trash: delete \<name> --confirm
- `eval`: +live: run JavaScript in Obsidian: eval \<code>
- `dev`: +live: developer surface: dev {errors|screenshot|dom|console|css|mobile}
- `plugin`: +live: plugin management: plugin reload \<id>

**Examples**

```bash
# check that the obsidian CLI is wired up
agent-do obsidian doctor --json
# read today's daily note
agent-do obsidian daily read
# append a task to today's daily note
agent-do obsidian daily append "- [ ] Review PR"
# create a new note silently
agent-do obsidian create "Inbox/Idea" --content "Pricing experiment"
# search the active vault
agent-do obsidian search "review" --limit 5
# build the semantic vault index
agent-do obsidian embed refresh --json
# build cited agent context from the vault
agent-do obsidian context build "what did I decide about voice" --json
# ask the vault a question with citations
agent-do obsidian chat "what is on my plate today?" --json
# save a note with related links
agent-do obsidian save --content "Pricing experiment" --related auto --json
# ask the vault a question
agent-do obsidian summarize "Trinity Site" --json
# choose next tasks
agent-do obsidian tasks next --horizon today --json
# mark a project as done
agent-do obsidian prop set status done --file "Projects/agent-obsidian"
# list backlinks for a note
agent-do obsidian backlinks "agent-do roadmap"
# run obsidian dev tools (requires +live)
agent-do +live(scope=desktop,app=Obsidian,ttl=15m) obsidian dev errors
```

**Credentials**

- Optional: `VOYAGE_API_KEY`, `OPENAI_API_KEY`, `COHERE_API_KEY`
- `VOYAGE_API_KEY`: default voyage-4-large semantic embeddings and Voyage rerank-2.5 reranking [recommended]
- `OPENAI_API_KEY`: GPT-5.5 vault chat and text-embedding-3-large fallback embeddings [recommended]
- `COHERE_API_KEY`: future multimodal vault embeddings with Cohere embed-v4.0
- Note: Obsidian read, save, keyword search, tasks, graph, audit, and local indexing work without API keys.
- Note: Add VOYAGE_API_KEY for the recommended semantic vault index.
- Note: Add OPENAI_API_KEY for vault chat and the OpenAI embedding fallback.

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `audit`, `backlinks`, `connections`, `context build`, `daily list`, `daily read`, `embed status`, `graph broken-links`, `graph cluster`, `graph clusters`, `graph orphans`, `graph tag-usage`, `period read`, `prop get`, `prop list`, `query`, `read`, `relate`, `search`, `snapshot`, `summarize`, `tags`, `tasks list`, `tasks next`, `templates list`, `templates show`, `weekly list`, `weekly read`
- Write (connect/interact/save): `append`, `audit fix`, `chat`, `create`, `daily append`, `delete`, `doctor`, `embed refresh`, `move`, `prop batch`, `prop set`, `refresh`, `save`, `save-group`, `tags merge`, `tags rename`, `tasks add`, `tasks complete`, `tasks update`, `templates apply`, `templates register`, `weekly append`
- destructive (irreversible data loss; confirm before auto-running): `delete`
- long_running (daemon/stream/session; may never return): `chat`, `embed refresh`
- composite (one call performs several beats internally): `doctor`

### ocr

Screen text extraction

Concurrency: `read`

**Capabilities**

- extract text from screen
- extract from images
- find text location

**Commands**

- `screen`: OCR entire screen
- `region`: OCR screen region
- `file`: OCR image file
- `find`: Find text on screen

**Examples**

```bash
# extract text from screen
agent-do ocr screen
# find where 'Submit' button is
agent-do ocr find 'Submit'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `file`, `find`, `region`, `screen`

### okta

Okta tenant management — applications (OIDC/SAML), SSO configuration, users, groups, authorization servers, system logs

Concurrency: `mixed`

**Capabilities**

- create and manage OIDC applications (web, SPA, native, service)
- create and manage SAML 2.0 applications
- manage application credentials (client ID, secret, rotation)
- assign and unassign users and groups to applications
- search users and groups
- manage group memberships
- list and inspect authorization servers, scopes, claims, policies
- query system logs for auth events and errors
- manage trusted origins (CORS, redirect)

**Commands**

- `apps`: List applications: apps [--status active]
- `app`: Application details: app \<name-or-id>
- `app-create-oidc`: Create OIDC app: app-create-oidc \<label> --type web|spa|native|service --redirect-uris \<uris>
- `app-create-saml`: Create SAML app: app-create-saml \<label> --sso-url \<url> --audience \<uri>
- `app-update`: Update app: app-update \<app> --redirect-uris \<uris> --grant-types \<types>
- `app-creds`: Get credentials: app-creds \<app> [--reveal]
- `app-creds-rotate`: Rotate client secret: app-creds-rotate \<app>
- `app-assign-group`: Assign group: app-assign-group \<app> \<group>
- `users`: List/search users: users [--search \<query>]
- `groups`: List/search groups: groups [--search \<query>]
- `auth-servers`: List authorization servers
- `logs`: System logs: logs [--since 24h] [--filter \<expression>]
- `trusted-origins`: List trusted origins
- `snapshot`: Full tenant state as JSON

**Examples**

```bash
# list Okta applications
agent-do okta apps
# create an OIDC web app
agent-do okta app-create-oidc "My App" --type web --redirect-uris "http://localhost:3000/callback"
# get app credentials
agent-do okta app-creds "Versova Align"
# assign group to app
agent-do okta app-assign-group "Versova Align" Everyone
# check auth events
agent-do okta logs --since 1h
# Okta tenant overview
agent-do okta snapshot
```

**Credentials**

- Required: `OKTA_API_TOKEN`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `app`, `app-creds`, `apps`, `auth-servers`, `groups`, `logs`, `snapshot`, `trusted-origins`, `users`
- Write (connect/interact/save): `app-assign-group`, `app-create-oidc native`, `app-create-oidc service`, `app-create-oidc spa`, `app-create-oidc web`, `app-create-saml`, `app-creds-rotate`, `app-update`
- sensitive (emits or persists secret material; guard output): `app-create-oidc service`, `app-create-oidc web`, `app-creds`, `app-creds-rotate`

### pdf

Control PDF operations

Concurrency: `mixed`

**Capabilities**

- read PDF content
- merge/split PDFs
- extract text

**Commands**

- `read`: Read PDF
- `merge`: Merge PDFs
- `split`: Split PDF
- `extract`: Extract text

**Examples**

```bash
# extract text from document.pdf
agent-do pdf extract document.pdf
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `extract`, `read`
- Write (connect/interact/save): `merge`, `split`

### pdf2md

Convert PDF files to Markdown

Concurrency: `read`

**Capabilities**

- convert PDF to markdown
- auto-detect tabular vs prose PDFs
- batch convert directories
- preserve table layout for AI consumption

**Commands**

- `convert`: Convert PDF to markdown
- `batch`: Batch convert directory of PDFs
- `snapshot`: Show available tools and PDFs

**Examples**

```bash
# convert report.pdf to markdown
agent-do pdf2md convert report.pdf
# convert all PDFs in current directory
agent-do pdf2md batch .
# convert spreadsheet PDF preserving table layout
agent-do pdf2md convert data.pdf --mode table
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `snapshot`
- Write (connect/interact/save): `batch`, `convert`
- own_state (writes only its own cache/state; parallel-safe): `batch`, `convert`

### printer

Printer control

Concurrency: `write`

**Capabilities**

- list printers
- print documents
- check status

**Commands**

- `list`: List printers
- `print`: Print document
- `status`: Check status

**Examples**

```bash
# print document.pdf
agent-do printer print document.pdf
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `status`
- Write (connect/interact/save): `print`

### prompt

Prompt management and templating

Concurrency: `read`

**Capabilities**

- save/load prompts
- template variables
- prompt library

**Commands**

- `save`: Save prompt
- `load`: Load prompt
- `run`: Run with variables
- `list`: List saved prompts

**Examples**

```bash
# save this prompt as explain
agent-do prompt save explain
# run explain prompt with topic=AI
agent-do prompt run explain topic=AI
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `load`, `run`
- Write (connect/interact/save): `save`
- own_state (writes only its own cache/state; parallel-safe): `save`

### psql

PostgreSQL CLI wrapper for AI agents over the native psql binary

Concurrency: `mixed`

**Capabilities**

- connect via connection string or saved profile (Render, Supabase, any Postgres)
- explore schema (tables, views, columns, constraints, indexes, FKs, extensions, sizes)
- run SQL queries returning JSON, sample tables, count rows, execute SQL files
- inspect administration state (connections, locks, table stats, index usage, version)
- back up and restore with pg_dump and pg_restore wrappers

**Commands**

- `connect`: Connect via connection string or saved profile
- `disconnect`: End session
- `status`: Show connection status
- `profiles`: List saved connection profiles
- `profile`: Add or remove a connection profile (password in keychain)
- `snapshot`: Full schema overview (tables, views, sizes, extensions)
- `tables`: List tables (optional LIKE pattern)
- `views`: List views
- `describe`: Columns, types, constraints, indexes, FKs for a table
- `schemas`: List schemas
- `extensions`: List installed extensions
- `sizes`: Table and index sizes
- `relations`: FK relationship map
- `query`: Execute SQL and return JSON
- `sample`: Sample rows from a table
- `count`: Row count for a table
- `exec`: Execute a SQL file
- `connections`: Active database connections
- `locks`: Current lock contention
- `stats`: Table statistics (seq/idx scans, live/dead tuples)
- `indexes`: Index details and usage stats
- `version`: PostgreSQL server version
- `dump`: pg_dump wrapper (table, schema-only, format options)
- `restore`: pg_restore wrapper (clean, schema-only options)

**Examples**

```bash
# connect to a postgres database with a connection string
agent-do psql connect "postgresql://user:pass@host:5432/db"
# show the full schema overview
agent-do psql snapshot
# describe a postgres table
agent-do psql describe users
# run a SQL query returning JSON
agent-do psql query "SELECT count(*) FROM orders"
# dump a postgres database
agent-do psql dump backup.sql --schema-only
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `connections`, `count`, `describe`, `extensions`, `indexes`, `locks`, `profile`, `profiles`, `relations`, `sample`, `schemas`, `sizes`, `snapshot`, `stats`, `status`, `tables`, `version`, `views`
- Write (connect/interact/save): `connect`, `disconnect`, `dump`, `exec`, `query`, `restore`
- destructive (irreversible data loss; confirm before auto-running): `restore`
- polymorphic (beat decided by payload or flag at call time): `exec`, `query`

### render

Full-surface Render.com control — services (create/update/delete/lifecycle), deploys (trigger/show/cancel/rollback), one-off jobs, cron runs, env vars + secret files, env groups, postgres lifecycle + creds + recovery, key value, blueprints, custom domains + headers + routes, persistent disks + snapshots, dedicated IPs, registry credentials, projects + environments, webhooks, notifications, maintenance, audit logs, owners, observability (logs + metrics)

Concurrency: `write`

**Capabilities**

- create and manage services (web, worker, static, private, cron)
- trigger, view, cancel, and roll back deploys
- run and cancel one-off jobs
- trigger and cancel cron job runs
- manage env vars and secret files at service and env-group scope
- link env groups to services
- full PostgreSQL lifecycle (create, update, delete, suspend, resume, restart, failover, recovery, exports, credentials, connection info)
- full Key Value (Redis-compatible) lifecycle
- validate render.yaml blueprints, manage existing blueprints, view sync history
- custom domains add/show/verify/delete; HTTP headers and static-site routes
- persistent disks with snapshots and restore
- dedicated IPs, registry credentials for private Docker registries
- projects and environments with resource linking
- webhooks for deploy and lifecycle events
- notification settings and per-service overrides
- audit log retrieval and maintenance windows
- structured logs and metrics with filters
- cross-account snapshot

**Commands**

- `owners`: List workspaces (for --owner resolution)
- `whoami`: Show authenticated user
- `audit`: Audit log entries
- `services`: List services
- `show`: Service details
- `create`: Create service: create \<web|worker|static|private|cron> \<name> [opts]
- `update`: Update service settings
- `delete`: Delete a service (--yes required)
- `cache-purge`: Purge build cache
- `events`: Recent service events
- `instances`: Running instance list
- `restart`: Restart service
- `suspend`: Suspend service
- `resume`: Resume service
- `scale`: Scale instance count
- `autoscaling`: Autoscaling: show|enable|disable
- `deploy`: Trigger deploy, or deploy {show|cancel} for sub-ops
- `deploys`: List recent deploys
- `rollback`: Roll back to a prior deploy
- `jobs`: List one-off jobs
- `job`: One-off job ops: run|show|cancel
- `cron`: Cron job ops: run|cancel
- `env`: List env vars
- `env-set`: Upsert env var
- `env-del`: Delete env var
- `secret`: Per-service secret files: list|get|set|del
- `env-group`: Env groups: list|show|create|delete|rename|link|unlink|set|get|del-var|secret
- `db`: Postgres: list|show|create|update|delete|suspend|resume|restart|failover|connect-info|backup|backups|recover|creds
- `kv`: Key Value: list|show|create|update|delete|connect-info|suspend|resume
- `domains`: List custom domains
- `domain`: Custom domain ops: add|show|del|verify
- `header`: HTTP header rules: list|add|del
- `route`: Static-site routes: list|add|del
- `blueprint`: Blueprints: list|show|validate|update|delete|syncs
- `disk`: Persistent disks: list|show|create|update|delete|snapshots|restore
- `dedicated-ip`: Dedicated IPs: list|show|create|delete
- `registry`: Docker registry creds: list|show|add|delete
- `projects`: List projects (shorthand)
- `project`: Project ops: list|show|create|update|delete
- `environment`: Environment ops: list|show|create|delete|link|unlink
- `webhook`: Webhooks: list|show|create|update|delete|events
- `notify`: Notifications: show|update|overrides|override
- `maintenance`: Maintenance windows: list|show|reschedule|trigger
- `metrics`: Service metrics
- `logs`: Structured logs with filters
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my render services
agent-do render services
# create a new web service on render from a github repo
agent-do render create web my-api --repo https://github.com/me/api --build "npm ci && npm run build" --start "npm start"
# create a render cron job
agent-do render create cron daily-task --repo https://github.com/me/jobs --schedule "0 12 * * *" --start "node daily.js"
# dry-run a render service create to see the request body
agent-do render create web my-api --repo https://github.com/me/api --build "npm ci" --start "npm start" --dry-run
# create a render postgres database
agent-do render db create main-db --plan basic_1gb --version 16 --region oregon
# list render env groups
agent-do render env-group list
# link a render env group to a service
agent-do render env-group link shared-env my-api
# validate a render.yaml blueprint
agent-do render blueprint validate render.yaml
# roll back a render deploy
agent-do render rollback my-api dep-xxxxx
# trigger a render cron job manually
agent-do render cron run daily-task
# add a custom domain on render
agent-do render domain add my-api example.com
# create a webhook for render deploys
agent-do render webhook create --name slack --url https://hooks.slack.com/... --event deploy_ended
# deploy my-api on render
agent-do render deploy my-api
# show render service details
agent-do render show my-api
# view render service logs
agent-do render logs my-api
# set env var on render
agent-do render env-set my-api DATABASE_URL postgres://...
# list render databases
agent-do render db list
# get render account snapshot
agent-do render snapshot
```

**Credentials**

- Required: `RENDER_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `audit`, `autoscaling show`, `blueprint list`, `blueprint show`, `blueprint syncs`, `blueprint validate`, `dedicated-ip list`, `dedicated-ip show`, `deploys`, `disk list`, `disk show`, `disk snapshots`, `domain`, `domains`, `env`, `env-group get`, `env-group list`, `env-group secret`, `env-group show`, `environment list`, `environment show`, `events`, `header list`, `instances`, `job show`, `jobs`, `kv connect-info`, `kv list`, `kv show`, `logs`, `maintenance list`, `maintenance show`, `metrics`, `notify override`, `notify overrides`, `notify show`, `owners`, `project`, `projects`, `registry list`, `registry show`, `route list`, `secret get`, `secret list`, `services`, `show`, `snapshot`, `webhook events`, `webhook list`, `webhook show`, `whoami`
- Write (connect/interact/save): `autoscaling disable`, `autoscaling enable`, `blueprint delete`, `blueprint update`, `cache-purge`, `create`, `cron cancel`, `cron run`, `db`, `dedicated-ip create`, `dedicated-ip delete`, `delete`, `deploy`, `disk create`, `disk delete`, `disk restore`, `disk update`, `env-del`, `env-group create`, `env-group del-var`, `env-group delete`, `env-group link`, `env-group rename`, `env-group set`, `env-group unlink`, `env-set`, `environment create`, `environment delete`, `environment link`, `environment unlink`, `header add`, `header del`, `job cancel`, `job run`, `kv create`, `kv delete`, `kv resume`, `kv suspend`, `kv update`, `maintenance reschedule`, `maintenance trigger`, `notify update`, `registry add`, `registry delete`, `restart`, `resume`, `rollback`, `route add`, `route del`, `scale`, `secret del`, `secret set`, `suspend`, `update`, `webhook create`, `webhook delete`, `webhook update`
- destructive (irreversible data loss; confirm before auto-running): `blueprint delete`, `cache-purge`, `dedicated-ip delete`, `delete`, `disk delete`, `env-del`, `env-group del-var`, `env-group delete`, `environment delete`, `header del`, `kv delete`, `registry delete`, `route del`, `secret del`, `webhook delete`
- sensitive (emits or persists secret material; guard output): `db`, `env-group secret`, `kv connect-info`, `secret get`
- polymorphic (beat decided by payload or flag at call time): `db`

### repl

Control interactive REPLs (Python, Node, psql, etc.)

Concurrency: `mixed`

**Capabilities**

- spawn REPL sessions
- send commands
- read output
- detect prompts

**Commands**

- `spawn`: Start a REPL
- `send`: Send command to REPL
- `read`: Read REPL output
- `list`: List active REPLs
- `kill`: Kill a REPL session

**Examples**

```bash
# start a python REPL
agent-do repl spawn python
# send x = 42 to my python session
agent-do repl send 1 'x = 42'
# read output from python
agent-do repl read 1
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `read`
- Write (connect/interact/save): `kill`, `send`, `spawn`
- destructive (irreversible data loss; confirm before auto-running): `kill`

### resend

Resend domain management and DNS verification — exact records, verification state, and public DNS checks

Concurrency: `mixed`

**Capabilities**

- list and inspect Resend domains
- create Resend domains
- retrieve exact DNS records without UI truncation
- trigger domain verification
- compare public DNS against Resend's expected records

**Commands**

- `domains`: List domains: domains [--limit N]
- `domain`: Domain details: domain \<name-or-id>
- `add`: Create domain: add \<name> [--region R] [--tracking-subdomain sub]
- `records`: Exact DNS records: records \<name-or-id>
- `status`: Verification summary: status \<name-or-id>
- `verify`: Trigger verification: verify \<name-or-id> [--wait N]
- `dns-check`: Compare public DNS to Resend records: dns-check \<name-or-id> [--wait N]

**Examples**

```bash
# list my resend domains
agent-do resend domains
# inspect one resend domain
agent-do resend domain example.com
# get exact dns records from resend
agent-do resend records example.com
# trigger resend verification
agent-do resend verify example.com
# compare public dns against resend
agent-do resend dns-check example.com --wait 60
```

**Credentials**

- Required: `RESEND_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `dns-check`, `domain`, `domains`, `records`, `status`
- Write (connect/interact/save): `add`, `verify`

### screen

Vision-based screen perception and control (macOS)

Concurrency: `mixed`

**Capabilities**

- capture screenshots across multiple displays
- OCR text extraction from screen
- detect and locate UI elements
- mouse click, move, and keyboard control
- find text on screen with fuzzy matching

**Commands**

- `snapshot`: Capture screen with OCR: snapshot [display] [--no-ocr] [--output path]
- `displays`: List connected displays
- `elements`: List detected text elements from last snapshot
- `find`: Find text on screen: find \<text> [--exact]
- `click`: Click at coordinates or text: click \<x> \<y> | click --text \<text>
- `type`: Type text: type \<text>
- `press`: Press key: press \<key>
- `cursor`: Get/move cursor: cursor | move \<x> \<y>
- `scroll`: Scroll: scroll \<direction>

**Examples**

```bash
# capture the screen
agent-do screen snapshot
# find text on screen
agent-do screen find 'Submit'
# click on text
agent-do screen click --text 'OK'
# type text
agent-do screen type 'hello world'
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `cursor`, `displays`, `elements`, `find`, `snapshot`
- Write (connect/interact/save): `click`, `press`, `scroll`, `type`

### sentry

Sentry error tracking, issue management, alerts, and releases

Concurrency: `mixed`

**Capabilities**

- list and inspect projects
- search and filter issues with Sentry query syntax
- view issue details with assignee, level, and event count
- resolve, unresolve, ignore, and assign issues
- list alert rules across all projects
- list recent releases
- full account snapshot as JSON

**Commands**

- `projects`: List all projects with platforms
- `project`: Detailed project info
- `issues`: List issues (--project, --query, --sort, --limit)
- `issue`: Detailed issue info by short ID
- `resolve`: Resolve an issue
- `unresolve`: Reopen a resolved issue
- `ignore`: Mark an issue as ignored
- `assign`: Assign an issue to a user by email
- `alerts`: List alert rules
- `alert`: Detailed alert rule info
- `releases`: List recent releases (--project)
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list sentry projects
agent-do sentry projects
# show unresolved sentry issues
agent-do sentry issues
# show sentry issues for versova-chat
agent-do sentry issues --project versova-chat
# get sentry issue details
agent-do sentry issue VERSOVA-CHAT-B
# resolve a sentry issue
agent-do sentry resolve VERSOVA-CHAT-B
# list sentry alert rules
agent-do sentry alerts
# get sentry account snapshot
agent-do sentry snapshot
```

**Credentials**

- Required: `SENTRY_AUTH_TOKEN`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `alert`, `alerts`, `issue`, `issues`, `project`, `projects`, `releases`, `snapshot`
- Write (connect/interact/save): `assign`, `ignore`, `resolve`, `unresolve`
- composite (one call performs several beats internally): `assign`, `ignore`, `resolve`, `unresolve`

### serial

Serial port communication

Concurrency: `mixed`

**Capabilities**

- list ports
- send/receive data
- monitor traffic

**Commands**

- `list`: List ports
- `send`: Send data
- `monitor`: Monitor port

**Examples**

```bash
# list serial ports
agent-do serial list
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `send`
- long_running (daemon/stream/session; may never return): `monitor`

### sessions

Search and retrieve AI coding session history

Concurrency: `read`

**Capabilities**

- search past coding sessions by keyword
- list recent sessions by project or harness
- retrieve session context and summaries
- view project activity stats
- search within session transcripts by regex
- get recent conversation turns from a session

**Commands**

- `search`: FTS search across session prompts and metadata
- `list`: List recent sessions with filters
- `show`: Show session metadata and summary
- `context`: Get session context (prompt + response + summary)
- `projects`: List projects by session count
- `stats`: Database overview statistics
- `snapshot`: Database state as JSON
- `grep`: Search within a session transcript by regex
- `turns`: Get recent turns from a session

**Examples**

```bash
# find sessions about authentication
agent-do sessions search authentication
# what did I work on in IAMtheSTAR today
agent-do sessions list --project IAMtheSTAR --after today
# show me that broadcast signal session
agent-do sessions search 'broadcast signal'
# show session details
agent-do sessions show <session-id>
# get session context for AI
agent-do sessions context <session-id>
# what was discussed about scoring in that session
agent-do sessions grep <session-id> scoring
# show me the last few messages from that session
agent-do sessions turns <session-id> --last 5
# list all projects
agent-do sessions projects
# session database stats
agent-do sessions stats
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `context`, `grep`, `list`, `projects`, `search`, `show`, `snapshot`, `stats`, `turns`

### sheets

Control Google Sheets

Concurrency: `mixed`

**Capabilities**

- read/write cells
- create sheets
- run formulas

**Commands**

- `read`: Read cells
- `write`: Write cells
- `create`: Create sheet

**Examples**

```bash
# read A1:B10 from my sheet
agent-do sheets read A1:B10
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `read`
- Write (connect/interact/save): `create`, `write`

### slack

Control Slack

Concurrency: `mixed`

**Capabilities**

- send messages
- send direct messages as a user token
- read channels
- upload files

**Commands**

- `send`: Send message to channel or conversation
- `dm`: Send direct message to a person, email, user ID, or DM ID
- `resolve-user`: Resolve Slack user by name, email, or user ID
- `read`: Read channel
- `upload`: Upload file

**Examples**

```bash
# post 'deploy complete' to #engineering
agent-do slack send '#engineering' 'deploy complete'
# DM a teammate as me
agent-do slack dm --as-user teammate@example.com 'hello'
# read #general
agent-do slack read '#general'
```

**Credentials**

- Optional: `SLACK_WEBHOOK_URL`
- One of: `SLACK_USER_TOKEN` | `SLACK_TOKEN` | `SLACK_BOT_TOKEN` | `SLACK_WEBHOOK_URL`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `read`, `resolve-user`
- Write (connect/interact/save): `dm`, `send`, `upload`
- composite (one call performs several beats internally): `dm`

### sms

SMS messaging

Concurrency: `write`

**Capabilities**

- send SMS
- read messages
- search conversations
- query recent messages for auth and automation workflows
- extract verification codes from matching messages
- extract links from matching messages

**Commands**

- `send`: Send SMS
- `list`: List recent messages
- `search`: Search messages
- `snapshot`: Inbox/message state as JSON
- `latest`: Show latest matching message
- `wait`: Wait for a matching message
- `code`: Extract verification code from matching message
- `link`: Extract link from matching message

**Examples**

```bash
# send sms to +1234567890
agent-do sms send '+1234567890' 'Hello!'
# list recent sms
agent-do sms list
# wait for a verification code text
agent-do sms code --from WidgetHub --contains verification
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `code`, `latest`, `link`, `list`, `search`, `snapshot`, `wait`
- Write (connect/interact/save): `send`
- sensitive (emits or persists secret material; guard output): `code`, `link`
- composite (one call performs several beats internally): `code`, `link`

### spec

Repo-local specifications and change artifacts for intended behavior, change deltas, and archive readiness

Concurrency: `mixed`

**Capabilities**

- initialize repo-local spec storage under agent-do-spec/
- create structured change packages with proposal, design, tasks, and deltas
- list canonical specs, active changes, and archived changes
- show one spec or one change package in human or JSON form
- derive change status from repo files instead of hidden state

**Commands**

- `init`: Initialize storage: init [--force]
- `list`: List specs or changes: list [--specs|--changes|--archived]
- `show`: Show one spec or change: show \<name> [--type spec|change]
- `new`: Create a change package: new \<change-id> [--title T] [--spec S]
- `status`: Summarize progress: status [--change \<id>]

**Examples**

```bash
# initialize repo-local specs
agent-do spec init
# create a new change proposal
agent-do spec new add-oauth-device-flow --spec auth
# show what changes exist
agent-do spec list --changes
# inspect one change package
agent-do spec show add-oauth-device-flow --type change
# see what artifacts are missing before implementation
agent-do spec status --change add-oauth-device-flow
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `show`, `status`
- Write (connect/interact/save): `init`, `new`

### ssh

Control remote server sessions

Concurrency: `write`

**Capabilities**

- connect to remote servers
- execute commands
- transfer files
- manage sessions

**Commands**

- `connect`: Connect to server
- `exec`: Execute remote command
- `upload`: Upload file
- `download`: Download file
- `list`: List active sessions

**Examples**

```bash
# connect to production server
agent-do ssh connect prod
# run df -h on server1
agent-do ssh exec server1 'df -h'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `connect`, `download`, `upload`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `exec`

### substack

Draft and publish Substack essays through the editor API — markdown to ProseMirror drafts, auth rides a saved agent-browse session

Concurrency: `mixed`

**Capabilities**

- convert markdown to Substack's ProseMirror document format
- create and update drafts through the editor API
- list drafts and recent published posts
- publish a reviewed draft on explicit command (subscriber email only with --email)
- verify a draft by reading it back and comparing against the local receipt or source file

**Commands**

- `connect`: Verify auth + save publication config: connect --publication \<url-or-subdomain> [--session name]
- `snapshot`: Publication info + drafts + recent posts: snapshot [--json]
- `drafts`: List drafts: drafts [--limit N]
- `posts`: List recent published posts: posts [--limit N]
- `get`: Fetch one draft: get \<id>
- `convert`: Markdown to ProseMirror JSON, offline: convert \<file.md>
- `draft`: Create a DRAFT (never publishes): draft \<file.md> [--title T] [--subtitle S]
- `update`: Replace draft body/title: update \<id> \<file.md>
- `publish`: Publish a reviewed draft: publish \<id> [--email]
- `verify`: Read back and compare: verify \<id> [--file \<file.md>]
- `receipts`: Local draft/publish receipts: receipts [--limit N]

**Examples**

```bash
# post my essay to substack as a draft
agent-do substack draft essay.md
# connect to my substack publication
agent-do substack connect --publication example.substack.com
# list my substack drafts
agent-do substack drafts
# publish the reviewed substack draft
agent-do substack publish 12345678
# check the draft matches what I wrote
agent-do substack verify 12345678 --file essay.md
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `convert`, `drafts`, `get`, `posts`, `receipts`, `snapshot`, `verify`
- Write (connect/interact/save): `connect`, `draft`, `publish`, `update`
- destructive (irreversible data loss; confirm before auto-running): `publish`
- sensitive (emits or persists secret material; guard output): `publish`
- composite (one call performs several beats internally): `draft`, `publish`, `update`
- own_state (writes only its own cache/state; parallel-safe): `connect`, `receipts`

### supabase

Supabase project lifecycle + management + data access (full Management API, REST API, SQL, and agent-db)

Concurrency: `write`

**Capabilities**

- create, update, delete, pause, and restore projects
- view service health
- manage API keys and secrets
- create, list, merge, push, reset, and delete database branches (preview environments)
- scale compute, apply/remove billing addons, set up and remove read replicas
- upgrade Postgres versions and check eligibility
- manage network restrictions (allowed CIDRs) and network bans
- configure custom hostnames and vanity subdomains
- deploy, update, and delete edge functions
- generate TypeScript types
- list organizations and regions
- query, update, insert, upsert, delete via PostgREST REST API (no DB password needed)
- run SQL via Management API (no DB password needed)
- run SQL migrations from .sql files via Management API
- run SQL queries via agent-db bridge (full SQL power, requires DB password)
- list tables, describe schema, sample data via agent-db

**Commands**

- `projects`: List all projects
- `show`: Project details
- `create`: Create a project (billable; requires --yes)
- `update`: Rename a project
- `delete`: Delete a project (irreversible; requires --yes)
- `pause`: Pause project
- `restore`: Restore paused project
- `restore-versions`: List available restore points
- `restore-cancel`: Cancel an in-progress restore
- `health`: Service health status
- `api-keys`: List API keys
- `secrets`: List secrets (env vars)
- `secret-set`: Create/update secret
- `secret-del`: Delete secret
- `functions`: List edge functions
- `function-show`: Edge function details
- `function-deploy`: Deploy/create an edge function from a source file
- `function-update`: Update an edge function
- `function-delete`: Delete an edge function (requires --yes)
- `branches`: List database branches
- `branch-create`: Create a database branch
- `branch-show`: Branch config
- `branch-update`: Update branch config
- `branch-delete`: Delete a branch (requires --yes)
- `branch-merge`: Merge branch into production
- `branch-push`: Push branch migrations/functions
- `branch-reset`: Reset branch to production
- `branch-diff`: Diff branch vs production
- `branching-disable`: Disable preview branching (requires --yes)
- `addons`: List billing addons
- `addon-apply`: Apply a billing addon (billable; requires --yes)
- `addon-remove`: Remove a billing addon (requires --yes)
- `compute-scale`: Scale the compute instance (billable; requires --yes)
- `upgrade`: Upgrade Postgres version (downtime; requires --yes)
- `upgrade-eligibility`: Check Postgres upgrade eligibility
- `upgrade-status`: Get Postgres upgrade status
- `replica-setup`: Set up a read replica (billable; requires --yes)
- `replica-remove`: Remove a read replica (requires --yes)
- `network-restrictions`: Show DB network restrictions
- `network-restrict`: Apply DB network restrictions (allowed CIDRs)
- `network-bans`: List banned IPs
- `network-unban`: Remove network bans
- `domains`: Custom hostname info
- `domain-init`: Initialize a custom hostname
- `domain-reverify`: Re-verify custom hostname DNS
- `domain-activate`: Activate a custom hostname
- `domain-delete`: Delete custom hostname config (requires --yes)
- `vanity`: Show vanity subdomain config
- `vanity-check`: Check vanity subdomain availability
- `vanity-activate`: Activate a vanity subdomain
- `vanity-delete`: Delete vanity subdomain (requires --yes)
- `types`: Generate TypeScript types
- `orgs`: List organizations
- `regions`: List available regions
- `postgrest`: PostgREST config
- `snapshot`: Full account state as JSON
- `rest`: Read/write table via PostgREST REST API (GET, PATCH, POST, DELETE)
- `sql`: Run SQL via Management API (no DB password needed)
- `db-connect`: Auto-create agent-db profile and connect
- `db-status`: Check if agent-db profile exists
- `query`: Run SQL via agent-db (requires DB password)
- `tables`: List tables via agent-db
- `describe`: Describe table schema via agent-db
- `sample`: Sample rows via agent-db

**Examples**

```bash
# list my supabase projects
agent-do supabase projects
# create a new supabase project
agent-do supabase create my-app --org my-org-slug --region us-east-1 --yes
# delete a supabase project
agent-do supabase delete abcdefghijklmnopqrst --yes
# create a supabase preview branch
agent-do supabase branch-create abcdefghijklmnopqrst feature-x --persistent
# scale supabase compute
agent-do supabase compute-scale abcdefghijklmnopqrst --size large --yes
# deploy a supabase edge function
agent-do supabase function-deploy abcdefghijklmnopqrst hello --file ./hello.ts
# restrict supabase database network access
agent-do supabase network-restrict abcdefghijklmnopqrst --cidr 1.2.3.4/32
# show supabase project details
agent-do supabase show abcdefghijklmnopqrst
# check supabase project health
agent-do supabase health abcdefghijklmnopqrst
# query supabase table
agent-do supabase rest <ref> users --select id,email --limit 10
# filter supabase data
agent-do supabase rest <ref> orders --filter status=eq.pending
# update supabase row
agent-do supabase rest <ref> reports --update '{"published": false}' --filter "slug=eq.my-report"
# insert supabase row
agent-do supabase rest <ref> users --insert '{"name": "Alice", "email": "alice@example.com"}'
# upsert supabase row
agent-do supabase rest <ref> users --upsert '{"id": 1, "name": "Alice"}'
# delete supabase rows
agent-do supabase rest <ref> old_logs --delete --filter "created_at=lt.2024-01-01"
# run SQL on supabase
agent-do supabase sql <ref> "SELECT count(*) FROM users"
# create table on supabase
agent-do supabase sql <ref> "CREATE TABLE items (id serial primary key, name text)"
# run migration file on supabase
agent-do supabase sql <ref> --file migrations/001_init.sql
# read-only SQL query on supabase
agent-do supabase sql <ref> "SELECT * FROM users" --read-only
# connect to supabase database directly
agent-do supabase db-connect <ref>
# list supabase tables
agent-do supabase tables <ref>
# sample supabase table data
agent-do supabase sample <ref> orders 5
# list supabase secrets
agent-do supabase secrets abcdefghijklmnopqrst
# list supabase organizations
agent-do supabase orgs
# get supabase account snapshot
agent-do supabase snapshot
```

**Credentials**

- Required: `SUPABASE_ACCESS_TOKEN`
- Optional: `SUPABASE_DB_PASSWORD`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `addons`, `api-keys`, `branch-diff`, `branch-show`, `branches`, `db-status`, `describe`, `domain-reverify`, `domains`, `function-show`, `functions`, `health`, `network-bans`, `network-restrictions`, `orgs`, `postgrest`, `projects`, `regions`, `restore-versions`, `sample`, `secrets`, `show`, `snapshot`, `tables`, `types`, `upgrade-eligibility`, `upgrade-status`, `vanity`, `vanity-check`
- Write (connect/interact/save): `addon-apply`, `addon-remove`, `branch-create`, `branch-delete`, `branch-merge`, `branch-push`, `branch-reset`, `branch-update`, `branching-disable`, `compute-scale`, `create`, `db-connect`, `delete`, `domain-activate`, `domain-delete`, `domain-init`, `function-delete`, `function-deploy`, `function-update`, `network-restrict`, `network-unban`, `pause`, `query`, `replica-remove`, `replica-setup`, `rest`, `restore`, `restore-cancel`, `secret-del`, `secret-set`, `sql`, `update`, `upgrade`, `vanity-activate`, `vanity-delete`
- destructive (irreversible data loss; confirm before auto-running): `addon-remove`, `branch-delete`, `branch-reset`, `delete`, `domain-delete`, `function-delete`, `replica-remove`, `secret-del`, `vanity-delete`
- sensitive (emits or persists secret material; guard output): `api-keys`, `db-connect`, `secrets`
- polymorphic (beat decided by payload or flag at call time): `query`, `rest`, `sql`
- composite (one call performs several beats internally): `db-connect`

### swarm

Multi-agent orchestration

Concurrency: `write`

**Capabilities**

- spawn multiple agents
- parallel execution
- pipeline coordination

**Commands**

- `spawn`: Spawn agents
- `parallel`: Run in parallel
- `pipeline`: Run in sequence
- `status`: Show swarm status

**Examples**

```bash
# run 3 agents on this task
agent-do swarm spawn 3 'search for best practices'
# run tests and linting in parallel
agent-do swarm parallel 'test' 'lint'
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `status`
- Write (connect/interact/save): `parallel`, `pipeline`, `spawn`
- composite (one call performs several beats internally): `parallel`, `pipeline`, `spawn`

### tail

Wrap dev commands, capture output to log files for AI agents

Concurrency: `read`

**Capabilities**

- run multiple dev services with output capture
- individual and combined log files per session
- timestamped sessions with latest symlink
- search and filter log content

**Commands**

- `run`: Start services foreground: run 'name: cmd' ...
- `start`: Start services background: start 'name: cmd' ...
- `stop`: Stop services: stop [name]
- `read`: Read log: read [name] [-n lines]
- `follow`: Follow log: follow [name]
- `grep`: Search logs: grep \<pattern> [name]
- `errors`: Show error lines: errors [name]
- `list`: Show running services
- `sessions`: List all sessions
- `prune`: Remove old sessions
- `snapshot`: Full state as JSON

**Examples**

```bash
# run frontend and backend with logging
agent-do tail start 'fe: npm run dev' 'api: uvicorn main:app'
# check dev server output
agent-do tail read fe
# search for errors in logs
agent-do tail errors
# find pattern in api logs
agent-do tail grep 'TypeError' api
# stop all dev services
agent-do tail stop
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `errors`, `grep`, `list`, `read`, `sessions`, `snapshot`
- Write (connect/interact/save): `prune`, `stop`
- destructive (irreversible data loss; confirm before auto-running): `prune`
- passthrough (arbitrary-payload escape hatch; beat decided by the argument): `run`, `start`
- long_running (daemon/stream/session; may never return): `follow`, `run`, `start`
- own_state (writes only its own cache/state; parallel-safe): `prune`, `stop`

### teams

Microsoft Teams control

Concurrency: `mixed`

**Capabilities**

- join meetings
- send messages
- control calls

**Commands**

- `join`: Join meeting
- `new`: Start new meeting
- `chat`: Send message
- `mute`: Toggle mute

**Examples**

```bash
# start teams meeting
agent-do teams new
# chat with john in teams
agent-do teams chat john
```

**Safety (from contracts)**

- Write (connect/interact/save): `chat`, `join`, `mute`, `new`
- long_running (daemon/stream/session; may never return): `chat`

### transcribe

Source-to-transcript ingestion pipeline (YouTube URLs, authenticated downloads, Whisper API + local Whisper + caption fallbacks, batch, cost preflight, structured JSON)

Concurrency: `mixed`

**Capabilities**

- transcribe YouTube videos by URL or ID (public and members-only)
- transcribe local audio/video files
- use authenticated agent-do browse sessions for members-only content
- pass yt-dlp extractor args and YouTube player-client overrides when cookies alone are insufficient
- capture authenticated browser tab audio for member-tier/paywalled media that yt-dlp cannot extract
- call OpenAI Whisper API with automatic ffmpeg chunking for large audio
- fall back to local Whisper, YouTube auto-captions, or yt-dlp VTT subtitles
- batch transcribe from stdin or a file of URLs
- estimate API cost before committing (preflight, never blocks)
- cache results per source/method to skip repeat work

**Commands**

- `doctor`: Report dependency, credential, and browse-session readiness
- `snapshot`: Report cache state, available browse sessions, default method order
- `cost`: Estimate Whisper API cost for one source or a batch (informational preflight)
- `transcribe`: Transcribe a source to text+JSON (default verb when first arg is a URL/ID/path)

**Examples**

```bash
# transcribe a public YouTube video
agent-do transcribe https://youtube.com/watch?v=dQw4w9WgXcQ
# transcribe a members-only YouTube video using saved auth
agent-do transcribe https://youtube.com/watch?v=XXX --browse-session youtube_arc
# retry a members-only YouTube video through a mobile player client
agent-do transcribe https://youtube.com/watch?v=XXX --browse-session youtube_arc --youtube-player-client ios
# transcribe browser-only member-tier YouTube content
agent-do transcribe https://youtube.com/watch?v=XXX --browse-session youtube_arc --browser-capture --json
# estimate cost for a batch before transcribing
agent-do transcribe cost --batch-file urls.txt --youtube-player-client ios --json
# batch transcribe with structured output
agent-do transcribe --batch-file urls.txt --browse-session youtube_arc --browser-capture --output-dir ./transcripts --json
# free fallback only (no Whisper API)
agent-do transcribe <url> --prefer-free
# check tool readiness as JSON
agent-do transcribe doctor --json
```

**Credentials**

- Optional: `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `cost`, `snapshot`
- Write (connect/interact/save): `doctor`, `transcribe`
- long_running (daemon/stream/session; may never return): `transcribe`
- composite (one call performs several beats internally): `cost`, `doctor`, `transcribe`

### tui

Control any terminal/TUI application via tmux

Concurrency: `mixed`

**Capabilities**

- spawn terminal applications
- send keystrokes
- capture screen state
- wait for text/patterns

**Commands**

- `spawn`: Start a new TUI session
- `snapshot`: Capture current screen
- `send`: Send keys to session
- `type`: Type text into session
- `wait`: Wait for condition
- `kill`: Kill a session
- `list`: List active sessions

**Examples**

```bash
# start htop
agent-do tui spawn htop
# take a screenshot of session 1
agent-do tui snapshot 1
# send q to htop
agent-do tui send 1 q
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `snapshot`, `wait`
- Write (connect/interact/save): `kill`, `send`, `spawn`, `type`
- destructive (irreversible data loss; confirm before auto-running): `kill`
- long_running (daemon/stream/session; may never return): `spawn`

### unbrowse

Standalone API traffic capture → reusable curl-based skills. For SSO/MFA → headless handoff, use browse login instead.

Concurrency: `mixed`

**Capabilities**

- capture XHR/fetch network traffic during manual browsing
- filter out static assets, CDN, and analytics noise
- extract authentication headers, cookies, and tokens
- generate source-able bash functions wrapping curl
- replay API calls without a browser (~100x faster)
- capture pipeline shared with browse via lib/capture/

**Commands**

- `capture`: Start headed browser and capture traffic: capture \<url> [--headless]
- `stop`: Stop capture and generate skill: stop \<name>
- `status`: Show capture status (requests, domains, elapsed)
- `close`: Close browser and daemon
- `list`: List generated skills
- `show`: Show skill documentation: show \<name>
- `replay`: Call a skill function via curl: replay \<name> \<function> [args...]
- `test`: Test GET endpoints: test \<name>
- `delete`: Remove a skill: delete \<name>

**Examples**

```bash
# capture API traffic from a website
agent-do unbrowse capture https://api.example.com
# stop capturing and save as a skill
agent-do unbrowse stop myservice
# what APIs did I capture
agent-do unbrowse status
# list my captured API skills
agent-do unbrowse list
# show endpoints for a service
agent-do unbrowse show myservice
# call the get_users API directly
agent-do unbrowse replay myservice get_users
# test if my captured APIs still work
agent-do unbrowse test myservice
# remove a captured skill
agent-do unbrowse delete myservice
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `show`, `status`, `test`
- Write (connect/interact/save): `capture`, `close`, `delete`, `replay`, `stop`
- destructive (irreversible data loss; confirm before auto-running): `delete`
- long_running (daemon/stream/session; may never return): `capture`
- polymorphic (beat decided by payload or flag at call time): `replay`

### usb

USB device management

Concurrency: `mixed`

**Capabilities**

- list devices
- mount/unmount
- eject

**Commands**

- `list`: List devices
- `mount`: Mount device
- `eject`: Eject device

**Examples**

```bash
# list USB devices
agent-do usb list
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`
- Write (connect/interact/save): `eject`, `mount`

### vector

Operate Versova Vector portfolio command center

Concurrency: `write`

**Capabilities**

- read portfolio project status, snapshots, work, support, links, and activity
- create snapshots, decisions, work items, support items, links, and asks
- manage project bindings and members
- launch the local Vector sync package

**Commands**

- `today`: Show engineer-owned projects, open work, and commits
- `inbox`: Show asks, new intake, and support queue
- `ls`: List portfolio projects
- `show`: Show one project with live sections
- `snapshot`: Create a project snapshot
- `decide`: Record a decision
- `work`: Add, complete, or block work items
- `support`: Add or resolve support items
- `ask`: Create an ask-only snapshot
- `link`: Add or remove project links
- `open`: Open project binding location and primary URLs
- `sync`: Run @vector/sync locally
- `bind`: Upsert project substrate binding
- `members`: List or add members
- `feed`: Read project_activity feed
- `intake`: List, create, accept, or decline intake

**Examples**

```bash
# show my vector standup
agent-do vector today
# list vector projects
agent-do vector ls
# show the VMS project in vector
agent-do vector show vms-io
# add a vector snapshot
agent-do vector snapshot versova-research "Research sync is green"
# record a vector decision
agent-do vector decide versova-research advance "Ship the sync daemon"
# add vector work
agent-do vector work versova-research add "Wire digest route"
# resolve vector support
agent-do vector support versova-research resolve <id>
# add a vector project link
agent-do vector link versova-research add repo "Repository" https://github.com/example/repo
# run vector sync
agent-do vector sync --dry-run
# bind a vector project
agent-do vector bind versova-research --dir ~/Custom-Coding/versova-research
```

**Credentials**

- Required: `VECTOR_SUPABASE_URL`, `VECTOR_SUPABASE_SERVICE_KEY`
- Optional: `VECTOR_USER_EMAIL`, `VECTOR_ORG_ID`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `feed`, `inbox`, `ls`, `show`, `snapshot`, `today`
- Write (connect/interact/save): `ask`, `bind`, `decide`, `intake`, `link`, `members`, `open`, `support`, `sync`, `work`
- destructive (irreversible data loss; confirm before auto-running): `link`
- polymorphic (beat decided by payload or flag at call time): `intake`, `members`
- composite (one call performs several beats internally): `intake`

### vercel

Control Vercel projects, deployments, domains, and env vars

Concurrency: `write`

**Capabilities**

- list and manage projects
- trigger and inspect deployments
- view build logs
- manage environment variables
- view project domains
- list teams

**Commands**

- `projects`: List all projects
- `show`: Project details
- `deployments`: Recent deployments
- `deploy`: Trigger deployment
- `inspect`: Deployment details
- `logs`: Build logs
- `cancel`: Cancel deployment
- `promote`: Promote to production
- `env`: List env vars
- `env-set`: Set env var
- `env-del`: Delete env var by ID
- `domains`: List project domains
- `teams`: List teams
- `snapshot`: Full account state as JSON

**Examples**

```bash
# list my vercel projects
agent-do vercel projects
# deploy my-app on vercel
agent-do vercel deploy my-app
# show vercel project details
agent-do vercel show my-app
# view vercel deployment logs
agent-do vercel logs dpl_abc123
# set env var on vercel
agent-do vercel env-set my-app DATABASE_URL postgres://...
# list vercel project domains
agent-do vercel domains my-app
# get vercel account snapshot
agent-do vercel snapshot
```

**Credentials**

- Required: `VERCEL_ACCESS_TOKEN`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `deployments`, `domains`, `env`, `inspect`, `logs`, `projects`, `show`, `snapshot`, `teams`
- Write (connect/interact/save): `cancel`, `deploy`, `env-del`, `env-set`, `promote`
- destructive (irreversible data loss; confirm before auto-running): `env-del`

### video

Video processing

Concurrency: `mixed`

**Capabilities**

- trim/merge videos
- extract frames
- convert formats

**Commands**

- `trim`: Trim video
- `merge`: Merge videos
- `extract`: Extract frames

**Examples**

```bash
# extract frames from video
agent-do video extract video.mp4
```

**Safety (from contracts)**

- Write (connect/interact/save): `extract`, `merge`, `trim`

### vision

AI-first visual perception with object detection, OCR, and face detection

Concurrency: `read`

**Capabilities**

- capture from webcam, screen, window, video file, or iOS simulator
- YOLO object detection and counting
- OCR text extraction from frames
- face detection and identification
- motion detection
- vision LLM analysis

**Commands**

- `source`: Set capture source: source webcam|screen|window|file|image|ios|rtsp
- `snapshot`: Capture frame with analysis: snapshot [--yolo] [--ocr] [--faces] [--all]
- `detect`: Run YOLO detection: detect [--classes person] [--annotate]
- `count`: Count objects: count [class]
- `ocr`: Extract text: ocr [--region x,y,w,h] [--find text]
- `faces`: Detect faces: faces [--identify]
- `status`: Show current source

**Examples**

```bash
# detect objects on screen
agent-do vision source screen && agent-do vision snapshot --yolo
# extract text from an image
agent-do vision source image photo.png && agent-do vision ocr
# count people in webcam
agent-do vision source webcam && agent-do vision count person
# detect faces
agent-do vision snapshot --faces
```

**Credentials**

- Optional: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `count`, `faces`, `ocr`, `snapshot`, `status`
- Write (connect/interact/save): `detect`, `source file`, `source image`, `source ios`, `source rtsp`, `source screen`, `source webcam`, `source window`
- polymorphic (beat decided by payload or flag at call time): `detect`
- own_state (writes only its own cache/state; parallel-safe): `detect`, `source file`, `source image`, `source ios`, `source rtsp`, `source screen`, `source webcam`, `source window`

### vm

Control virtual machines

Concurrency: `write`

**Capabilities**

- start/stop VMs
- snapshot
- manage images

**Commands**

- `start`: Start VM
- `stop`: Stop VM
- `snapshot`: Create snapshot
- `list`: List VMs

**Examples**

```bash
# start dev VM
agent-do vm start dev
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `list`, `snapshot`
- Write (connect/interact/save): `start`, `stop`

### voice

Voice synthesis and recognition

Concurrency: `write`

**Capabilities**

- text-to-speech
- speech-to-text
- record audio

**Commands**

- `speak`: Text-to-speech
- `listen`: Speech-to-text
- `record`: Record audio
- `transcribe`: Transcribe audio file

**Examples**

```bash
# speak hello world
agent-do voice speak 'Hello, world'
# transcribe recording.wav
agent-do voice transcribe recording.wav
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `listen`
- Write (connect/interact/save): `record`, `speak`, `transcribe`
- long_running (daemon/stream/session; may never return): `listen`, `record`, `transcribe`
- composite (one call performs several beats internally): `transcribe`

### wireshark

Network packet capture and analysis

Concurrency: `read`

**Capabilities**

- capture packets
- analyze pcap files
- filter traffic

**Commands**

- `capture`: Start packet capture
- `read`: Read pcap file
- `filter`: Filter packets
- `stats`: Show statistics

**Examples**

```bash
# capture on en0
agent-do wireshark capture en0
# read capture.pcap
agent-do wireshark read capture.pcap
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `read`, `stats`
- Write (connect/interact/save): `capture`, `filter`
- long_running (daemon/stream/session; may never return): `capture`
- own_state (writes only its own cache/state; parallel-safe): `capture`, `filter`

### zoom

Zoom meeting control

Concurrency: `mixed`

**Capabilities**

- join/start meetings
- control audio/video
- screen sharing

**Commands**

- `join`: Join meeting
- `start`: Start instant meeting
- `mute`: Toggle mute
- `video`: Toggle video
- `share`: Start screen share

**Examples**

```bash
# join zoom meeting 123-456-789
agent-do zoom join 123-456-789
# start a zoom meeting
agent-do zoom start
```

**Safety (from contracts)**

- Write (connect/interact/save): `join`, `mute`, `share`, `start`, `video`

### zpc

Experience journal — structured lessons, decisions, patterns per project. Complementary to context (knowledge library).

Concurrency: `mixed`

**Capabilities**

- capture structured lessons (context/problem/solution/takeaway)
- log architectural decisions with options, rationale, confidence
- hold positions with a falsifier and refuse evidence-free flips
- name every claim with a content-derived id (les-/dec-) and retract it with evidence
- inject memory as dated claims that live observation outranks, never as standing law
- carry the user's recorded preferences into any directory, store or no store
- re-litigate the most-exposed claims against current code and file challenges on divergence
- clean-context second opinion on a receipts-only brief
- consolidate lessons into patterns via harvest
- inject memory context into AI agents
- search and query memory by tag, date, or text
- git history review for post-sprint lesson extraction
- swarm checkpoints for multi-agent phase boundary compliance
- lesson promotion (local → team → global)
- per-project storage at .zpc/ (not global)

**Commands**

- `learn`: Capture a structured lesson
- `decide`: Log a decision with rationale
- `decide-batch`: Batch-log decisions from planning phase
- `retract`: Correct a wrong lesson or decision with named evidence (append-only tombstone; --candidate files a challenge instead, --backfill assigns derived ids)
- `position`: Record a verdict with its falsifier; flip it only with named evidence (an evidence-free flip also fires a detached second opinion)
- `counsel`: Clean-context second opinion on a receipts-only brief; --auto-brief assembles the receipts mechanically from git and the newest run log
- `harvest`: Post-build consolidation scan
- `query`: Search project lessons and decisions; add --global for machine-wide lessons
- `patterns`: View and score patterns
- `review`: Post-sprint lesson extraction from git history
- `promote`: Promote lessons: --to team copies rows; --to global is gated and refuses (exit 2, nothing written) unless the one row carries --rule, --why, --when kind:match (prompt|command|path|always) and --seen-in a,b | --scope machine|user; machine-written rows never qualify; re-promoting updates the global copy in place
- `inject`: Emit agent context blob (claims rendered dated, kinded and retractable, never as law); fits itself to a budget derived from the quantity authority and states the magnitude of anything it drops, or takes the caller's own with --max-tokens; --trigger prompt|command|path \<value> emits only the machine-wide lessons whose `when` fires for that moment (the hook path; empty when nothing matches; session start carries `always` rows and a count of the rest); --compact carries patterns and claims alone for pasting into a subagent's prompt; --preferences emits only the machine-wide preference slice and needs no .zpc store, so what the user already said about working follows them into any directory; --relitigate re-tries the most-exposed claims against current code in a detached counsel pass (AGENT_DO_ZPC_RELITIGATE=0 disables)
- `init`: Initialize .zpc/ in a project; --store-only creates the store alone (no .gitignore append, no agent instruction file) and keeps it out of git through .git/info/exclude, which is what an unattended caller may run in a repo it does not own
- `status`: Memory snapshot with health check
- `checkpoint`: Swarm phase boundary check
- `profile`: View/update project profile

**Examples**

```bash
# log a lesson about mypy
agent-do zpc learn 'type checking' 'mypy missed Optional' 'added strict mode' 'always use --strict' --tags mypy,typing
# what decisions have we made
agent-do zpc query --type decisions
# batch log planning decisions
echo 'Color | oklch dark | perceptual' | agent-do zpc decide-batch --tags design
# check swarm phase boundary
agent-do zpc checkpoint --phase 'Phase 2' --agents 'agent-a,agent-b'
# review sprint and extract lessons from git
agent-do zpc review --since HEAD~20 --dry-run
# auto-extract lessons from recent work
agent-do zpc review --auto --phase 'Sprint 3'
# consolidate after swarm build
agent-do zpc harvest
# what has this user already told me about how to work
agent-do zpc inject --preferences
# make a project lesson machine-wide with its rule, why and trigger
agent-do zpc promote 14 --to global --rule 'Prove the premise inside the test' --why 'a faked premise proves nothing' --when 'path:test_*.py' --scope user
# which machine-wide lessons fire for this moment
agent-do zpc inject --trigger prompt 'write a test for the parser'
# check memory status
agent-do zpc status
# search for docker lessons
agent-do zpc query --tag docker
# set up zpc in this project
agent-do zpc init
# correct a lesson that turned out to be wrong
agent-do zpc retract les-1a2b3c --evidence 'src/api.ts:44 sets Retry-After on every 429' --takeaway 'the API does send Retry-After'
# file doubt about a lesson without arguing it
agent-do zpc retract --candidate les-1a2b3c --evidence 'no such handler in src/ today'
# record a position I can be wrong about
agent-do zpc position add 'the proxy corrupts the payload' --verdict 'double content-encoding' --confidence med --falsifier 'byte-identical body across the hop'
# get a second opinion that has not seen the argument
agent-do zpc counsel --brief .dev/receipts.md --question 'Did the payload survive the hop?'
# second opinion without hand-picking the receipts
agent-do zpc counsel --auto-brief --question 'Does the working tree do what the commit message claims?'
# memory blob small enough to paste into a subagent prompt
agent-do zpc inject --compact
# re-check the lessons this project keeps repeating
agent-do zpc inject --relitigate
```

**Safety (from contracts)**

- Read-only (snapshot/verify; safe to parallelize): `patterns`, `profile`, `query`, `status`
- Write (connect/interact/save): `checkpoint`, `counsel`, `decide`, `decide-batch`, `harvest`, `init`, `inject`, `learn`, `position`, `promote`, `retract`, `review`
- long_running (daemon/stream/session; may never return): `counsel`
- polymorphic (beat decided by payload or flag at call time): `harvest`, `inject`, `position`, `review`
- composite (one call performs several beats internally): `checkpoint`
- own_state (writes only its own cache/state; parallel-safe): `counsel`
