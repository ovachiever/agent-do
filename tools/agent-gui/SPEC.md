# agent-gui v2 Specification

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
│                       agent-gui                              │
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
Like other agent-do tools, agent-gui maintains session state:
- Active application
- Last snapshot (for ref resolution)
- Interaction history

## Commands

### Application Management

```bash
# List running applications
agent-gui apps
# → {"apps": ["Finder", "Safari", "VS Code", ...], "frontmost": "Finder"}

# Open application
agent-gui open "Calculator"
agent-gui open "com.apple.calculator"  # By bundle ID

# Focus/activate application
agent-gui focus "Safari"

# Quit application
agent-gui quit "Preview"
agent-gui quit "Preview" --force  # Force quit

# Get frontmost app
agent-gui frontmost
# → {"app": "Finder", "pid": 12345, "bundle": "com.apple.finder"}
```

### Window Management

```bash
# List windows for app (or all)
agent-gui windows "Safari"
agent-gui windows --all

# Focus specific window
agent-gui window focus "Safari" --title "Downloads"
agent-gui window focus "Safari" --index 1

# Window actions
agent-gui window minimize "Finder"
agent-gui window maximize "Finder"       # Zoom button
agent-gui window fullscreen "Safari"     # Enter fullscreen
agent-gui window close "Preview"

# Window positioning
agent-gui window move "Finder" 0 0           # Move to x,y
agent-gui window resize "Finder" 800 600     # Set size
agent-gui window tile "Finder" left          # Tile left half
agent-gui window tile "Safari" right         # Tile right half
agent-gui window center "Calculator"

# Get window info
agent-gui window info "Finder"
# → {"title": "Documents", "position": [100, 100], "size": [800, 600], "minimized": false}
```

### Snapshot (Core Pattern)

```bash
# Snapshot frontmost app
agent-gui snapshot
# → Full element tree with @refs

# Snapshot specific app
agent-gui snapshot "Finder"

# Snapshot options
agent-gui snapshot -i              # Interactive elements only (buttons, fields, etc.)
agent-gui snapshot -d 3            # Limit depth to 3
agent-gui snapshot --window 1      # Specific window
agent-gui snapshot --focused       # Only focused element subtree
agent-gui snapshot --visible       # Only visible elements

# Output formats
agent-gui snapshot --json          # Full JSON (default)
agent-gui snapshot --tree          # ASCII tree view
agent-gui snapshot --csv           # Flat CSV of elements
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
agent-gui click @g2                # Single click
agent-gui dblclick @g12            # Double click (open file)
agent-gui rightclick @g12          # Context menu
agent-gui click @g4 --hold 1.0     # Click and hold

# Type into element (or focused)
agent-gui type @g5 "search query"  # Type into specific element
agent-gui type "hello"             # Type into focused element

# Clear and type
agent-gui fill @g5 "new text"      # Clear first, then type

# Press keys
agent-gui press Enter
agent-gui press Tab
agent-gui press Escape
agent-gui press "Cmd+S"            # Keyboard shortcut
agent-gui press "Cmd+Shift+4"      # Multi-modifier

# Key sequences
agent-gui keys "Cmd+A" "Cmd+C"     # Select all, copy

# Element-specific actions
agent-gui action @g5 "showMenu"    # Trigger AX action
agent-gui action @g7 "expand"      # Expand disclosure
agent-gui action @g7 "collapse"

# Drag and drop
agent-gui drag @g12 to @g8         # Drag file to folder
agent-gui drag @g12 to 500 300     # Drag to coordinates

# Scroll
agent-gui scroll @g10 down 3       # Scroll down 3 units
agent-gui scroll @g10 up
agent-gui scroll @g10 to @g20      # Scroll until element visible

# Checkbox/radio
agent-gui check @g15               # Check checkbox
agent-gui uncheck @g15
agent-gui toggle @g15

# Slider/stepper
agent-gui set @g16 75              # Set slider to 75
agent-gui increment @g17           # Increment stepper
agent-gui decrement @g17

# Select (dropdown, list, table)
agent-gui select @g18 "Option 2"   # Select by label
agent-gui select @g18 --index 2    # Select by index
```

### Reading Element Data

```bash
# Get element attribute
agent-gui get @g12 label           # Get label/title
agent-gui get @g5 value            # Get current value
agent-gui get @g15 checked         # Get checkbox state
agent-gui get @g16 value           # Get slider value
agent-gui get @g12 position        # Get position [x, y]
agent-gui get @g12 size            # Get size [w, h]
agent-gui get @g2 enabled          # Is enabled?
agent-gui get @g5 focused          # Is focused?

# Get all attributes
agent-gui inspect @g12
# → {"ref": "@g12", "role": "row", "label": "file1.txt", "position": [...], ...}

# Find elements
agent-gui find --role button                    # All buttons
agent-gui find --label "Save"                   # By label
agent-gui find --role textfield --empty         # Empty text fields
agent-gui find --contains "report"              # Label contains text

# Count elements
agent-gui count --role button
agent-gui count --role row --parent @g11
```

### Menu Interaction

```bash
# Click menu item
agent-gui menu "File" "New Window"
agent-gui menu "File" "Open Recent" "file.txt"  # Submenu

# Get menu structure
agent-gui menubar
# → {"menus": ["Apple", "Finder", "File", "Edit", "View", ...]}

agent-gui menubar "File"
# → {"items": ["New Finder Window", "New Folder", "---", "Open", ...]}

# Menu bar item by index
agent-gui menubar --index 3 "New Window"
```

### Dialog Handling

```bash
# Detect dialogs
agent-gui dialog detect
# → {"type": "sheet", "title": "Save changes?", "buttons": ["Don't Save", "Cancel", "Save"]}

# Click dialog button
agent-gui dialog click "Save"
agent-gui dialog click --default              # Click default button
agent-gui dialog click --cancel               # Click cancel button

# Handle file dialogs
agent-gui filepicker detect
# → {"type": "save", "filename": "Untitled.txt", "location": "Documents"}

agent-gui filepicker navigate ~/Downloads
agent-gui filepicker filename "report.pdf"
agent-gui filepicker select "file.txt"        # In open dialog
agent-gui filepicker save                     # Click Save
agent-gui filepicker cancel
```

### Clipboard

```bash
# Get clipboard
agent-gui clipboard
# → {"text": "copied text", "types": ["public.utf8-plain-text"]}

# Set clipboard
agent-gui clipboard "text to copy"
agent-gui clipboard --file /path/to/file      # Copy file reference

# Copy from element
agent-gui copy @g12                           # Copy element content
```

### Screenshots

```bash
# Screenshot app window
agent-gui screenshot "Finder"
agent-gui screenshot "Finder" ~/Desktop/finder.png

# Screenshot element
agent-gui screenshot @g10
agent-gui screenshot @g10 --highlight         # With highlight box

# Screenshot with annotation
agent-gui screenshot --annotate               # Show all @refs on image
```

### Waiting

```bash
# Wait for element
agent-gui wait @g5                            # Wait for element to exist
agent-gui wait @g5 --enabled                  # Wait until enabled
agent-gui wait @g5 --visible                  # Wait until visible
agent-gui wait --label "Complete"             # Wait for element with label
agent-gui wait --gone @g5                     # Wait until element removed

# Wait for window/dialog
agent-gui wait --window "Preferences"         # Wait for window
agent-gui wait --dialog                       # Wait for any dialog
agent-gui wait --dialog "Save changes?"       # Wait for specific dialog

# Timeouts
agent-gui wait @g5 --timeout 10               # 10 second timeout (default: 30)
```

### Notifications

```bash
# List notifications
agent-gui notifications
# → [{"app": "Messages", "title": "New Message", "body": "Hey!"}]

# Dismiss notifications
agent-gui notifications dismiss --all
agent-gui notifications dismiss --app "Messages"

# Click notification
agent-gui notifications click 0               # Click first notification
```

### Vision Fallback

When accessibility APIs don't expose elements (games, Electron apps, custom UI):

```bash
# Force vision-based snapshot
agent-gui snapshot --vision
# Uses agent-vision to OCR text and detect UI elements

# Find by visual appearance
agent-gui vision find "red button"
agent-gui vision find "Save icon"

# Click by visual description
agent-gui vision click "the submit button at bottom right"

# OCR region
agent-gui vision ocr @g10                     # OCR within element bounds
agent-gui vision ocr --region 100,100,200,50  # OCR specific region
```

### Session Management

```bash
# Status
agent-gui status
# → {"app": "Finder", "window": "Documents", "elements": 47, "last_snapshot": "..."}

# Clear session
agent-gui reset
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

agent-gui requires accessibility permissions on macOS:
- System Settings → Privacy & Security → Accessibility
- Add Terminal (or the running app) to allowed apps

First run will prompt. Can check programmatically:
```bash
agent-gui --check-permissions
# → {"accessibility": true, "screen_recording": true}
```

## Example Workflows

### 1. Automate Save Dialog

```bash
# User is in TextEdit with unsaved document
agent-gui focus "TextEdit"
agent-gui press "Cmd+S"
agent-gui wait --dialog
agent-gui filepicker filename "notes.txt"
agent-gui filepicker navigate ~/Documents
agent-gui filepicker save
```

### 2. Extract Data from Native App

```bash
# Get contacts from Contacts.app
agent-gui open "Contacts"
agent-gui wait --window "Contacts"
agent-gui snapshot -i
# Find the contact list
agent-gui click @g8                    # First contact
agent-gui snapshot --focused
# Read contact details
agent-gui get @g15 value               # Phone number field
```

### 3. System Settings Automation

```bash
agent-gui open "System Settings"
agent-gui wait --window "System Settings"
agent-gui snapshot -i

# Navigate to Displays
agent-gui find --label "Displays"      # Find in sidebar
agent-gui click @g12                   # Click Displays

agent-gui wait --stable
agent-gui snapshot -i

# Change resolution
agent-gui click @g18                   # Resolution dropdown
agent-gui select @g18 "1920 x 1080"
```

### 4. Cross-App Workflow

```bash
# Copy table from Numbers to Pages
agent-gui focus "Numbers"
agent-gui snapshot -i
agent-gui click @g25                   # Select table
agent-gui press "Cmd+C"

agent-gui focus "Pages"
agent-gui snapshot -i
agent-gui click @g10                   # Click in document
agent-gui press "Cmd+V"
agent-gui press "Cmd+S"
```

### 5. Handle Unknown App with Vision

```bash
# Electron app with poor accessibility
agent-gui focus "Slack"
agent-gui snapshot --vision            # Use vision fallback

# Elements detected via OCR/vision
agent-gui vision click "message field"
agent-gui type "Hello team!"
agent-gui press Enter
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
