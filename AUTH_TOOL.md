# agent-do auth

Design for a native authentication orchestration tool inside `agent-do`.

This is a forward design document. It describes a proposed tool and storage model. It does not describe current shipped behavior.

## Purpose

`agent-do` already has pieces of the auth story:

- static secret storage via `creds`
- browser login automation and session persistence via `browse`
- browser cookie import via `browse session import-browser`

What is missing is a native orchestrator for authenticated state:

- what login strategy a site should use
- how an agent should reuse existing auth before asking for help
- how to validate whether a session is still good
- how to escalate through safer fallback layers before requiring a human

`agent-do auth` fills that gap.

## Product Thesis

The tool should be:

- agent-facing first
- site-centric
- layered
- validation-driven
- secure by default
- explicit about what it can and cannot do

It should not become a magical claim that every site can be logged into from zero with no human involvement. It should make the safe reusable path first-class, then create a framework for progressively deeper autonomy.

## Reality Constraints

The design should start from the real boundary, not a fantasy one.

What can be automated well:

- username and password forms
- stored browser sessions
- cookie and storage import from an already-authenticated browser profile
- TOTP-driven second factor when the secret is available
- provider APIs that support device flow or refresh tokens
- repeated site access after one successful human bootstrap

What cannot be promised universally in v1:

- fresh Google SSO on arbitrary sites with no prior state
- fresh GitHub SSO on arbitrary sites with no prior state
- CAPTCHA-heavy flows
- passkey-only flows with device prompts the agent cannot satisfy
- challenge ladders that depend on human mailbox, phone, or device approval

So the right v1 is not "universal fresh SSO from zero." The right v1 is "autonomous auth reuse plus structured fallbacks."

## Non-Goals

`agent-do auth` should not:

- replace `creds` as the canonical secret store
- replace `browse` as the browser control surface
- store API secrets directly in a second secret system
- promise universal zero-touch first login in v1
- solve CAPTCHA bypass generically in v1
- invent a new browser automation engine

## Why This Belongs In agent-do

This is a strong fit for `agent-do` because auth is currently split across unrelated surfaces:

- `creds` knows static secrets
- `browse` knows cookies, localStorage, sessionStorage, and headed login handoff
- the agent has to know which primitive to reach for and in what order

That is exactly the class of problem `agent-do` should absorb: turn improvised, fragile, repeated outer-world work into one native contract.

## Current Repo Boundary

Today:

- `agent-do creds` stores API keys and env-shaped secrets
- `agent-do browse auth ...` handles site email and password credentials
- `agent-do browse login ...` handles manual headed login handoff
- `agent-do browse session ...` handles saved browser state

The missing layer is orchestration.

Without `agent-do auth`, the agent has to infer:

- whether a site should use saved session reuse
- whether cookie import is available
- whether stored first-party credentials exist
- how to validate that it is actually signed in
- when to stop and ask for human help

`agent-do auth` should own that decision tree.

## Core Model

The core unit should be a site profile.

One site profile answers:

- what the site is
- what domains are relevant
- what login URL to use
- how to tell if auth is valid
- which strategies are enabled
- what secure credentials are referenced
- what provider adapter applies, if any

Examples:

- `github`
- `google-workspace`
- `vercel-dashboard`
- `notion`
- `my-internal-admin`

This should be site-centric, not URL-fragment-centric.

## Storage Model

The canonical storage root should be:

```text
~/.agent-do/auth/
```

Proposed layout:

```text
~/.agent-do/auth/
├── config.yaml
├── profiles/
│   ├── github.yaml
│   ├── google-workspace.yaml
│   └── my-internal-admin.yaml
├── sessions/
│   ├── github/
│   │   ├── default/
│   │   │   ├── meta.json
│   │   │   └── state.enc
│   │   └── imported-arc/
│   │       ├── meta.json
│   │       └── state.enc
│   └── my-internal-admin/
│       └── default/
│           ├── meta.json
│           └── state.enc
└── adapters/
    └── registry.json
```

Why this root:

- auth state is per-user, not per-project
- it belongs with other `agent-do` runtime state
- it makes room for site profiles, session bundles, and adapter metadata
- it lets `browse` become an implementation detail instead of the storage owner

### Session Storage

Session bundles should not live as naked JSON by default. The desired state is:

- metadata in plain JSON for indexing and status
- browser state encrypted at rest
- encryption key rooted in the OS secure store

If v1 implementation needs a migration bridge, `auth` can wrap existing `browse` session files while moving toward encrypted bundles. The design target should still be encrypted storage under `~/.agent-do/auth/sessions/`.

## Site Profile Shape

Each profile should be YAML.

Example:

```yaml
id: github
title: GitHub
domains:
  - github.com
  - api.github.com
login_url: https://github.com/login
validation:
  url_patterns:
    - https://github.com/*
  signed_out_markers:
    - "Sign in to GitHub"
  signed_in_markers:
    - "aria-label=View profile and more"
strategies:
  - saved-session
  - browser-import
  - site-creds
  - provider-refresh
provider:
  type: github
credentials:
  site:
    username: GITHUB_EMAIL
    password: GITHUB_PASSWORD
  totp:
    secret: GITHUB_TOTP_SECRET
browser_import:
  browser: arc
  domains:
    - .github.com
notes:
  - Prefer session reuse before fresh login
```

The profile is the contract. Agents should not need to rediscover these details each run.

## Strategy Ladder

`agent-do auth ensure <site>` should use a fixed ladder:

1. `saved-session`
   - load last known good session
   - validate signed-in state
   - return success if valid

2. `browser-import`
   - import cookies and storage from a configured real browser profile
   - validate signed-in state
   - save refreshed session bundle if valid

3. `site-creds`
   - resolve site credentials and optional TOTP from `agent-do creds`
   - use browser automation to navigate, detect the login form, autofill, submit, and validate
   - save session bundle if valid

4. `provider-refresh`
   - use provider-specific refresh or device-flow logic where supported
   - validate and save session bundle

5. `interactive`
   - only now require headed human help

That order matters. It optimizes for reuse first, then deterministic automation, then human intervention.

## Lifecycle States

State should be derived from profile and validation results, not from hidden flags.

Suggested states:

1. `unconfigured`
   - no site profile exists

2. `configured`
   - profile exists, but no valid session known

3. `authenticated`
   - a saved or imported session validates

4. `stale`
   - a session exists, but validation fails and recovery may still work

5. `action-required`
   - no strategy succeeded, and a human or new secret is required

## CLI Surface

The native command should be:

```bash
agent-do auth <command>
```

### v1 command set

```bash
agent-do auth init <site>
agent-do auth list
agent-do auth show <site>
agent-do auth status <site>
agent-do auth ensure <site>
agent-do auth save <site>
agent-do auth load <site>
agent-do auth import-browser <site>
agent-do auth clear <site>
agent-do auth validate <site>
agent-do auth instructions <site>
```

### init

Creates a site profile.

Examples:

```bash
agent-do auth init github
agent-do auth init my-admin --domain admin.example.com --login-url https://admin.example.com/login
```

Behavior:

- creates `~/.agent-do/auth/profiles/<site>.yaml`
- seeds validation and strategy sections
- optionally seeds provider adapter metadata when the site is known

### list

Lists configured sites and current auth state.

Examples:

```bash
agent-do auth list
agent-do auth list --json
```

### show

Displays one site profile and recent session metadata.

Examples:

```bash
agent-do auth show github
agent-do auth show my-admin --json
```

### status

Summarizes whether the site is currently authenticated and what strategy last worked.

Examples:

```bash
agent-do auth status github
agent-do auth status my-admin --json
```

### ensure

The highest-leverage command. It runs the strategy ladder and stops at first success.

Examples:

```bash
agent-do auth ensure github
agent-do auth ensure my-admin --json
agent-do auth ensure google-workspace --strategy browser-import
```

Behavior:

- loads profile
- tries strategies in order unless overridden
- validates after each attempt
- saves the winning session state
- returns structured `action_required` output if no strategy succeeds

### save

Persists the current authenticated browser state for the site.

Examples:

```bash
agent-do auth save github
agent-do auth save my-admin --name rollout-2026-04
```

Behavior:

- captures current browser state through `browse`
- writes encrypted session bundle plus metadata
- marks the bundle as reusable for future `ensure`

### load

Loads the preferred saved session for the site into the browser.

Examples:

```bash
agent-do auth load github
agent-do auth load my-admin --name default
```

### import-browser

Imports cookies and storage from an already-authenticated real browser profile.

Examples:

```bash
agent-do auth import-browser github --browser arc --domain .github.com
agent-do auth import-browser google-workspace --browser chrome --domain .google.com
```

Behavior:

- delegates to browser import primitives
- validates the result
- persists as a reusable session bundle if valid

### clear

Deletes saved auth state for a site.

Examples:

```bash
agent-do auth clear github
agent-do auth clear my-admin --all
```

### validate

Performs a direct sign-in check against the site without mutating strategy state.

Examples:

```bash
agent-do auth validate github
agent-do auth validate github --json
```

### instructions

Returns next-step guidance for agents.

Examples:

```bash
agent-do auth instructions github
agent-do auth instructions my-admin --json
```

This command should answer:

- whether the site is ready
- which strategy should be tried next
- which credentials or setup are missing
- whether a human login is actually required

## JSON Contracts

Every command above should support `--json`.

### status --json

```json
{
  "site": "github",
  "state": "authenticated",
  "last_strategy": "saved-session",
  "session": {
    "name": "default",
    "validated_at": "2026-04-12T18:40:00Z"
  },
  "next": []
}
```

### ensure --json

```json
{
  "site": "github",
  "ok": true,
  "strategy_used": "browser-import",
  "validated": true,
  "session": {
    "name": "default"
  }
}
```

Failure case:

```json
{
  "site": "github",
  "ok": false,
  "state": "action-required",
  "attempted": [
    "saved-session",
    "browser-import",
    "site-creds"
  ],
  "action_required": "INTERACTIVE_LOGIN",
  "message": "No reusable authenticated state is available and configured strategies were exhausted"
}
```

### instructions --json

```json
{
  "site": "my-admin",
  "state": "stale",
  "recommended": [
    "agent-do auth ensure my-admin",
    "agent-do auth validate my-admin"
  ],
  "missing": [],
  "guidance": [
    "Prefer saved-session before site-creds",
    "If validation still fails, import cookies from the configured browser profile"
  ]
}
```

## Validation Model

Validation should be explicit and site-aware.

The validator should support:

- URL checks
- signed-in markers
- signed-out markers
- cookie presence checks
- localStorage key checks
- provider adapter checks for token freshness

The point is not "page loaded." The point is "authenticated state is actually usable."

## Secrets Model

`agent-do auth` should reference secrets from `agent-do creds`. It should not create a parallel secret system.

Examples of referenced secret material:

- site username
- site password
- TOTP secret
- provider refresh token
- client secret

That keeps one secure-store story for static secrets while allowing auth orchestration to consume them.

## Boundaries With Existing Tools

### auth vs creds

`creds` stores static secret material.

`auth` orchestrates authentication state and strategy.

Use `creds` when:

- storing API keys
- storing usernames and passwords
- storing TOTP seeds
- storing refresh tokens

Use `auth` when:

- reusing authenticated browser state
- deciding which login strategy to try next
- validating whether a session is still good
- importing or refreshing authenticated state

### auth vs browse

`browse` remains the browser control plane.

`auth` should call into `browse` primitives rather than duplicate them.

Use `browse` when:

- clicking, typing, waiting, inspecting
- saving raw browser state
- importing cookies from a real browser
- interacting with login pages directly

Use `auth` when:

- selecting the strategy ladder
- deciding whether to load, import, or autofill
- validating sign-in success
- emitting agent-facing next-step guidance

### auth vs context

`context` remains the place for vendor docs and auth-provider references.

`auth` should not absorb external auth documentation.

Future integration:

- `auth instructions` can suggest `context fetch-llms` or `context search` for provider-specific flows
- provider adapters can cite indexed docs when a flow is partially supported

## Provider Adapter Model

The design should support explicit adapters.

Examples:

- `github`
- `google`
- `okta`
- `clerk`
- `custom-saml`
- `custom-oidc`

Adapter responsibilities:

- detect common login shapes
- define better validation heuristics
- refresh tokens when supported
- expose known escalation paths

This is how the system eventually moves from generic site automation to provider-aware auth.

## v1 Scope

The right v1 is:

- site profiles
- saved session reuse
- browser import orchestration
- site credential reuse through `creds`
- validation
- agent-facing `ensure` and `instructions`

The right v1 is not:

- zero-touch fresh Google or GitHub SSO on arbitrary sites
- universal passkey automation
- CAPTCHA bypass

## Phase Two: Fresh SSO From Zero

This is a real research direction, but it should be treated as phase two.

To approach it cleanly, the design will need:

- provider-specific adapters for Google and GitHub
- challenge checkpointing so the agent can resume after redirects and handoffs
- first-class TOTP handling through `creds`
- support for magic-link and email-code flows through existing mail tools
- passkey-aware browser automation where the OS/browser allows it
- stronger validation to distinguish "signed in to provider" from "signed in to target app"

That is plausible. It is just not the same problem as v1.

## Discovery And Hook Fit

This tool should participate in the discovery layer.

Routing metadata should cover prompts like:

- "log into this site"
- "reuse github auth"
- "load the saved google session"
- "check if we are signed in"
- "import cookies from Arc"
- "store login state for later"

The point is to make the native auth path easier for agents to choose than raw improvisation.

## Summary

`agent-do auth` should become the site-level auth orchestrator:

- `creds` holds the secrets
- `browse` performs the browser actions
- `auth` decides, validates, persists, and escalates

That gives `agent-do` a clean layered auth story today, and a credible path toward fully autonomous fresh SSO later.
