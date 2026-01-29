# agent-vision Specification

> AI-first visual perception. Capture, detect, describe, react.

## Philosophy

The same pattern that makes agent-browse and agent-db work:

```
SOURCE → SNAPSHOT → DETECT → DESCRIBE → ACT
```

**Key insight:** Vision-Agents is a framework for *building* video AI agents. agent-vision is a CLI tool that lets AI *use* visual perception as a capability - the same way agent-browse lets AI see web pages.

## Design Principles

1. **Snapshot pattern** - AI sees a frame, makes decisions, acts
2. **Local-first** - Works offline with local models, cloud optional
3. **Zero-config** - `agent-vision snapshot` just works
4. **JSON everything** - All output is AI-parseable
5. **Composable** - Chain with agent-browse, agent-excel, agent-slack

## Core Commands

### Source Management

```bash
agent-vision source webcam               # Default webcam (index 0)
agent-vision source webcam 1             # Specific camera index
agent-vision source screen               # Full screen capture
agent-vision source screen 0             # Specific display
agent-vision source window "Safari"      # Capture specific window (macOS)
agent-vision source file video.mp4       # Video file as source
agent-vision source image photo.jpg      # Single image
agent-vision source rtsp://user:pass@ip/stream  # RTSP/IP camera
agent-vision source ios                  # iOS simulator (via agent-ios)
agent-vision source browse               # Current browser page (via agent-browse)

agent-vision status                      # Show current source
agent-vision disconnect                  # Release source
```

### Snapshot (The Core Pattern)

```bash
agent-vision snapshot                    # Capture frame → JSON + image path
agent-vision snapshot --output frame.png # Custom output path
agent-vision snapshot --analyze          # + Vision LLM description
agent-vision snapshot --yolo             # + YOLO object detection
agent-vision snapshot --ocr              # + OCR text extraction
agent-vision snapshot --faces            # + Face detection
agent-vision snapshot --motion           # + Motion delta from last frame
agent-vision snapshot --all              # Run all detectors
```

### Object Detection

```bash
agent-vision detect                      # One-shot YOLO detection
agent-vision detect --model yolov8n      # Specify model
agent-vision detect --classes person,car # Filter classes
agent-vision detect --confidence 0.7     # Confidence threshold
agent-vision detect --annotate           # Save annotated image

agent-vision count "person"              # Count specific class
agent-vision count --all                 # Count all detected objects
agent-vision locate "dog"                # Get bounding box for class
```

### Face Detection & Recognition

```bash
agent-vision faces                       # Detect faces in frame
agent-vision faces --identify            # Match against known faces
agent-vision faces --emotions            # Detect emotions
agent-vision faces --landmarks           # Include facial landmarks

agent-vision face learn "Erik" face.jpg  # Add face to known set
agent-vision face forget "Erik"          # Remove from known set
agent-vision face list                   # List known faces
```

### OCR / Text Extraction

```bash
agent-vision ocr                         # Extract all text from frame
agent-vision ocr --region x,y,w,h        # OCR specific region
agent-vision ocr --lang eng+spa          # Specify languages
agent-vision ocr --find "ERROR"          # Search for text, return location
```

### Vision LLM Analysis

```bash
agent-vision describe                    # Describe current frame
agent-vision describe --detail high      # More detailed description
agent-vision describe --focus "people"   # Focus description on topic

agent-vision ask "Is anyone at the door?"           # Yes/no question
agent-vision ask "What color is the car?"           # Specific question
agent-vision ask "Count the people in the room"     # Counting question

agent-vision compare frame1.png frame2.png          # Describe differences
agent-vision compare --last                         # Compare to previous snapshot
```

### Watch (Event Detection)

```bash
agent-vision watch "person"              # Wait until person detected
agent-vision watch "person" --timeout 60 # With timeout (seconds)
agent-vision watch "person" --enter      # Wait for person to ENTER frame
agent-vision watch "person" --exit       # Wait for person to LEAVE frame

agent-vision watch --motion              # Wait for any motion
agent-vision watch --motion 0.3          # Motion threshold (0-1)

agent-vision watch --face                # Wait for face detected
agent-vision watch --face "Erik"         # Wait for specific person

agent-vision watch --text "READY"        # Wait for text to appear (OCR)
agent-vision watch --text-gone "Loading" # Wait for text to disappear

agent-vision watch --change              # Wait for significant scene change
agent-vision watch --stable              # Wait for scene to stabilize
```

### Recording

```bash
agent-vision record 10                   # Record 10 seconds
agent-vision record 10 output.mp4        # Record to specific file
agent-vision record --until "person"     # Record until detection
agent-vision record --while "person"     # Record while detected
agent-vision record --motion             # Record only when motion detected

agent-vision stream start                # Start continuous capture
agent-vision stream stop                 # Stop capture
agent-vision stream clip 30              # Save last 30 seconds
```

### Pose Detection

```bash
agent-vision pose                        # Detect body poses
agent-vision pose --skeleton             # Return skeleton keypoints
agent-vision pose --hands                # Focus on hand positions
agent-vision pose --annotate             # Save annotated image
```

## Output Format

All commands return JSON for AI parsing:

### snapshot
```json
{
  "ok": true,
  "source": "webcam:0",
  "timestamp": "2026-01-28T15:30:45.123Z",
  "frame": {
    "path": "/tmp/agent-vision/frame_001.png",
    "width": 1920,
    "height": 1080
  },
  "analysis": {
    "description": "A home office with a person sitting at a desk...",
    "detections": [
      {"class": "person", "confidence": 0.95, "box": [100, 50, 400, 600]},
      {"class": "laptop", "confidence": 0.89, "box": [200, 300, 450, 500]}
    ],
    "faces": [
      {"id": "face_0", "box": [150, 80, 250, 220], "emotion": "neutral"}
    ],
    "text": ["Dell", "Microsoft Teams"],
    "motion_score": 0.12
  }
}
```

### watch (event triggered)
```json
{
  "ok": true,
  "event": "person_detected",
  "waited_seconds": 23.5,
  "trigger": {
    "class": "person",
    "confidence": 0.91,
    "box": [300, 100, 500, 600],
    "direction": "entered_left"
  },
  "frame": {
    "path": "/tmp/agent-vision/event_frame.png"
  }
}
```

### detect
```json
{
  "ok": true,
  "model": "yolov8n",
  "detections": [
    {
      "class": "person",
      "confidence": 0.94,
      "box": [x, y, width, height],
      "center": [cx, cy]
    },
    {
      "class": "car",
      "confidence": 0.87,
      "box": [x, y, width, height],
      "center": [cx, cy]
    }
  ],
  "counts": {
    "person": 2,
    "car": 1
  },
  "annotated_frame": "/tmp/agent-vision/detected.png"
}
```

### Error Response
```json
{
  "ok": false,
  "error": "No webcam found",
  "suggestion": "Connect a webcam or use 'agent-vision source screen' for screen capture",
  "exit_code": 2
}
```

## Session State

State persisted in `~/.agent-vision/session.json`:

```json
{
  "source": {
    "type": "webcam",
    "index": 0,
    "resolution": [1920, 1080],
    "fps": 30
  },
  "connected_at": "2026-01-28T15:30:00Z",
  "frame_count": 47,
  "last_snapshot": "/tmp/agent-vision/frame_047.png",
  "known_faces": ["Erik", "Sarah"],
  "recording": false
}
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Source not available |
| 2 | No video device found |
| 3 | Detection failed |
| 4 | Model not found |
| 5 | Timeout waiting for event |
| 6 | Vision LLM error |
| 7 | Recording error |
| 8 | Unknown error |

## Example Workflows

### Security Camera Monitoring
```bash
# Connect to IP camera
agent-vision source rtsp://admin:pass@192.168.1.100/stream

# Check current view
agent-vision snapshot --yolo
# → Shows 0 persons detected

# Wait for someone to appear
agent-vision watch "person" --timeout 3600
# → Waits up to 1 hour...
# → Returns when person detected

# Describe what's happening
agent-vision describe
# → "A person in a blue jacket is approaching the front door carrying a package"

# Record the interaction
agent-vision record 30 delivery.mp4

# Alert via Slack
agent-slack send "#security" "Person at front door - see delivery.mp4"
```

### Meeting Attendance
```bash
# Capture screen with video call
agent-vision source window "Zoom"

# Count participants
agent-vision faces
# → {"face_count": 8, "identified": ["Erik", "Sarah"], "unknown": 6}

# Check if specific person joined
agent-vision watch --face "Bob" --timeout 300
# → Wait up to 5 min for Bob to appear

# Get meeting summary
agent-vision describe --focus "participants and their engagement"
```

### Document Processing
```bash
# Source from phone camera via iOS simulator
agent-vision source ios

# Wait for document to be in frame
agent-vision watch --text --stable

# Extract text
agent-vision ocr
# → Returns all text from document

# Or ask specific question
agent-vision ask "What is the total amount on this invoice?"
```

### Quality Control (Manufacturing)
```bash
# Connect to production line camera
agent-vision source rtsp://factory-cam/line1

# Continuous monitoring loop
agent-vision watch "defect" --timeout 0  # No timeout, run forever
# → On detection, returns and pipeline can alert/log

# Or count products
agent-vision count "bottle"
# → {"count": 24, "positions": [...]}
```

## Model Support

### Object Detection
| Model | Size | Speed | Use Case |
|-------|------|-------|----------|
| yolov8n | 6MB | Fast | Real-time, edge |
| yolov8s | 22MB | Medium | Balanced |
| yolov8m | 52MB | Slower | Higher accuracy |
| yolov11n | 5MB | Fastest | Latest gen |

### Vision LLMs
| Provider | Model | Use Case |
|----------|-------|----------|
| OpenAI | gpt-4o | Best quality |
| Anthropic | claude-3.5-sonnet | Detailed analysis |
| Google | gemini-2.0-flash | Fast + cheap |
| Local | llava | Offline |

### OCR
| Engine | Notes |
|--------|-------|
| Tesseract | Default, offline |
| Apple Vision | macOS native, fast |
| EasyOCR | Multi-language |

### Face Detection
| Engine | Notes |
|--------|-------|
| OpenCV Haar | Fast, basic |
| dlib | Accurate, landmarks |
| face_recognition | Identification support |

## Implementation Notes

### Architecture
```
agent-vision (bash CLI)
    ↓
vision_ops.py (Python module)
    ↓
├── capture.py      (webcam, screen, file sources)
├── detect.py       (YOLO, faces, motion)
├── ocr.py          (text extraction)
├── llm.py          (vision LLM integration)
├── record.py       (video recording)
└── watch.py        (event detection loop)
```

### Dependencies
```
# Core (always needed)
opencv-python       # Capture + basic processing
pillow              # Image handling

# Detection (optional)
ultralytics         # YOLO models
face_recognition    # Face detection/recognition
dlib                # Face landmarks

# OCR (optional)  
pytesseract         # OCR engine
easyocr             # Alternative OCR

# Vision LLM (optional)
openai              # GPT-4V
anthropic           # Claude Vision
google-generativeai # Gemini Vision
```

### macOS-Specific
- Screen capture via `screencapture` or CGWindowListCreateImage
- Window capture via window ID lookup
- Apple Vision framework for native OCR
- AVFoundation for webcam access

## Integration with Other Tools

### With agent-browse
```bash
# Capture browser screenshot and analyze
agent-browse screenshot /tmp/page.png
agent-vision source image /tmp/page.png
agent-vision ask "Is there a login form on this page?"

# Or directly
agent-vision source browse
agent-vision ocr --find "Sign In"
```

### With agent-ios
```bash
# Analyze iOS simulator
agent-vision source ios
agent-vision describe
agent-vision ocr
agent-vision watch --text "Welcome"
```

### With agent-excel
```bash
# Security log to spreadsheet
agent-vision watch "person" --timeout 0 | while read event; do
  agent-excel open security_log.xlsx
  agent-excel set A$ROW "$(date)"
  agent-excel set B$ROW "Person detected"
  agent-excel save
done
```

## Future Enhancements

- `agent-vision diff` - Visual diff between frames
- `agent-vision track "person"` - Track object across frames
- `agent-vision annotate` - Draw boxes/labels on frame
- `agent-vision stream mjpeg` - Serve annotated stream
- `agent-vision calibrate` - Camera calibration
- `agent-vision depth` - Depth estimation (with stereo/ML)
- `agent-vision segment` - Instance segmentation
- GPU acceleration for faster inference
- WebRTC source for remote streams
