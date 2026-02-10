# agent-screen: True Vision for macOS AI Agents

> Real-time screen perception across all displays at 24fps - see like a human, act like a human.

## The Problem

Current GUI automation approaches fail for modern apps:

| Approach | Limitation |
|----------|------------|
| **Accessibility APIs** | Electron apps (Slack, VS Code, Discord) expose almost nothing |
| **Coordinate-based** | Breaks on resolution/layout changes |
| **Image matching** | Slow, brittle, high maintenance |
| **Single display** | Most power users have multiple monitors |

**The solution**: A vision-first approach that captures all screens continuously, understands what's visible through OCR and ML, and provides a unified API for AI agents to query and interact with any application.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CAPTURE LAYER (24fps)                        │
├─────────────────────────────────────────────────────────────────┤
│  ScreenCaptureKit (macOS 12.3+)                                 │
│  ├─ Best API for continuous multi-monitor capture               │
│  ├─ Can capture at 60fps+, hardware accelerated                 │
│  ├─ Enumerate all displays: SCShareableContent.getDisplays()    │
│  └─ Exclude own window (don't capture the agent UI)             │
│                                                                  │
│  Alternatives:                                                   │
│  ├─ CGDisplayCreateImage (older, per-display)                   │
│  ├─ AVCaptureScreenInput (legacy)                               │
│  └─ screencapture CLI (slow, for snapshots only)                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   PERCEPTION LAYER (parallel)                    │
├─────────────────────────────────────────────────────────────────┤
│  FAST (<50ms) - Every frame:                                    │
│  ├─ Frame diff: only process changed regions                    │
│  ├─ Apple Vision OCR: VNRecognizeTextRequest (on-device)        │
│  └─ Cursor/focus tracking                                       │
│                                                                  │
│  MEDIUM (~100ms) - Every N frames:                              │
│  ├─ UI element detection (YOLO/custom model via Core ML)        │
│  ├─ Icon/button recognition                                     │
│  └─ Window boundary detection                                   │
│                                                                  │
│  SLOW (1-3s) - On demand:                                       │
│  ├─ Vision LLM (GPT-4V, Claude, Gemini)                        │
│  ├─ Complex scene understanding                                 │
│  └─ "Where should I click to send a message?"                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     STATE LAYER (continuous)                     │
├─────────────────────────────────────────────────────────────────┤
│  Screen Model:                                                   │
│  ├─ displays: [{id, bounds, scale, elements: [...]}]            │
│  ├─ focused_app, focused_window                                 │
│  ├─ elements: [{type, text, bounds, confidence, screen_id}]     │
│  ├─ cursor_position                                             │
│  └─ last_action, last_action_time, action_result                │
│                                                                  │
│  Multi-Monitor Coordinate System:                                │
│  ├─ Primary display at (0,0)                                    │
│  ├─ Other displays relative to primary                          │
│  └─ Unified coordinate space for all interactions               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ACTION LAYER (execute)                        │
├─────────────────────────────────────────────────────────────────┤
│  Input Synthesis:                                                │
│  ├─ CGEvent: mouse move, click, drag, scroll                    │
│  ├─ CGEvent: keyboard input, modifiers                          │
│  └─ Multi-monitor aware (post to correct display)               │
│                                                                  │
│  Hybrid Approach:                                                │
│  ├─ Accessibility first (if available) - most reliable          │
│  ├─ Vision + coordinates fallback (for Electron, games, etc.)   │
│  └─ Verify action effect (did UI change as expected?)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Perception Strategies

| Approach | Latency | Accuracy | Best For |
|----------|---------|----------|----------|
| **Accessibility APIs** | <10ms | 100% | Native apps with AX support |
| **Apple Vision OCR** | ~50ms | 95%+ | Any text on screen |
| **YOLO UI Detection** | ~100ms | 85-95% | Buttons, inputs, icons |
| **Vision LLM** | 1-3s | 90%+ | Complex/ambiguous UI |
| **Template Matching** | ~20ms | 99% (known) | Specific icons/images |
| **Frame Diff** | <5ms | 100% | Detecting changes |

---

## CLI Interface

### Daemon Control

```bash
# Start the vision daemon (captures all displays at 24fps)
agent-screen start
agent-screen start --fps 30           # Higher frame rate
agent-screen start --displays 1,2     # Specific displays only

# Stop the daemon
agent-screen stop

# Status
agent-screen status
# → {"running": true, "fps": 24, "displays": 5, "elements": 847, "uptime": "2h34m"}
```

### Display Information

```bash
# List all displays with bounds and scale
agent-screen displays
# → [
#     {"id": 1, "name": "Built-in", "bounds": [0, 0, 2560, 1440], "scale": 2, "primary": true},
#     {"id": 2, "name": "LG 27UK850", "bounds": [2560, -75, 1512, 950], "scale": 1},
#     ...
#   ]

# Get info about specific display
agent-screen display 2
```

### Element Queries

```bash
# Get all detected elements (text, buttons, inputs)
agent-screen elements
agent-screen elements --display 2     # On specific display
agent-screen elements --type button   # Filter by type
agent-screen elements --app Slack     # In specific app window

# Find element by text (fuzzy match)
agent-screen find "Send message"
agent-screen find "Erik Fritsch" --type text
# → {"text": "Erik Fritsch", "bounds": [3100, 200, 150, 24], "display": 2, "confidence": 0.97}

# What's at specific coordinates?
agent-screen at 3316 825
agent-screen at 3316 825 --display 2
# → {"type": "textfield", "text": "Message Erik Fritsch", "bounds": [3000, 800, 400, 50]}
```

### Actions

```bash
# Mouse actions (unified coordinate system)
agent-screen click 3316 825                    # Click at coordinates
agent-screen click --display 2 756 900         # Click on specific display
agent-screen click --text "Send"               # Click element containing text
agent-screen click --near "Message" --below    # Click below element with text
agent-screen dblclick 3316 825                 # Double click
agent-screen rightclick 3316 825               # Right click
agent-screen drag 100 200 to 300 400           # Drag from/to

# Cursor
agent-screen move 3316 825                     # Move cursor
agent-screen cursor                            # Get current cursor position

# Scroll
agent-screen scroll down 3                     # Scroll down 3 units
agent-screen scroll up --at 3316 825           # Scroll at position

# Keyboard
agent-screen type "hello, from agent-do!"      # Type text
agent-screen press Enter                       # Press key
agent-screen press Cmd+Shift+K                 # Key combination
agent-screen hotkey Cmd V                      # Hotkey

# Combined (click then type)
agent-screen input --at 3316 825 "hello"       # Click, then type
agent-screen input --text "Message" "hello"    # Find field, click, type
```

### Vision LLM Queries

```bash
# Describe current screen state
agent-screen describe
agent-screen describe --display 2
agent-screen describe --focus "Slack window"

# Ask questions about the screen
agent-screen ask "Where is the message input field in Slack?"
# → {"answer": "Bottom center of the Slack window", "coordinates": [3200, 850], "confidence": 0.92}

agent-screen ask "What buttons are visible?"
agent-screen ask "Is there an error message on screen?"
```

### Snapshots

```bash
# Take snapshot (for debugging/logging)
agent-screen snapshot
agent-screen snapshot --display 2
agent-screen snapshot --output /tmp/screen.png

# Full state dump (for AI reasoning)
agent-screen snapshot --json
# → Full JSON with all displays, elements, cursor, focused app, etc.
```

### Watching/Waiting

```bash
# Wait for text to appear
agent-screen wait --text "Upload complete" --timeout 30
agent-screen wait --text "Error" --gone        # Wait for text to disappear

# Wait for element
agent-screen wait --type dialog                # Wait for dialog
agent-screen wait --app Slack --window "Erik"  # Wait for window

# Watch for changes (stream mode)
agent-screen watch                             # Stream all changes
agent-screen watch --text "notification"       # Stream when text appears
```

---

## The 24fps Loop

```python
while running:
    # 1. Capture all displays (~5ms with ScreenCaptureKit)
    frames = capture_all_displays()
    
    # 2. Diff detection - skip unchanged regions (~2ms)
    changed_regions = detect_changes(frames, previous_frames)
    
    # 3. Fast perception on changed regions (~30ms parallel)
    for region in changed_regions:
        text = apple_vision_ocr(region)        # Parallel
        elements = detect_ui_elements(region)  # Parallel
        update_state(text, elements)
    
    # 4. Maintain state model
    state.update(
        cursor_pos=get_cursor_position(),
        focused_app=get_focused_app(),
        elements=accumulated_elements
    )
    
    # 5. If AI has pending action, execute
    if pending_action:
        execute(pending_action)
        verify_result()  # Did UI change as expected?
    
    # Target: 41.67ms per iteration (24fps)
    sleep_remaining(frame_start, target_ms=41.67)
```

---

## Key Technical Components

### 1. ScreenCaptureKit Daemon (Swift)

```swift
import ScreenCaptureKit

class ScreenCapture: NSObject, SCStreamDelegate, SCStreamOutput {
    var displays: [SCDisplay] = []
    var stream: SCStream?
    
    func startCapture(fps: Int = 24) async throws {
        let content = try await SCShareableContent.current
        displays = content.displays
        
        let config = SCStreamConfiguration()
        config.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(fps))
        config.queueDepth = 3
        
        // Capture all displays
        let filter = SCContentFilter(display: displays[0], excludingWindows: [])
        stream = SCStream(filter: filter, configuration: config, delegate: self)
        try stream?.addStreamOutput(self, type: .screen, sampleHandlerQueue: .global())
        try await stream?.startCapture()
    }
    
    func stream(_ stream: SCStream, didOutputSampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        // Process frame, run OCR, detect elements
        processFrame(sampleBuffer)
    }
}
```

### 2. Apple Vision OCR (Swift/Python via PyObjC)

```python
import Vision
import Quartz

def ocr_image(image_path):
    """Run Apple Vision OCR on image, return text with bounding boxes."""
    image = Quartz.CGImageCreateWithPNGDataProvider(...)
    
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    handler.performRequests_error_([request], None)
    
    results = []
    for observation in request.results():
        text = observation.topCandidates_(1)[0].string()
        bbox = observation.boundingBox()  # Normalized coordinates
        results.append({"text": text, "bounds": denormalize(bbox, image_size)})
    
    return results
```

### 3. Multi-Monitor Coordinate Mapping

```python
import Quartz

def get_display_layout():
    """Get all displays with unified coordinate system."""
    max_displays = 16
    displays, count = Quartz.CGGetActiveDisplayList(max_displays, None, None)
    
    layout = []
    for display_id in displays[:count]:
        bounds = Quartz.CGDisplayBounds(display_id)
        scale = Quartz.CGDisplayPixelsWide(display_id) / bounds.size.width
        
        layout.append({
            "id": display_id,
            "bounds": [bounds.origin.x, bounds.origin.y, 
                       bounds.size.width, bounds.size.height],
            "scale": scale,
            "primary": Quartz.CGDisplayIsMain(display_id)
        })
    
    return layout

def unified_to_display(x, y, displays):
    """Convert unified coordinates to display-local coordinates."""
    for display in displays:
        bx, by, bw, bh = display["bounds"]
        if bx <= x < bx + bw and by <= y < by + bh:
            return display["id"], x - bx, y - by
    return None, x, y
```

### 4. CGEvent Input Synthesis

```python
import Quartz

def click(x, y):
    """Click at unified coordinates."""
    # Move cursor
    Quartz.CGWarpMouseCursorPosition((x, y))
    
    # Post click events
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, (x, y), Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, (x, y), Quartz.kCGMouseButtonLeft
    )
    
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

def type_text(text):
    """Type text using CGEvent."""
    for char in text:
        # Create key down/up events
        event = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(event, len(char), char)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        
        event = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(event, len(char), char)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Display enumeration and coordinate mapping
- [ ] Single-frame capture (all displays)
- [ ] Apple Vision OCR integration
- [ ] Basic CLI (displays, snapshot, elements)

### Phase 2: Continuous Capture
- [ ] ScreenCaptureKit daemon (Swift helper)
- [ ] Frame diff detection
- [ ] State accumulation across frames
- [ ] Performance optimization (<42ms/frame)

### Phase 3: Actions
- [ ] CGEvent mouse actions (click, drag, scroll)
- [ ] CGEvent keyboard actions (type, press)
- [ ] Multi-monitor coordinate handling
- [ ] Action verification (did UI change?)

### Phase 4: Intelligence
- [ ] UI element detection (YOLO/Core ML)
- [ ] Vision LLM integration (describe, ask)
- [ ] Semantic element finding ("click Send button")
- [ ] Hybrid accessibility + vision approach

### Phase 5: Polish
- [ ] Watch/wait commands
- [ ] Streaming output mode
- [ ] Integration with agent-macos
- [ ] Performance tuning for 5-monitor setup

---

## Dependencies

**Required:**
- macOS 12.3+ (for ScreenCaptureKit)
- Python 3.9+
- pyobjc-framework-Quartz
- pyobjc-framework-Vision
- pyobjc-framework-ScreenCaptureKit

**Optional:**
- ultralytics (YOLO for UI detection)
- openai / anthropic (Vision LLM)
- numpy (frame processing)

---

## Permissions

agent-screen requires:
- **Screen Recording**: System Settings → Privacy & Security → Screen Recording
- **Accessibility**: System Settings → Privacy & Security → Accessibility (for CGEvent input)

---

## Example Workflow: Send Slack DM

```bash
# 1. Find Slack and the message input
agent-screen find "Message Erik"
# → {"text": "Message Erik Fritsch", "bounds": [3100, 850, 400, 40], "display": 2}

# 2. Click the message field
agent-screen click --text "Message Erik"
# → {"clicked": [3300, 870], "element": "Message Erik Fritsch"}

# 3. Type the message
agent-screen type "hello, from agent-do!"
# → {"typed": "hello, from agent-do!"}

# 4. Press Enter to send
agent-screen press Enter
# → {"pressed": "Enter"}

# 5. Verify it sent (optional)
agent-screen wait --text "hello, from agent-do!" --timeout 5
# → {"found": true, "text": "hello, from agent-do!", "bounds": [...]}
```

---

## Integration with agent-macos

agent-screen provides the **vision backbone** that agent-macos can use:

```bash
# agent-macos can fall back to agent-screen when accessibility fails
agent-macos click @g5              # Try accessibility first
# If element not found or action fails:
agent-screen click --text "Send" # Fall back to vision
```

Or agent-macos could use agent-screen internally for Electron apps:

```python
def click(self, ref_or_text):
    # Try accessibility
    element = self.resolve_ref(ref_or_text)
    if element:
        return self.ax_click(element)
    
    # Fall back to vision
    result = subprocess.run(["agent-screen", "find", ref_or_text], capture_output=True)
    if result.returncode == 0:
        bounds = json.loads(result.stdout)["bounds"]
        return subprocess.run(["agent-screen", "click", str(bounds[0]), str(bounds[1])])
    
    return {"error": "Element not found via accessibility or vision"}
```
