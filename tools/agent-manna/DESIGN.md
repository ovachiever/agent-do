# Manna Design Document

## Architecture

Manna follows the agent-do tool pattern: **Bash wrapper + Backend binary**.

```
agent-manna (bash wrapper, ~50 LOC)
    ↓
manna-core (Rust binary)
    ↓
.manna/ (JSONL storage)
```

### Components

1. **agent-manna** - Bash wrapper script
   - Discovers `manna-core` binary relative to script location
   - Passes all arguments through to Rust binary
   - Provides helpful error if binary not found

2. **manna-core** - Rust binary
   - CLI parsing with `clap`
   - JSONL read/write with file locking
   - All business logic

3. **.manna/** - Storage directory
   - `issues.jsonl` - Issue records
   - `sessions.jsonl` - Session event log
   - Created by `manna init`

## Storage Strategy

### JSONL Only (No Database)

- **Format**: JSON Lines (one JSON object per line)
- **Why**: Simple, git-friendly, human-readable, no schema migrations
- **Trade-off**: Linear scan for queries (acceptable for <10K issues)

### File Locking

All writes use `fs2` crate for cross-platform file locking:

```rust
use fs2::FileExt;

let file = OpenOptions::new().append(true).open("issues.jsonl")?;
file.lock_exclusive()?;  // Block until lock acquired
// ... write data ...
file.unlock()?;
```

This prevents corruption from concurrent writes.

### Atomic Writes

For updates (not appends):
1. Write to temporary file (`.manna/issues.jsonl.tmp`)
2. Acquire lock on original file
3. Rename temp file over original (atomic on POSIX)
4. Release lock

### Corruption Recovery

If JSONL parsing fails on a line:
- Skip the malformed line
- Log warning to stderr: `Warning: Skipping malformed line N in issues.jsonl`
- Continue processing remaining lines

This allows recovery from partial writes.

## Session Identity

Sessions are identified by `$MANNA_SESSION_ID` environment variable.

**Default format** (if env var not set):
```
ses_pid{pid}_{timestamp}
```

Example: `ses_pid12345_1706544000`

**Why**: Allows multiple concurrent sessions without conflicts.

## CLI Design

### Commands

| Command | Description | Output |
|---------|-------------|--------|
| `init` | Create `.manna/` directory | Success message (YAML) |
| `status` | Show current state + active issues | YAML with summary |
| `create <title>` | Create new issue | YAML with issue details |
| `claim <id>` | Claim issue for work | YAML with updated issue |
| `done <id>` | Mark issue complete | YAML with updated issue |
| `abandon <id>` | Unclaim without completing | YAML with updated issue |
| `block <id> <blocker>` | Add dependency | YAML with updated issue |
| `unblock <id> <blocker>` | Remove dependency | YAML with updated issue |
| `list [--mine\|--open\|--blocked]` | List issues | YAML array of issues |
| `show <id>` | Show issue details | YAML with full issue |
| `context` | Generate context blob | YAML with context data |

### Output Format

**All commands output YAML** (machine-readable for AI agents).

Example:
```yaml
id: mn-a1b2c3
title: Fix login bug
status: open
created_at: "2026-01-29T10:00:00Z"
```

**Why YAML**: Easier for LLMs to parse than JSON, more readable than JSON.

### Exit Codes

| Code | Meaning | Examples |
|------|---------|----------|
| 0 | Success | Command completed successfully |
| 1 | User error | Invalid input, validation failure, issue not found |
| 2 | System error | File I/O error, corruption, permission denied |

**Usage in scripts**:
```bash
if ! manna-core create "Fix bug"; then
  echo "Failed to create issue" >&2
  exit 1
fi
```

## ID Generation

### Algorithm

1. Generate random bytes (16 bytes)
2. Append current timestamp (nanoseconds)
3. SHA256 hash the combined data
4. Take first 6 hex characters
5. Prefix with `mn-`

### Collision Handling

If ID already exists:
- Extend hash to 7 characters
- If still collision, extend to 8, 9, ...
- Probability of collision with 6 hex chars: ~1 in 16 million

### Format

```
mn-{hex}
```

Examples: `mn-a1b2c3`, `mn-f4e5d6`, `mn-1234567` (extended)

## Dependencies

### Rust Crates

| Crate | Purpose |
|-------|---------|
| `clap` | CLI argument parsing (derive macros) |
| `serde` | Serialization framework |
| `serde_json` | JSON parsing for JSONL |
| `serde_yaml` | YAML output formatting |
| `chrono` | Timestamp handling |
| `sha2` | SHA256 hashing for IDs |
| `fs2` | Cross-platform file locking |
| `thiserror` | Error type derivation |

### No Async

Manna is **synchronous only** for simplicity:
- No tokio, async-std, or async runtime
- Blocking I/O is acceptable for <100ms operations
- Simpler error handling and testing

## Integration with agent-do

### Registry Entry

```yaml
manna:
  description: "Git-backed issue tracker for AI agent memory"
  path: "tools/agent-manna/agent-manna"
  category: "data"
```

### Hook Integration

Manna can be invoked from agent-do hooks:

**SessionStart hook**:
```bash
# Log session start
manna-core session-start
```

**Stop hook**:
```bash
# Log session end
manna-core session-end
```

**PreCompact hook**:
```bash
# Inject context into prompt
manna-core context
```

## Performance Targets

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `create` | <50ms | Simple append |
| `list` | <100ms | Linear scan acceptable for <10K issues |
| `claim` | <100ms | Read + write with lock |
| `status` | <50ms | Read-only, no lock |

## Security Considerations

### No Authentication

Manna has **no authentication** - it trusts the filesystem:
- Anyone with write access to `.manna/` can modify issues
- Session IDs are not secret
- Suitable for single-user or trusted environments only

### No Encryption

JSONL files are **plain text**:
- Do not store sensitive data in issue titles/descriptions
- Suitable for task tracking, not secrets management

## Future Considerations (Out of Scope for v1)

These are explicitly **NOT** in v1:

- SQLite backend (JSONL only)
- Web UI (CLI only)
- Multi-repo spanning (single repo only)
- Labels/tags (status enum only)
- Comments/threads (no discussion)
- Time tracking (no duration/estimates)
- Priority levels (no prioritization)
- Custom fields (fixed schema)
- Search/filtering beyond basic flags
- Undo/history (append-only log)

## Design Principles

1. **Minimal** - <5K LOC total (Rust + Bash)
2. **Git-friendly** - JSONL diffs cleanly
3. **Agent-first** - YAML output, no colors/spinners
4. **Robust** - File locking, corruption recovery
5. **Simple** - No database, no async, no config files
6. **Fast** - <100ms for all operations

## References

- **Beads**: Original 120K+ LOC implementation by Steve Yegge
- **agent-do**: Tool integration framework
- **agent-browse**: Reference for bash+backend pattern
