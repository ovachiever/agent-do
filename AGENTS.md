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

### Authentication
```bash
agent-do browse auth check-creds <domain>   # Check if credentials exist
agent-do browse auth login <domain> --submit  # Auto-login with stored creds
agent-do browse session save mysite "desc"  # Save cookies/storage
agent-do browse session load mysite         # Restore session
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

### Mistakes to Avoid
- **DON'T** skip waits after navigation clicks
- **DON'T** use stale @refs after page changes (always re-snapshot)
- **DO** use `snapshot -i` for interactive elements only
- **DO** use `wait --stable` instead of fixed delays
- **DO** use `capture start/stop` to discover APIs, then `api` to call them directly

---

## agent-do unbrowse (API Traffic → Curl Skills)

Standalone API capture: launches headed browser, captures XHR/fetch, generates reusable curl-based skills.

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

### When to Use unbrowse vs browse capture
- **`unbrowse`**: Quick one-shot captures — launches its own browser, browse manually
- **`browse capture`**: Integrated — start capture on an existing browse session with auth/sessions already set up

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

## agent-do zpc (Project Memory)

Structured project memory for AI coding agents. Lessons, decisions, and patterns persist across sessions.

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
```

### Integration
```bash
agent-do zpc inject                  # Emit agent context blob (for spawned agents)
agent-do zpc status --json           # JSON snapshot for automation
agent-do zpc profile                 # View project profile
agent-do zpc profile detect          # Auto-detect project stack
```

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
