#!/usr/bin/env python3
"""
agent-screen: True vision for macOS AI agents.
Real-time screen perception across all displays.
"""

import json
import os
import sys
import time
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

# macOS frameworks
try:
    import Quartz
    from Quartz import (
        CGGetActiveDisplayList,
        CGDisplayBounds,
        CGDisplayPixelsWide,
        CGDisplayPixelsHigh,
        CGDisplayIsMain,
        CGDisplayCreateImage,
        CGRectMake,
        CGWarpMouseCursorPosition,
        CGEventCreateMouseEvent,
        CGEventCreateKeyboardEvent,
        CGEventPost,
        CGEventKeyboardSetUnicodeString,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGEventRightMouseDown,
        kCGEventRightMouseUp,
        kCGMouseButtonLeft,
        kCGMouseButtonRight,
        kCGHIDEventTap,
        kCGEventKeyDown,
        kCGEventKeyUp,
    )
    from AppKit import NSWorkspace, NSBitmapImageRep, NSPNGFileType
    from Foundation import NSURL
    QUARTZ_AVAILABLE = True
except ImportError:
    QUARTZ_AVAILABLE = False

# Apple Vision framework for OCR
VISION_AVAILABLE = False
try:
    import objc
    from Foundation import NSData
    # Load Vision framework via objc
    _vision_bundle = objc.loadBundle(
        'Vision', 
        module_globals=globals(), 
        bundle_path='/System/Library/Frameworks/Vision.framework'
    )
    # Check if key classes are available
    if 'VNRecognizeTextRequest' in dir():
        VISION_AVAILABLE = True
except Exception:
    pass

# Exit codes
EXIT_SUCCESS = 0
EXIT_DISPLAY_ERROR = 1
EXIT_CAPTURE_ERROR = 2
EXIT_OCR_ERROR = 3
EXIT_ELEMENT_NOT_FOUND = 4
EXIT_ACTION_FAILED = 5
EXIT_PERMISSION_DENIED = 6
EXIT_TIMEOUT = 7
EXIT_UNKNOWN = 8

STATE_DIR = Path.home() / ".agent-screen"
STATE_FILE = STATE_DIR / "state.json"
FRAMES_DIR = STATE_DIR / "frames"


def output(data: dict, exit_code: int = 0):
    """Output JSON and exit."""
    print(json.dumps(data, indent=2, default=str))
    sys.exit(exit_code)


def error(message: str, code: int = EXIT_UNKNOWN, details: dict = None):
    """Output error and exit."""
    result = {"ok": False, "error": message, "code": code}
    if details:
        result.update(details)
    output(result, code)


class ScreenState:
    """Maintains screen state across captures."""
    
    def __init__(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        self.displays = []
        self.elements = []
        self.cursor_position = (0, 0)
        self.focused_app = None
        self.last_capture = None
        self.frame_count = 0
    
    def save(self):
        """Save state to disk."""
        state = {
            "displays": self.displays,
            "elements": self.elements,
            "cursor_position": self.cursor_position,
            "focused_app": self.focused_app,
            "last_capture": self.last_capture,
            "frame_count": self.frame_count
        }
        STATE_FILE.write_text(json.dumps(state, indent=2, default=str))
    
    def load(self):
        """Load state from disk."""
        if STATE_FILE.exists():
            try:
                state = json.loads(STATE_FILE.read_text())
                self.displays = state.get("displays", [])
                self.elements = state.get("elements", [])
                self.cursor_position = tuple(state.get("cursor_position", (0, 0)))
                self.focused_app = state.get("focused_app")
                self.last_capture = state.get("last_capture")
                self.frame_count = state.get("frame_count", 0)
            except:
                pass


class ScreenCapture:
    """Screen capture and perception for macOS."""
    
    def __init__(self):
        self.state = ScreenState()
        self.state.load()
        self.workspace = NSWorkspace.sharedWorkspace() if QUARTZ_AVAILABLE else None
    
    def get_displays(self) -> List[Dict]:
        """Get all displays with bounds and scale."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        # pyobjc returns (error, display_ids_tuple, count) directly
        err, display_ids, display_count = CGGetActiveDisplayList(16, None, None)
        if err != 0:
            error(f"Failed to get display list: {err}", EXIT_DISPLAY_ERROR)
        
        displays = []
        for i in range(display_count):
            display_id = display_ids[i]
            bounds = CGDisplayBounds(display_id)
            
            # Get pixel dimensions for scale calculation
            pixel_width = CGDisplayPixelsWide(display_id)
            point_width = bounds.size.width
            scale = pixel_width / point_width if point_width > 0 else 1
            
            displays.append({
                "id": int(display_id),
                "index": i,
                "bounds": {
                    "x": int(bounds.origin.x),
                    "y": int(bounds.origin.y),
                    "width": int(bounds.size.width),
                    "height": int(bounds.size.height)
                },
                "pixels": {
                    "width": int(pixel_width),
                    "height": int(CGDisplayPixelsHigh(display_id))
                },
                "scale": round(scale, 1),
                "primary": bool(CGDisplayIsMain(display_id))
            })
        
        # Sort by x position (left to right)
        displays.sort(key=lambda d: d["bounds"]["x"])
        
        self.state.displays = displays
        self.state.save()
        
        return displays
    
    def get_focused_app(self) -> Dict:
        """Get currently focused application."""
        if not self.workspace:
            return None
        
        app = self.workspace.frontmostApplication()
        if app:
            return {
                "name": app.localizedName(),
                "bundle": app.bundleIdentifier() or "",
                "pid": app.processIdentifier()
            }
        return None
    
    def get_cursor_position(self) -> Tuple[int, int]:
        """Get current cursor position."""
        if not QUARTZ_AVAILABLE:
            return (0, 0)
        
        event = Quartz.CGEventCreate(None)
        if event:
            pos = Quartz.CGEventGetLocation(event)
            return (int(pos.x), int(pos.y))
        return (0, 0)
    
    def capture_display(self, display_id: int, output_path: str = None) -> str:
        """Capture a single display to PNG."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        image = CGDisplayCreateImage(display_id)
        if not image:
            error(f"Failed to capture display {display_id}", EXIT_CAPTURE_ERROR)
        
        if output_path is None:
            self.state.frame_count += 1
            output_path = str(FRAMES_DIR / f"display_{display_id}_{self.state.frame_count:04d}.png")
        
        # Convert to PNG
        bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
        png_data = bitmap.representationUsingType_properties_(NSPNGFileType, None)
        png_data.writeToFile_atomically_(output_path, True)
        
        return output_path
    
    def capture_all_displays(self, output_dir: str = None) -> List[Dict]:
        """Capture all displays."""
        displays = self.get_displays()
        results = []
        
        if output_dir is None:
            output_dir = str(FRAMES_DIR)
        
        for display in displays:
            self.state.frame_count += 1
            path = os.path.join(output_dir, f"display_{display['index']}_{self.state.frame_count:04d}.png")
            
            try:
                self.capture_display(display["id"], path)
                results.append({
                    "display": display["index"],
                    "display_id": display["id"],
                    "path": path,
                    "bounds": display["bounds"]
                })
            except Exception as e:
                results.append({
                    "display": display["index"],
                    "error": str(e)
                })
        
        self.state.last_capture = datetime.now().isoformat()
        self.state.save()
        
        return results
    
    def capture_region(self, x: int, y: int, width: int, height: int, output_path: str = None) -> str:
        """Capture a specific region across displays."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        # Find which display contains this region
        displays = self.get_displays()
        for display in displays:
            b = display["bounds"]
            if (b["x"] <= x < b["x"] + b["width"] and 
                b["y"] <= y < b["y"] + b["height"]):
                
                # Capture from this display
                rect = CGRectMake(
                    x - b["x"],  # Convert to display-local coords
                    y - b["y"],
                    width,
                    height
                )
                
                image = Quartz.CGDisplayCreateImageForRect(display["id"], rect)
                if not image:
                    error(f"Failed to capture region", EXIT_CAPTURE_ERROR)
                
                if output_path is None:
                    self.state.frame_count += 1
                    output_path = str(FRAMES_DIR / f"region_{self.state.frame_count:04d}.png")
                
                bitmap = NSBitmapImageRep.alloc().initWithCGImage_(image)
                png_data = bitmap.representationUsingType_properties_(NSPNGFileType, None)
                png_data.writeToFile_atomically_(output_path, True)
                
                return output_path
        
        error(f"Region ({x}, {y}) not on any display", EXIT_DISPLAY_ERROR)
    
    def ocr_image(self, image_path: str) -> List[Dict]:
        """Run Apple Vision OCR on an image."""
        if not VISION_AVAILABLE:
            # Fallback to tesseract if available
            try:
                result = subprocess.run(
                    ["tesseract", image_path, "stdout", "-c", "tessedit_create_boxfile=1"],
                    capture_output=True, text=True
                )
                # Parse tesseract output (simplified)
                elements = []
                for line in result.stdout.strip().split("\n"):
                    if line:
                        elements.append({"text": line, "source": "tesseract"})
                return elements
            except:
                error("Vision framework and tesseract not available", EXIT_OCR_ERROR)
        
        # Load image
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # Create CGImage from data
        data_provider = Quartz.CGDataProviderCreateWithData(None, image_data, len(image_data), None)
        cg_image = Quartz.CGImageCreateWithPNGDataProvider(data_provider, None, True, Quartz.kCGRenderingIntentDefault)
        
        if not cg_image:
            # Try loading via NSBitmapImageRep
            ns_data = NSData.dataWithBytes_length_(image_data, len(image_data))
            bitmap = NSBitmapImageRep.alloc().initWithData_(ns_data)
            if bitmap:
                cg_image = bitmap.CGImage()
        
        if not cg_image:
            error(f"Failed to load image: {image_path}", EXIT_OCR_ERROR)
        
        # Get image dimensions
        img_width = Quartz.CGImageGetWidth(cg_image)
        img_height = Quartz.CGImageGetHeight(cg_image)
        
        # Create Vision request (classes loaded into globals via objc.loadBundle)
        request = VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(1)  # VNRequestTextRecognitionLevelAccurate = 1
        request.setUsesLanguageCorrection_(True)
        
        # Create handler and perform
        handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
        success = handler.performRequests_error_([request], None)
        
        if not success:
            error(f"OCR failed", EXIT_OCR_ERROR)
        
        # Extract results
        elements = []
        results = request.results()
        
        if results:
            for observation in results:
                # Get top candidate
                candidates = observation.topCandidates_(1)
                if candidates and len(candidates) > 0:
                    text = candidates[0].string()
                    confidence = candidates[0].confidence()
                    
                    # Get bounding box (normalized 0-1, origin bottom-left)
                    bbox = observation.boundingBox()
                    
                    # Convert to pixel coordinates (origin top-left)
                    x = int(bbox.origin.x * img_width)
                    y = int((1 - bbox.origin.y - bbox.size.height) * img_height)
                    w = int(bbox.size.width * img_width)
                    h = int(bbox.size.height * img_height)
                    
                    elements.append({
                        "type": "text",
                        "text": text,
                        "bounds": {"x": x, "y": y, "width": w, "height": h},
                        "confidence": round(confidence, 3)
                    })
        
        return elements
    
    def snapshot(self, display_index: int = None, output_path: str = None, 
                 run_ocr: bool = True) -> Dict:
        """Take snapshot and optionally run OCR."""
        displays = self.get_displays()
        
        if display_index is not None:
            # Single display
            if display_index >= len(displays):
                error(f"Display {display_index} not found", EXIT_DISPLAY_ERROR)
            
            display = displays[display_index]
            if output_path is None:
                self.state.frame_count += 1
                output_path = str(FRAMES_DIR / f"snapshot_{self.state.frame_count:04d}.png")
            
            self.capture_display(display["id"], output_path)
            
            result = {
                "ok": True,
                "display": display_index,
                "path": output_path,
                "bounds": display["bounds"],
                "timestamp": datetime.now().isoformat()
            }
            
            if run_ocr:
                elements = self.ocr_image(output_path)
                result["elements"] = elements
                result["element_count"] = len(elements)
                
                # Store elements with display offset
                for elem in elements:
                    elem["display"] = display_index
                    elem["bounds"]["x"] += display["bounds"]["x"]
                    elem["bounds"]["y"] += display["bounds"]["y"]
                
                self.state.elements = elements
                self.state.save()
        else:
            # All displays - create composite or capture each
            captures = self.capture_all_displays()
            all_elements = []
            
            result = {
                "ok": True,
                "displays": len(captures),
                "captures": captures,
                "timestamp": datetime.now().isoformat()
            }
            
            if run_ocr:
                # Build index-to-display mapping since displays are sorted
                display_by_index = {d["index"]: d for d in displays}
                
                for cap in captures:
                    if "path" in cap:
                        elements = self.ocr_image(cap["path"])
                        
                        # Add display offset to element bounds
                        display = display_by_index[cap["display"]]
                        for elem in elements:
                            elem["display"] = cap["display"]
                            elem["bounds"]["x"] += display["bounds"]["x"]
                            elem["bounds"]["y"] += display["bounds"]["y"]
                        
                        all_elements.extend(elements)
                        cap["elements"] = len(elements)
                
                result["elements"] = all_elements
                result["element_count"] = len(all_elements)
                
                self.state.elements = all_elements
                self.state.save()
        
        # Update cursor and focused app
        self.state.cursor_position = self.get_cursor_position()
        self.state.focused_app = self.get_focused_app()
        self.state.last_capture = result["timestamp"]
        self.state.save()
        
        result["cursor"] = self.state.cursor_position
        result["focused_app"] = self.state.focused_app
        
        return result
    
    def find_text(self, search_text: str, fuzzy: bool = True) -> List[Dict]:
        """Find elements containing text."""
        if not self.state.elements:
            # Take fresh snapshot
            self.snapshot()
        
        matches = []
        search_lower = search_text.lower()
        
        for elem in self.state.elements:
            if elem.get("type") != "text":
                continue
            
            elem_text = elem.get("text", "")
            elem_lower = elem_text.lower()
            
            if fuzzy:
                if search_lower in elem_lower:
                    matches.append({
                        **elem,
                        "match_type": "contains"
                    })
            else:
                if search_lower == elem_lower:
                    matches.append({
                        **elem,
                        "match_type": "exact"
                    })
        
        # Sort by confidence
        matches.sort(key=lambda m: m.get("confidence", 0), reverse=True)
        
        return matches
    
    def element_at(self, x: int, y: int) -> Optional[Dict]:
        """Get element at coordinates."""
        if not self.state.elements:
            self.snapshot()
        
        for elem in self.state.elements:
            b = elem.get("bounds", {})
            if (b.get("x", 0) <= x < b.get("x", 0) + b.get("width", 0) and
                b.get("y", 0) <= y < b.get("y", 0) + b.get("height", 0)):
                return elem
        
        return None
    
    def display_at(self, x: int, y: int) -> Optional[Dict]:
        """Get display at coordinates."""
        displays = self.get_displays() if not self.state.displays else self.state.displays
        
        for display in displays:
            b = display["bounds"]
            if (b["x"] <= x < b["x"] + b["width"] and
                b["y"] <= y < b["y"] + b["height"]):
                return display
        
        return None
    
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> Dict:
        """Click at coordinates."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        # Move cursor
        CGWarpMouseCursorPosition((x, y))
        time.sleep(0.05)
        
        # Determine button
        if button == "right":
            down_type = kCGEventRightMouseDown
            up_type = kCGEventRightMouseUp
            mouse_button = kCGMouseButtonRight
        else:
            down_type = kCGEventLeftMouseDown
            up_type = kCGEventLeftMouseUp
            mouse_button = kCGMouseButtonLeft
        
        # Perform clicks
        for i in range(clicks):
            down = CGEventCreateMouseEvent(None, down_type, (x, y), mouse_button)
            up = CGEventCreateMouseEvent(None, up_type, (x, y), mouse_button)
            
            if clicks > 1:
                Quartz.CGEventSetIntegerValueField(down, Quartz.kCGMouseEventClickState, i + 1)
                Quartz.CGEventSetIntegerValueField(up, Quartz.kCGMouseEventClickState, i + 1)
            
            CGEventPost(kCGHIDEventTap, down)
            CGEventPost(kCGHIDEventTap, up)
            
            if i < clicks - 1:
                time.sleep(0.05)
        
        self.state.cursor_position = (x, y)
        self.state.save()
        
        return {
            "ok": True,
            "action": "click",
            "position": [x, y],
            "button": button,
            "clicks": clicks
        }
    
    def move_cursor(self, x: int, y: int) -> Dict:
        """Move cursor to coordinates."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        CGWarpMouseCursorPosition((x, y))
        self.state.cursor_position = (x, y)
        self.state.save()
        
        return {
            "ok": True,
            "action": "move",
            "position": [x, y]
        }
    
    def type_text(self, text: str) -> Dict:
        """Type text at current focus."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        for char in text:
            # Key down
            event = CGEventCreateKeyboardEvent(None, 0, True)
            CGEventKeyboardSetUnicodeString(event, 1, char)
            CGEventPost(kCGHIDEventTap, event)
            
            # Key up
            event = CGEventCreateKeyboardEvent(None, 0, False)
            CGEventKeyboardSetUnicodeString(event, 1, char)
            CGEventPost(kCGHIDEventTap, event)
            
            time.sleep(0.01)  # Small delay between characters
        
        return {
            "ok": True,
            "action": "type",
            "text": text,
            "length": len(text)
        }
    
    def press_key(self, key: str) -> Dict:
        """Press a key or key combination."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        # Parse modifiers
        parts = key.replace("+", " ").split()
        modifiers = []
        key_char = parts[-1] if parts else key
        
        modifier_flags = {
            "cmd": Quartz.kCGEventFlagMaskCommand,
            "command": Quartz.kCGEventFlagMaskCommand,
            "ctrl": Quartz.kCGEventFlagMaskControl,
            "control": Quartz.kCGEventFlagMaskControl,
            "alt": Quartz.kCGEventFlagMaskAlternate,
            "option": Quartz.kCGEventFlagMaskAlternate,
            "shift": Quartz.kCGEventFlagMaskShift
        }
        
        flags = 0
        for part in parts[:-1]:
            flag = modifier_flags.get(part.lower(), 0)
            flags |= flag
        
        # Key codes for special keys
        key_codes = {
            "return": 36, "enter": 36,
            "tab": 48,
            "space": 49,
            "delete": 51, "backspace": 51,
            "escape": 53, "esc": 53,
            "up": 126, "down": 125, "left": 123, "right": 124,
            "home": 115, "end": 119,
            "pageup": 116, "pagedown": 121,
            "f1": 122, "f2": 120, "f3": 99, "f4": 118,
            "f5": 96, "f6": 97, "f7": 98, "f8": 100,
            "f9": 101, "f10": 109, "f11": 103, "f12": 111
        }
        
        key_lower = key_char.lower()
        
        if key_lower in key_codes:
            # Special key
            keycode = key_codes[key_lower]
            
            down = CGEventCreateKeyboardEvent(None, keycode, True)
            up = CGEventCreateKeyboardEvent(None, keycode, False)
            
            if flags:
                Quartz.CGEventSetFlags(down, flags)
                Quartz.CGEventSetFlags(up, flags)
            
            CGEventPost(kCGHIDEventTap, down)
            CGEventPost(kCGHIDEventTap, up)
        else:
            # Regular character
            down = CGEventCreateKeyboardEvent(None, 0, True)
            up = CGEventCreateKeyboardEvent(None, 0, False)
            
            CGEventKeyboardSetUnicodeString(down, 1, key_char)
            CGEventKeyboardSetUnicodeString(up, 1, key_char)
            
            if flags:
                Quartz.CGEventSetFlags(down, flags)
                Quartz.CGEventSetFlags(up, flags)
            
            CGEventPost(kCGHIDEventTap, down)
            CGEventPost(kCGHIDEventTap, up)
        
        return {
            "ok": True,
            "action": "press",
            "key": key
        }
    
    def scroll(self, direction: str, amount: int = 3, x: int = None, y: int = None) -> Dict:
        """Scroll at position."""
        if not QUARTZ_AVAILABLE:
            error("Quartz not available", EXIT_PERMISSION_DENIED)
        
        # Move cursor if position specified
        if x is not None and y is not None:
            CGWarpMouseCursorPosition((x, y))
        
        # Create scroll event
        dy = amount if direction == "up" else -amount if direction == "down" else 0
        dx = amount if direction == "right" else -amount if direction == "left" else 0
        
        event = Quartz.CGEventCreateScrollWheelEvent(
            None,
            Quartz.kCGScrollEventUnitLine,
            2,  # Number of axes
            dy,
            dx
        )
        
        CGEventPost(kCGHIDEventTap, event)
        
        return {
            "ok": True,
            "action": "scroll",
            "direction": direction,
            "amount": amount
        }
    
    def describe(self, display_index: int = None) -> Dict:
        """Use Vision LLM to describe the screen."""
        # First take a snapshot
        snapshot_result = self.snapshot(display_index=display_index, run_ocr=False)
        
        # Get the image path
        if display_index is not None:
            image_path = snapshot_result["path"]
        else:
            # Use first display for now
            if snapshot_result["captures"]:
                image_path = snapshot_result["captures"][0].get("path")
            else:
                error("No captures available", EXIT_CAPTURE_ERROR)
        
        # Try OpenAI Vision
        if os.environ.get("OPENAI_API_KEY"):
            try:
                import base64
                import httpx
                
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                response = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "gpt-4o",
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Describe what you see on this screen. Focus on the main application, visible UI elements, and any actionable items like buttons, text fields, or links. Be concise."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
                            ]
                        }],
                        "max_tokens": 500
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    description = response.json()["choices"][0]["message"]["content"]
                    return {
                        "ok": True,
                        "description": description,
                        "source": "openai",
                        "image": image_path
                    }
            except Exception as e:
                pass
        
        # Try Anthropic
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import base64
                import httpx
                
                with open(image_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode()
                
                response = httpx.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                        "Content-Type": "application/json",
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 500,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": image_data}},
                                {"type": "text", "text": "Describe what you see on this screen. Focus on the main application, visible UI elements, and any actionable items like buttons, text fields, or links. Be concise."}
                            ]
                        }]
                    },
                    timeout=30
                )
                
                if response.status_code == 200:
                    description = response.json()["content"][0]["text"]
                    return {
                        "ok": True,
                        "description": description,
                        "source": "anthropic",
                        "image": image_path
                    }
            except Exception as e:
                pass
        
        # Fallback to OCR summary
        elements = self.ocr_image(image_path)
        texts = [e["text"] for e in elements[:20]]  # First 20 elements
        
        return {
            "ok": True,
            "description": f"Screen contains {len(elements)} text elements. Sample: {', '.join(texts[:10])}",
            "source": "ocr",
            "image": image_path,
            "element_count": len(elements)
        }


def main():
    if not QUARTZ_AVAILABLE:
        error("macOS Quartz framework not available", EXIT_PERMISSION_DENIED)
    
    screen = ScreenCapture()
    args = sys.argv[1:]
    
    if not args:
        output({"error": "No command specified", "usage": "agent-screen <command> [args]"}, EXIT_UNKNOWN)
    
    cmd = args[0].lower()
    
    # Display commands
    if cmd == "displays":
        displays = screen.get_displays()
        output({"ok": True, "displays": displays, "count": len(displays)})
    
    elif cmd == "display":
        if len(args) < 2:
            error("Usage: agent-screen display <index>")
        displays = screen.get_displays()
        idx = int(args[1])
        if idx >= len(displays):
            error(f"Display {idx} not found")
        output({"ok": True, "display": displays[idx]})
    
    # Snapshot
    elif cmd == "snapshot":
        display_idx = None
        output_path = None
        no_ocr = "--no-ocr" in args
        
        for i, arg in enumerate(args[1:], 1):
            if arg == "--display" and i + 1 < len(args):
                display_idx = int(args[i + 1])
            elif arg == "--output" and i + 1 < len(args):
                output_path = args[i + 1]
            elif arg.startswith("-"):
                continue
            elif arg.isdigit():
                display_idx = int(arg)
        
        result = screen.snapshot(display_index=display_idx, output_path=output_path, run_ocr=not no_ocr)
        output(result)
    
    # Elements
    elif cmd == "elements":
        display_idx = None
        element_type = None
        
        for i, arg in enumerate(args[1:], 1):
            if arg == "--display" and i + 1 < len(args):
                display_idx = int(args[i + 1])
            elif arg == "--type" and i + 1 < len(args):
                element_type = args[i + 1]
        
        if not screen.state.elements:
            screen.snapshot(display_index=display_idx)
        
        elements = screen.state.elements
        if display_idx is not None:
            elements = [e for e in elements if e.get("display") == display_idx]
        if element_type:
            elements = [e for e in elements if e.get("type") == element_type]
        
        output({"ok": True, "elements": elements, "count": len(elements)})
    
    # Find
    elif cmd == "find":
        if len(args) < 2:
            error("Usage: agent-screen find <text>")
        
        search_text = " ".join(args[1:])
        # Remove flags from search text
        for flag in ["--exact", "--fuzzy"]:
            search_text = search_text.replace(flag, "").strip()
        
        exact = "--exact" in args
        matches = screen.find_text(search_text, fuzzy=not exact)
        
        if matches:
            output({"ok": True, "matches": matches, "count": len(matches)})
        else:
            output({"ok": False, "error": f"No matches for '{search_text}'", "matches": [], "count": 0}, EXIT_ELEMENT_NOT_FOUND)
    
    # At
    elif cmd == "at":
        if len(args) < 3:
            error("Usage: agent-screen at <x> <y>")
        
        x, y = int(args[1]), int(args[2])
        elem = screen.element_at(x, y)
        display = screen.display_at(x, y)
        
        result = {
            "ok": True,
            "position": [x, y],
            "display": display,
            "element": elem
        }
        output(result)
    
    # Cursor
    elif cmd == "cursor":
        pos = screen.get_cursor_position()
        display = screen.display_at(pos[0], pos[1])
        output({
            "ok": True,
            "position": list(pos),
            "display": display["index"] if display else None
        })
    
    # Click
    elif cmd == "click":
        if len(args) < 2:
            error("Usage: agent-screen click <x> <y> | --text <text>")
        
        x, y = None, None
        button = "left"
        clicks = 1
        
        if "--text" in args:
            idx = args.index("--text")
            if idx + 1 < len(args):
                search_text = args[idx + 1]
                matches = screen.find_text(search_text)
                if matches:
                    b = matches[0]["bounds"]
                    x = b["x"] + b["width"] // 2
                    y = b["y"] + b["height"] // 2
                else:
                    error(f"Text '{search_text}' not found", EXIT_ELEMENT_NOT_FOUND)
        else:
            x, y = int(args[1]), int(args[2])
        
        if "--right" in args:
            button = "right"
        if "--double" in args:
            clicks = 2
        
        result = screen.click(x, y, button=button, clicks=clicks)
        output(result)
    
    elif cmd == "dblclick":
        if len(args) < 3:
            error("Usage: agent-screen dblclick <x> <y>")
        x, y = int(args[1]), int(args[2])
        result = screen.click(x, y, clicks=2)
        output(result)
    
    elif cmd == "rightclick":
        if len(args) < 3:
            error("Usage: agent-screen rightclick <x> <y>")
        x, y = int(args[1]), int(args[2])
        result = screen.click(x, y, button="right")
        output(result)
    
    # Move
    elif cmd == "move":
        if len(args) < 3:
            error("Usage: agent-screen move <x> <y>")
        x, y = int(args[1]), int(args[2])
        result = screen.move_cursor(x, y)
        output(result)
    
    # Type
    elif cmd == "type":
        if len(args) < 2:
            error("Usage: agent-screen type <text>")
        text = " ".join(args[1:])
        result = screen.type_text(text)
        output(result)
    
    # Press
    elif cmd == "press":
        if len(args) < 2:
            error("Usage: agent-screen press <key>")
        key = " ".join(args[1:])
        result = screen.press_key(key)
        output(result)
    
    # Scroll
    elif cmd == "scroll":
        if len(args) < 2:
            error("Usage: agent-screen scroll <up|down|left|right> [amount]")
        
        direction = args[1]
        amount = 3
        x, y = None, None
        
        for i, arg in enumerate(args[2:], 2):
            if arg == "--at" and i + 2 < len(args):
                x, y = int(args[i + 1]), int(args[i + 2])
            elif arg.isdigit():
                amount = int(arg)
        
        result = screen.scroll(direction, amount, x, y)
        output(result)
    
    # Describe
    elif cmd == "describe":
        display_idx = None
        for i, arg in enumerate(args[1:], 1):
            if arg == "--display" and i + 1 < len(args):
                display_idx = int(args[i + 1])
            elif arg.isdigit():
                display_idx = int(arg)
        
        result = screen.describe(display_index=display_idx)
        output(result)
    
    # Status
    elif cmd == "status":
        screen.state.load()
        output({
            "ok": True,
            "displays": len(screen.state.displays),
            "elements": len(screen.state.elements),
            "cursor": screen.state.cursor_position,
            "focused_app": screen.state.focused_app,
            "last_capture": screen.state.last_capture,
            "frame_count": screen.state.frame_count
        })
    
    # Focused app
    elif cmd == "focused":
        app = screen.get_focused_app()
        output({"ok": True, "app": app})
    
    else:
        error(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
