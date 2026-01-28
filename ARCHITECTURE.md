# agent-do System Architecture

## Overview

agent-do is a universal automation layer that works with any AI agent harness (Factory Droid, Claude Code, OpenCode, etc.). It provides:

1. **Structured CLI API** - Direct tool invocation without LLM overhead
2. **Natural Language Mode** - LLM-routed for human users
3. **60+ specialized tools** - iOS, Android, browser, TUI, GUI, databases, cloud, etc.

### Supported Harnesses

| Harness | Config Location | Hooks | Skills/Droids |
|---------|-----------------|-------|---------------|
| **Factory AI** | `~/.factory/AGENTS.md` | ✓ | Droids |
| **Claude Code** | `~/.claude/CLAUDE.md` | ✓ | Skills |
| **OpenCode** | `~/.config/opencode/AGENTS.md` | Plugins | Agents |
| **Cursor** | `.cursorrules` | MCP | - |
| **Aider** | `.aider.conf.yml` | - | - |
| **Continue.dev** | `.continue/config.json` | - | Context providers |

**OpenCode** also has fallback compatibility with `~/.claude/CLAUDE.md` and `~/.claude/skills/`.

## Quick Start: OpenCode Integration

Add to your `~/.config/opencode/AGENTS.md` (or `~/.claude/CLAUDE.md` for fallback compatibility):

```markdown
## agent-do

Universal automation CLI. Use structured API (instant, no LLM overhead):

```bash
agent-do <tool> <command> [args...]
```

**Core tools:**
| Tool | Purpose | Example |
|------|---------|---------|
| `ios` | iOS Simulator | `agent-do ios tap-label "Sign In"` |
| `android` | Android Emulator | `agent-do android screenshot` |
| `browse` | Headless browser | `agent-do browse open https://example.com` |
| `tui` | Terminal apps | `agent-do tui spawn htop --session monitor` |
| `gui` | Desktop automation | `agent-do gui click-text "Save"` |
| `db` | Databases | `agent-do db query "SELECT * FROM users"` |

**Discovery:** `agent-do --list` | `agent-do <tool> --help`
```

This gives OpenCode immediate access to 60+ automation tools with the same interface used by Factory AI and Claude Code.

## Integration Patterns

### Pattern 1: AGENTS.md / CLAUDE.md Instructions

The AI harness reads project/global instructions from markdown files. Add agent-do documentation:

```markdown
## agent-do

**STRUCTURED API (for AI - instant, no LLM):**
```bash
agent-do <tool> <command> [args...]
```

**Examples:**
```bash
agent-do ios screenshot ~/Downloads/screen.png
agent-do ios tap-label "Sign In"
agent-do browse open https://example.com
agent-do tui spawn htop --session my-htop
```

**Available tools:** `agent-do --list`
**Tool help:** `agent-do <tool> --help`
```

### Pattern 2: Hooks (Enforcement)

Hooks intercept AI actions and guide toward agent-do tools:

| Hook Event | Purpose | Example |
|------------|---------|---------|
| `SessionStart` | Remind AI about agent-do tools | Show tooling hierarchy |
| `PreToolUse` | Suggest agent-do when raw commands detected | `xcrun simctl` → `agent-do ios` |
| `UserPromptSubmit` | Route prompts to appropriate tools | "iOS screenshot" → suggest `agent-do ios` |
| `PostToolUse` | Auto-format, auto-lint after edits | Run biome/ruff on files |
| `Stop` | Auto-commit, notifications | Atomic commits per session |

#### Example: PreToolUse Hook (Python)

```python
#!/usr/bin/env python3
# Install at:
#   ~/.claude/hooks/agent-do-pretooluse.py   (Claude Code / OpenCode)
#   ~/.factory/hooks/agent-do-pretooluse.py  (Factory AI)
import json, sys, re

AGENT_DO_PATTERNS = {
    r'\bxcrun\s+simctl\b': ('ios', 'Use agent-do ios instead'),
    r'\badb\s+(shell|install)': ('android', 'Use agent-do android instead'),
    r'\bosascript\b': ('gui', 'Use agent-do gui instead'),
    r'\bplaywright\b|\bpuppeteer\b': ('browse', 'Use agent-do browse instead'),
    r'\bexpect\b.*spawn': ('tui', 'Use agent-do tui instead'),
}

def main():
    data = json.load(sys.stdin)
    # Claude Code/OpenCode use "Bash", Factory AI uses "Execute"
    if data.get("tool_name") not in ("Bash", "Execute"):
        sys.exit(0)
    
    command = data.get("tool_input", {}).get("command", "")
    for pattern, (tool, msg) in AGENT_DO_PATTERNS.items():
        if re.search(pattern, command):
            print(json.dumps({
                "decision": "block",
                "reason": f"Use agent-do {tool} instead. Run: agent-do {tool} --help"
            }))
            sys.exit(0)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**Hook Configuration (settings.json):**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": ["~/.claude/hooks/agent-do-pretooluse.py"]
      }
    ]
  }
}
```

### Pattern 3: Droids (Factory AI) / Skills (Claude Code & OpenCode)

Both Factory AI's Droids and Claude Code/OpenCode's Skills serve the same purpose:
- **Focused system prompts** - Domain expertise
- **Restricted tool access** - Only relevant tools
- **Model selection** - Right model for the task

#### Factory AI: Droid Frontmatter

```yaml
---
name: ios-tester
description: iOS app testing specialist. Use for UI audits, automation, accessibility testing.
model: claude-sonnet-4-5-20250929
tools: Read, Execute, Task, TodoWrite
---
```

#### Claude Code / OpenCode: Skill Frontmatter

```yaml
---
name: ios-automation
description: iOS app testing and automation. Use for UI audits, simulator control, accessibility testing.
globs: ["**/ios/**", "*.xcodeproj", "*.swift"]
alwaysApply: false
---
```

#### Shared Content (works for both)

```markdown
# iOS Testing Specialist

You test iOS applications using agent-do ios commands:

## Available Commands
- `agent-do ios tree` - Get UI element hierarchy
- `agent-do ios tap-label "element"` - Tap by accessibility label
- `agent-do ios screenshot path` - Capture screen
- `agent-do ios swipe x1 y1 x2 y2` - Swipe gesture

## Workflow
1. Get UI tree: `agent-do ios tree`
2. Find elements: `agent-do ios find "label"`
3. Interact: `agent-do ios tap-label "label"`
4. Verify: `agent-do ios screenshot`
```

#### File Locations
| Harness | Location |
|---------|----------|
| Factory AI | `~/.factory/droids/ios-tester.md` |
| Claude Code / OpenCode | `~/.claude/skills/ios-automation/SKILL.md` |

## File Locations

### Factory AI
```
~/.factory/
├── AGENTS.md           # Global instructions
├── hooks/              # Hook scripts
│   ├── agent-do-session-start.sh
│   ├── agent-do-pretooluse-check.py
│   └── agent-do-prompt-router.py
├── droids/             # Specialist subagents
│   ├── ios-tester.md
│   └── debugger.md
└── skills/             # Dynamic capabilities
    └── */SKILL.md
```

### Claude Code
```
~/.claude/
├── CLAUDE.md               # Global instructions (loaded automatically)
├── hooks/                  # Hook scripts (Python/Bash)
│   ├── agent-do-pretooluse.py
│   ├── post-edit.sh
│   └── stop-quality-gate.sh
├── skills/                 # Skills with YAML frontmatter
│   └── */SKILL.md
├── commands/               # Custom slash commands
│   └── *.md
└── settings.json           # Configuration
```

### OpenCode
```
~/.config/opencode/
├── AGENTS.md               # Global instructions (primary)
├── opencode.json           # Configuration
├── agents/                 # Custom agents (like droids)
│   └── *.md
├── commands/               # Custom slash commands
│   └── *.md
└── plugins/                # Extension plugins
```

**Fallback:** OpenCode also reads `~/.claude/CLAUDE.md` and `~/.claude/skills/` if native config doesn't exist.

### Project-Level
```
project/
├── AGENTS.md           # Project instructions (team-shared)
├── CLAUDE.md           # Project instructions (Claude Code)
├── CLAUDE.local.md     # Personal project settings (gitignored)
└── .factory/
    └── droids/         # Project-specific droids
```

## Hook Events Reference

| Event | Trigger | Use Case |
|-------|---------|----------|
| `SessionStart` | New session begins | Load context, remind about tools |
| `SessionEnd` | Session closes | Cleanup, save state |
| `UserPromptSubmit` | User sends message | Route to tools, add context |
| `PreToolUse` | Before tool executes | Block dangerous commands, suggest alternatives |
| `PostToolUse` | After tool executes | Auto-format, lint, validate |
| `Stop` | Agent finishes responding | Auto-commit, notifications |
| `PreCompact` | Before context compaction | Save important state |
| `Notification` | Agent sends notification | Custom alerts |

### Hook Input/Output Format

**Input (JSON on stdin):**
```json
{
  "tool_name": "Execute",
  "tool_input": {"command": "xcrun simctl screenshot"},
  "cwd": "/path/to/project",
  "session_id": "abc123"
}
```

**Output (JSON on stdout):**
```json
{
  "systemMessage": "HINT: Use agent-do ios screenshot instead",
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "Detailed suggestion..."
  }
}
```

**Exit codes:**
- `0` = Allow (with optional message)
- `1` = Block (show error)
- `2` = Needs input (for clarification flows)

## Tool Discovery

agent-do tools live in `tools/agent-*`:

```
agent-do2/
├── agent-do            # Main CLI
├── bin/
│   ├── intent-router   # LLM routing (natural language mode)
│   ├── pattern-matcher # Offline routing
│   └── status          # Session status
├── tools/
│   ├── agent-ios       # iOS Simulator
│   ├── agent-android   # Android Emulator
│   ├── agent-browse/   # Headless browser (Node.js)
│   ├── agent-tui       # Terminal UI automation
│   ├── agent-gui       # Desktop GUI automation
│   └── ...             # 60+ more tools
└── registry.yaml       # Tool catalog
```

## Applying to Other AI Harnesses

### Claude Code
1. Copy relevant sections to `~/.claude/CLAUDE.md`
2. Install hooks in `~/.claude/hooks/`
3. Create custom commands in `~/.claude/commands/`
4. Add skills in `~/.claude/skills/` for domain-specific tooling

### OpenCode
1. Copy relevant sections to `~/.config/opencode/AGENTS.md`
2. Install plugins in `~/.config/opencode/plugins/` for tool integration
3. Create custom commands in `~/.config/opencode/commands/`
4. Add agents in `~/.config/opencode/agents/` for domain-specific tooling

**Note:** OpenCode also supports fallback to `~/.claude/CLAUDE.md` and `~/.claude/skills/`.

### Cursor
1. Add to `.cursorrules` or project instructions
2. Use MCP servers for tool integration
3. Configure in Cursor settings

### Aider
1. Add to `.aider` configuration
2. Use `--read` flag to include AGENTS.md
3. Define conventions in `.aider.conf.yml`

### Continue.dev
1. Add to `.continue/config.json`
2. Define context providers
3. Create slash commands

### Generic Pattern
Any AI coding assistant that:
1. Reads markdown instruction files
2. Can execute shell commands
3. Supports hooks or extensions

...can integrate agent-do by:
1. **Document the API** in its instruction file
2. **Enforce with hooks** when available
3. **Create subagents/tools** for specialized workflows

## Key Design Principles

1. **Structured > Natural Language for AI**
   - AI → AI communication should be structured
   - Natural language is for humans
   - `agent-do ios tap-label "Sign In"` not `agent-do -n "tap sign in button"`

2. **Semantic > Coordinate Interaction**
   - `tap-label "Meal Plan"` not `tap 83 785`
   - `find "Search"` returns coordinates if needed
   - UI tree provides accessibility labels

3. **Tools are Composable**
   - Each tool is standalone
   - Can be called directly or via agent-do
   - Same interface for AI and humans

4. **Hooks Enforce, Don't Block**
   - Suggest better alternatives
   - Provide context and hints
   - Allow override when needed
