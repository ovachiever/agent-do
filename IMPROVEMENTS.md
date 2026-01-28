# agent-browse Improvement Spec

Analysis of AI session failure modes and proposed fixes.

---

## 1. Browser State & Recovery

### Problem
AI encountered "Browser not launched" errors when daemon was running but browser instance died. Recovery required multiple trial-and-error attempts.

**Failure sequence:**
```
session load ninety-test → "Browser not launched"
pkill chromium → didn't help
agent-do browse launch → "Unknown command: launch"
close → timed out
open https://google.com → finally worked
```

### Proposed Fix
```bash
# New commands
agent-do browse restart          # Kill browser, restart clean
agent-do browse recover          # Smart recovery (try relaunch, restore session)
agent-do browse health           # Full health check with actionable suggestions

# Better status output
agent-do browse status
# Current: "Daemon: running"
# Proposed:
# {
#   "daemon": {"running": true, "pid": 82817},
#   "browser": {"launched": false, "reason": "crashed"},  # NEW
#   "suggestion": "Run 'agent-do browse restart' to recover"
# }
```

### Auto-recovery
- `session load` should auto-launch browser if needed
- `open <url>` should auto-recover from crashed state
- Failed commands should suggest recovery actions in error JSON

---

## 2. DNS/Network Recovery

### Problem
Browser had stale DNS cache, couldn't resolve `eos.ninety.io` even when `dig` resolved it fine.

**Failure sequence:**
```
open https://eos.ninety.io → net::ERR_NAME_NOT_RESOLVED
curl → also failed
dig → resolved fine (3.166.118.102)
sleep 3 + retry → still failed
pkill chromium → eventually worked after browser restart
```

### Proposed Fix
```bash
# Network recovery commands
agent-do browse network flush-dns      # Clear browser DNS cache
agent-do browse network reconnect      # Force new connection context

# Auto-retry with fresh context on DNS failures
# Current: exits with error
# Proposed: auto-restart browser context and retry (once) on DNS failures
```

---

## 3. Ref Collisions (Critical)

### Problem
`@e26` matched 9 elements, forcing AI to use raw Playwright selectors.

**Failure sequence:**
```
snapshot -i → shows @e26 as combobox
click @e26 → "matched 9 elements"
# AI had to discover workaround:
click 'role=combobox >> nth=0' → worked
```

### Root Cause
Refs are assigned based on element position in tree traversal, not unique identity. When elements have same role/attributes, refs collide.

### Proposed Fix

**Option A: Guarantee unique refs**
- Append incrementing suffix when collision detected: `@e26`, `@e26-2`, `@e26-3`
- More complex but maintains clean ref syntax

**Option B: Support nth selector on refs**
```bash
agent-do browse click '@e26 >> nth=0'   # First match
agent-do browse click '@e26[0]'          # Array-style syntax
```

**Option C: Better deduplication in snapshot**
- Include more attributes in ref identity (name, value, aria-label)
- Refs should be stable across repeated snapshots of same page state

**Recommended: Option A + better error message**
```json
{
  "error": "ref_collision",
  "ref": "@e26",
  "matches": 9,
  "suggestions": [
    "Use '@e26 >> nth=0' for first match",
    "Use 'role=combobox >> nth=0' as alternative",
    "Run 'snapshot -i' for detailed element info"
  ]
}
```

---

## 4. Stale Ref Detection

### Problem
AI kept trying to use refs from previous page state after navigation.

### Proposed Fix
```bash
# Track ref generation ID
agent-do browse snapshot -i
# Output includes: "ref_generation": "abc123"

# Click with stale ref warns
agent-do browse click @e7
# Warning: "Refs are from 45 seconds ago. Re-snapshot recommended."

# Option to auto-refresh
agent-do browse click @e7 --refresh   # Auto-snapshot before click
```

---

## 5. Command Discovery & Error Messages

### Problem
AI tried non-existent commands (`launch`) and invalid syntax (`wait --load networkidle`).

**Failure sequence:**
```
agent-do browse launch → "Unknown command"
# AI had to grep through --help
wait --load networkidle → validation error (was fixed in previous session)
```

### Proposed Fix
**Fuzzy command matching with suggestions:**
```bash
agent-do browse launch
# Error: Unknown command: launch
# Did you mean:
#   open <url>     - Navigate (launches browser if needed)
#   restart        - Kill and restart browser
#   status         - Check browser state
```

**Better validation errors:**
```bash
agent-do browse wait --load networkidle
# Error: Invalid option combination
# Use one of:
#   wait --stable           (networkidle + DOM stable)
#   wait --load             (load event only)
#   wait 2000               (milliseconds)
```

---

## 6. Dropdown/Modal Scoping

### Problem
When querying options in dropdown, got unrelated elements (issue checkboxes mixed with team options).

### Proposed Fix
```bash
# Scoped queries within last clicked element
agent-do browse click '@e26'
agent-do browse snapshot --scope=active   # Only elements in open dropdown/modal

# Or explicit scope
agent-do browse snapshot --scope='[role=listbox]'

# Better option detection
agent-do browse get options             # Auto-detect open dropdown, list its options
agent-do browse get options @e26        # Get options for specific combobox
```

---

## 7. Timeout Handling

### Problem
`close` command timed out after 30 seconds, but browser was actually responsive.

### Proposed Fix
```bash
# Graceful timeout with partial success
agent-do browse close --timeout 5
# Output: {"partial": true, "browser_closed": true, "cleanup_pending": true}

# Async operations for long-running commands
agent-do browse close --async
# Returns immediately, cleanup continues in background
```

---

## 8. Streamlined Auth Flow

### Problem
Login required 4 separate commands with conditional logic.

**Current flow:**
```bash
auth check-creds domain   # Check
# if not ready → ask user → auth store-creds
auth login domain --submit
wait --stable
get url                   # Verify
```

### Proposed Fix
```bash
# Single smart command
agent-do browse auth login <domain> --auto
# 1. Check creds (env → keychain)
# 2. If missing: exit 2 with action_required
# 3. If present: navigate to login, fill, submit, wait, verify
# 4. Return success/failure with final URL

# Output on success:
{
  "success": true,
  "logged_in": true,
  "url": "https://eos.ninety.io/home",
  "session_saved": "ninety-io"
}

# Output on missing creds:
{
  "success": false,
  "action_required": "STORE_CREDENTIALS",
  "domain": "ninety.io",
  "command": "auth store-creds ninety.io <email> <password>"
}
```

---

## 9. Session Auto-Recovery

### Problem
`session load` failed because browser wasn't launched.

### Proposed Fix
```bash
# session load should auto-handle browser state
agent-do browse session load mysite
# 1. Check if browser running → launch if not
# 2. Load cookies/storage
# 3. Navigate to saved URL
# 4. Verify page loaded
# 5. Return success with current state
```

---

## 10. AI-Friendly Error Codes

### Current Exit Codes
- 0: Success
- 1: General error
- 2: Action required (credentials)

### Proposed Expanded Codes
| Code | Meaning | AI Action |
|------|---------|-----------|
| 0 | Success | Continue |
| 1 | General error | Debug/retry |
| 2 | User input needed | Ask user |
| 3 | Browser crashed | Run `restart` |
| 4 | Network error | Run `network reconnect` |
| 5 | Ref collision | Re-snapshot or use nth selector |
| 6 | Stale refs | Re-snapshot |
| 7 | Element not found | Re-snapshot, try different selector |
| 8 | Timeout | Increase timeout or check page state |

---

## Implementation Priority

| Priority | Issue | Effort | Impact | Status |
|----------|-------|--------|--------|--------|
| P0 | Ref collisions (#3) | Medium | High | ✅ Done - nth selector suggestion |
| P0 | Browser recovery (#1) | Medium | High | ✅ Done - restart command |
| P1 | Better error messages (#5) | Low | High | ✅ Done - fuzzy suggestions |
| P1 | Session auto-launch (#9) | Low | Medium | ✅ Done |
| P1 | Streamlined auth (#8) | Medium | Medium | ✅ Done - --auto flag |
| P2 | DNS recovery (#2) | Low | Medium | ✅ Done - network reconnect |
| P2 | Stale ref detection (#4) | Medium | Medium | ✅ Done - warns when >30s old |
| P2 | Dropdown scoping (#6) | Medium | Medium | ✅ Done - get options |
| P3 | Timeout handling (#7) | Low | Low | ✅ Done - --timeout flag |
| P3 | Expanded exit codes (#10) | Low | Low | ✅ Done - codes 0-8 |

---

## Implemented Quick Wins

1. ✅ **`restart` command** - Kill browser, restart daemon connection
2. ✅ **Better ref collision error** - Suggests `@ref >> nth=0` or `role=X >> nth=N`
3. ✅ **Session load auto-launch** - Launch browser before restoring session
4. ✅ **Fuzzy command suggestions** - Prefix matching on unknown commands
5. ✅ **JSON status output** - Returns daemon/browser state with suggestion
6. ✅ **`auth login --auto`** - Full login flow in one command
7. ✅ **`network reconnect`** - Force new browser context
8. ✅ **`get options`** - Query dropdown/select options
9. ✅ **Stale ref warnings** - Errors include ref age when >30s
10. ✅ **Exit codes 0-8** - Specific codes for crash/network/collision/timeout
11. ✅ **`--timeout` flag** - Command-level timeout control
