# AGENTS.md - agent-do Development

> AI automation toolkit. ALWAYS prefer agent-do tools over direct implementations.

---

## CRITICAL: agent-do First

**BEFORE writing any automation code, ALWAYS check if agent-do has a tool:**

```bash
# Load the index to see what's available
cat ~/.factory/agent-do-index.yaml

# Or check full catalog for details
cat ~/.factory/agent-do-catalog.yaml

# Or get help for a specific tool
agent-do <tool> --help
```

### Why agent-do Over Direct Code?

| Task | ❌ Don't Do This | ✅ Do This Instead |
|------|------------------|-------------------|
| Read Excel | Write Python with openpyxl | `agent-do excel open file.xlsx` → `snapshot` |
| Query database | Write Python with psycopg2 | `agent-do db connect` → `query "SELECT..."` |
| iOS automation | Use xcrun simctl directly | `agent-do ios launch` → `tap` → `screenshot` |
| Browser automation | Write Playwright scripts | `agent-do browse open` → `snapshot -i` → `click @ref` |
| Track issues | Create custom JSON files | `agent-do manna create` → `claim` → `done` |

**The pattern is always:** Connect/Open → Snapshot → Interact → Verify

---

## Tool Index (Load This First)

Key tools by category:

| Category | Tools | Use For |
|----------|-------|---------|
| **Core** | browse, ios, android, gui, tui, screen | Device/UI automation |
| **Data** | db, excel, manna, vision, ocr | Data access and tracking |
| **Apps** | slack, email, calendar, notion | Communication |
| **Infra** | docker, k8s, cloud, ci | Infrastructure |

**Full index:** `~/.factory/agent-do-index.yaml`
**Full catalog:** `~/.factory/agent-do-catalog.yaml`

---

## agent-do browse (Headless Browser)

AI-first browser automation. Uses @ref-based element selection from snapshots.

### Core Workflow Pattern
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

### Snapshot Options
```bash
agent-do browse snapshot           # Full page structure with @refs
agent-do browse snapshot -i        # Interactive elements only (recommended)
agent-do browse snapshot -c        # Compact (remove empty elements)
agent-do browse snapshot -s "table"  # Scope to selector
agent-do browse snapshot --csv     # Output as CSV (for data extraction)
```

### Waiting (IMPORTANT: wait after clicks that navigate)
```bash
agent-do browse wait 2000          # Wait 2 seconds (milliseconds)
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

### Example: Login and Extract Table
```bash
# 1. Open and check credentials
agent-do browse open https://app.example.com
agent-do browse auth check-creds example.com
# If ready: false → ask user, then store-creds

# 2. Login
agent-do browse auth login example.com --submit
agent-do browse wait --stable

# 3. Navigate to data
agent-do browse snapshot -i
agent-do browse click @e12          # Click data link
agent-do browse wait --stable

# 4. Extract table data
agent-do browse snapshot --csv -s "table"
```

### Common Mistakes
- **DON'T** skip waits after navigation clicks
- **DON'T** use stale @refs after page changes (always re-snapshot)
- **DO** use `snapshot -i` for interactive elements only
- **DO** use `wait --stable` instead of fixed delays when possible

---

## agent-do ios (iOS Simulator)

Complete iOS Simulator control. **ALWAYS use instead of xcrun simctl.**

### Core Workflow Pattern
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
agent-do ios boot [device]           # Boot simulator (default: first iPhone)
agent-do ios shutdown [device|all]   # Shutdown simulator(s)
agent-do ios erase <device>          # Erase device contents
```

### App Management
```bash
agent-do ios install <path.app>      # Install .app bundle
agent-do ios uninstall <bundle-id>   # Uninstall app
agent-do ios launch <bundle-id>      # Launch app
agent-do ios terminate <bundle-id>   # Terminate app
agent-do ios listapps                # List installed apps with versions
agent-do ios appinfo <bundle-id>     # Show app information
agent-do ios appcontainer <bundle-id> # Get app container path
```

### Interaction
```bash
agent-do ios screenshot [path]       # Take screenshot (returns path)
agent-do ios screenrecord <path> [duration]  # Record screen video
agent-do ios tap <x> <y>             # Tap at coordinates
agent-do ios swipe <x1> <y1> <x2> <y2>  # Swipe gesture
agent-do ios type <text>             # Type text into focused field
agent-do ios keypress <key>          # Press key (home, lock, volumeup/down)
agent-do ios shake                   # Shake device gesture
```

### Media & Data
```bash
agent-do ios addmedia <files...>     # Add photos/videos to library
agent-do ios openurl <url>           # Open URL in device
agent-do ios push <bundle-id> <payload.json>  # Send push notification
agent-do ios pbcopy <text>           # Copy text to device clipboard
agent-do ios pbpaste                 # Get device clipboard contents
agent-do ios location <lat> <lon>    # Set simulated GPS location
```

### System
```bash
agent-do ios status                  # Show booted simulator status
agent-do ios statusbar --time "9:41" --battery 100  # Override status bar
agent-do ios privacy grant location-always <bundle>  # Manage permissions
agent-do ios ui appearance light|dark  # Set appearance mode
```

### Example: Test App Login Flow
```bash
# 1. Setup
agent-do ios boot "iPhone 15 Pro"
agent-do ios install ~/builds/MyApp.app
agent-do ios launch com.myapp.id

# 2. Wait for app to load
sleep 2
agent-do ios screenshot ~/test/01_launch.png

# 3. Login
agent-do ios tap 200 300             # Tap email field
agent-do ios type "test@example.com"
agent-do ios tap 200 380             # Tap password field
agent-do ios type "password123"
agent-do ios tap 200 450             # Tap login button

# 4. Verify
sleep 2
agent-do ios screenshot ~/test/02_logged_in.png

# 5. Record video of feature
agent-do ios screenrecord ~/test/feature_demo.mov 10
```

### Common Mistakes
- **DON'T** use `xcrun simctl` directly - use agent-do ios
- **DON'T** forget to boot before interacting
- **DO** use screenshots to verify state between interactions
- **DO** add delays after launches and taps for UI to settle

---

## agent-do db (Database Client)

AI-first database exploration. Snapshot schema first, then query.

### Core Workflow Pattern
```bash
agent-do db connect prod-sales       # 1. Connect to database
agent-do db snapshot                 # 2. See all tables/columns/types
agent-do db describe orders          # 3. Understand specific table
agent-do db sample orders 5          # 4. Peek at actual data
agent-do db query "SELECT ..."       # 5. Query with confidence
agent-do db disconnect               # 6. Clean up
```

### Connection
```bash
agent-do db connect <profile>        # Connect using saved profile
agent-do db connect "postgresql://user:pass@host/db"  # Connection string
agent-do db disconnect               # End session
agent-do db status                   # Show current connection
agent-do db profiles                 # List saved profiles
```

### Schema Exploration (The "Snapshot")
```bash
agent-do db snapshot                 # Full schema: tables, columns, types, FKs
agent-do db snapshot --tables        # Tables only with row counts
agent-do db snapshot --compact       # Just table names
agent-do db tables [pattern]         # List tables matching pattern
agent-do db describe <table>         # Detailed schema with indexes
agent-do db relations                # FK relationship map
agent-do db relations <table>        # Relations for specific table
```

### Data Sampling
```bash
agent-do db sample <table> [n]       # Sample n rows (default: 5)
agent-do db sample <table> --random  # Random sample
agent-do db count <table>            # Row count
agent-do db stats <table>            # Column stats (nulls, uniques, min/max)
```

### Query Execution
```bash
agent-do db query "<sql>"            # Run query, return JSON results
agent-do db query "<sql>" --explain  # Show execution plan
agent-do db query "<sql>" --limit 100  # Override/add LIMIT
agent-do db export "<sql>" <file>    # Export to CSV/JSON/Excel
agent-do db history                  # Recent queries
```

### Transactions
```bash
agent-do db begin                    # Start transaction
agent-do db commit                   # Commit transaction
agent-do db rollback                 # Rollback transaction
```

### Example: Analyze Sales Data
```bash
# 1. Connect and explore
agent-do db connect prod-sales
agent-do db snapshot
# → See: customers, orders, products, order_items tables

# 2. Understand orders table
agent-do db describe orders
# → columns: id, customer_id (FK→customers.id), total, status, created_at

# 3. Sample data to understand shape
agent-do db sample orders 5
# → See actual values, date formats, status values

# 4. Query with confidence
agent-do db query "
  SELECT c.name, COUNT(o.id) as orders, SUM(o.total) as revenue
  FROM customers c
  JOIN orders o ON o.customer_id = c.id
  WHERE o.created_at > '2024-01-01'
  GROUP BY c.name
  ORDER BY revenue DESC
  LIMIT 10
"

# 5. Export results
agent-do db export "SELECT * FROM orders WHERE status='pending'" pending.csv

# 6. Disconnect
agent-do db disconnect
```

### Common Mistakes
- **DON'T** query without checking schema first (snapshot!)
- **DON'T** write Python database code - use agent-do db
- **DO** sample data to understand actual values
- **DO** use --limit to avoid huge result sets

---

## agent-do excel (Spreadsheet Automation)

AI-first Excel automation. Open → Snapshot → Read/Write → Save.

### Core Workflow Pattern
```bash
agent-do excel open sales.xlsx       # 1. Open workbook
agent-do excel snapshot --headers    # 2. See structure (headers, preview)
agent-do excel get A1:F100           # 3. Read data range
agent-do excel set D42 150           # 4. Update cells
agent-do excel save                  # 5. Save changes
```

### Workbook Management
```bash
agent-do excel open <path>           # Open existing workbook
agent-do excel new [path]            # Create new workbook
agent-do excel save [path]           # Save (optionally to new path)
agent-do excel close                 # Close without saving
agent-do excel export csv <path>     # Export active sheet to CSV
agent-do excel status                # Current workbook info
```

### Sheet Navigation
```bash
agent-do excel sheets                # List all sheets
agent-do excel sheet <name>          # Switch to sheet
agent-do excel sheet new <name>      # Create new sheet
agent-do excel sheet rename <old> <new>  # Rename sheet
agent-do excel sheet delete <name>   # Delete sheet
```

### Reading Data
```bash
agent-do excel snapshot              # Overview: headers, preview, used range
agent-do excel snapshot --range A1:Z50  # Specific range
agent-do excel snapshot --used       # Only used range
agent-do excel get <cell>            # Get single cell: A1, B2
agent-do excel get <range>           # Get range: A1:D10
agent-do excel get row <n>           # Get entire row
agent-do excel get col <letter>      # Get entire column
agent-do excel get formula <cell>    # Formula if present
```

### Writing Data
```bash
agent-do excel set <cell> <value>    # Set single cell
agent-do excel set <range> <json>    # Set range from 2D array
agent-do excel fill <range> <value>  # Fill range with value
agent-do excel clear <range>         # Clear cell contents
agent-do excel formula <cell> <expr> # Set formula: =SUM(A1:A10)
```

### Row/Column Operations
```bash
agent-do excel insert row <n> [count]   # Insert row(s)
agent-do excel insert col <letter> [n]  # Insert column(s)
agent-do excel delete row <n> [count]   # Delete row(s)
agent-do excel delete col <letter> [n]  # Delete column(s)
agent-do excel autofit col <letter>     # Auto-fit column width
```

### Finding & Filtering
```bash
agent-do excel find <text>           # Find text, return cell refs
agent-do excel find <text> --regex   # Regex search
agent-do excel find <text> --col B   # Search in column only
agent-do excel replace <old> <new>   # Replace all occurrences
agent-do excel filter <col> <op> <val>  # Filter: filter B ">" 100
agent-do excel filter clear          # Clear all filters
agent-do excel sort <col> [asc|desc] # Sort by column
```

### Formatting
```bash
agent-do excel format <range> --bold    # Bold text
agent-do excel format <range> --bg <hex>  # Background color
agent-do excel format <range> --number <fmt>  # Number format: #,##0.00
agent-do excel merge <range>            # Merge cells
```

### Quick Calculations
```bash
agent-do excel sum <range>           # =SUM(range)
agent-do excel avg <range>           # =AVERAGE(range)
agent-do excel count <range>         # =COUNT(range)
agent-do excel calc                  # Recalculate all formulas
```

### Example: Update Inventory Report
```bash
# 1. Open and explore
agent-do excel open inventory.xlsx
agent-do excel snapshot --headers
# → Headers: SKU, Name, Quantity, Price, Total

# 2. Find specific item
agent-do excel find "SKU-12345"
# → {"cell": "A42", "value": "SKU-12345"}

# 3. Update quantity and add formula
agent-do excel set C42 150
agent-do excel formula E42 "=C42*D42"

# 4. Add totals row
agent-do excel formula C100 "=SUM(C2:C99)"
agent-do excel formula E100 "=SUM(E2:E99)"
agent-do excel format A100:E100 --bold

# 5. Save
agent-do excel save
```

### Example: Create Report From Scratch
```bash
# 1. Create new workbook
agent-do excel new monthly_report.xlsx

# 2. Set up headers
agent-do excel set A1:D1 '["Metric","Jan","Feb","Mar"]'
agent-do excel set A2:A5 '["Revenue","Costs","Profit","Margin"]'

# 3. Format headers
agent-do excel format A1:D1 --bold --bg "#4472C4"
agent-do excel format A2:A5 --bold

# 4. Add formulas
agent-do excel formula B4 "=B2-B3"
agent-do excel formula B5 "=B4/B2"
agent-do excel format B5:D5 --number "0.0%"

# 5. Save
agent-do excel save
```

### Common Mistakes
- **DON'T** write Python with openpyxl - use agent-do excel
- **DON'T** forget to save after changes
- **DO** snapshot first to understand structure
- **DO** use JSON arrays for setting multiple cells: `'[["A","B"],["C","D"]]'`

---

## agent-do manna (Issue Tracking)

Git-backed issue tracking designed for AI agents. Claims prevent conflicts.

### Core Workflow Pattern
```bash
agent-do manna init                  # 1. Initialize in project
agent-do manna create "Fix bug" "Details"  # 2. Create issues
agent-do manna list                  # 3. See all issues
agent-do manna claim mn-abc123       # 4. Claim to work on
# ... do work ...
agent-do manna done mn-abc123        # 5. Mark complete
```

### Initialization
```bash
agent-do manna init                  # Initialize .manna/ directory
agent-do manna status                # Show session and claimed issues
```

### Issue Lifecycle
```bash
agent-do manna create <title> [desc] # Create new issue → returns ID (mn-abc123)
agent-do manna claim <id>            # Claim issue (sets to in_progress)
agent-do manna done <id>             # Mark as completed
agent-do manna abandon <id>          # Release without completing (back to open)
```

### Dependencies
```bash
agent-do manna block <id> <blocker_id>   # Add blocker (sets to blocked)
agent-do manna unblock <id> <blocker_id> # Remove blocker
```

### Querying
```bash
agent-do manna list                  # All issues
agent-do manna list --status open    # Filter by status
agent-do manna list --status in_progress
agent-do manna list --status blocked
agent-do manna list --status done
agent-do manna show <id>             # Full issue details
```

### Context Generation (for AI prompts)
```bash
agent-do manna context               # Generate context blob (default: 8000 tokens)
agent-do manna context --max-tokens 4000  # Limit size
```

### Example: Multi-Issue Workflow
```bash
# 1. Initialize and create issues
agent-do manna init
agent-do manna create "Implement auth" "Add JWT-based authentication"
# → id: mn-a1b2c3
agent-do manna create "Add login page" "Frontend login form"
# → id: mn-d4e5f6
agent-do manna create "Write auth tests" "Unit tests for auth"
# → id: mn-g7h8i9

# 2. Set up dependencies
agent-do manna block mn-d4e5f6 mn-a1b2c3  # Login page blocked by auth
agent-do manna block mn-g7h8i9 mn-a1b2c3  # Tests blocked by auth

# 3. Work on auth first
agent-do manna claim mn-a1b2c3
# ... implement auth ...
agent-do manna done mn-a1b2c3
# → mn-d4e5f6 and mn-g7h8i9 automatically unblocked

# 4. Continue with login page
agent-do manna list --status open
agent-do manna claim mn-d4e5f6
# ... implement login ...
agent-do manna done mn-d4e5f6
```

### Example: Generate Context for AI
```bash
# Get current state for AI prompt injection
agent-do manna context --max-tokens 2000
# → Returns YAML with:
#   - Open issues (prioritized)
#   - In-progress issues (what's being worked on)
#   - Blocked issues (and what's blocking them)
```

### Issue Statuses
| Status | Meaning |
|--------|---------|
| `open` | Ready to work on |
| `in_progress` | Claimed by a session |
| `blocked` | Waiting on dependencies |
| `done` | Completed |

### Common Mistakes
- **DON'T** create custom JSON files for tracking - use manna
- **DON'T** forget to claim before working (prevents conflicts)
- **DO** use block/unblock for dependencies
- **DO** generate context for AI prompt injection

---

## Development Patterns

### Always Load Index First
```bash
# At start of any automation task:
cat ~/.factory/agent-do-index.yaml
# Then use the appropriate tool
```

### The Universal Pattern
All agent-do tools follow the same pattern:

```
1. CONNECT/OPEN   → Establish session
2. SNAPSHOT       → Understand current state  
3. INTERACT       → Read/write/click/type
4. VERIFY         → Confirm changes worked
5. SAVE/CLOSE     → Clean up
```

### Tool Selection Guide

| Need To... | Use Tool | Not |
|------------|----------|-----|
| Automate browser | `agent-do browse` | Playwright scripts |
| Control iOS Simulator | `agent-do ios` | xcrun simctl |
| Query database | `agent-do db` | Python + psycopg2 |
| Edit spreadsheet | `agent-do excel` | Python + openpyxl |
| Track issues | `agent-do manna` | Custom JSON files |
| Detect objects in images | `agent-do vision` | Python + YOLO |
| Control macOS apps | `agent-do gui` | AppleScript |
| Automate terminal apps | `agent-do tui` | expect scripts |

---

## Resources

- **Tool index:** `~/.factory/agent-do-index.yaml`
- **Full catalog:** `~/.factory/agent-do-catalog.yaml`
- **Tool help:** `agent-do <tool> --help`
- **List all tools:** `agent-do --list`
