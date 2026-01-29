# Manna

> Git-backed issue tracking and context management for AI agents

Manna is a minimal (<5K LOC) issue tracking system designed specifically for AI agent workflows. It provides issue tracking with dependencies, session-based claims for multi-agent coordination, and context injection for AI prompts.

## Overview

### Why Manna?

Traditional issue trackers (Jira, Linear, GitHub Issues) are designed for human workflows. Manna is designed for **AI agents**:

- **YAML output** - Machine-readable, LLM-friendly format
- **Session-based claims** - Prevents multiple agents from working on the same issue
- **Context injection** - Generates context blobs for AI prompts
- **Git-backed** - JSONL storage that diffs cleanly in version control
- **Fast** - All operations complete in <100ms

### Features

- **11 commands** for full issue lifecycle management
- **Dependency tracking** with blockers
- **Session management** for multi-agent coordination
- **File locking** for concurrent safety
- **Corruption recovery** for partial writes

## Installation

### Prerequisites

- Rust toolchain (1.70+)
- Cargo package manager

### Build

```bash
cd /path/to/agent-do2/tools/agent-manna
cargo build --release
```

The binary will be at `target/release/manna-core`.

### Verify Installation

```bash
./agent-manna --help
```

## Quick Start

```bash
# Initialize manna in current directory
agent-do manna init

# Create an issue
agent-do manna create "Fix authentication bug" "Users can't login with SSO"

# List all issues
agent-do manna list

# Claim an issue to work on
agent-do manna claim mn-abc123

# Mark as done when complete
agent-do manna done mn-abc123

# Generate context for AI prompt
agent-do manna context
```

## Commands

### `init`

Initialize a `.manna/` directory in the current location.

```bash
agent-do manna init
```

**Output:**
```yaml
success: true
initialized: true
path: .manna
```

### `status`

Show current session status and claimed issues.

```bash
agent-do manna status
```

**Output:**
```yaml
success: true
session_id: ses_abc123
claimed_issues:
  - mn-def456
```

### `create <title> [description]`

Create a new issue.

```bash
agent-do manna create "Fix login bug"
agent-do manna create "Implement feature" "Full description here"
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: open
  created_at: "2026-01-29T10:00:00Z"
  updated_at: "2026-01-29T10:00:00Z"
  blocked_by: []
```

**Constraints:**
- Title: 1-500 characters

### `claim <id>`

Claim an issue for the current session. Sets status to `in_progress`.

```bash
agent-do manna claim mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: in_progress
  claimed_by: ses_test123
  claimed_at: "2026-01-29T10:05:00Z"
```

**Notes:**
- An issue can only be claimed by one session at a time
- Attempting to claim an already-claimed issue returns an error

### `done <id>`

Mark an issue as completed.

```bash
agent-do manna done mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: done
```

### `abandon <id>`

Release a claimed issue without completing it. Sets status back to `open`.

```bash
agent-do manna abandon mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  status: open
  claimed_by: null
```

### `block <id> <blocker_id>`

Add a blocker dependency. The issue's status becomes `blocked`.

```bash
agent-do manna block mn-abc123 mn-def456
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Implement feature
  status: blocked
  blocked_by:
    - mn-def456
```

### `unblock <id> <blocker_id>`

Remove a blocker dependency. If no blockers remain, status reverts to `open`.

```bash
agent-do manna unblock mn-abc123 mn-def456
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Implement feature
  status: open
  blocked_by: []
```

### `list [--status <status>]`

List issues with optional status filter.

```bash
agent-do manna list
agent-do manna list --status open
agent-do manna list --status in_progress
agent-do manna list --status blocked
agent-do manna list --status done
```

**Output:**
```yaml
success: true
issues:
  - id: mn-abc123
    title: Fix login bug
    status: open
  - id: mn-def456
    title: Implement feature
    status: in_progress
    claimed_by: ses_test123
```

### `show <id>`

Show full details of an issue.

```bash
agent-do manna show mn-abc123
```

**Output:**
```yaml
success: true
issue:
  id: mn-abc123
  title: Fix login bug
  description: Users can't login with SSO
  status: open
  created_at: "2026-01-29T10:00:00Z"
  updated_at: "2026-01-29T10:05:00Z"
  blocked_by: []
  claimed_by: null
  claimed_at: null
```

### `context [--max-tokens <n>]`

Generate a context blob for AI agent prompts. Default max tokens: 8000.

```bash
agent-do manna context
agent-do manna context --max-tokens 4000
```

**Output:**
```yaml
success: true
context: |
  # Manna Context

  ## Open Issues (2)
  - mn-abc123: Fix login bug [open]
  - mn-ghi789: Add tests [open]

  ## In Progress Issues (1)
  - mn-def456: Implement feature [in_progress, claimed by ses_test123]

  ## Blocked Issues (0)
```

## Architecture

### Storage

Manna stores all data in `.manna/` directory:

```
.manna/
├── issues.jsonl     # Issue records (one JSON per line)
└── sessions.jsonl   # Session event log
```

**Why JSONL?**
- Simple, human-readable format
- Git-friendly (line-based diffs)
- No database dependencies
- Easy corruption recovery (skip malformed lines)

### ID Format

Issues use hash-based IDs:

```
mn-{6-hex}
```

Examples: `mn-abc123`, `mn-f4e5d6`

IDs automatically extend (7, 8, ... chars) on collision.

### Session Management

Sessions are identified by `$MANNA_SESSION_ID` environment variable.

**Default format** (if not set):
```
ses_pid{pid}_{timestamp}
```

This allows multiple agents to work concurrently without conflicts.

### Exit Codes

| Code | Meaning | Examples |
|------|---------|----------|
| 0 | Success | Command completed |
| 1 | User error | Invalid input, issue not found |
| 2 | System error | I/O error, lock failed |

### Concurrency

All write operations use file locking (`fs2` crate):
- Exclusive locks prevent concurrent writes
- Atomic updates via temp file + rename
- Safe for parallel agent execution

## Integration

### With agent-do

Manna is registered in agent-do's registry:

```bash
agent-do manna <command> [args]
```

### Session Hooks

Use with agent-do hooks for automatic session tracking:

**SessionStart hook:**
```bash
export MANNA_SESSION_ID="ses_$(uuidgen)"
```

**PreCompact hook:**
```bash
CONTEXT=$(agent-do manna context --max-tokens 2000)
# Inject $CONTEXT into AI prompt
```

### Scripting

```bash
#!/bin/bash
# Create issue and capture ID
output=$(agent-do manna create "Automated task")
id=$(echo "$output" | grep -o 'id: mn-[a-f0-9]*' | awk '{print $2}')

# Work on it
agent-do manna claim "$id"
# ... do work ...
agent-do manna done "$id"
```

## Development

### Project Structure

```
agent-manna/
├── agent-manna          # Bash wrapper (26 LOC)
├── src/
│   ├── main.rs          # CLI entry point
│   ├── lib.rs           # Library exports
│   ├── id.rs            # ID generation
│   ├── issue.rs         # Issue types and operations
│   ├── store.rs         # JSONL storage
│   └── error.rs         # Error types
├── test/
│   └── integration.sh   # Integration tests
├── Cargo.toml
├── DESIGN.md            # Architecture documentation
├── SCHEMA.md            # JSONL format specification
└── README.md            # This file
```

### Running Tests

```bash
# Unit tests
cargo test

# Integration tests
./test/integration.sh
```

### Test Coverage

- **55 unit tests** covering all modules
- **~20 integration tests** covering full workflows and edge cases

### Dependencies

| Crate | Purpose |
|-------|---------|
| clap | CLI argument parsing |
| serde | Serialization framework |
| serde_json | JSON parsing for JSONL |
| serde_yaml | YAML output formatting |
| chrono | Timestamp handling |
| sha2 | SHA256 hashing for IDs |
| fs2 | Cross-platform file locking |
| thiserror | Error type derivation |
| rand | Random number generation |

### Design Principles

1. **Minimal** - <5K LOC total
2. **Git-friendly** - JSONL diffs cleanly
3. **Agent-first** - YAML output, no colors/spinners
4. **Robust** - File locking, corruption recovery
5. **Simple** - No database, no async, no config files
6. **Fast** - <100ms for all operations

## Troubleshooting

### "Storage not initialized"

Run `manna init` in your project directory:
```bash
agent-do manna init
```

### "Issue not found"

Verify the ID with:
```bash
agent-do manna list
```

### "Issue already claimed"

Another session has claimed this issue. Check who:
```bash
agent-do manna show mn-abc123
```

To release from another session, use that session's ID:
```bash
export MANNA_SESSION_ID="ses_other"
agent-do manna abandon mn-abc123
```

### Binary not found

Build the Rust binary:
```bash
cd /path/to/agent-manna
cargo build --release
```

## License

See repository root for license information.
