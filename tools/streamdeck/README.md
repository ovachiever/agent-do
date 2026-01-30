# Stream Deck XL Profile for agent-do (ghostty)

Creates a 32-button Stream Deck XL profile that types agent-do tool instructions at cursor position. Configured as a **Smart Profile** that auto-activates when Ghostty terminal is focused.

## Concept

Press a button → types `use agent-do <tool> CLI tool` wherever your cursor is focused (Claude, ChatGPT, terminal, IDE, etc.)

## Features

- **32 agent-do tool buttons** organized by category
- **Smart Profile**: Auto-activates when Ghostty is the active window
- **Multi-page support**: Add more pages via Stream Deck app

## Requirements

- Python 3.8+
- Pillow: `pip install Pillow PyYAML`
- Stream Deck XL (32 buttons, 8×4 layout)

## Quick Start

```bash
cd tools/streamdeck

# 1. Generate icons
python generate_icons.py

# 2. Create profile
python create_profile.py

# 3. Install profile (note: ProfilesV3, not V2)
cp -r *.sdProfile ~/Library/Application\ Support/com.elgato.StreamDeck/ProfilesV3/

# 4. Restart Stream Deck app - "ghostty" profile appears automatically when Ghostty is focused
```

## Button Layout

```
┌─────────┬─────────┬─────────┬─────────┐
│ browse  │   ios   │   db    │  excel  │ Row 0
├─────────┼─────────┼─────────┼─────────┤
│  macos  │ android │ docker  │   k8s   │ Row 1
├─────────┼─────────┼─────────┼─────────┤
│   ssh   │   tui   │  repl   │   ide   │ Row 2
├─────────┼─────────┼─────────┼─────────┤
│   git   │  debug  │   api   │   ocr   │ Row 3
├─────────┼─────────┼─────────┼─────────┤
│  slack  │clipboard│   ci    │  logs   │ Row 4
├─────────┼─────────┼─────────┼─────────┤
│ metrics │  manna  │  agent  │  voice  │ Row 5
├─────────┼─────────┼─────────┼─────────┤
│calendar │ network │ jupyter │  latex  │ Row 6
├─────────┼─────────┼─────────┼─────────┤
│   pdf   │  video  │  image  │   NLP   │ Row 7
└─────────┴─────────┴─────────┴─────────┘
```

## Color Categories

| Color | Hex | Category |
|-------|-----|----------|
| Cyan | `#00d9ff` | Browser/GUI (browse, ios, macos, android) |
| Green | `#00ff88` | Dev (git, ide, debug, docker, k8s, repl) |
| Orange | `#ff9500` | Integration (slack, manna, agent, ci, logs, metrics) |
| Purple | `#bf5af2` | Content (video, image, pdf, latex, jupyter, calendar) |
| Blue | `#007aff` | System (ssh, tui, api, ocr, db, excel, network) |
| Yellow | `#ffcc00` | NLP mode (special) |

## Files

```
tools/streamdeck/
├── generate_icons.py    # Icon generator (Pillow)
├── create_profile.py    # Profile JSON builder
├── buttons.yaml         # Button definitions
├── README.md            # This file
└── icons/               # Generated icons (after running generate_icons.py)
    ├── browse.png
    ├── ios.png
    └── ...
```

## Customization

Edit `buttons.yaml` to:
- Change tool names
- Modify typed text output
- Adjust button positions
- Change colors

Then regenerate:
```bash
python generate_icons.py
python create_profile.py
```

## How It Works

1. **Icons**: `generate_icons.py` creates 144×144 PNG icons with dark gradient background, tool name text, and colored accent bar

2. **Profile**: `create_profile.py` builds a `.sdProfile` directory with:
   - `manifest.json`: Profile metadata (device type, name)
   - `Profiles/<uuid>/manifest.json`: Button configurations using `com.elgato.streamdeck.system.text` action

3. **System Text Action**: Each button uses Stream Deck's built-in "Text" action that types the configured string at cursor position

## Troubleshooting

**Profile doesn't appear:**
- Check the path: `~/Library/Application Support/com.elgato.StreamDeck/ProfilesV3/`
- Profile folder must be named `<UUID>.sdProfile` (e.g., `3A2AADDA-DAB6-4B5A-ABE1-62436A22BCF8.sdProfile`)
- Device Model/UUID in manifest.json must match your Stream Deck
- Restart Stream Deck app completely

**Smart Profile not auto-switching:**
- Ensure `AppIdentifier` in manifest.json matches the app bundle ID
- For Ghostty: `com.mitchellh.ghostty`
- Check app bundle ID with: `osascript -e 'id of app "AppName"'`

**Icons missing:**
- Run `generate_icons.py` before `create_profile.py`
- Check that `icons/` directory has PNG files

**Text not typing:**
- Ensure cursor is in a text input field
- Check System Preferences > Security & Privacy > Accessibility
- Stream Deck app may need accessibility permissions
