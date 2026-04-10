# agent-macos v2 Specification

> Desktop GUI automation with semantic element refs - see and control native apps like a human.

## Philosophy

**The Problem:** Existing GUI automation tools are either:
1. **Coordinate-based** (pyautogui) - Fragile, breaks on resolution/layout changes
2. **Image-based** (Sikuli) - Slow, high maintenance, can't read text
3. **Script-only** (AppleScript) - No visual feedback, hard to debug

**The Solution:** Combine accessibility APIs with the snapshot/@ref pattern:
1. **Snapshot** the UI → get semantic elements with @refs
2. **Interact** by @ref → AI doesn't need to know coordinates
3. **Vision fallback** → when accessibility fails, use OCR/detection

```
┌─────────────────────────────────────────────────────────────┐
│                       agent-macos                              │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Accessibility APIs (fast, semantic)               │
│  └─ macOS: AXUIElement via pyobjc                           │
│     - Full element tree with roles, labels, values          │
│     - Actions (press, increment, showMenu)                  │
│     - Attributes (enabled, focused, position, size)         │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Vision Fallback (for opaque/custom UI)            │
│  └─ OCR for text extraction (agent-vision)                  │
│  └─ Template matching for icons                             │
│  └─ YOLO for generic UI element detection                   │
├─────────────────────────────────────────────────────────────┤
│  Output: Unified @refs regardless of detection method       │
└─────────────────────────────────────────────────────────────┘
```

## Core Concepts

### Element Refs (@gN)
Every UI element gets a ref like `@g1`, `@g2`, etc. Refs are:
- Stable within a snapshot
- Invalidated after UI changes (re-snapshot needed)
- Prefixed with `g` to distinguish from browser refs (`@e`)

### Element Tree
macOS accessibility provides a tree:
```
Application (Finder)
└── Window (Documents)
    ├── Toolbar (@g1)
    │   ├── Button "Back" (@g2)
    │   ├── Button "Forward" (@g3)
    │   └── Button "View" (@g4)
    ├── SplitGroup (@g5)
    │   ├── ScrollArea - Sidebar (@g6)
    │   │   └── Outline (@g7)
    │   │       ├── Row "Favorites" (@g8)
    │   │       └── Row "Locations" (@g9)
    │   └── ScrollArea - Content (@g10)
    │       └── List (@g11)
    │           ├── Row "file1.txt" (@g12)
    │           └── Row "file2.pdf" (@g13)
    └── Toolbar - bottom (@g14)
        └── StaticText "2 items" (@g15)
```

### Session State
Like other agent-do tools, agent-macos maintains session state:
- Active application
- Last snapshot (for ref resolution)
- Interaction history

## Commands

### Application Management

```bash
# List running applications
agent-macos apps
# → {"apps": ["Finder", "Safari", "VS Code", ...], "frontmost": "Finder"}

# Open application
agent-macos open "Calculator"
agent-macos open "com.apple.calculator"  # By bundle ID

# Focus/activate application
agent-macos focus "Safari"

# Quit application
agent-macos quit "Preview"
agent-macos quit "Preview" --force  # Force quit

# Get frontmost app
agent-macos frontmost
# → {"app": "Finder", "pid": 12345, "bundle": "com.apple.finder"}
```

### Window Management

```bash
# List windows for app (or all)
agent-macos windows "Safari"
agent-macos windows --all

# Focus specific window
agent-macos window focus "Safari" --title "Downloads"
agent-macos window focus "Safari" --index 1

# Window actions
agent-macos window minimize "Finder"
agent-macos window maximize "Finder"       # Zoom button
agent-macos window fullscreen "Safari"     # Enter fullscreen
agent-macos window close "Preview"

# Window positioning
agent-macos window move "Finder" 0 0           # Move to x,y
agent-macos window resize "Finder" 800 600     # Set size
agent-macos window tile "Finder" left          # Tile left half
agent-macos window tile "Safari" right         # Tile right half
agent-macos window center "Calculator"

# Get window info
agent-macos window info "Finder"
# → {"title": "Documents", "position": [100, 100], "size": [800, 600], "minimized": false}
```

### Snapshot (Core Pattern)

```bash
# Snapshot frontmost app
agent-macos snapshot
# → Full element tree with @refs

# Snapshot specific app
agent-macos snapshot "Finder"

# Snapshot options
agent-macos snapshot -i              # Interactive elements only (buttons, fields, etc.)
agent-macos snapshot -d 3            # Limit depth to 3
agent-macos snapshot --window 1      # Specific window
agent-macos snapshot --focused       # Only focused element subtree
agent-macos snapshot --visible       # Only visible elements

# Output formats
agent-macos snapshot --json          # Full JSON (default)
agent-macos snapshot --tree          # ASCII tree view
agent-macos snapshot --csv           # Flat CSV of elements
```

**Snapshot JSON Output:**
```json
{
  "app": "Finder",
  "bundle": "com.apple.finder",
  "pid": 12345,
  "window": {
    "title": "Documents",
    "position": [100, 100],
    "size": [800, 600]
  },
  "elements": [
    {
      "ref": "@g1",
      "role": "toolbar",
      "label": "Toolbar",
      "children": ["@g2", "@g3", "@g4"]
    },
    {
      "ref": "@g2",
      "role": "button",
      "label": "Back",
      "enabled": true,
      "position": [110, 110],
      "size": [30, 30],
      "actions": ["press"]
    },
    {
      "ref": "@g12",
      "role": "row",
      "label": "file1.txt",
      "value": null,
      "selected": false,
      "position": [200, 300],
      "size": [400, 22]
    }
  ],
  "focused": "@g11",
  "timestamp": "2024-01-29T10:30:00Z"
}
```

### Element Interaction

```bash
# Click element
agent-macos click @g2                # Single click
agent-macos dblclick @g12            # Double click (open file)
agent-macos rightclick @g12          # Context menu
agent-macos click @g4 --hold 1.0     # Click and hold

# Type into element (or focused)
agent-macos type @g5 "search query"  # Type into specific element
agent-macos type "hello"             # Type into focused element

# Clear and type
agent-macos fill @g5 "new text"      # Clear first, then type

# Press keys
agent-macos press Enter
agent-macos press Tab
agent-macos press Escape
agent-macos press "Cmd+S"            # Keyboard shortcut
agent-macos press "Cmd+Shift+4"      # Multi-modifier

# Key sequences
agent-macos keys "Cmd+A" "Cmd+C"     # Select all, copy

# Element-specific actions
agent-macos action @g5 "showMenu"    # Trigger AX action
agent-macos action @g7 "expand"      # Expand disclosure
agent-macos action @g7 "collapse"

# Drag and drop
agent-macos drag @g12 to @g8         # Drag file to folder
agent-macos drag @g12 to 500 300     # Drag to coordinates

# Scroll
agent-macos scroll @g10 down 3       # Scroll down 3 units
agent-macos scroll @g10 up
agent-macos scroll @g10 to @g20      # Scroll until element visible

# Checkbox/radio
agent-macos check @g15               # Check checkbox
agent-macos uncheck @g15
agent-macos toggle @g15

# Slider/stepper
agent-macos set @g16 75              # Set slider to 75
agent-macos increment @g17           # Increment stepper
agent-macos decrement @g17

# Select (dropdown, list, table)
agent-macos select @g18 "Option 2"   # Select by label
agent-macos select @g18 --index 2    # Select by index
```

### Reading Element Data

```bash
# Get element attribute
agent-macos get @g12 label           # Get label/title
agent-macos get @g5 value            # Get current value
agent-macos get @g15 checked         # Get checkbox state
agent-macos get @g16 value           # Get slider value
agent-macos get @g12 position        # Get position [x, y]
agent-macos get @g12 size            # Get size [w, h]
agent-macos get @g2 enabled          # Is enabled?
agent-macos get @g5 focused          # Is focused?

# Get all attributes
agent-macos inspect @g12
# → {"ref": "@g12", "role": "row", "label": "file1.txt", "position": [...], ...}

# Find elements
agent-macos find --role button                    # All buttons
agent-macos find --label "Save"                   # By label
agent-macos find --role textfield --empty         # Empty text fields
agent-macos find --contains "report"              # Label contains text

# Count elements
agent-macos count --role button
agent-macos count --role row --parent @g11
```

### Menu Interaction

```bash
# Click menu item
agent-macos menu "File" "New Window"
agent-macos menu "File" "Open Recent" "file.txt"  # Submenu

# Get menu structure
agent-macos menubar
# → {"menus": ["Apple", "Finder", "File", "Edit", "View", ...]}

agent-macos menubar "File"
# → {"items": ["New Finder Window", "New Folder", "---", "Open", ...]}

# Menu bar item by index
agent-macos menubar --index 3 "New Window"
```

### Dialog Handling

```bash
# Detect dialogs
agent-macos dialog detect
# → {"type": "sheet", "title": "Save changes?", "buttons": ["Don't Save", "Cancel", "Save"]}

# Click dialog button
agent-macos dialog click "Save"
agent-macos dialog click --default              # Click default button
agent-macos dialog click --cancel               # Click cancel button

# Handle file dialogs
agent-macos filepicker detect
# → {"type": "save", "filename": "Untitled.txt", "location": "Documents"}

agent-macos filepicker navigate ~/Downloads
agent-macos filepicker filename "report.pdf"
agent-macos filepicker select "file.txt"        # In open dialog
agent-macos filepicker save                     # Click Save
agent-macos filepicker cancel
```

### Clipboard

```bash
# Get clipboard
agent-macos clipboard
# → {"text": "copied text", "types": ["public.utf8-plain-text"]}

# Set clipboard
agent-macos clipboard "text to copy"
agent-macos clipboard --file /path/to/file      # Copy file reference

# Copy from element
agent-macos copy @g12                           # Copy element content
```

### Screenshots

```bash
# Screenshot app window
agent-macos screenshot "Finder"
agent-macos screenshot "Finder" ~/Desktop/finder.png

# Screenshot element
agent-macos screenshot @g10
agent-macos screenshot @g10 --highlight         # With highlight box

# Screenshot with annotation
agent-macos screenshot --annotate               # Show all @refs on image
```

### Waiting

```bash
# Wait for element
agent-macos wait @g5                            # Wait for element to exist
agent-macos wait @g5 --enabled                  # Wait until enabled
agent-macos wait @g5 --visible                  # Wait until visible
agent-macos wait --label "Complete"             # Wait for element with label
agent-macos wait --gone @g5                     # Wait until element removed

# Wait for window/dialog
agent-macos wait --window "Preferences"         # Wait for window
agent-macos wait --dialog                       # Wait for any dialog
agent-macos wait --dialog "Save changes?"       # Wait for specific dialog

# Timeouts
agent-macos wait @g5 --timeout 10               # 10 second timeout (default: 30)
```

### Notifications

```bash
# List notifications
agent-macos notifications
# → [{"app": "Messages", "title": "New Message", "body": "Hey!"}]

# Dismiss notifications
agent-macos notifications dismiss --all
agent-macos notifications dismiss --app "Messages"

# Click notification
agent-macos notifications click 0               # Click first notification
```

### Vision Fallback

When accessibility APIs don't expose elements (games, Electron apps, custom UI):

```bash
# Force vision-based snapshot
agent-macos snapshot --vision
# Uses agent-vision to OCR text and detect UI elements

# Find by visual appearance
agent-macos vision find "red button"
agent-macos vision find "Save icon"

# Click by visual description
agent-macos vision click "the submit button at bottom right"

# OCR region
agent-macos vision ocr @g10                     # OCR within element bounds
agent-macos vision ocr --region 100,100,200,50  # OCR specific region
```

### Session Management

```bash
# Status
agent-macos status
# → {"app": "Finder", "window": "Documents", "elements": 47, "last_snapshot": "..."}

# Clear session
agent-macos reset
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Application not found or not running |
| 2 | Window not found |
| 3 | Element not found (invalid @ref or no match) |
| 4 | Action failed (element disabled, etc.) |
| 5 | Timeout waiting for element/window |
| 6 | Accessibility permission denied |
| 7 | Vision fallback failed |
| 8 | Unknown error |

## Accessibility Permissions

agent-macos requires accessibility permissions on macOS:
- System Settings → Privacy & Security → Accessibility
- Add Terminal (or the running app) to allowed apps

First run will prompt. Can check programmatically:
```bash
agent-macos --check-permissions
# → {"accessibility": true, "screen_recording": true}
```

## Example Workflows

### 1. Automate Save Dialog

```bash
# User is in TextEdit with unsaved document
agent-macos focus "TextEdit"
agent-macos press "Cmd+S"
agent-macos wait --dialog
agent-macos filepicker filename "notes.txt"
agent-macos filepicker navigate ~/Documents
agent-macos filepicker save
```

### 2. Extract Data from Native App

```bash
# Get contacts from Contacts.app
agent-macos open "Contacts"
agent-macos wait --window "Contacts"
agent-macos snapshot -i
# Find the contact list
agent-macos click @g8                    # First contact
agent-macos snapshot --focused
# Read contact details
agent-macos get @g15 value               # Phone number field
```

### 3. System Settings Automation

```bash
agent-macos open "System Settings"
agent-macos wait --window "System Settings"
agent-macos snapshot -i

# Navigate to Displays
agent-macos find --label "Displays"      # Find in sidebar
agent-macos click @g12                   # Click Displays

agent-macos wait --stable
agent-macos snapshot -i

# Change resolution
agent-macos click @g18                   # Resolution dropdown
agent-macos select @g18 "1920 x 1080"
```

### 4. Cross-App Workflow

```bash
# Copy table from Numbers to Pages
agent-macos focus "Numbers"
agent-macos snapshot -i
agent-macos click @g25                   # Select table
agent-macos press "Cmd+C"

agent-macos focus "Pages"
agent-macos snapshot -i
agent-macos click @g10                   # Click in document
agent-macos press "Cmd+V"
agent-macos press "Cmd+S"
```

### 5. Handle Unknown App with Vision

```bash
# Electron app with poor accessibility
agent-macos focus "Slack"
agent-macos snapshot --vision            # Use vision fallback

# Elements detected via OCR/vision
agent-macos vision click "message field"
agent-macos type "Hello team!"
agent-macos press Enter
```

## Implementation Notes

### macOS Accessibility API (pyobjc)

```python
from ApplicationServices import (
    AXUIElementCreateApplication,
    AXUIElementCopyAttributeValue,
    AXUIElementPerformAction,
    AXUIElementSetAttributeValue,
)
import Quartz

# Get running apps
workspace = NSWorkspace.sharedWorkspace()
apps = workspace.runningApplications()

# Create AX element for app
app_ref = AXUIElementCreateApplication(pid)

# Get attribute
err, value = AXUIElementCopyAttributeValue(element, "AXTitle", None)

# Perform action
AXUIElementPerformAction(element, "AXPress")

# Get children
err, children = AXUIElementCopyAttributeValue(element, "AXChildren", None)
```

### Key Dependencies

```
pyobjc-core
pyobjc-framework-Cocoa
pyobjc-framework-Quartz
pyobjc-framework-ApplicationServices
```

### Vision Integration

When accessibility fails:
1. Take screenshot of target region
2. Call agent-vision for OCR/detection
3. Map detected elements to @refs
4. Use coordinate-based interaction as fallback

## Future Enhancements

1. **Record & Replay**: Record user interactions, generate script
2. **Cross-platform**: Windows (UI Automation), Linux (AT-SPI)
3. **Element diff**: Compare snapshots, detect UI changes
4. **Fuzzy matching**: Find elements by approximate label
5. **Macro library**: Common workflows (save file, open URL, etc.)
