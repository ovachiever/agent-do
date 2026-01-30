#!/usr/bin/env python3
"""
Generate Stream Deck XL icons for agent-do tools.

Creates 144x144 PNG icons with:
- Dark gradient background (#1a1a2e to #0f0f1a)
- Tool name centered ("agent-<tool>")
- Colored accent bar at bottom by category

Usage:
    python generate_icons.py

Output:
    icons/*.png (32 icons)
"""

import os
import yaml
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow")
    exit(1)


# Icon dimensions
ICON_SIZE = 144
ACCENT_HEIGHT = 8

# Colors
BG_TOP = (26, 26, 46)      # #1a1a2e
BG_BOTTOM = (15, 15, 26)   # #0f0f1a
TEXT_COLOR = (255, 255, 255)


def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def create_gradient_background(size: int) -> Image.Image:
    """Create a vertical gradient background."""
    img = Image.new('RGB', (size, size))
    draw = ImageDraw.Draw(img)

    for y in range(size):
        ratio = y / size
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (size, y)], fill=(r, g, b))

    return img


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """Get a suitable font, falling back to default if needed."""
    font_paths = [
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/SF-Pro-Display-Bold.otf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    # Fallback to default
    return ImageFont.load_default()


def create_icon(display_name: str, accent_color: str, output_path: Path) -> None:
    """Create a single Stream Deck icon."""
    # Create gradient background
    img = create_gradient_background(ICON_SIZE)
    draw = ImageDraw.Draw(img)

    # Draw accent bar at bottom
    accent_rgb = hex_to_rgb(accent_color)
    draw.rectangle(
        [(0, ICON_SIZE - ACCENT_HEIGHT), (ICON_SIZE, ICON_SIZE)],
        fill=accent_rgb
    )

    # Determine font size based on text length
    if len(display_name) <= 10:
        font_size = 18
    elif len(display_name) <= 12:
        font_size = 16
    else:
        font_size = 14

    font = get_font(font_size)

    # Calculate text position (centered, slightly above middle to account for accent bar)
    bbox = draw.textbbox((0, 0), display_name, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (ICON_SIZE - text_width) // 2
    y = (ICON_SIZE - ACCENT_HEIGHT - text_height) // 2 - 2

    # Draw text
    draw.text((x, y), display_name, font=font, fill=TEXT_COLOR)

    # Save icon
    img.save(output_path, "PNG")


def main():
    # Determine script directory
    script_dir = Path(__file__).parent
    icons_dir = script_dir / "icons"
    buttons_file = script_dir / "buttons.yaml"

    # Create icons directory
    icons_dir.mkdir(exist_ok=True)

    # Load button definitions
    with open(buttons_file, 'r') as f:
        config = yaml.safe_load(f)

    buttons = config['buttons']

    print(f"Generating {len(buttons)} icons...")

    for button in buttons:
        tool = button['tool']
        display = button['display']
        color = button['color']

        output_path = icons_dir / f"{tool}.png"
        create_icon(display, color, output_path)
        print(f"  Created: {output_path.name}")

    print(f"\nDone! Icons saved to: {icons_dir}")


if __name__ == "__main__":
    main()
