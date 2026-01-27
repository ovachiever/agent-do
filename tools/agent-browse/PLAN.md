# agent-browse Enhancement Plan

Phase 1 complete: Basic CLI wrapper + Playwright daemon working.

---

## Phase 2: Enhanced Snapshots

**Goal:** Rich element metadata for precise AI-driven interaction.

### 2.1 Position & Size Data
- Add bounding box (x, y, width, height) to each ref
- Include viewport-relative and document-relative coords
- Flag elements that are off-screen or occluded

### 2.2 Semantic Labels
- Detect common patterns: login form, search box, nav menu, modal, toast
- Label landmark regions: header, footer, main, sidebar, article
- Identify input types: email, password, phone, date, credit card

### 2.3 Output Formats
- `--format tree` (default): Current accessible tree format
- `--format json`: Machine-readable with full metadata
- `--format csv`: Flat table for analysis
- `--format markdown`: Human-readable summary

### 2.4 Visual Indicators
- `snapshot --highlight`: Overlay ref numbers on screenshot
- `snapshot --heatmap`: Show interactive density
- Color-code by element type

**Implementation:**
- Extend `snapshot.js` to collect bounding boxes via `element.boundingBox()`
- Add semantic classifier (regex patterns + aria roles)
- New output formatters in protocol layer

---

## Phase 3: Session Persistence

**Goal:** Save/restore complete browser state for resumable workflows.

### 3.1 State Components
- Cookies (all domains)
- localStorage per origin
- sessionStorage per origin  
- IndexedDB databases
- Service worker registrations
- Auth tokens in memory

### 3.2 Commands
```bash
agent-browse session save <name>      # Save current state
agent-browse session load <name>      # Restore state
agent-browse session list             # Show saved sessions
agent-browse session delete <name>    # Remove saved session
agent-browse session export <file>    # Export to portable format
agent-browse session import <file>    # Import from file
```

### 3.3 Storage Format
```
~/.agent-browse/sessions/
├── <name>/
│   ├── cookies.json
│   ├── storage.json        # localStorage + sessionStorage
│   ├── indexeddb/          # Per-origin DB dumps
│   ├── state.json          # URL, viewport, scroll position
│   └── meta.json           # Created, last used, description
```

### 3.4 Auto-save
- `--autosave <name>`: Periodic state snapshots
- `--autosave-interval 60`: Save every N seconds
- Recovery on crash

**Implementation:**
- Use Playwright's `storageState()` for cookies/localStorage
- Custom IndexedDB serialization via `page.evaluate()`
- Session manager module

---

## Phase 4: Network Intelligence

**Goal:** Full visibility and control over network traffic.

### 4.1 HAR Export
```bash
agent-browse har start              # Begin capture
agent-browse har stop <file.har>    # Save HAR file
agent-browse har --auto <file>      # Auto-capture entire session
```

### 4.2 Request Interception
```bash
agent-browse route "**/*.jpg" --block           # Block images
agent-browse route "**/api/*" --mock data.json  # Mock API
agent-browse route "**/slow" --delay 2000       # Add latency
agent-browse route "**/api/*" --modify-headers '{"X-Test": "1"}'
agent-browse unroute "**/*.jpg"                 # Remove route
```

### 4.3 Request Log
```bash
agent-browse requests                  # List all requests
agent-browse requests --failed         # Only failures
agent-browse requests --type xhr       # Filter by type
agent-browse requests --url "*api*"    # Filter by pattern
agent-browse requests --body           # Include request bodies
```

### 4.4 Bandwidth Throttling
```bash
agent-browse throttle 3g              # Preset: 3G network
agent-browse throttle slow            # Preset: slow connection
agent-browse throttle --down 1000 --up 500 --latency 100  # Custom
agent-browse throttle off             # Disable
```

**Implementation:**
- HAR via Playwright's native HAR recording
- Route interception already in protocol, enhance with more options
- Throttling via CDP Network.emulateNetworkConditions

---

## Phase 5: Auth Flow Helpers

**Goal:** Handle common authentication patterns automatically.

### 5.1 TOTP/2FA
```bash
agent-browse totp <secret>              # Generate current code
agent-browse totp <secret> --fill @e5   # Generate and fill
agent-browse totp --scan                # Read QR from page, store secret
```

### 5.2 OAuth Flows
```bash
agent-browse oauth google --callback <url>    # Handle Google OAuth
agent-browse oauth github --callback <url>    # Handle GitHub OAuth
agent-browse oauth --wait-redirect <pattern>  # Wait for redirect, capture token
```

### 5.3 Credential Management
```bash
agent-browse creds save <site> <user> <pass>  # Store encrypted
agent-browse creds get <site>                 # Retrieve
agent-browse creds autofill                   # Fill detected login form
agent-browse creds list                       # Show stored sites
```

### 5.4 Captcha Handling
```bash
agent-browse captcha --detect           # Check if captcha present
agent-browse captcha --type             # Identify type (reCAPTCHA, hCaptcha, etc)
agent-browse captcha --wait             # Wait for manual solve
agent-browse captcha --audio            # Attempt audio challenge
```

**Implementation:**
- TOTP via otpauth library
- OAuth state machine for common providers
- Encrypted credential store (~/.agent-browse/creds.enc)
- Captcha detection via common selectors/patterns

---

## Phase 6: Vision Integration

**Goal:** Enable visual understanding for AI agents.

### 6.1 Page Description
```bash
agent-browse describe                   # AI describes visible page
agent-browse describe --detail high     # Verbose description
agent-browse describe --focus "form"    # Describe specific area
```

### 6.2 Visual Element Finding
```bash
agent-browse find-visual "red button"           # Find by appearance
agent-browse find-visual "login form" --click   # Find and act
agent-browse find-visual "error message"        # Find by visual pattern
```

### 6.3 Continuous Vision
```bash
agent-browse watch --interval 1000      # Screenshot every N ms
agent-browse watch --on-change          # Screenshot on visual change
agent-browse watch --describe           # Continuous AI description
```

### 6.4 Multi-Model Support
- Claude (claude-3-5-sonnet vision)
- GPT-4V
- Gemini Pro Vision
- Local models (LLaVA, etc.)

```bash
agent-browse describe --model claude
agent-browse describe --model gpt4v
agent-browse describe --model local
```

**Implementation:**
- Screenshot → base64 → vision API
- Configurable model selection
- Caching to avoid redundant API calls
- Streaming for continuous watch mode

---

## Phase 7: AI Agent Helpers

**Goal:** High-level primitives for autonomous browsing.

### 7.1 Goal Execution
```bash
agent-browse goal "log into example.com with user@test.com"
agent-browse goal "find the pricing page and extract plan names"
agent-browse goal "fill out the contact form with test data"
```

### 7.2 Page Exploration
```bash
agent-browse explore                    # Discover all interactions
agent-browse explore --depth 2          # Follow links 2 levels
agent-browse explore --map              # Build site structure
```

### 7.3 Smart Recovery
```bash
agent-browse retry --on-error           # Auto-retry failed actions
agent-browse recover                    # Attempt to fix stuck state
agent-browse fallback "click @e1" "click @e2"  # Try alternatives
```

### 7.4 Explanation Mode
```bash
agent-browse explain                    # Explain current page state
agent-browse explain @e5                # Explain specific element
agent-browse explain --action "click @e5"  # Predict action result
```

**Implementation:**
- Goal parser → action planner → executor loop
- State machine for multi-step flows
- Error classification and recovery strategies
- LLM integration for planning/explanation

---

## Implementation Order

1. **Phase 2** (Enhanced Snapshots) - Foundation for everything else
2. **Phase 3** (Session Persistence) - Critical for auth flows
3. **Phase 4** (Network Tools) - Important for debugging
4. **Phase 5** (Auth Helpers) - Builds on sessions
5. **Phase 6** (Vision) - Requires stable base
6. **Phase 7** (AI Helpers) - Requires vision + all primitives

---

## File Changes

### Phase 2
- `snapshot.js` - Add bounding boxes, semantic labels
- `protocol.js` - New snapshot options schema
- `agent-browse` - New format flags

### Phase 3
- `session.js` (new) - Session persistence logic
- `protocol.js` - Session commands
- `agent-browse` - Session subcommands

### Phase 4
- `network.js` (new) - HAR, routing, throttling
- `protocol.js` - Network commands
- `agent-browse` - Network subcommands

### Phase 5
- `auth.js` (new) - TOTP, OAuth, creds, captcha
- `protocol.js` - Auth commands
- `agent-browse` - Auth subcommands

### Phase 6
- `vision.js` (new) - Vision API integration
- `protocol.js` - Vision commands
- `agent-browse` - Vision subcommands

### Phase 7
- `agent.js` (new) - Goal execution, exploration
- `protocol.js` - Agent commands
- `agent-browse` - Agent subcommands

---

## Current Status

- [x] Phase 1: Basic CLI + daemon (COMPLETE)
- [x] Phase 2: Enhanced snapshots (COMPLETE)
  - [x] Bounding boxes (x, y, width, height, center)
  - [x] Viewport awareness (visible, offScreen flags)
  - [x] Semantic region detection (login-form, cookie-banner, signup-form, etc.)
  - [x] Input type detection (email, password, phone, etc.)
  - [x] Output formats: --json, --csv, --markdown, --boxes
  - [x] Stats: total, interactive, visible, offScreen counts
- [x] Phase 3: Session persistence (COMPLETE)
  - [x] session save <name> [desc] - Save cookies, localStorage, sessionStorage, URL, scroll
  - [x] session load <name> - Restore session state
  - [x] session list - List all saved sessions with metadata
  - [x] session delete <name> - Remove saved session
  - [x] session export <name> <file> - Export to portable JSON
  - [x] session import <file> [name] - Import from file
  - [x] Storage at ~/.agent-browse/sessions/<name>/
- [x] Phase 4: Network intelligence (COMPLETE)
  - [x] network har start/stop <path> - HAR 1.2 format recording
  - [x] network stats - Request statistics (by type, status)
  - [x] network throttle <preset> - Presets: offline, slow-3g, 3g, 4g, fast, off
  - [x] network throttle --latency/--download/--upload - Custom throttling
  - [x] network requests [filter] - View tracked requests
  - [x] network route <url> --abort/--body - Request mocking/blocking
- [x] Phase 5: Auth helpers (COMPLETE)
  - [x] auth totp <secret> [--fill @ref] - Generate and optionally fill TOTP code
  - [x] auth detect-login - Detect login form fields on page
  - [x] auth autofill <user> <pass> [--submit] - Auto-fill login form
  - [x] auth detect-captcha - Detect CAPTCHA presence (reCAPTCHA, hCaptcha, etc.)
  - [x] auth wait-captcha [timeout] - Wait for manual CAPTCHA solve
- [x] Phase 6: Vision integration (COMPLETE)
  - [x] vision describe [--detail low|medium|high] [--focus <area>] [--full] - AI describes page
  - [x] vision find <description> - Find element by visual description (returns location)
  - [x] vision click <description> - Click element found by visual description
  - [x] vision analyze <pattern> - Analyze for patterns: errors, forms, login, products, navigation
  - [x] vision explain <action> <target> - Predict what action will do
  - [x] vision compare <before> [after] - Compare screenshots for changes
  - [x] Uses Claude Sonnet 4 with vision capabilities
  - [x] Returns structured JSON with coordinates, confidence levels
- [x] Phase 7: AI agent helpers (COMPLETE)
  - [x] agent goal "<goal>" [--max-steps N] [--verbose] - Execute high-level goal through planning loop
  - [x] agent explore [--depth N] [--max-links N] [--all-origins] - Discover page interactions
  - [x] agent explain - Explain current page state, forms, errors, possible actions
  - [x] agent recover - Attempt to recover from stuck state (dismiss overlays, reload, etc.)
  - [x] Smart recovery strategies for common failures (element not found, blocked, timeout)
  - [x] Vision-guided action planning with Claude Sonnet 4
