#!/usr/bin/env python3
"""
Create Stream Deck XL profile for Versova skills.

Each button types: use <skill-name> skill to
"""

import json
import os
import shutil
import uuid
import yaml
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow required. pip install Pillow")
    exit(1)

ICON_SIZE = 144
ACCENT_HEIGHT = 8
BG_TOP = (26, 26, 46)
BG_BOTTOM = (15, 15, 26)
TEXT_COLOR = (255, 255, 255)


def hex_to_rgb(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def get_font(size: int):
    font_paths = [
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


def create_icon(text: str, accent_color: str, output_path: Path):
    """Create icon with shortened display name."""
    img = Image.new('RGB', (ICON_SIZE, ICON_SIZE))
    draw = ImageDraw.Draw(img)

    for y in range(ICON_SIZE):
        ratio = y / ICON_SIZE
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (ICON_SIZE, y)], fill=(r, g, b))

    accent_rgb = hex_to_rgb(accent_color)
    draw.rectangle([(0, ICON_SIZE - ACCENT_HEIGHT), (ICON_SIZE, ICON_SIZE)], fill=accent_rgb)

    # Shorten versova- prefix for display
    display = text.replace("versova-", "")
    if len(display) > 14:
        display = display[:14]

    font_size = 10 if len(display) > 12 else 12
    font = get_font(font_size)
    bbox = draw.textbbox((0, 0), display, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (ICON_SIZE - text_width) // 2
    y = (ICON_SIZE - ACCENT_HEIGHT - text_height) // 2 - 2

    draw.text((x, y), display, font=font, fill=TEXT_COLOR)
    img.save(output_path, "PNG")


def generate_image_id():
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(26)) + 'Z'


def create_text_action(skill_name: str, image_filename: str) -> dict:
    # Skills are invoked with "use <skill> skill to"
    text = f'use {skill_name} skill to '
    return {
        "ActionID": str(uuid.uuid4()).lower(),
        "LinkedTitle": True,
        "Name": "Text",
        "Plugin": {
            "Name": "Text",
            "UUID": "com.elgato.streamdeck.system.text",
            "Version": "1.0"
        },
        "Resources": None,
        "Settings": {
            "openInBrowser": False,
            "sendEnter": False,
            "text": text
        },
        "State": 0,
        "States": [{
            "FontFamily": "",
            "FontSize": 12,
            "FontStyle": "",
            "FontUnderline": False,
            "Image": f"Images/{image_filename}",
            "OutlineThickness": 2,
            "ShowTitle": False,
            "TitleAlignment": "bottom",
            "TitleColor": "#ffffff"
        }],
        "UUID": "com.elgato.streamdeck.system.text"
    }


def create_nav_action(nav_type: str) -> dict:
    return {
        "ActionID": str(uuid.uuid4()).lower(),
        "LinkedTitle": True,
        "Name": f"{nav_type} Page",
        "Plugin": {
            "Name": "Pages",
            "UUID": "com.elgato.streamdeck.page",
            "Version": "1.0"
        },
        "Resources": None,
        "Settings": {},
        "State": 0,
        "States": [{}],
        "UUID": f"com.elgato.streamdeck.page.{nav_type.lower()}"
    }


def main():
    script_dir = Path(__file__).parent
    config_file = script_dir / "versova-skills.yaml"

    with open(config_file) as f:
        config = yaml.safe_load(f)

    # Flatten skills
    all_skills = []
    for cat in config['categories']:
        color = cat['color']
        for skill in cat.get('skills', []):
            all_skills.append({'name': skill, 'color': color, 'category': cat['name']})

    print(f"Total Versova skills: {len(all_skills)}")

    if len(all_skills) == 0:
        print("No skills found!")
        return

    skills_per_page = 30
    num_pages = max(1, (len(all_skills) + skills_per_page - 1) // skills_per_page)
    print(f"Pages needed: {num_pages}")

    profile_uuid = str(uuid.uuid4()).upper()
    page_uuids = [str(uuid.uuid4()).upper() for _ in range(num_pages)]

    output_dir = script_dir / f"{profile_uuid}.sdProfile"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()
    (output_dir / "Images").mkdir()

    skill_idx = 0
    for page_num, page_uuid in enumerate(page_uuids):
        page_dir = output_dir / "Profiles" / page_uuid
        page_dir.mkdir(parents=True)
        (page_dir / "Images").mkdir()

        actions = {}

        for row in range(8):
            for col in range(4):
                pos = f"{row},{col}"

                if (row, col) == (0, 3) and page_num > 0:
                    actions[pos] = create_nav_action("Previous")
                    continue
                elif (row, col) == (7, 3) and page_num < num_pages - 1:
                    actions[pos] = create_nav_action("Next")
                    continue

                if skill_idx >= len(all_skills):
                    continue

                skill = all_skills[skill_idx]
                skill_idx += 1

                image_id = generate_image_id()
                image_filename = f"{image_id}.png"
                icon_path = page_dir / "Images" / image_filename
                create_icon(skill['name'], skill['color'], icon_path)

                actions[pos] = create_text_action(skill['name'], image_filename)

        page_manifest = {
            "Controllers": [{"Actions": actions, "Type": "Keypad"}],
            "Icon": "",
            "Name": f"Page {page_num + 1}"
        }
        with open(page_dir / "manifest.json", 'w') as f:
            json.dump(page_manifest, f, separators=(',', ':'))

        count = len([a for a in actions.values() if 'text' in a.get('Settings', {})])
        print(f"  Page {page_num + 1}: {count} skills")

    profile_manifest = {
        "Device": {
            "Model": "20GAT9902",
            "UUID": "@(1)[4057/143/A00NA5353146X0]"
        },
        "Name": "versova-skills",
        "Pages": {
            "Current": page_uuids[0].lower(),
            "Default": page_uuids[0].lower(),
            "Pages": [p.lower() for p in page_uuids]
        },
        "Version": "3.0"
    }

    with open(output_dir / "manifest.json", 'w') as f:
        json.dump(profile_manifest, f, separators=(',', ':'))

    print(f"\nCreated profile: {output_dir.name}")
    print(f"Install: cp -r '{output_dir}' ~/Library/Application\\ Support/com.elgato.StreamDeck/ProfilesV3/")


if __name__ == "__main__":
    main()
