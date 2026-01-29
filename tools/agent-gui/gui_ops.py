#!/usr/bin/env python3
"""
agent-gui: Desktop GUI automation with semantic element refs.
macOS implementation using Accessibility APIs (AXUIElement).
"""

import json
import os
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# macOS frameworks
try:
    from ApplicationServices import (
        AXUIElementCreateApplication,
        AXUIElementCreateSystemWide,
        AXUIElementCopyAttributeValue,
        AXUIElementCopyAttributeNames,
        AXUIElementCopyActionNames,
        AXUIElementPerformAction,
        AXUIElementSetAttributeValue,
        AXIsProcessTrusted,
        AXUIElementCopyElementAtPosition,
    )
    from CoreFoundation import CFEqual
    import Quartz
    from AppKit import NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps
    MACOS_AVAILABLE = True
except ImportError:
    MACOS_AVAILABLE = False

# Exit codes
EXIT_SUCCESS = 0
EXIT_APP_NOT_FOUND = 1
EXIT_WINDOW_NOT_FOUND = 2
EXIT_ELEMENT_NOT_FOUND = 3
EXIT_ACTION_FAILED = 4
EXIT_TIMEOUT = 5
EXIT_PERMISSION_DENIED = 6
EXIT_VISION_FAILED = 7
EXIT_UNKNOWN = 8

SESSION_DIR = Path.home() / ".agent-gui"
SESSION_FILE = SESSION_DIR / "session.json"


def output(data: dict, exit_code: int = 0):
    """Output JSON and exit."""
    print(json.dumps(data, indent=2, default=str))
    sys.exit(exit_code)


def error(message: str, code: int = EXIT_UNKNOWN, details: dict = None):
    """Output error and exit."""
    result = {"error": message, "code": code}
    if details:
        result.update(details)
    output(result, code)


class GUISession:
    """Manages GUI automation session state."""
    
    def __init__(self):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        self.state = self._load_state()
        self._element_cache = {}  # @ref -> AXUIElement
        self._ref_counter = 0
    
    def _load_state(self) -> dict:
        if SESSION_FILE.exists():
            try:
                return json.loads(SESSION_FILE.read_text())
            except:
                pass
        return {
            "app": None,
            "pid": None,
            "window": None,
            "last_snapshot": None,
            "history": []
        }
    
    def _save_state(self):
        SESSION_FILE.write_text(json.dumps(self.state, indent=2, default=str))
    
    def set_app(self, app_name: str, pid: int):
        self.state["app"] = app_name
        self.state["pid"] = pid
        self._save_state()
    
    def add_history(self, action: str):
        self.state["history"].append({
            "action": action,
            "timestamp": datetime.now().isoformat()
        })
        if len(self.state["history"]) > 100:
            self.state["history"] = self.state["history"][-100:]
        self._save_state()
    
    def get_ref(self, element) -> str:
        """Generate @ref for an element."""
        self._ref_counter += 1
        ref = f"@g{self._ref_counter}"
        self._element_cache[ref] = element
        return ref
    
    def resolve_ref(self, ref: str):
        """Resolve @ref to AXUIElement."""
        if ref in self._element_cache:
            return self._element_cache[ref]
        return None
    
    def clear_cache(self):
        """Clear element cache (call before new snapshot)."""
        self._element_cache = {}
        self._ref_counter = 0
    
    def reset(self):
        """Reset session."""
        self.state = {
            "app": None,
            "pid": None,
            "window": None,
            "last_snapshot": None,
            "history": []
        }
        self._element_cache = {}
        self._ref_counter = 0
        self._save_state()


class MacOSGUI:
    """macOS GUI automation via Accessibility APIs."""
    
    def __init__(self, session: GUISession):
        self.session = session
        self.workspace = NSWorkspace.sharedWorkspace()
    
    def check_permissions(self) -> dict:
        """Check accessibility permissions."""
        trusted = AXIsProcessTrusted()
        return {
            "accessibility": bool(trusted),
            "message": "Granted" if trusted else "Please enable in System Settings > Privacy & Security > Accessibility"
        }
    
    def get_running_apps(self) -> list:
        """Get list of running applications."""
        apps = []
        for app in self.workspace.runningApplications():
            if not app.isHidden() and app.activationPolicy() == 0:  # Regular apps
                apps.append({
                    "name": app.localizedName(),
                    "pid": app.processIdentifier(),
                    "bundle": app.bundleIdentifier() or "",
                    "active": app.isActive()
                })
        return sorted(apps, key=lambda x: x["name"].lower())
    
    def get_frontmost_app(self) -> dict:
        """Get frontmost application."""
        app = self.workspace.frontmostApplication()
        if app:
            return {
                "name": app.localizedName(),
                "pid": app.processIdentifier(),
                "bundle": app.bundleIdentifier() or ""
            }
        return None
    
    def find_app(self, name_or_bundle: str) -> Optional[NSRunningApplication]:
        """Find running app by name or bundle ID."""
        for app in self.workspace.runningApplications():
            if app.localizedName() == name_or_bundle:
                return app
            if app.bundleIdentifier() == name_or_bundle:
                return app
        # Fuzzy match
        name_lower = name_or_bundle.lower()
        for app in self.workspace.runningApplications():
            if name_lower in app.localizedName().lower():
                return app
        return None
    
    def open_app(self, name_or_bundle: str) -> dict:
        """Open application."""
        # Try to find already running
        app = self.find_app(name_or_bundle)
        if app:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            self.session.set_app(app.localizedName(), app.processIdentifier())
            return {
                "opened": app.localizedName(),
                "pid": app.processIdentifier(),
                "already_running": True
            }
        
        # Try to launch
        success = self.workspace.launchApplication_(name_or_bundle)
        if success:
            time.sleep(0.5)  # Wait for launch
            app = self.find_app(name_or_bundle)
            if app:
                self.session.set_app(app.localizedName(), app.processIdentifier())
                return {
                    "opened": app.localizedName(),
                    "pid": app.processIdentifier(),
                    "already_running": False
                }
        
        return None
    
    def focus_app(self, name_or_bundle: str) -> dict:
        """Focus/activate application."""
        app = self.find_app(name_or_bundle)
        if not app:
            return None
        
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        self.session.set_app(app.localizedName(), app.processIdentifier())
        return {
            "focused": app.localizedName(),
            "pid": app.processIdentifier()
        }
    
    def quit_app(self, name_or_bundle: str, force: bool = False) -> dict:
        """Quit application."""
        app = self.find_app(name_or_bundle)
        if not app:
            return None
        
        name = app.localizedName()
        if force:
            app.forceTerminate()
        else:
            app.terminate()
        
        return {"quit": name, "force": force}
    
    def _get_ax_app(self, pid: int = None):
        """Get AXUIElement for application."""
        if pid is None:
            pid = self.session.state.get("pid")
        if pid is None:
            app = self.workspace.frontmostApplication()
            if app:
                pid = app.processIdentifier()
        if pid:
            return AXUIElementCreateApplication(pid)
        return None
    
    def _get_attribute(self, element, attr: str):
        """Get attribute from AXUIElement."""
        err, value = AXUIElementCopyAttributeValue(element, attr, None)
        if err == 0:
            return value
        return None
    
    def _get_attributes(self, element) -> list:
        """Get all attribute names for element."""
        err, names = AXUIElementCopyAttributeNames(element, None)
        if err == 0 and names:
            return list(names)
        return []
    
    def _get_actions(self, element) -> list:
        """Get available actions for element."""
        err, actions = AXUIElementCopyActionNames(element, None)
        if err == 0 and actions:
            return list(actions)
        return []
    
    def _element_to_dict(self, element, depth: int = 0, max_depth: int = 10, 
                         interactive_only: bool = False) -> Optional[dict]:
        """Convert AXUIElement to dictionary with @ref."""
        if depth > max_depth:
            return None
        
        role = self._get_attribute(element, "AXRole") or ""
        subrole = self._get_attribute(element, "AXSubrole") or ""
        
        # Skip non-interactive if filtering
        interactive_roles = {
            "AXButton", "AXTextField", "AXTextArea", "AXCheckBox", "AXRadioButton",
            "AXPopUpButton", "AXComboBox", "AXSlider", "AXStepper", "AXTable",
            "AXList", "AXOutline", "AXRow", "AXCell", "AXMenuItem", "AXMenu",
            "AXLink", "AXTab", "AXTabGroup", "AXDisclosureTriangle"
        }
        
        is_interactive = role in interactive_roles
        
        # Get basic attributes
        label = self._get_attribute(element, "AXTitle") or \
                self._get_attribute(element, "AXDescription") or \
                self._get_attribute(element, "AXLabel") or ""
        value = self._get_attribute(element, "AXValue")
        enabled = self._get_attribute(element, "AXEnabled")
        focused = self._get_attribute(element, "AXFocused")
        
        # Position and size
        position = self._get_attribute(element, "AXPosition")
        size = self._get_attribute(element, "AXSize")
        
        pos = None
        sz = None
        if position:
            try:
                pos = [int(position.x), int(position.y)]
            except:
                pass
        if size:
            try:
                sz = [int(size.width), int(size.height)]
            except:
                pass
        
        # Get actions
        actions = self._get_actions(element)
        
        # Generate ref
        ref = self.session.get_ref(element)
        
        # Build element dict
        elem_dict = {
            "ref": ref,
            "role": role.replace("AX", "").lower() if role else "",
        }
        
        if subrole:
            elem_dict["subrole"] = subrole.replace("AX", "").lower()
        if label:
            elem_dict["label"] = str(label)
        if value is not None:
            elem_dict["value"] = str(value) if not isinstance(value, (int, float, bool)) else value
        if enabled is not None:
            elem_dict["enabled"] = bool(enabled)
        if focused:
            elem_dict["focused"] = True
        if pos:
            elem_dict["position"] = pos
        if sz:
            elem_dict["size"] = sz
        if actions:
            elem_dict["actions"] = [a.replace("AX", "").lower() for a in actions]
        
        # Get children
        children = self._get_attribute(element, "AXChildren")
        if children and depth < max_depth:
            child_dicts = []
            for child in children:
                child_dict = self._element_to_dict(
                    child, depth + 1, max_depth, interactive_only
                )
                if child_dict:
                    if interactive_only:
                        # Include if interactive or has interactive children
                        if child_dict.get("_has_interactive") or \
                           child_dict["role"] in [r.replace("AX", "").lower() for r in interactive_roles]:
                            child_dicts.append(child_dict)
                    else:
                        child_dicts.append(child_dict)
            
            if child_dicts:
                elem_dict["children"] = [c["ref"] for c in child_dicts]
                elem_dict["_children_data"] = child_dicts
        
        # Mark if has interactive descendants
        if is_interactive or any(c.get("_has_interactive") for c in elem_dict.get("_children_data", [])):
            elem_dict["_has_interactive"] = True
        
        return elem_dict
    
    def _flatten_elements(self, elem_dict: dict) -> list:
        """Flatten nested element tree to list."""
        elements = []
        
        # Copy without nested children data
        elem_copy = {k: v for k, v in elem_dict.items() 
                     if k not in ("_children_data", "_has_interactive")}
        elements.append(elem_copy)
        
        # Recurse
        for child in elem_dict.get("_children_data", []):
            elements.extend(self._flatten_elements(child))
        
        return elements
    
    def snapshot(self, app_name: str = None, interactive_only: bool = False,
                 max_depth: int = 10, window_index: int = 0) -> dict:
        """Take snapshot of application UI."""
        # Clear cache for fresh refs
        self.session.clear_cache()
        
        # Get target app
        if app_name:
            app = self.find_app(app_name)
            if not app:
                return None
            pid = app.processIdentifier()
            name = app.localizedName()
        else:
            app = self.workspace.frontmostApplication()
            if not app:
                return None
            pid = app.processIdentifier()
            name = app.localizedName()
        
        self.session.set_app(name, pid)
        ax_app = AXUIElementCreateApplication(pid)
        
        # Get windows
        windows = self._get_attribute(ax_app, "AXWindows") or []
        if not windows:
            # Some apps use AXMainWindow
            main_window = self._get_attribute(ax_app, "AXMainWindow")
            if main_window:
                windows = [main_window]
        
        if not windows:
            return {
                "app": name,
                "pid": pid,
                "bundle": app.bundleIdentifier() or "",
                "window": None,
                "elements": [],
                "warning": "No windows found"
            }
        
        # Get target window
        if window_index >= len(windows):
            window_index = 0
        window = windows[window_index]
        
        window_title = self._get_attribute(window, "AXTitle") or "Untitled"
        window_pos = self._get_attribute(window, "AXPosition")
        window_size = self._get_attribute(window, "AXSize")
        
        # Build element tree
        tree = self._element_to_dict(window, 0, max_depth, interactive_only)
        elements = self._flatten_elements(tree) if tree else []
        
        # Find focused element
        focused_element = self._get_attribute(ax_app, "AXFocusedUIElement")
        focused_ref = None
        if focused_element:
            for elem in elements:
                if elem.get("focused"):
                    focused_ref = elem["ref"]
                    break
        
        result = {
            "app": name,
            "pid": pid,
            "bundle": app.bundleIdentifier() or "",
            "window": {
                "title": window_title,
                "index": window_index,
                "position": [int(window_pos.x), int(window_pos.y)] if window_pos else None,
                "size": [int(window_size.width), int(window_size.height)] if window_size else None
            },
            "elements": elements,
            "element_count": len(elements),
            "focused": focused_ref,
            "timestamp": datetime.now().isoformat()
        }
        
        self.session.state["last_snapshot"] = result["timestamp"]
        self.session._save_state()
        
        return result
    
    def click(self, ref: str, action: str = "press") -> dict:
        """Click element by ref."""
        element = self.session.resolve_ref(ref)
        if not element:
            return None
        
        # Map action names
        action_map = {
            "press": "AXPress",
            "click": "AXPress",
            "showmenu": "AXShowMenu",
            "pick": "AXPick",
            "increment": "AXIncrement",
            "decrement": "AXDecrement",
            "confirm": "AXConfirm",
            "cancel": "AXCancel",
            "expand": "AXExpand",
            "collapse": "AXCollapse"
        }
        
        ax_action = action_map.get(action.lower(), f"AX{action.title()}")
        
        err = AXUIElementPerformAction(element, ax_action)
        if err != 0:
            # Try AXPress as fallback
            if ax_action != "AXPress":
                err = AXUIElementPerformAction(element, "AXPress")
        
        if err == 0:
            self.session.add_history(f"click {ref}")
            return {"clicked": ref, "action": action}
        
        return {"error": f"Action failed with code {err}", "ref": ref}
    
    def type_text(self, text: str, ref: str = None) -> dict:
        """Type text into element or focused element."""
        if ref:
            element = self.session.resolve_ref(ref)
            if element:
                # Focus the element first
                AXUIElementSetAttributeValue(element, "AXFocused", True)
                time.sleep(0.1)
        
        # Use AppleScript for reliable typing
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        subprocess.run(["osascript", "-e", script], capture_output=True)
        
        self.session.add_history(f"type '{text[:20]}...' " + (f"into {ref}" if ref else ""))
        return {"typed": text, "ref": ref}
    
    def fill(self, ref: str, text: str) -> dict:
        """Clear and fill text field."""
        element = self.session.resolve_ref(ref)
        if not element:
            return None
        
        # Try to set value directly
        err = AXUIElementSetAttributeValue(element, "AXValue", text)
        if err == 0:
            self.session.add_history(f"fill {ref} with '{text[:20]}...'")
            return {"filled": ref, "value": text}
        
        # Fallback: focus, select all, type
        AXUIElementSetAttributeValue(element, "AXFocused", True)
        time.sleep(0.1)
        
        # Cmd+A to select all
        subprocess.run(["osascript", "-e", 
            'tell application "System Events" to keystroke "a" using command down'], 
            capture_output=True)
        time.sleep(0.05)
        
        # Type new text
        return self.type_text(text)
    
    def press_key(self, key: str) -> dict:
        """Press key or key combination."""
        # Parse key combo (e.g., "Cmd+S", "Cmd+Shift+4")
        parts = key.replace("+", " ").split()
        
        modifiers = []
        key_char = parts[-1] if parts else key
        
        modifier_map = {
            "cmd": "command down",
            "command": "command down",
            "ctrl": "control down",
            "control": "control down",
            "alt": "option down",
            "option": "option down",
            "shift": "shift down"
        }
        
        for part in parts[:-1]:
            mod = modifier_map.get(part.lower())
            if mod:
                modifiers.append(mod)
        
        # Special keys
        special_keys = {
            "enter": "return",
            "return": "return",
            "tab": "tab",
            "escape": "escape",
            "esc": "escape",
            "delete": "delete",
            "backspace": "delete",
            "up": "up arrow",
            "down": "down arrow",
            "left": "left arrow",
            "right": "right arrow",
            "space": "space",
            "home": "home",
            "end": "end",
            "pageup": "page up",
            "pagedown": "page down",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
            "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
            "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12"
        }
        
        key_lower = key_char.lower()
        if key_lower in special_keys:
            # Key code press
            if modifiers:
                script = f'tell application "System Events" to key code {self._get_key_code(special_keys[key_lower])} using {{{", ".join(modifiers)}}}'
            else:
                script = f'tell application "System Events" to key code {self._get_key_code(special_keys[key_lower])}'
        else:
            # Regular keystroke
            if modifiers:
                script = f'tell application "System Events" to keystroke "{key_char}" using {{{", ".join(modifiers)}}}'
            else:
                script = f'tell application "System Events" to keystroke "{key_char}"'
        
        subprocess.run(["osascript", "-e", script], capture_output=True)
        self.session.add_history(f"press {key}")
        return {"pressed": key}
    
    def _get_key_code(self, key_name: str) -> int:
        """Get macOS key code for special key."""
        codes = {
            "return": 36, "tab": 48, "space": 49, "delete": 51,
            "escape": 53, "up arrow": 126, "down arrow": 125,
            "left arrow": 123, "right arrow": 124,
            "home": 115, "end": 119, "page up": 116, "page down": 121,
            "F1": 122, "F2": 120, "F3": 99, "F4": 118,
            "F5": 96, "F6": 97, "F7": 98, "F8": 100,
            "F9": 101, "F10": 109, "F11": 103, "F12": 111
        }
        return codes.get(key_name, 36)
    
    def get_element_attr(self, ref: str, attr: str) -> dict:
        """Get attribute from element."""
        element = self.session.resolve_ref(ref)
        if not element:
            return None
        
        attr_map = {
            "label": "AXTitle",
            "title": "AXTitle",
            "value": "AXValue",
            "enabled": "AXEnabled",
            "focused": "AXFocused",
            "checked": "AXValue",  # For checkboxes
            "selected": "AXSelected",
            "position": "AXPosition",
            "size": "AXSize",
            "description": "AXDescription",
            "help": "AXHelp",
            "role": "AXRole"
        }
        
        ax_attr = attr_map.get(attr.lower(), f"AX{attr.title()}")
        value = self._get_attribute(element, ax_attr)
        
        # Convert position/size
        if attr.lower() == "position" and value:
            value = [int(value.x), int(value.y)]
        elif attr.lower() == "size" and value:
            value = [int(value.width), int(value.height)]
        elif value is not None:
            value = str(value) if not isinstance(value, (int, float, bool)) else value
        
        return {"ref": ref, "attribute": attr, "value": value}
    
    def inspect_element(self, ref: str) -> dict:
        """Get all attributes for element."""
        element = self.session.resolve_ref(ref)
        if not element:
            return None
        
        attrs = self._get_attributes(element)
        result = {"ref": ref, "attributes": {}}
        
        for attr in attrs:
            value = self._get_attribute(element, attr)
            if value is not None:
                # Convert special types
                attr_name = attr.replace("AX", "").lower()
                if attr in ("AXPosition",):
                    try:
                        value = [int(value.x), int(value.y)]
                    except:
                        continue
                elif attr in ("AXSize",):
                    try:
                        value = [int(value.width), int(value.height)]
                    except:
                        continue
                elif attr == "AXChildren":
                    value = len(value) if value else 0
                elif not isinstance(value, (int, float, bool, str)):
                    value = str(value)
                
                result["attributes"][attr_name] = value
        
        result["actions"] = self._get_actions(element)
        return result
    
    def find_elements(self, role: str = None, label: str = None, 
                      contains: str = None) -> dict:
        """Find elements matching criteria."""
        # Need a snapshot first
        if not self.session._element_cache:
            self.snapshot()
        
        matches = []
        for ref, element in self.session._element_cache.items():
            elem_role = self._get_attribute(element, "AXRole") or ""
            elem_label = self._get_attribute(element, "AXTitle") or \
                        self._get_attribute(element, "AXDescription") or ""
            
            if role and role.lower() not in elem_role.lower():
                continue
            if label and label.lower() != elem_label.lower():
                continue
            if contains and contains.lower() not in elem_label.lower():
                continue
            
            matches.append({
                "ref": ref,
                "role": elem_role.replace("AX", "").lower(),
                "label": str(elem_label)
            })
        
        return {"matches": matches, "count": len(matches)}
    
    def menu_click(self, menu_path: list) -> dict:
        """Click menu item by path (e.g., ["File", "Save As"])."""
        if not menu_path:
            return None
        
        app = self.workspace.frontmostApplication()
        if not app:
            return None
        
        app_name = app.localizedName()
        
        # Build AppleScript for menu navigation
        if len(menu_path) == 1:
            script = f'''
tell application "{app_name}" to activate
tell application "System Events"
    tell process "{app_name}"
        click menu bar item "{menu_path[0]}" of menu bar 1
    end tell
end tell
'''
        elif len(menu_path) == 2:
            script = f'''
tell application "{app_name}" to activate
tell application "System Events"
    tell process "{app_name}"
        click menu item "{menu_path[1]}" of menu "{menu_path[0]}" of menu bar 1
    end tell
end tell
'''
        else:
            # Submenu
            script = f'''
tell application "{app_name}" to activate
tell application "System Events"
    tell process "{app_name}"
        click menu item "{menu_path[-1]}" of menu "{menu_path[-2]}" of menu item "{menu_path[-2]}" of menu "{menu_path[0]}" of menu bar 1
    end tell
end tell
'''
        
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode == 0:
            self.session.add_history(f"menu {' > '.join(menu_path)}")
            return {"clicked": " > ".join(menu_path)}
        
        return {"error": result.stderr.strip(), "menu": menu_path}
    
    def get_menubar(self, menu_name: str = None) -> dict:
        """Get menu bar structure."""
        app = self.workspace.frontmostApplication()
        if not app:
            return None
        
        app_name = app.localizedName()
        pid = app.processIdentifier()
        ax_app = AXUIElementCreateApplication(pid)
        
        menu_bar = self._get_attribute(ax_app, "AXMenuBar")
        if not menu_bar:
            return {"error": "No menu bar found"}
        
        children = self._get_attribute(menu_bar, "AXChildren") or []
        menus = []
        
        for child in children:
            title = self._get_attribute(child, "AXTitle") or ""
            if title:
                menus.append(title)
        
        if menu_name:
            # Get items for specific menu
            for child in children:
                if self._get_attribute(child, "AXTitle") == menu_name:
                    submenu = self._get_attribute(child, "AXChildren")
                    if submenu:
                        submenu = submenu[0] if submenu else None
                        if submenu:
                            items = self._get_attribute(submenu, "AXChildren") or []
                            menu_items = []
                            for item in items:
                                item_title = self._get_attribute(item, "AXTitle")
                                if item_title:
                                    menu_items.append(item_title)
                                else:
                                    menu_items.append("---")  # Separator
                            return {"menu": menu_name, "items": menu_items}
        
        return {"menus": menus}
    
    def window_action(self, app_name: str, action: str, 
                      title: str = None, index: int = 0) -> dict:
        """Perform window action."""
        app = self.find_app(app_name)
        if not app:
            return None
        
        name = app.localizedName()
        
        actions = {
            "minimize": f'tell application "{name}" to set miniaturized of window {index + 1} to true',
            "unminimize": f'tell application "{name}" to set miniaturized of window {index + 1} to false',
            "maximize": f'''
tell application "{name}" to activate
tell application "System Events"
    tell process "{name}"
        click button 2 of window {index + 1}
    end tell
end tell
''',
            "fullscreen": f'''
tell application "{name}" to activate
tell application "System Events"
    tell process "{name}"
        keystroke "f" using {{command down, control down}}
    end tell
end tell
''',
            "close": f'tell application "{name}" to close window {index + 1}',
            "center": f'''
tell application "{name}"
    set bounds of window {index + 1} to {{200, 200, 1000, 800}}
end tell
'''
        }
        
        script = actions.get(action.lower())
        if not script:
            return {"error": f"Unknown action: {action}"}
        
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if result.returncode == 0:
            return {"window": name, "action": action}
        
        return {"error": result.stderr.strip()}
    
    def window_move(self, app_name: str, x: int, y: int) -> dict:
        """Move window to position."""
        app = self.find_app(app_name)
        if not app:
            return None
        
        name = app.localizedName()
        pid = app.processIdentifier()
        ax_app = AXUIElementCreateApplication(pid)
        
        windows = self._get_attribute(ax_app, "AXWindows") or []
        if windows:
            import Quartz
            pos = Quartz.CGPointMake(x, y)
            AXUIElementSetAttributeValue(windows[0], "AXPosition", pos)
            return {"moved": name, "position": [x, y]}
        
        return {"error": "No window found"}
    
    def window_resize(self, app_name: str, width: int, height: int) -> dict:
        """Resize window."""
        app = self.find_app(app_name)
        if not app:
            return None
        
        name = app.localizedName()
        pid = app.processIdentifier()
        ax_app = AXUIElementCreateApplication(pid)
        
        windows = self._get_attribute(ax_app, "AXWindows") or []
        if windows:
            import Quartz
            size = Quartz.CGSizeMake(width, height)
            AXUIElementSetAttributeValue(windows[0], "AXSize", size)
            return {"resized": name, "size": [width, height]}
        
        return {"error": "No window found"}
    
    def get_windows(self, app_name: str = None) -> dict:
        """List windows for app or all apps."""
        windows = []
        
        if app_name:
            app = self.find_app(app_name)
            if not app:
                return None
            apps = [app]
        else:
            apps = [a for a in self.workspace.runningApplications() 
                    if a.activationPolicy() == 0]
        
        for app in apps:
            pid = app.processIdentifier()
            ax_app = AXUIElementCreateApplication(pid)
            wins = self._get_attribute(ax_app, "AXWindows") or []
            
            for i, win in enumerate(wins):
                title = self._get_attribute(win, "AXTitle") or "Untitled"
                pos = self._get_attribute(win, "AXPosition")
                size = self._get_attribute(win, "AXSize")
                
                windows.append({
                    "app": app.localizedName(),
                    "index": i,
                    "title": title,
                    "position": [int(pos.x), int(pos.y)] if pos else None,
                    "size": [int(size.width), int(size.height)] if size else None
                })
        
        return {"windows": windows, "count": len(windows)}
    
    def screenshot(self, app_name: str = None, output_path: str = None,
                   ref: str = None, annotate: bool = False) -> dict:
        """Take screenshot of app, window, or element."""
        if output_path is None:
            output_path = f"/tmp/agent-gui-screenshot-{int(time.time())}.png"
        
        if ref:
            # Screenshot element bounds
            element = self.session.resolve_ref(ref)
            if element:
                pos = self._get_attribute(element, "AXPosition")
                size = self._get_attribute(element, "AXSize")
                if pos and size:
                    x, y = int(pos.x), int(pos.y)
                    w, h = int(size.width), int(size.height)
                    subprocess.run([
                        "screencapture", "-R", f"{x},{y},{w},{h}", output_path
                    ], capture_output=True)
                    return {"screenshot": output_path, "element": ref, "bounds": [x, y, w, h]}
        
        if app_name:
            # Screenshot specific app window
            app = self.find_app(app_name)
            if app:
                # Activate and capture
                app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                time.sleep(0.3)
                
                # Try to get window ID
                script = f'tell application "{app.localizedName()}" to id of window 1'
                result = subprocess.run(["osascript", "-e", script], 
                                       capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    window_id = result.stdout.strip()
                    subprocess.run(["screencapture", "-l", window_id, output_path],
                                  capture_output=True)
                else:
                    # Fallback: capture focused window
                    subprocess.run(["screencapture", "-w", output_path],
                                  capture_output=True)
                
                return {"screenshot": output_path, "app": app_name}
        
        # Full screen
        subprocess.run(["screencapture", output_path], capture_output=True)
        return {"screenshot": output_path}
    
    def wait_for_element(self, ref: str = None, label: str = None,
                         role: str = None, timeout: float = 30,
                         condition: str = "exists") -> dict:
        """Wait for element condition."""
        start = time.time()
        
        while time.time() - start < timeout:
            if ref:
                element = self.session.resolve_ref(ref)
                if element:
                    if condition == "exists":
                        return {"found": ref}
                    elif condition == "enabled":
                        if self._get_attribute(element, "AXEnabled"):
                            return {"found": ref, "enabled": True}
                    elif condition == "visible":
                        pos = self._get_attribute(element, "AXPosition")
                        if pos:
                            return {"found": ref, "visible": True}
            else:
                # Search by label/role
                self.snapshot()
                result = self.find_elements(role=role, label=label)
                if result["count"] > 0:
                    return {"found": result["matches"][0]["ref"], "matches": result["count"]}
            
            time.sleep(0.5)
        
        return None  # Timeout
    
    def wait_for_window(self, title: str = None, timeout: float = 30) -> dict:
        """Wait for window to appear."""
        start = time.time()
        
        while time.time() - start < timeout:
            windows = self.get_windows()
            for win in windows.get("windows", []):
                if title is None or title.lower() in win["title"].lower():
                    return {"found": win}
            
            time.sleep(0.5)
        
        return None
    
    def dialog_detect(self) -> dict:
        """Detect active dialog/sheet."""
        app = self.workspace.frontmostApplication()
        if not app:
            return None
        
        pid = app.processIdentifier()
        ax_app = AXUIElementCreateApplication(pid)
        
        # Check for sheets
        windows = self._get_attribute(ax_app, "AXWindows") or []
        for window in windows:
            sheets = self._get_attribute(window, "AXSheets") or []
            if sheets:
                sheet = sheets[0]
                title = self._get_attribute(sheet, "AXTitle") or ""
                
                # Find buttons
                buttons = []
                children = self._get_attribute(sheet, "AXChildren") or []
                for child in children:
                    role = self._get_attribute(child, "AXRole")
                    if role == "AXButton":
                        btn_title = self._get_attribute(child, "AXTitle") or ""
                        if btn_title:
                            buttons.append(btn_title)
                
                return {
                    "type": "sheet",
                    "title": title,
                    "buttons": buttons,
                    "app": app.localizedName()
                }
        
        # Check for dialogs (separate windows with modal behavior)
        for window in windows:
            role = self._get_attribute(window, "AXRole")
            subrole = self._get_attribute(window, "AXSubrole")
            
            if subrole == "AXDialog" or subrole == "AXStandardWindow":
                title = self._get_attribute(window, "AXTitle") or ""
                
                # Could be a dialog - look for buttons
                buttons = []
                self._find_buttons(window, buttons)
                
                if buttons:
                    return {
                        "type": "dialog",
                        "title": title,
                        "buttons": buttons,
                        "app": app.localizedName()
                    }
        
        return {"type": None, "message": "No dialog detected"}
    
    def _find_buttons(self, element, buttons: list, depth: int = 0):
        """Recursively find buttons in element tree."""
        if depth > 5:
            return
        
        role = self._get_attribute(element, "AXRole")
        if role == "AXButton":
            title = self._get_attribute(element, "AXTitle") or ""
            if title and title not in buttons:
                buttons.append(title)
        
        children = self._get_attribute(element, "AXChildren") or []
        for child in children:
            self._find_buttons(child, buttons, depth + 1)
    
    def dialog_click(self, button: str) -> dict:
        """Click button in active dialog."""
        app = self.workspace.frontmostApplication()
        if not app:
            return None
        
        name = app.localizedName()
        
        # Use AppleScript for reliable dialog button clicking
        script = f'''
tell application "System Events"
    tell process "{name}"
        click button "{button}" of sheet 1 of window 1
    end tell
end tell
'''
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        
        if result.returncode != 0:
            # Try window button
            script = f'''
tell application "System Events"
    tell process "{name}"
        click button "{button}" of window 1
    end tell
end tell
'''
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        
        if result.returncode == 0:
            self.session.add_history(f"dialog click {button}")
            return {"clicked": button}
        
        return {"error": result.stderr.strip()}
    
    def get_clipboard(self) -> dict:
        """Get clipboard contents."""
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        return {
            "text": result.stdout,
            "length": len(result.stdout)
        }
    
    def set_clipboard(self, text: str) -> dict:
        """Set clipboard contents."""
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode())
        return {"copied": len(text)}


def main():
    if not MACOS_AVAILABLE:
        error("macOS frameworks not available", EXIT_PERMISSION_DENIED)
    
    session = GUISession()
    gui = MacOSGUI(session)
    
    args = sys.argv[1:]
    if not args:
        output({"error": "No command specified", "usage": "agent-gui <command> [args]"}, EXIT_UNKNOWN)
    
    cmd = args[0].lower()
    
    # Permission check
    if cmd == "--check-permissions" or cmd == "permissions":
        output(gui.check_permissions())
    
    # Status
    elif cmd == "status":
        perms = gui.check_permissions()
        output({
            "session": session.state,
            "permissions": perms,
            "cached_elements": len(session._element_cache)
        })
    
    # Reset
    elif cmd == "reset":
        session.reset()
        output({"reset": True})
    
    # Apps
    elif cmd == "apps" or cmd == "list":
        apps = gui.get_running_apps()
        frontmost = gui.get_frontmost_app()
        output({"apps": apps, "frontmost": frontmost})
    
    elif cmd == "frontmost":
        result = gui.get_frontmost_app()
        if result:
            output(result)
        else:
            error("No frontmost app", EXIT_APP_NOT_FOUND)
    
    elif cmd == "open":
        if len(args) < 2:
            error("Usage: agent-gui open <app>", EXIT_UNKNOWN)
        result = gui.open_app(args[1])
        if result:
            output(result)
        else:
            error(f"Could not open: {args[1]}", EXIT_APP_NOT_FOUND)
    
    elif cmd == "focus":
        if len(args) < 2:
            error("Usage: agent-gui focus <app>", EXIT_UNKNOWN)
        result = gui.focus_app(args[1])
        if result:
            output(result)
        else:
            error(f"App not found: {args[1]}", EXIT_APP_NOT_FOUND)
    
    elif cmd == "quit":
        if len(args) < 2:
            error("Usage: agent-gui quit <app> [--force]", EXIT_UNKNOWN)
        force = "--force" in args
        result = gui.quit_app(args[1], force=force)
        if result:
            output(result)
        else:
            error(f"App not found: {args[1]}", EXIT_APP_NOT_FOUND)
    
    # Snapshot
    elif cmd == "snapshot":
        app_name = None
        interactive = "-i" in args or "--interactive" in args
        max_depth = 10
        window_idx = 0
        
        for i, arg in enumerate(args[1:], 1):
            if arg in ("-i", "--interactive", "--json", "--tree"):
                continue
            if arg == "-d" and i + 1 < len(args):
                max_depth = int(args[i + 1])
            elif arg == "--window" and i + 1 < len(args):
                window_idx = int(args[i + 1])
            elif not arg.startswith("-"):
                app_name = arg
        
        result = gui.snapshot(app_name, interactive_only=interactive, 
                             max_depth=max_depth, window_index=window_idx)
        if result:
            output(result)
        else:
            error("Could not take snapshot", EXIT_APP_NOT_FOUND)
    
    # Click
    elif cmd == "click":
        if len(args) < 2:
            error("Usage: agent-gui click <@ref>", EXIT_UNKNOWN)
        ref = args[1]
        action = "press"
        if len(args) > 2:
            action = args[2]
        result = gui.click(ref, action)
        if result:
            output(result)
        else:
            error(f"Element not found: {ref}", EXIT_ELEMENT_NOT_FOUND)
    
    elif cmd == "dblclick":
        if len(args) < 2:
            error("Usage: agent-gui dblclick <@ref>", EXIT_UNKNOWN)
        ref = args[1]
        # Double click via press twice
        gui.click(ref)
        time.sleep(0.05)
        result = gui.click(ref)
        if result:
            output({"doubleclicked": ref})
        else:
            error(f"Element not found: {ref}", EXIT_ELEMENT_NOT_FOUND)
    
    elif cmd == "rightclick":
        if len(args) < 2:
            error("Usage: agent-gui rightclick <@ref>", EXIT_UNKNOWN)
        result = gui.click(args[1], "showmenu")
        if result:
            output(result)
        else:
            error(f"Element not found: {args[1]}", EXIT_ELEMENT_NOT_FOUND)
    
    # Type
    elif cmd == "type":
        if len(args) < 2:
            error("Usage: agent-gui type [<@ref>] <text>", EXIT_UNKNOWN)
        
        if args[1].startswith("@"):
            ref = args[1]
            text = " ".join(args[2:])
            result = gui.type_text(text, ref)
        else:
            text = " ".join(args[1:])
            result = gui.type_text(text)
        output(result)
    
    elif cmd == "fill":
        if len(args) < 3:
            error("Usage: agent-gui fill <@ref> <text>", EXIT_UNKNOWN)
        ref = args[1]
        text = " ".join(args[2:])
        result = gui.fill(ref, text)
        if result:
            output(result)
        else:
            error(f"Element not found: {ref}", EXIT_ELEMENT_NOT_FOUND)
    
    # Press key
    elif cmd == "press":
        if len(args) < 2:
            error("Usage: agent-gui press <key>", EXIT_UNKNOWN)
        key = " ".join(args[1:])
        result = gui.press_key(key)
        output(result)
    
    elif cmd == "keys":
        for key in args[1:]:
            gui.press_key(key)
            time.sleep(0.1)
        output({"pressed": args[1:]})
    
    # Get attribute
    elif cmd == "get":
        if len(args) < 3:
            error("Usage: agent-gui get <@ref> <attribute>", EXIT_UNKNOWN)
        result = gui.get_element_attr(args[1], args[2])
        if result:
            output(result)
        else:
            error(f"Element not found: {args[1]}", EXIT_ELEMENT_NOT_FOUND)
    
    # Inspect
    elif cmd == "inspect":
        if len(args) < 2:
            error("Usage: agent-gui inspect <@ref>", EXIT_UNKNOWN)
        result = gui.inspect_element(args[1])
        if result:
            output(result)
        else:
            error(f"Element not found: {args[1]}", EXIT_ELEMENT_NOT_FOUND)
    
    # Find
    elif cmd == "find":
        role = None
        label = None
        contains = None
        
        i = 1
        while i < len(args):
            if args[i] == "--role" and i + 1 < len(args):
                role = args[i + 1]
                i += 2
            elif args[i] == "--label" and i + 1 < len(args):
                label = args[i + 1]
                i += 2
            elif args[i] == "--contains" and i + 1 < len(args):
                contains = args[i + 1]
                i += 2
            else:
                i += 1
        
        result = gui.find_elements(role=role, label=label, contains=contains)
        output(result)
    
    # Count
    elif cmd == "count":
        role = None
        if len(args) > 1 and args[1] == "--role":
            role = args[2] if len(args) > 2 else None
        result = gui.find_elements(role=role)
        output({"count": result["count"]})
    
    # Menu
    elif cmd == "menu":
        if len(args) < 2:
            error("Usage: agent-gui menu <Menu> [<Item>] [<SubItem>]", EXIT_UNKNOWN)
        menu_path = args[1:]
        result = gui.menu_click(menu_path)
        if result and "error" not in result:
            output(result)
        else:
            error(result.get("error", "Menu action failed"), EXIT_ACTION_FAILED)
    
    elif cmd == "menubar":
        menu_name = None
        if len(args) > 1 and not args[1].startswith("--"):
            menu_name = args[1]
        result = gui.get_menubar(menu_name)
        if result:
            output(result)
        else:
            error("Could not get menu bar", EXIT_ACTION_FAILED)
    
    # Window
    elif cmd == "window" or cmd == "win":
        if len(args) < 2:
            error("Usage: agent-gui window <action> <app> [args]", EXIT_UNKNOWN)
        
        action = args[1]
        
        if action == "list":
            app_name = args[2] if len(args) > 2 else None
            result = gui.get_windows(app_name)
            if result:
                output(result)
            else:
                error(f"App not found: {app_name}", EXIT_APP_NOT_FOUND)
        
        elif action == "info":
            app_name = args[2] if len(args) > 2 else None
            result = gui.get_windows(app_name)
            if result and result["windows"]:
                output(result["windows"][0])
            else:
                error("No window found", EXIT_WINDOW_NOT_FOUND)
        
        elif action in ("minimize", "maximize", "fullscreen", "close", "center"):
            if len(args) < 3:
                error(f"Usage: agent-gui window {action} <app>", EXIT_UNKNOWN)
            result = gui.window_action(args[2], action)
            if result and "error" not in result:
                output(result)
            else:
                error(result.get("error", "Window action failed"), EXIT_ACTION_FAILED)
        
        elif action == "move":
            if len(args) < 5:
                error("Usage: agent-gui window move <app> <x> <y>", EXIT_UNKNOWN)
            result = gui.window_move(args[2], int(args[3]), int(args[4]))
            if result and "error" not in result:
                output(result)
            else:
                error(result.get("error", "Move failed"), EXIT_ACTION_FAILED)
        
        elif action == "resize":
            if len(args) < 5:
                error("Usage: agent-gui window resize <app> <width> <height>", EXIT_UNKNOWN)
            result = gui.window_resize(args[2], int(args[3]), int(args[4]))
            if result and "error" not in result:
                output(result)
            else:
                error(result.get("error", "Resize failed"), EXIT_ACTION_FAILED)
        
        else:
            error(f"Unknown window action: {action}", EXIT_UNKNOWN)
    
    elif cmd == "windows":
        app_name = None
        if len(args) > 1 and not args[1].startswith("--"):
            app_name = args[1]
        all_windows = "--all" in args
        
        if all_windows:
            app_name = None
        
        result = gui.get_windows(app_name)
        if result:
            output(result)
        else:
            error("Could not list windows", EXIT_ACTION_FAILED)
    
    # Dialog
    elif cmd == "dialog":
        if len(args) < 2:
            error("Usage: agent-gui dialog <detect|click> [button]", EXIT_UNKNOWN)
        
        sub = args[1]
        if sub == "detect":
            result = gui.dialog_detect()
            output(result)
        elif sub == "click":
            if len(args) < 3:
                error("Usage: agent-gui dialog click <button>", EXIT_UNKNOWN)
            button = args[2]
            if button == "--default":
                # Click first button (usually default)
                dialog = gui.dialog_detect()
                if dialog.get("buttons"):
                    button = dialog["buttons"][-1]  # Last is usually default on macOS
            elif button == "--cancel":
                dialog = gui.dialog_detect()
                if dialog.get("buttons"):
                    for b in dialog["buttons"]:
                        if b.lower() in ("cancel", "don't save", "no"):
                            button = b
                            break
            
            result = gui.dialog_click(button)
            if result and "error" not in result:
                output(result)
            else:
                error(result.get("error", "Dialog click failed"), EXIT_ACTION_FAILED)
        else:
            error(f"Unknown dialog command: {sub}", EXIT_UNKNOWN)
    
    # Screenshot
    elif cmd == "screenshot":
        app_name = None
        output_path = None
        ref = None
        annotate = "--annotate" in args
        
        for i, arg in enumerate(args[1:], 1):
            if arg.startswith("@"):
                ref = arg
            elif arg.startswith("-"):
                continue
            elif "/" in arg or arg.endswith(".png"):
                output_path = arg
            else:
                app_name = arg
        
        result = gui.screenshot(app_name, output_path, ref, annotate)
        output(result)
    
    # Wait
    elif cmd == "wait":
        timeout = 30
        ref = None
        label = None
        role = None
        condition = "exists"
        window_title = None
        
        i = 1
        while i < len(args):
            if args[i].startswith("@"):
                ref = args[i]
            elif args[i] == "--timeout":
                timeout = float(args[i + 1])
                i += 1
            elif args[i] == "--enabled":
                condition = "enabled"
            elif args[i] == "--visible":
                condition = "visible"
            elif args[i] == "--label":
                label = args[i + 1]
                i += 1
            elif args[i] == "--role":
                role = args[i + 1]
                i += 1
            elif args[i] == "--window":
                window_title = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            i += 1
        
        if window_title is not None:
            result = gui.wait_for_window(window_title, timeout)
        else:
            result = gui.wait_for_element(ref, label, role, timeout, condition)
        
        if result:
            output(result)
        else:
            error("Timeout waiting", EXIT_TIMEOUT)
    
    # Clipboard
    elif cmd == "clipboard":
        if len(args) == 1:
            result = gui.get_clipboard()
            output(result)
        else:
            text = " ".join(args[1:])
            result = gui.set_clipboard(text)
            output(result)
    
    # Action
    elif cmd == "action":
        if len(args) < 3:
            error("Usage: agent-gui action <@ref> <action>", EXIT_UNKNOWN)
        result = gui.click(args[1], args[2])
        if result:
            output(result)
        else:
            error(f"Element not found: {args[1]}", EXIT_ELEMENT_NOT_FOUND)
    
    else:
        error(f"Unknown command: {cmd}", EXIT_UNKNOWN)


if __name__ == "__main__":
    main()
