# AGENTS.md - agent-do Tool Reference

> Use agent-do tools for automation instead of writing scripts directly.

---

## Tool Index

| Category | Tools | Primary Use |
|----------|-------|-------------|
| **Browser** | browse, unbrowse | Headless browser, API traffic capture → curl skills |
| **Mobile** | ios, android | Simulator/emulator control |
| **Desktop** | macos, tui, screen, ide | Desktop GUI automation, terminal apps |
| **Data** | db, excel, sheets, pdf, pdf2md, ocr, vision | Data access and extraction |
| **Communication** | slack, discord, email, sms, teams, zoom, meet, voice | Messaging and meetings |
| **Productivity** | calendar, notion, linear, figma, jupyter, lab, colab | App integrations |
| **Infrastructure** | docker, k8s, cloud, ci, vm, network, dns, ssh, render, vercel, supabase | Container/cluster/server/PaaS management |
| **Creative** | image, video, audio, 3d, cad, latex | Media processing |
| **Security** | burp, wireshark, ghidra | Security analysis |
| **Hardware** | serial, midi, homekit, bluetooth, usb, printer | Device control |
| **AI/Meta** | prompt, eval, memory, learn, swarm, agent, repl | Agent orchestration |
| **Memory** | zpc | Structured project memory (lessons, decisions, patterns) |
| **Tracking** | manna | Git-backed issue tracking |
| **Dev Tools** | git, api, tail, logs | Git, HTTP testing, log capture |
| **System** | clipboard, metrics, debug | System utilities |

**Discovery:** `agent-do --list` | `agent-do <tool> --help` | `agent-do --health`

---

## agent-do browse (Headless Browser)

AI-first browser automation. Uses @ref-based element selection from snapshots.

### Core Workflow
```bash
agent-do browse open https://example.com     # 1. Navigate
agent-do browse snapshot -i                  # 2. Get interactive elements with @refs
agent-do browse fill @e3 "username"          # 3. Interact by @ref
agent-do browse fill @e4 "password"
agent-do browse click @e7                    # 4. Submit
agent-do browse wait --stable                # 5. Wait for page change
agent-do browse snapshot -i                  # 6. Re-snapshot after navigation
```

### Navigation
```bash
agent-do browse open <url>         # Navigate to URL
agent-do browse back               # Go back
agent-do browse forward            # Go forward
agent-do browse reload             # Reload page
```

### Interaction (use @ref from snapshot)
```bash
agent-do browse click @e3          # Click element
agent-do browse dblclick @e3       # Double-click
agent-do browse fill @e3 "text"    # Clear and fill input
agent-do browse type @e3 "text"    # Append text (no clear)
agent-do browse press Enter        # Press key (Enter, Tab, Escape, etc.)
agent-do browse hover @e3          # Hover over element
agent-do browse check @e5          # Check checkbox
agent-do browse select @e6 "value" # Select dropdown option
agent-do browse upload @e7 /path   # Upload file
```

### Reading Data
```bash
agent-do browse get text @e3       # Get element text content
agent-do browse get value @e3      # Get input value
agent-do browse get attr href @e3  # Get attribute
agent-do browse get title          # Get page title
agent-do browse get url            # Get current URL
```

### Snapshots
```bash
agent-do browse snapshot           # Full page structure with @refs
agent-do browse snapshot -i        # Interactive elements only (recommended)
agent-do browse snapshot -c        # Compact (remove empty elements)
agent-do browse snapshot -s "table"  # Scope to CSS selector
agent-do browse snapshot --csv     # Output as CSV (for data extraction)
```

### Waiting
```bash
agent-do browse wait 2000          # Wait milliseconds
agent-do browse wait "selector"    # Wait for element to appear
agent-do browse wait --text "Welcome"  # Wait for text to appear
agent-do browse wait --stable      # Wait for network idle + DOM stable
```

### Login (SSO/MFA → Headless Handoff)

For sites requiring SSO, MFA, CAPTCHA, or any manual authentication flow. Opens a headed browser, user completes auth, then transfers the authenticated state to the headless daemon.

```bash
agent-do browse login <url>                  # Open headed Chromium window
# User completes SSO/MFA/CAPTCHA in the visible window...
agent-do browse login done                   # Extract auth → reinitialize headless context
agent-do browse login done --save <name>     # Same, plus persist session for future use
agent-do browse login status                 # Check if login window is open
agent-do browse login cancel                 # Close window without transferring
```

`login done` extracts `storageState()` (cookies + localStorage) from the headed browser, closes it, and creates a new headless browser context initialized with that auth. All subsequent `browse` commands operate with full authentication.

### Sessions (Persistent Auth)

Sessions save complete browser auth state. `session load` creates a new browser context with saved cookies + localStorage injected at context creation time — auth is live from the first request.

```bash
agent-do browse session save <name> [desc]   # Save cookies + localStorage + sessionStorage + URL
agent-do browse session load <name>           # Restore: new context with saved auth, navigate to URL
agent-do browse session list                  # List saved sessions
agent-do browse session delete <name>         # Delete saved session
agent-do browse session export <name> <file>  # Export to portable file
agent-do browse session import <file> [name]  # Import from file
agent-do browse session active                # List running daemon sessions
```

Session storage: `~/.agent-browse/sessions/<name>/` — `storage.json` (Playwright storageState), `session-storage.json`, `state.json` (URL, viewport, scroll), `meta.json`.

### Credential Auth (Username/Password)
```bash
agent-do browse auth check-creds <domain>      # Check if credentials exist
agent-do browse auth store-creds <dom> <e> <p>  # Store in OS keychain
agent-do browse auth login <domain> --submit    # Auto-login with stored creds
agent-do browse auth login <domain> --auto      # Navigate + fill + submit + verify
```

### Tabs
```bash
agent-do browse tab                    # Show active tab
agent-do browse tab list               # List all tabs
agent-do browse tab new [url]          # Open new tab
agent-do browse tab close              # Close current tab
agent-do browse tab <n>                # Switch to tab N
```

### API Capture & Replay
```bash
# Capture API traffic while browsing
agent-do browse capture start              # Start recording XHR/fetch
# ... click around, trigger API calls ...
agent-do browse capture status             # See captured requests
agent-do browse capture stop myservice     # Filter → extract auth → generate skill

# Replay captured APIs directly (no browser, ~100x faster)
agent-do browse api list                   # List generated skills
agent-do browse api show myservice         # View endpoints
agent-do browse api myservice get_users    # Call via curl
agent-do browse api test myservice         # Verify endpoints still work
agent-do browse api delete myservice       # Remove skill
```

Skills saved to `~/.agent-do/skills/<name>/` with `SKILL.md`, `auth.json`, and `api.sh`.

### Exit Codes
| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | User input needed (credentials missing) |
| `3` | Browser crashed (run `restart`) |
| `5` | Ref collision (use nth selector) |
| `6` | Stale refs (re-snapshot) |
| `7` | Element not found |
| `8` | Timeout |

### Mistakes to Avoid
- **DON'T** skip waits after navigation clicks
- **DON'T** use stale @refs after page changes (always re-snapshot)
- **DON'T** use `unbrowse` for SSO login → headless handoff (use `browse login` instead)
- **DO** use `snapshot -i` for interactive elements only
- **DO** use `wait --stable` instead of fixed delays
- **DO** use `browse login <url>` for SSO/MFA sites, then `login done --save <name>`
- **DO** use `session load <name>` to restore auth in future sessions
- **DO** use `capture start/stop` to discover APIs, then `api` to call them directly

---

## agent-do unbrowse (API Traffic → Curl Skills)

Standalone API capture: launches headed browser, captures XHR/fetch, generates reusable curl-based skills. Minimal footprint: `daemon.js` + `protocol.js`. Capture pipeline shared with browse via `lib/capture/`.

### Core Workflow
```bash
agent-do unbrowse capture https://api.example.com  # 1. Open browser + start capture
# Browse around manually in the headed browser...
agent-do unbrowse status                            # 2. See captured requests
agent-do unbrowse stop myservice                    # 3. Filter → generate skill
agent-do unbrowse replay myservice get_users        # 4. Call API via curl
```

### Capture
```bash
agent-do unbrowse capture <url>        # Launch headed browser + capture
agent-do unbrowse capture <url> --headless  # Headless mode
agent-do unbrowse stop <name>          # Stop → filter → generate skill
agent-do unbrowse status               # Show capture progress
agent-do unbrowse close                # Close browser + daemon
```

### Skills
```bash
agent-do unbrowse list                 # List generated skills
agent-do unbrowse show <name>          # Show SKILL.md documentation
agent-do unbrowse replay <name> <fn>   # Call function via curl
agent-do unbrowse test <name>          # HEAD test GET endpoints
agent-do unbrowse delete <name>        # Remove skill
```

### When to Use What
| Goal | Tool | Why |
|------|------|-----|
| SSO/MFA login → headless automation | `browse login <url>` | One daemon, session handoff built in |
| Quick one-shot API capture | `unbrowse capture <url>` | Own headed browser, browse manually |
| Capture APIs during existing automation | `browse capture start/stop` | Piggybacks on current browse session |
| Restore previous auth session | `browse session load <name>` | Cookies injected at context creation |

---

## agent-do ios (iOS Simulator)

Complete iOS Simulator control. Use instead of `xcrun simctl`.

### Core Workflow
```bash
agent-do ios boot "iPhone 15 Pro"    # 1. Boot simulator
agent-do ios install ./MyApp.app     # 2. Install app
agent-do ios launch com.myapp.id     # 3. Launch app
agent-do ios screenshot              # 4. See current state
agent-do ios tap 200 400             # 5. Interact
agent-do ios type "hello"            # 6. Type text
```

### Device Management
```bash
agent-do ios list                    # List available simulators
agent-do ios list-booted             # List running simulators
agent-do ios boot [device]           # Boot simulator
agent-do ios shutdown [device|all]   # Shutdown simulator(s)
agent-do ios snapshot                # JSON state: device, apps, status
```

### Interaction
```bash
agent-do ios screenshot [path]       # Take screenshot
agent-do ios screenrecord <path> [duration]  # Record video
agent-do ios tap <x> <y>             # Tap at coordinates
agent-do ios swipe <x1> <y1> <x2> <y2>  # Swipe gesture
agent-do ios type <text>             # Type text into focused field
agent-do ios keypress <key>          # Press key (home, lock, volumeup/down)
```

### Media & Data
```bash
agent-do ios addmedia <files...>     # Add photos/videos
agent-do ios openurl <url>           # Open URL in device
agent-do ios push <bundle-id> <payload.json>  # Send push notification
agent-do ios location <lat> <lon>    # Set simulated GPS location
```

---

## agent-do db (Database Client)

AI-first database exploration. Snapshot schema first, then query.

### Core Workflow
```bash
agent-do db connect prod-sales       # 1. Connect
agent-do db snapshot                 # 2. See all tables/columns/types
agent-do db describe orders          # 3. Understand specific table
agent-do db sample orders 5          # 4. Peek at actual data
agent-do db query "SELECT ..."       # 5. Query with confidence
agent-do db disconnect               # 6. Clean up
```

### Schema Exploration
```bash
agent-do db snapshot                 # Full schema: tables, columns, types, FKs
agent-do db snapshot --tables        # Tables only with row counts
agent-do db snapshot --compact       # Just table names
agent-do db tables [pattern]         # List tables matching pattern
agent-do db describe <table>         # Detailed schema with indexes
agent-do db relations                # FK relationship map
```

### Querying
```bash
agent-do db query "<sql>"            # Run query, return JSON
agent-do db query "<sql>" --explain  # Show execution plan
agent-do db sample <table> [n]       # Sample n rows (default: 5)
agent-do db export "<sql>" <file>    # Export to CSV/JSON/Excel
```

---

## agent-do excel (Spreadsheet)

AI-first Excel automation. Open → Snapshot → Read/Write → Save.

### Core Workflow
```bash
agent-do excel open sales.xlsx       # 1. Open workbook
agent-do excel snapshot --headers    # 2. See structure
agent-do excel get A1:F100           # 3. Read data
agent-do excel set D42 150           # 4. Update cells
agent-do excel save                  # 5. Save changes
```

### Reading
```bash
agent-do excel snapshot              # Overview: headers, preview, used range
agent-do excel get <cell>            # Get single cell
agent-do excel get <range>           # Get range: A1:D10
agent-do excel find <text>           # Find text, return cell refs
```

### Writing
```bash
agent-do excel set <cell> <value>    # Set single cell
agent-do excel set <range> <json>    # Set range from 2D array
agent-do excel formula <cell> <expr> # Set formula: =SUM(A1:A10)
agent-do excel save [path]           # Save (optionally to new path)
```

---

## agent-do manna (Issue Tracking)

Git-backed issue tracking designed for AI agents. Claims prevent conflicts.

### Core Workflow
```bash
agent-do manna init                  # 1. Initialize in project
agent-do manna create "Fix bug" "Details"  # 2. Create issues
agent-do manna list                  # 3. See all issues
agent-do manna claim mn-abc123       # 4. Claim to work on
# ... do work ...
agent-do manna done mn-abc123        # 5. Mark complete
```

### Issue Lifecycle
```bash
agent-do manna create <title> [desc] # Create → returns ID (mn-abc123)
agent-do manna claim <id>            # Claim (sets to in_progress)
agent-do manna done <id>             # Mark completed
agent-do manna abandon <id>          # Release (back to open)
```

### Dependencies
```bash
agent-do manna block <id> <blocker>  # Add blocker (sets to blocked)
agent-do manna unblock <id> <blocker> # Remove blocker
```

### Querying
```bash
agent-do manna list                  # All issues
agent-do manna list --status open    # Filter by status
agent-do manna show <id>             # Full issue details
agent-do manna context               # Context blob for AI prompts
```

---

## agent-do context (Knowledge Library)

Fetches, indexes, and serves external reference documentation. SQLite FTS5 with BM25 scoring, trust tiers, feedback-influenced ranking, and token-budgeted retrieval. Storage: `~/.agent-do/context/` (global, per-user). 22 commands.

**Not for experiential memory** — that's `zpc`. Context stores *what the docs say*. ZPC stores *what we learned using them*.

### Core Workflow
```bash
agent-do context init                            # 1. Create ~/.agent-do/context/ with FTS5 index
agent-do context scan-skills                     # 2. Index all ~/.claude/skills/
agent-do context fetch-llms stripe.com           # 3. Fetch llms.txt from any domain
agent-do context search "payment intents"        # 4. BM25 search with trust-tier boosting
agent-do context budget 4000 "stripe payments"   # 5. Best content within token limit
```

### Fetching
```bash
agent-do context fetch <url>                     # Download + cache + index markdown from URL
agent-do context fetch-llms <domain>             # Fetch llms-full.txt or llms.txt from domain
agent-do context fetch-repo <owner/repo> [path]  # Fetch docs from GitHub repo via gh API
agent-do context scan-local [path]               # Index CLAUDE.md, README.md, .cursorrules from project
agent-do context scan-skills                     # Index all ~/.claude/skills/*/SKILL.md
```

### Search & Retrieval
```bash
agent-do context search "<query>"                # FTS5 BM25 search, re-ranked by trust + feedback
agent-do context get <id>                        # Retrieve cached content by package ID
agent-do context list                            # List all indexed packages with type/trust/tokens
agent-do context budget <tokens> "<query>"       # Greedy knapsack: best content within token limit
agent-do context inject [--max-tokens N]         # Emit context blob of most-accessed packages
```

### Curation
```bash
agent-do context annotate <id> "<note>"          # Attach persistent note to a package
agent-do context feedback <id> up|down           # Rate package (influences search ranking)
agent-do context cache list                      # Show cached packages with disk usage
agent-do context cache pin <id>                  # Pin package from eviction
agent-do context cache clear [id]                # Clear specific or all cached content
```

### Sources
```bash
agent-do context sources                         # List configured content sources
agent-do context add-source <url> [--type T]     # Add a source to config
agent-do context remove-source <url>             # Remove a source
```

### Data Layout
```
~/.agent-do/context/
├── config.yaml              # Sources, trust policy, defaults
├── index.db                 # SQLite FTS5 index (packages + package_meta tables)
├── annotations.jsonl        # Persistent notes on packages
├── feedback.jsonl           # Up/down ratings (influence search ranking)
└── cache/
    ├── fetched/<id>/        # Downloaded content: content.md + meta.json
    ├── local/<id>/          # Scanned local project files
    ├── skills/<id>/         # Indexed skill files
    └── _pins.json           # Pinned package IDs
```

---

## agent-do zpc (Experience Journal)

Structured project memory for AI coding agents. Lessons, decisions, and patterns persist across sessions. Storage: `.zpc/` (per-project, in cwd).

**Not for reference docs** — that's `context`. ZPC stores *what we learned from doing work*. Context stores *what external docs say*.

### Core Workflow
```bash
agent-do zpc init                    # 1. Initialize .zpc/ in project
agent-do zpc status                  # 2. Memory snapshot + health
agent-do zpc patterns                # 3. Review conventions before coding
# ... work ...
agent-do zpc learn "ctx" "problem" "solution" "takeaway" --tags "t1,t2"  # 4. Capture lesson
agent-do zpc decide "problem" --options "a,b" --chosen a --rationale "why"  # 5. Log decision
agent-do zpc harvest                 # 6. Consolidate lessons into patterns
```

### Memory Operations
```bash
agent-do zpc learn <ctx> <prob> <sol> <takeaway> --tags "t1,t2"   # Capture lesson
agent-do zpc decide <problem> --options "a,b,c" --chosen b --rationale "why" --confidence 0.8  # Log decision
agent-do zpc query --tag mypy        # Search by tag
agent-do zpc query --type decisions  # Search by type
agent-do zpc query --text "docker"   # Free text search
```

### Intelligence
```bash
agent-do zpc harvest                 # Consolidation scan + pattern drafting
agent-do zpc harvest --auto          # Auto-write patterns for tags with 5+ lessons
agent-do zpc patterns                # View established patterns
agent-do zpc patterns --score        # Score pattern effectiveness
agent-do zpc promote --tag mypy --to team   # Promote lessons to team scope
agent-do zpc review --since HEAD~20 --dry-run  # Extract lessons from git history
agent-do zpc review --auto --phase "Sprint 3"  # Auto-write lesson/decision drafts
```

### Swarm Coordination
```bash
agent-do zpc decide-batch --tags "design" < decisions.txt  # Batch-log planning decisions
agent-do zpc checkpoint --phase "Phase 2" --agents "a,b,c" # Phase boundary compliance check
```

### Integration
```bash
agent-do zpc inject                  # Emit agent context blob (for spawned agents)
agent-do zpc status --json           # JSON snapshot for automation
agent-do zpc profile                 # View project profile
agent-do zpc profile detect          # Auto-detect project stack
```

### Data Layout
```
.zpc/                                # Per-project, in cwd
├── memory/
│   ├── lessons.jsonl                # {date, context, problem, solution, takeaway, tags}
│   ├── decisions.jsonl              # {date, decision, options, chosen, rationale, confidence, tags}
│   ├── patterns.md                  # ## tag-name sections with bullet-point takeaways
│   └── profile.md                   # Stack, Architecture, Testing, Conventions
├── team/
│   └── shared-lessons.jsonl         # Promoted lessons (shared via git)
└── .state/
    ├── harvest-log.jsonl            # Harvest timestamps and counts
    ├── review-log.jsonl             # Git review phase/baseline/counts
    └── checkpoint-log.jsonl         # Swarm checkpoint snapshots

~/.agent-do/zpc/                     # Global (cross-project)
├── global-lessons.jsonl             # Promoted cross-project lessons
└── project-index.jsonl              # {project, initialized, last_activity}
```

---

## context vs zpc — Decision Guide

| Question | Tool |
|----------|------|
| "What does the Stripe API look like?" | `context` — fetch external reference docs |
| "What did we learn last time we touched auth?" | `zpc` — query experiential lessons |
| "Give my agent the Playwright docs" | `context fetch-llms playwright.dev` |
| "Log that we chose Postgres over SQLite" | `zpc decide` |
| "Search for everything about authentication" | **Both** — `context search "auth"` + `zpc query --text "auth"` |
| "Fill a spawned agent's context window" | **Both** — `context inject` for docs, `zpc inject` for memory |
| "What patterns have we established?" | `zpc patterns` |
| "Index our project's README and CLAUDE.md" | `context scan-local` |

**Complementary, not overlapping.** Context provides the *what* (reference material). ZPC provides the *so what* (lessons from applying it). Both have `inject` — use both when spawning agents that need full context.

---

## Snapshot Commands

Every tool supports a `snapshot` command that returns JSON state for AI consumption:

```bash
# Infrastructure
agent-do docker snapshot       # Running containers, images, volumes, networks
agent-do k8s snapshot          # Pods, services, deployments, cluster state
agent-do ssh snapshot          # Active connections, host configs
agent-do git snapshot          # Branch, status, stash, recent commits, remotes

# Communication
agent-do slack snapshot        # Channels, unread counts, workspace info
agent-do email snapshot        # Inbox summary, unread counts
agent-do calendar snapshot     # Upcoming events, free/busy

# Productivity
agent-do notion snapshot       # Recent pages, databases
agent-do linear snapshot       # Active issues, sprints

# Memory
agent-do zpc status            # Lessons, decisions, patterns, health

# System
agent-do clipboard snapshot    # Current clipboard contents
agent-do ios snapshot          # Device state, running apps
```

---

## Universal Pattern

All tools follow: **Connect → Snapshot → Interact → Verify → Save**

```
1. CONNECT/OPEN   → Establish session
2. SNAPSHOT        → Understand current state (JSON for AI)
3. INTERACT        → Read/write/click/type
4. VERIFY          → Confirm changes worked
5. SAVE/CLOSE      → Clean up
```

---

## Tool Selection Guide

| Need To... | Use Tool | Not |
|------------|----------|-----|
| Automate browser | `agent-do browse` | Playwright scripts |
| Capture API traffic | `agent-do unbrowse` or `browse capture` | Manual HAR analysis |
| Replay captured APIs | `agent-do browse api` or `unbrowse replay` | Custom HTTP clients |
| Control iOS Simulator | `agent-do ios` | xcrun simctl |
| Query database | `agent-do db` | Python + psycopg2 |
| Edit spreadsheet | `agent-do excel` | Python + openpyxl |
| Track issues | `agent-do manna` | Custom JSON files |
| Detect objects in images | `agent-do vision` | Python + YOLO |
| Control macOS apps | `agent-do macos` | AppleScript |
| Automate terminal apps | `agent-do tui` | expect scripts |
| Persist project memory | `agent-do zpc` | Manual JSONL files |
