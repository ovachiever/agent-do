# agent-do

Natural language automation CLI. One command to control anything.

```bash
agent-do "what you want to do"
```

## The Vision

```bash
# The outer LLM only ever needs to know this:
agent-do "take a screenshot of the iOS simulator"
agent-do "send 'x = 42' to my python REPL"
agent-do "click the Save button in Photoshop"
agent-do "post 'deploy complete' to #engineering on Slack"
agent-do "what's using port 3000"
```

One command. Natural language. Done.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    agent-do "intent"                     │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                   Intent Router                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Haiku 4.5 (medium thinking)                      │  │
│  │  - Parses natural language                        │  │
│  │  - Maps to tool + command + args                  │  │
│  │  - Has full tool registry in context              │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  Tool Executor                           │
│                                                          │
│   agent-tui  agent-gui  agent-ios  agent-db  ...        │
│                     (60 tools)                           │
└─────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Tool Registry (`~/.agent-do/registry.yaml`)

```yaml
tools:
  tui:
    description: "Control any terminal/TUI application via tmux"
    capabilities:
      - spawn terminal applications
      - send keystrokes
      - capture screen state
      - wait for text/patterns
    commands:
      spawn: "Start a new TUI session"
      snapshot: "Capture current screen"
      send: "Send keys to session"
      type: "Type text into session"
      wait: "Wait for condition"
    examples:
      - intent: "start htop"
        command: "agent-tui spawn htop"
      - intent: "take a screenshot of session 1"
        command: "agent-tui snapshot 1"

  ios:
    description: "Control iOS Simulator"
    capabilities:
      - tap/swipe gestures
      - take screenshots
      - install/launch apps
      - get UI hierarchy
    commands:
      tap: "Tap at coordinates"
      screenshot: "Capture simulator screen"
      launch: "Launch an app"
      tree: "Get UI element tree"
    examples:
      - intent: "screenshot the iPhone simulator"
        command: "agent-ios screenshot"
      - intent: "tap at 100, 200"
        command: "agent-ios tap 100 200"

  gui:
    description: "Control native desktop applications via accessibility APIs"
    capabilities:
      - click buttons and UI elements
      - type text into fields
      - read UI element tree
      - navigate menus
    commands:
      click: "Click an element"
      type: "Type text"
      tree: "Get UI hierarchy"
      find: "Find elements"
    examples:
      - intent: "click the Save button in Photoshop"
        command: "agent-gui click Photoshop --title Save"
      - intent: "type hello into the search field"
        command: "agent-gui type --role textfield hello"

  repl:
    description: "Control interactive REPLs (Python, Node, psql, etc.)"
    capabilities:
      - spawn REPL sessions
      - send commands
      - read output
      - detect prompts
    commands:
      spawn: "Start a REPL"
      send: "Send command to REPL"
      read: "Read REPL output"
    examples:
      - intent: "start a python REPL"
        command: "agent-repl spawn python"
      - intent: "send x = 42 to my python session"
        command: "agent-repl send 1 'x = 42'"

  docker:
    description: "Control Docker containers"
    capabilities:
      - list/start/stop containers
      - view logs
      - execute commands
      - manage compose stacks
    commands:
      ps: "List containers"
      logs: "View container logs"
      exec: "Run command in container"
      shell: "Interactive shell"
    examples:
      - intent: "show running containers"
        command: "agent-docker ps"
      - intent: "view logs for postgres container"
        command: "agent-docker logs postgres"

  # ... 55 more tools defined in full registry
```

### 2. Intent Router Prompt

```
You are an intent router for the agent-do CLI. Given a natural language request,
determine which tool and command to use.

Current state:
{STATE_SUMMARY}

Available tools:
{REGISTRY_SUMMARY}

User request: "{INTENT}"

Respond with JSON only:
{
  "tool": "tool_name",
  "command": "subcommand", 
  "args": ["arg1", "arg2"],
  "flags": {"--flag": "value"},
  "confidence": 0.95,
  "explanation": "brief explanation of what this will do",
  "clarification_needed": null
}

If ambiguous, set clarification_needed to a question string.
If no tool matches, set tool to null and explain in clarification_needed.
```

### 3. Main Entry Point

```bash
#!/usr/bin/env bash
# agent-do - Natural language automation CLI

set -euo pipefail

AGENT_DO_HOME="${AGENT_DO_HOME:-$HOME/.agent-do}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure home directory exists
mkdir -p "$AGENT_DO_HOME"

case "${1:-}" in
  --help|-h)
    echo "agent-do - Natural language automation"
    echo ""
    echo "Usage: agent-do \"what you want to do\""
    echo ""
    echo "Examples:"
    echo "  agent-do \"take a screenshot of the iOS simulator\""
    echo "  agent-do \"send 'x = 42' to my python REPL\""
    echo "  agent-do \"click Save in Photoshop\""
    echo ""
    echo "Options:"
    echo "  --help      Show this help"
    echo "  --status    Show active sessions and state"
    echo "  --how       Explain how to do something without doing it"
    echo "  --raw       Pass through to tool directly (power user)"
    echo "  --dry-run   Show what would be executed"
    ;;
  --status)
    exec "$SCRIPT_DIR/bin/status"
    ;;
  --how)
    shift
    exec "$SCRIPT_DIR/bin/intent-router" --explain "$*"
    ;;
  --raw)
    shift
    tool="$1"
    shift
    exec "$SCRIPT_DIR/tools/agent-$tool" "$@"
    ;;
  --dry-run)
    shift
    exec "$SCRIPT_DIR/bin/intent-router" --dry-run "$*"
    ;;
  "")
    echo "Usage: agent-do \"what you want to do\""
    echo "Try: agent-do --help"
    exit 1
    ;;
  *)
    # Main path: natural language intent
    exec "$SCRIPT_DIR/bin/intent-router" "$*"
    ;;
esac
```

---

## Command Interface

### Primary (LLM-facing)

```bash
agent-do "take a screenshot of the iOS simulator and save to ~/Desktop"
agent-do "send 'print(x)' to my python session"
agent-do "click the Save button in Photoshop"
agent-do "post 'deploy complete' to #engineering on Slack"
agent-do "show me what's using port 3000"
```

### Helper Commands

```bash
agent-do --status              # Show active sessions/state
# → TUI sessions: 2 (python REPL, htop)
# → iOS Simulator: booted (iPhone 15 Pro)
# → Docker: 3 containers running

agent-do --how "control a desktop application"
# → Use agent-gui. It controls native apps via accessibility APIs.
#   Example: agent-do "click Save in Photoshop"

agent-do --dry-run "screenshot iOS"
# → Would execute: agent-ios screenshot /tmp/screenshot.png
```

### Power User (Direct access)

```bash
agent-do --raw tui spawn python    # Bypass router, direct tool access
agent-tui spawn python             # Or use tools directly
```

---

## Intent Router Implementation

```python
#!/usr/bin/env python3
"""
Intent router using Claude Haiku 4.5 with extended thinking.
Maps natural language intents to agent-* tool commands.
"""

import anthropic
import yaml
import json
import subprocess
import sys
import os
from pathlib import Path

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))

def load_registry() -> dict:
    """Load tool registry"""
    registry_path = AGENT_DO_HOME / "registry.yaml"
    if not registry_path.exists():
        # Fall back to bundled registry
        registry_path = Path(__file__).parent.parent / "registry.yaml"
    
    with open(registry_path) as f:
        return yaml.safe_load(f)

def load_state() -> dict:
    """Load current session state"""
    state_path = AGENT_DO_HOME / "state.yaml"
    if state_path.exists():
        with open(state_path) as f:
            return yaml.safe_load(f) or {}
    return {}

def build_registry_context(registry: dict) -> str:
    """Build compact tool summary for LLM context"""
    lines = []
    for tool, info in registry.get('tools', {}).items():
        lines.append(f"## {tool}")
        lines.append(f"{info['description']}")
        lines.append(f"Commands: {', '.join(info.get('commands', {}).keys())}")
        if info.get('examples'):
            lines.append("Examples:")
            for ex in info['examples'][:3]:
                lines.append(f"  \"{ex['intent']}\" → `{ex['command']}`")
        lines.append("")
    return "\n".join(lines)

def build_state_context(state: dict) -> str:
    """Build state summary for LLM context"""
    if not state:
        return "No active sessions."
    
    lines = []
    if state.get('tui'):
        lines.append("Active TUI sessions:")
        for s in state['tui']:
            lines.append(f"  - Session {s['id']}: {s.get('label', s['command'])}")
    if state.get('ios'):
        lines.append(f"iOS Simulator: {state['ios'].get('booted', 'not running')}")
    if state.get('docker'):
        containers = state['docker'].get('containers', [])
        if containers:
            lines.append(f"Docker: {len(containers)} containers running")
    return "\n".join(lines) if lines else "No active sessions."

def route_intent(intent: str, registry: dict, state: dict, dry_run: bool = False, explain: bool = False) -> dict:
    """Route intent to tool command using Haiku"""
    client = anthropic.Anthropic()
    
    mode = "explain what tool to use" if explain else "determine the exact command"
    
    prompt = f"""You are an intent router for the agent-do CLI. Given a natural language request, {mode}.

Current state:
{build_state_context(state)}

Available tools (each is invoked as `agent-<tool> <command> [args]`):
{build_registry_context(registry)}

User request: "{intent}"

Respond with JSON only:
{{
  "tool": "tool_name",
  "command": "subcommand",
  "args": ["arg1", "arg2"],
  "flags": {{"--flag": "value"}},
  "confidence": 0.95,
  "explanation": "brief explanation of what this will do",
  "clarification_needed": null
}}

Rules:
- tool should be just the name (e.g., "tui" not "agent-tui")
- If the intent is ambiguous, set clarification_needed to a clarifying question
- If no tool matches, set tool to null
- Reference session IDs from current state when relevant"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",  # Using Sonnet for now, switch to Haiku when available
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Extract JSON from response
    text = response.content[0].text
    # Handle potential markdown code blocks
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    
    return json.loads(text.strip())

def execute(result: dict, dry_run: bool = False) -> int:
    """Execute the routed command"""
    
    if result.get('clarification_needed'):
        print(f"? {result['clarification_needed']}")
        return 1
    
    if not result.get('tool'):
        print(f"Could not determine which tool to use.")
        if result.get('explanation'):
            print(f"  {result['explanation']}")
        return 1
    
    # Build command
    cmd = [f"agent-{result['tool']}", result['command']]
    cmd.extend(result.get('args', []))
    for flag, value in result.get('flags', {}).items():
        if value is True:
            cmd.append(flag)
        else:
            cmd.extend([flag, str(value)])
    
    cmd_str = ' '.join(cmd)
    
    if dry_run:
        print(f"Would execute: {cmd_str}")
        if result.get('explanation'):
            print(f"  ({result['explanation']})")
        return 0
    
    print(f"→ {cmd_str}")
    if result.get('explanation'):
        print(f"  ({result['explanation']})")
    print()
    
    return subprocess.run(cmd).returncode

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Intent router for agent-do")
    parser.add_argument("intent", nargs="*", help="Natural language intent")
    parser.add_argument("--dry-run", action="store_true", help="Show command without executing")
    parser.add_argument("--explain", action="store_true", help="Explain how to do something")
    args = parser.parse_args()
    
    intent = " ".join(args.intent)
    if not intent:
        print("Usage: intent-router \"what you want to do\"")
        return 1
    
    registry = load_registry()
    state = load_state()
    
    try:
        result = route_intent(intent, registry, state, args.dry_run, args.explain)
        return execute(result, args.dry_run)
    except json.JSONDecodeError as e:
        print(f"Error parsing router response: {e}")
        return 1
    except anthropic.APIError as e:
        print(f"API error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

---

## Session State Management

The router needs context about active sessions:

```bash
agent-do "send 'print(x)' to my python session"
```

How does it know which session? State file tracks active sessions:

```yaml
# ~/.agent-do/state.yaml
tui:
  - id: 1
    command: "python3"
    started: "2024-01-15T10:00:00"
    label: "python REPL"
    cwd: "/Users/erik/project"
  - id: 2
    command: "htop"
    started: "2024-01-15T10:05:00"
    
ios:
  booted: "iPhone 15 Pro"
  udid: "ABC123..."
  
docker:
  containers:
    - id: "abc123"
      name: "postgres-dev"
      image: "postgres:15"
      status: "running"
```

Tools update state when sessions are created/destroyed. Router includes state in context, so "my python session" resolves correctly.

---

## AGENTS.md Entry

```markdown
## agent-do - Natural Language Automation

Control anything with natural language.

```bash
agent-do "what you want to do"
```

Examples:
- `agent-do "start a python REPL"`
- `agent-do "screenshot the iOS simulator"`
- `agent-do "click Save in Photoshop"`
- `agent-do "send 'SELECT * FROM users' to postgres"`
- `agent-do "post 'done' to #general on Slack"`

Status: `agent-do --status`
Help: `agent-do --how "your question"`
```

**~80 tokens. Complete documentation.**

---

## Fallback Layers

```
1. Intent Router (Haiku) → 95% of cases
         ↓ (if offline/rate-limited)
2. Local Pattern Cache → Common intents cached from previous runs
         ↓ (if no cache hit)  
3. Fuzzy Matching → Match intent keywords to tool descriptions
         ↓ (if still unclear)
4. Interactive → "Did you mean: [a] iOS screenshot [b] GUI screenshot?"
```

### Pattern Cache

```python
# ~/.agent-do/cache/patterns.db (SQLite)
# Stores successful intent → command mappings

def check_cache(intent: str) -> Optional[dict]:
    """Check if we've seen a similar intent before"""
    # Normalize intent
    normalized = normalize(intent)
    # Look for exact or fuzzy match
    result = db.query("SELECT result FROM patterns WHERE intent = ?", normalized)
    if result:
        return json.loads(result)
    return None

def cache_result(intent: str, result: dict):
    """Cache successful routing for future use"""
    normalized = normalize(intent)
    db.execute("INSERT OR REPLACE INTO patterns VALUES (?, ?)", 
               normalized, json.dumps(result))
```

---

## Cost Analysis

| Model | Input | Output | Per Request |
|-------|-------|--------|-------------|
| Haiku 4.5 | ~2K tokens | ~100 tokens | ~$0.002 |
| Sonnet (fallback) | ~2K tokens | ~100 tokens | ~$0.01 |

At 100 requests/day with Haiku = $0.20/day = $6/month

With caching, actual LLM calls drop 50%+ after initial learning period.

---

## Implementation Milestones

### Phase 1: Core Infrastructure
1. [x] Create project structure
2. [x] Main `agent-do` entry point script
3. [x] Intent router with Claude API
4. [x] State file reading/writing
5. [x] `--dry-run`, `--how`, `--status` modes
6. [x] Pattern caching system
7. [x] Offline fuzzy matching fallback

### Phase 2: Full Registry (60/60 Tools Implemented) ✅ COMPLETE
8. [x] Complete registry.yaml with all tools defined
9. [x] Tier 1 - Massive Unlock (9 tools): ✅ COMPLETE
   - [x] tui (integrate existing agent-tui)
   - [x] gui (desktop app control via accessibility)
   - [x] ide (VS Code/Cursor control)
   - [x] repl (Python/Node/psql REPLs)
   - [x] ssh (remote server sessions)
   - [x] docker (container management)
   - [x] ios (iOS Simulator)
   - [x] android (Android Emulator)
   - [x] agent (AI session control)
10. [x] Tier 2 - High Value (8 tools): ✅ COMPLETE
    - [x] db (database clients)
    - [x] k8s (Kubernetes)
    - [x] git (enhanced git)
    - [x] debug (debugger control)
    - [x] jupyter (notebook control)
    - [x] api (API testing)
    - [x] clipboard (cross-app clipboard)
    - [x] ocr (screen text extraction)
11. [x] Tier 3 - Domain-Specific (9 tools): ✅ COMPLETE
    - [x] slack, discord, email, calendar
    - [x] notion, linear, figma, sheets, pdf
12. [x] Tier 4 - Infrastructure (7 tools): ✅ COMPLETE
    - [x] cloud, ci, logs, metrics, vm, network, dns
13. [x] Tier 5 - Creative (5 tools): ✅ COMPLETE
    - [x] image, video, audio
    - [x] 3d, cad
14. [x] Tier 6 - Security & Research (6 tools): ✅ COMPLETE
    - [x] burp, wireshark, ghidra, latex, colab, lab
15. [x] Tier 7 - Communication (5 tools): ✅ COMPLETE
    - [x] zoom, meet, teams, voice, sms
16. [x] Tier 8 - Hardware (6 tools): ✅ COMPLETE
    - [x] serial, midi, homekit, bluetooth, usb, printer
17. [x] Tier 9 - Meta (5 tools): ✅ COMPLETE
    - [x] prompt, eval, memory, learn, swarm

### Phase 3: Integration & Polish
18. [ ] State file updates from all tools
19. [ ] Error handling and recovery
20. [ ] Tool installation/update mechanism
21. [ ] Hooks integration for Factory
22. [ ] Skill wrapper for discoverability
23. [ ] Symlinks to agent-CLIs implementations

---

## Project Structure

```
agent-do/
├── agent-do                 # Main entry point (bash)
├── bin/
│   ├── intent-router        # Haiku-powered router (python)
│   ├── pattern-matcher      # Offline fallback (python)
│   └── status               # Status display (bash)
├── tools/                   # All 60 tools (symlinks to agent-CLIs or bundled)
│   ├── agent-tui -> ../../agent-tui/agent-tui
│   ├── agent-gui -> ../../agent-CLIs/agent-gui/agent-gui
│   ├── agent-ide -> ../../agent-CLIs/agent-ide/agent-ide
│   ├── agent-repl -> ../../agent-CLIs/agent-repl/agent-repl
│   ├── agent-ssh -> ../../agent-CLIs/agent-ssh/agent-ssh
│   ├── agent-docker -> ../../agent-CLIs/agent-docker/agent-docker
│   ├── agent-ios -> ../../agent-CLIs/agent-ios/agent-ios
│   ├── agent-android -> ../../agent-CLIs/agent-android/agent-android
│   ├── agent-agent -> ../../agent-CLIs/agent-agent/agent-agent
│   ├── agent-db -> ../../agent-CLIs/agent-db/agent-db
│   ├── agent-k8s -> ../../agent-CLIs/agent-k8s/agent-k8s
│   ├── agent-git -> ../../agent-CLIs/agent-git/agent-git
│   ├── agent-debug -> ../../agent-CLIs/agent-debug/agent-debug
│   ├── agent-jupyter -> ../../agent-CLIs/agent-jupyter/agent-jupyter
│   ├── agent-api -> ../../agent-CLIs/agent-api/agent-api
│   ├── agent-clipboard -> ../../agent-CLIs/agent-clipboard/agent-clipboard
│   ├── agent-ocr -> ../../agent-CLIs/agent-ocr/agent-ocr
│   ├── agent-slack -> ../../agent-CLIs/agent-slack/agent-slack
│   ├── agent-discord -> ../../agent-CLIs/agent-discord/agent-discord
│   ├── agent-email -> ../../agent-CLIs/agent-email/agent-email
│   ├── agent-calendar -> ../../agent-CLIs/agent-calendar/agent-calendar
│   ├── agent-notion -> ../../agent-CLIs/agent-notion/agent-notion
│   ├── agent-linear -> ../../agent-CLIs/agent-linear/agent-linear
│   ├── agent-figma -> ../../agent-CLIs/agent-figma/agent-figma
│   ├── agent-sheets -> ../../agent-CLIs/agent-sheets/agent-sheets
│   ├── agent-pdf -> ../../agent-CLIs/agent-pdf/agent-pdf
│   ├── agent-cloud -> ../../agent-CLIs/agent-cloud/agent-cloud
│   ├── agent-ci -> ../../agent-CLIs/agent-ci/agent-ci
│   ├── agent-logs -> ../../agent-CLIs/agent-logs/agent-logs
│   ├── agent-metrics -> ../../agent-CLIs/agent-metrics/agent-metrics
│   ├── agent-vm -> ../../agent-CLIs/agent-vm/agent-vm
│   ├── agent-network -> ../../agent-CLIs/agent-network/agent-network
│   ├── agent-dns -> ../../agent-CLIs/agent-dns/agent-dns
│   ├── agent-image -> ../../agent-CLIs/agent-image/agent-image
│   ├── agent-video -> ../../agent-CLIs/agent-video/agent-video
│   ├── agent-audio -> ../../agent-CLIs/agent-audio/agent-audio
│   ├── agent-3d -> ../../agent-CLIs/agent-3d/agent-3d
│   ├── agent-cad -> ../../agent-CLIs/agent-cad/agent-cad
│   ├── agent-burp -> ../../agent-CLIs/agent-burp/agent-burp
│   ├── agent-wireshark -> ../../agent-CLIs/agent-wireshark/agent-wireshark
│   ├── agent-ghidra -> ../../agent-CLIs/agent-ghidra/agent-ghidra
│   ├── agent-latex -> ../../agent-CLIs/agent-latex/agent-latex
│   ├── agent-colab -> ../../agent-CLIs/agent-colab/agent-colab
│   ├── agent-lab -> ../../agent-CLIs/agent-lab/agent-lab
│   ├── agent-zoom -> ../../agent-CLIs/agent-zoom/agent-zoom
│   ├── agent-meet -> ../../agent-CLIs/agent-meet/agent-meet
│   ├── agent-teams -> ../../agent-CLIs/agent-teams/agent-teams
│   ├── agent-voice -> ../../agent-CLIs/agent-voice/agent-voice
│   ├── agent-sms -> ../../agent-CLIs/agent-sms/agent-sms
│   ├── agent-serial -> ../../agent-CLIs/agent-serial/agent-serial
│   ├── agent-midi -> ../../agent-CLIs/agent-midi/agent-midi
│   ├── agent-homekit -> ../../agent-CLIs/agent-homekit/agent-homekit
│   ├── agent-bluetooth -> ../../agent-CLIs/agent-bluetooth/agent-bluetooth
│   ├── agent-usb -> ../../agent-CLIs/agent-usb/agent-usb
│   ├── agent-printer -> ../../agent-CLIs/agent-printer/agent-printer
│   ├── agent-prompt -> ../../agent-CLIs/agent-prompt/agent-prompt
│   ├── agent-eval -> ../../agent-CLIs/agent-eval/agent-eval
│   ├── agent-memory -> ../../agent-CLIs/agent-memory/agent-memory
│   ├── agent-learn -> ../../agent-CLIs/agent-learn/agent-learn
│   └── agent-swarm -> ../../agent-CLIs/agent-swarm/agent-swarm
├── lib/
│   ├── state.py             # State management
│   ├── cache.py             # Pattern caching
│   └── registry.py          # Registry loading
├── registry.yaml            # All 60 tools defined
├── requirements.txt         # Python dependencies
├── PLAN.md                  # This file
├── README.md
└── LICENSE
```

---

## Dependencies

```
# requirements.txt
anthropic>=0.18.0
pyyaml>=6.0
```

System dependencies:
- Python 3.10+
- tmux (for agent-tui)
- Xcode Command Line Tools (for agent-ios)

---

## Environment Variables

```bash
AGENT_DO_HOME      # Config/state directory (default: ~/.agent-do)
ANTHROPIC_API_KEY  # Required for intent routing
```

---

## Future Enhancements

1. **Conversation Mode**: Multi-turn interactions for complex tasks
   ```bash
   agent-do --chat
   > start a python repl
   Started session 1
   > define a function that adds two numbers
   Sent to session 1
   > now test it with 2 and 3
   Sent to session 1: add(2, 3)
   ```

2. **Workflows**: Chain multiple intents
   ```bash
   agent-do --workflow "start postgres, wait for ready, run migrations"
   ```

3. **Learning**: Improve routing based on corrections
   ```bash
   agent-do "screenshot my app"
   → agent-gui screenshot
   $ agent-do --correct "I meant the iOS simulator"
   # Updates pattern cache
   ```

4. **Plugins**: Third-party tool integration
   ```yaml
   # ~/.agent-do/plugins/my-tool.yaml
   name: my-tool
   description: "Does custom thing"
   commands: ...
   ```
