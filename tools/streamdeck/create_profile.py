#!/usr/bin/env python3
"""
Create Stream Deck XL profile for agent-do tools (V3 format).

Generates a complete .sdProfile directory with:
- manifest.json (profile metadata)
- Profiles/<uuid>/manifest.json (page with 32 buttons)
- Profiles/<uuid>/Images/ (icon files)

Usage:
    python create_profile.py

Output:
    <UUID>.sdProfile/ (ready to copy to Stream Deck ProfilesV3)
"""

import json
import os
import shutil
import uuid
import yaml
from pathlib import Path


def generate_uuid() -> str:
    """Generate a UUID string for Stream Deck."""
    return str(uuid.uuid4()).upper()


def generate_action_id() -> str:
    """Generate an action ID (lowercase UUID)."""
    return str(uuid.uuid4()).lower()


def generate_image_id() -> str:
    """Generate an image file ID (uppercase alphanumeric with Z suffix)."""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(26)) + 'Z'


def create_text_action(tool: str, types_text: str, image_filename: str) -> dict:
    """Create a button action configuration for System Text action."""
    return {
        "ActionID": generate_action_id(),
        "LinkedTitle": True,
        "Name": "Text",
        "Plugin": {
            "Name": "Text",
            "UUID": "com.elgato.streamdeck.system.text",
            "Version": "1.0"
        },
        "Resources": None,
        "Settings": {
            "Hotkey": {"KeyModifiers": 0, "QTKeyCode": 33554431, "VKeyCode": -1},
            "isSendingEnter": False,
            "isTypingMode": False,
            "pastedText": types_text
        },
        "State": 0,
        "States": [
            {
                "FontFamily": "",
                "FontSize": 12,
                "FontStyle": "",
                "FontUnderline": False,
                "Image": f"Images/{image_filename}",
                "OutlineThickness": 2,
                "ShowTitle": False,
                "TitleAlignment": "bottom",
                "TitleColor": "#ffffff"
            }
        ],
        "UUID": "com.elgato.streamdeck.system.text"
    }


def main():
    script_dir = Path(__file__).parent
    icons_dir = script_dir / "icons"
    buttons_file = script_dir / "buttons.yaml"

    # Load button definitions
    with open(buttons_file, 'r') as f:
        config = yaml.safe_load(f)

    buttons = config['buttons']

    # Create button lookup by position
    button_map = {}
    for button in buttons:
        pos = (button['row'], button['col'])
        button_map[pos] = button

    # Generate UUIDs
    profile_uuid = generate_uuid()
    page_uuid = generate_uuid()

    # Create output directory with UUID name
    output_dir = script_dir / f"{profile_uuid}.sdProfile"

    # Clean and create output directory
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    # Create directory structure
    (output_dir / "Images").mkdir()
    page_dir = output_dir / "Profiles" / page_uuid
    page_dir.mkdir(parents=True)
    (page_dir / "Images").mkdir()

    # Copy icons and build actions
    actions = {}
    image_map = {}  # tool -> image_filename

    for row in range(8):
        for col in range(4):
            pos = (row, col)
            if pos in button_map:
                button = button_map[pos]
                tool = button['tool']
                types_text = button['types']

                # Generate unique image filename
                image_id = generate_image_id()
                image_filename = f"{image_id}.png"
                image_map[tool] = image_filename

                # Copy icon to page Images directory
                src_icon = icons_dir / f"{tool}.png"
                dst_icon = page_dir / "Images" / image_filename
                if src_icon.exists():
                    shutil.copy(src_icon, dst_icon)

                # Create action
                action = create_text_action(tool, types_text, image_filename)
                actions[f"{row},{col}"] = action

    # Create page manifest
    page_manifest = {
        "Controllers": [
            {
                "Actions": actions,
                "Type": "Keypad"
            }
        ],
        "Icon": "",
        "Name": ""
    }

    # Write page manifest
    page_manifest_path = page_dir / "manifest.json"
    with open(page_manifest_path, 'w') as f:
        json.dump(page_manifest, f, separators=(',', ':'))

    # Create profile manifest (V3 format)
    # Device info for Stream Deck XL - update if using different device
    profile_manifest = {
        "Device": {
            "Model": "20GAT9902",
            "UUID": "@(1)[4057/143/A00NA5353146X0]"
        },
        "Name": "ghostty",
        "AppIdentifier": "com.mitchellh.ghostty",  # Smart Profile for Ghostty
        "Pages": {
            "Current": page_uuid.lower(),
            "Default": page_uuid.lower(),
            "Pages": [page_uuid.lower()]
        },
        "Version": "3.0"
    }

    # Write profile manifest
    profile_manifest_path = output_dir / "manifest.json"
    with open(profile_manifest_path, 'w') as f:
        json.dump(profile_manifest, f, separators=(',', ':'))

    print(f"Created profile: {output_dir.name}")
    print(f"  Profile UUID: {profile_uuid}")
    print(f"  Page UUID: {page_uuid}")
    print(f"  Buttons configured: {len(buttons)}")
    print()
    print("To install:")
    print(f"  1. Copy {output_dir.name} to:")
    print("     ~/Library/Application Support/com.elgato.StreamDeck/ProfilesV3/")
    print("  2. Restart Stream Deck app")
    print("  3. Select 'agent-do' profile from the dropdown")


if __name__ == "__main__":
    main()
