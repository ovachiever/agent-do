# Tool Map

`agent-do` tools share one command shape:

```bash
agent-do <tool> <command> [args...]
```

This is an agent-call reference, not a human operations checklist. Humans can run
the same commands for setup, debugging, and verification, but normal use is an AI
agent or harness choosing structured `agent-do` calls instead of improvising raw
shell glue.

Use this page when the agent knows the kind of work to do but not the exact tool
surface.

## Discovery

```bash
agent-do --list
agent-do <tool> --help
agent-do suggest "deploy this service"
agent-do suggest --project
agent-do find playwright
agent-do --health
```

## Browser And API Capture

`browse` is the default browser automation surface. It is snapshot-first, uses
stable element refs, and supports authenticated session handoff.

```bash
agent-do browse open https://app.example.com
agent-do browse snapshot -i
agent-do browse fill @e3 "admin@example.com"
agent-do browse click @e7
agent-do browse wait --stable
```

Authenticated session flow:

```bash
agent-do browse login https://app.example.com
agent-do browse login done --save mysite
agent-do browse session load mysite
agent-do browse session import-browser mysite --browser comet --domain .example.com
```

API capture:

```bash
agent-do browse capture start
agent-do browse capture stop myapi
agent-do browse api myapi get_users
```

## Auth And Credentials

Use `creds` for secrets and `auth` for site-level authenticated state.

```bash
agent-do creds required render
agent-do creds store RENDER_API_KEY --stdin
agent-do creds check --tool render
```

Known-provider auth:

```bash
agent-do auth init github
agent-do creds store GITHUB_EMAIL --stdin
agent-do creds store GITHUB_PASSWORD --stdin
agent-do creds store GITHUB_TOTP_SECRET --stdin
agent-do auth ensure github
agent-do auth validate github
```

Custom provider-backed site:

```bash
agent-do auth init cloudflare --domain dash.cloudflare.com --login-url https://dash.cloudflare.com/login --provider github
agent-do auth ensure cloudflare --strategy provider-refresh
```

When a real visible browser is required:

```bash
agent-do auth ensure cloudflare --strategy interactive --timeout 300
agent-do +live(scope=browser,app=Arc,ttl=15m) auth ensure cloudflare --strategy live-browser-control --timeout 300
```

## Context And Memory

Use `context` for external reference material. Use `zpc` for durable lessons and
decisions learned from work.

```bash
agent-do context fetch-llms stripe.com
agent-do context fetch-repo vercel/next.js docs/
agent-do context search "payments api"
agent-do context budget 4000 "react hooks"
```

```bash
agent-do zpc init
agent-do zpc learn "deploying" "missing env var" "added .env.example" "always ship env templates" --tags "deploy,env"
agent-do zpc decide "Which DB?" --options "postgres,sqlite" --chosen postgres --rationale "team expertise" --confidence 0.9
agent-do zpc harvest --auto
```

## GitHub Work

`gh` covers PR review, issue management, release management, and raw API access across accessible GitHub repos.

### PR Review

```bash
agent-do gh inbox
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova
agent-do gh pr ovachiever/agent-do#3 --json
agent-do gh checks ovachiever/agent-do#3
agent-do gh threads ovachiever/agent-do#3
```

Review-risk audit:

```bash
agent-do gh audit ovachiever/agent-do#3 --reply --probe-deploys
agent-do gh awaiting --owner Versova-Intelligence-Division --author ctyrrell-versova --audit --replies --probe-deploys
```

Review actions:

```bash
agent-do gh approve ovachiever/agent-do#2 --body "LGTM"
agent-do gh request-changes ovachiever/agent-do#3 --body-file review.md
agent-do gh merge ovachiever/agent-do#2 --squash --delete-branch
```

### Issues

```bash
agent-do gh issue list ovachiever/agent-do --state open --json
agent-do gh issue view ovachiever/agent-do#42 --comments --json
agent-do gh issue triage ovachiever/agent-do#42 --json
agent-do gh issue create ovachiever/agent-do --title "Bug: crash on startup" --label bug --dry-run
agent-do gh issue close ovachiever/agent-do#42 --reason completed
agent-do gh issue label ovachiever/agent-do#42 --add confirmed --remove needs-triage
agent-do gh issue snapshot ovachiever/agent-do --json
```

### Releases

```bash
agent-do gh release list ovachiever/agent-do --json
agent-do gh release latest ovachiever/agent-do --json
agent-do gh release view ovachiever/agent-do v1.2.0 --json
agent-do gh release create ovachiever/agent-do v1.3.0 --generate-notes --dry-run
agent-do gh release publish ovachiever/agent-do v1.3.0
agent-do gh release delete ovachiever/agent-do v1.3.0 --confirm
agent-do gh release notes ovachiever/agent-do --since v1.1.0 --json
```

### Raw API

```bash
agent-do gh api GET /rate_limit --json
agent-do gh api POST /repos/ovachiever/agent-do/issues --field title=Test --dry-run
agent-do gh graphql '{ viewer { login } }' --json
```

## Cloud And Platform Tools

Use provider tools instead of hand-written `curl` when a structured surface
exists.

```bash
agent-do render services
agent-do render show my-service
agent-do render logs my-service --since 1h
agent-do render env my-service
```

```bash
agent-do vercel projects
agent-do vercel deployments my-project
agent-do vercel env my-project
```

```bash
agent-do supabase projects
agent-do cloudflare zones
agent-do resend records example.com
```

## Visual And Device Work

```bash
agent-do browse screenshot /tmp/ui.png
agent-do dpt score /tmp/ui.png
```

```bash
agent-do ios list
agent-do ios screenshot
agent-do screen snapshot
agent-do vision detect /tmp/screen.png
```

Visible desktop control requires explicit live approval:

```bash
agent-do +live(scope=desktop,ttl=15m) macos click @g5
agent-do +live(scope=desktop,ttl=15m) screen click --text "Continue"
```

## Communication

```bash
agent-do email latest --from WidgetHub --json
agent-do email code --from WidgetHub --subject "verification code"
agent-do sms code --from WidgetHub --contains "verification"
```

```bash
agent-do notify set-recipient me --sms +15551234567 --email me@example.com --prefer sms,email
agent-do notify me "Deploy complete" --via sms
agent-do notify templates
agent-do notify apply-template build_failed --recipient me
agent-do notify history --limit 10
```

## Coordination And Specs

`coord` is a local state board for parallel agents. It is not chat.

```bash
agent-do coord touch
agent-do coord focus set "generation cutover" --path app/api/generate/route.ts
agent-do coord claim app/api/generate/route.ts --reason "cutover path"
agent-do coord need add dm-sdk@1.2.2 --why "switch off tarball dependency"
agent-do coord publish add dm-sdk@1.2.2 --status ready --summary "private package published"
agent-do coord interrupts
```

`spec` stores repo-local intended behavior specs and active change artifacts.

```bash
agent-do spec init
agent-do spec new add-oauth-device-flow --spec auth
agent-do spec status --change add-oauth-device-flow
agent-do spec validate --change add-oauth-device-flow
```

## Harness Observability

```bash
agent-do harness inspect
agent-do harness nudges effectiveness --since 7d
agent-do harness evidence build <session-or-run>
agent-do harness manifest new <change-id> --component-type tool --file tools/agent-email
agent-do harness manifest verify <change-id> --before before.json --after after.json
```

## Full Catalog

The exact catalog lives in `registry.yaml`.

```bash
agent-do --list
agent-do <tool> --help
```
