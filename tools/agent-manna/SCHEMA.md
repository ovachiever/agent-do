# Manna JSONL Schema

This document defines the exact JSONL (JSON Lines) format for Manna's storage files.

## Storage Location

All data is stored in `.manna/` directory:
- `.manna/issues.jsonl` - Issue records (one JSON object per line)
- `.manna/sessions.jsonl` - Session event log (one JSON object per line)

## issues.jsonl

Each line is a complete JSON object representing one issue.

### Example
```jsonl
{"id":"mn-a1b2c3","title":"Fix login","status":"open","description":null,"created_at":"2026-01-29T10:00:00Z","updated_at":"2026-01-29T10:00:00Z","blocked_by":[],"claimed_by":null,"claimed_at":null}
```

### Field Definitions

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `id` | String | Yes | Format: `mn-{6-hex}`, auto-extends on collision | Unique issue identifier |
| `title` | String | Yes | 1-500 characters | Issue title/summary |
| `status` | String | Yes | Enum: `open`, `in_progress`, `blocked`, `done` | Current issue state |
| `description` | String or null | No | Optional long-form text | Detailed description |
| `created_at` | String | Yes | ISO8601 timestamp | When issue was created |
| `updated_at` | String | Yes | ISO8601 timestamp | Last modification time |
| `blocked_by` | Array | Yes | Array of issue IDs (strings) | Issues blocking this one |
| `claimed_by` | String or null | No | Session ID or null | Who is working on this |
| `claimed_at` | String or null | No | ISO8601 timestamp or null | When it was claimed |

### Status Transitions

```
open → in_progress (via claim)
in_progress → done (via done)
in_progress → open (via abandon)
* → blocked (when blocked_by is non-empty)
blocked → * (when blocked_by becomes empty)
```

### ID Format

- Prefix: `mn-` (manna)
- Hash: 6 hexadecimal characters (lowercase)
- Collision handling: Auto-extend to 7, 8, ... characters
- Example: `mn-a1b2c3`, `mn-f4e5d6c`

## sessions.jsonl

Each line is a session event (append-only log).

### Example
```jsonl
{"session_id":"ses_abc123","event":"start","timestamp":"2026-01-29T10:00:00Z","context":{}}
{"session_id":"ses_abc123","event":"claim","timestamp":"2026-01-29T10:01:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"done","timestamp":"2026-01-29T10:05:00Z","issue_id":"mn-a1b2c3"}
{"session_id":"ses_abc123","event":"end","timestamp":"2026-01-29T11:00:00Z","context":{}}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | String | Yes | Session identifier (from `$MANNA_SESSION_ID`) |
| `event` | String | Yes | Event type (see below) |
| `timestamp` | String | Yes | ISO8601 timestamp of event |
| `issue_id` | String | Conditional | Required for `claim`, `release`, `done` events |
| `context` | Object | Conditional | Required for `start`, `end` events (can be empty) |

### Event Types

| Event | Description | Required Fields |
|-------|-------------|-----------------|
| `start` | Session begins | `session_id`, `event`, `timestamp`, `context` |
| `claim` | Issue claimed for work | `session_id`, `event`, `timestamp`, `issue_id` |
| `release` | Issue unclaimed (abandoned) | `session_id`, `event`, `timestamp`, `issue_id` |
| `done` | Issue completed | `session_id`, `event`, `timestamp`, `issue_id` |
| `end` | Session ends | `session_id`, `event`, `timestamp`, `context` |

## File Format Rules

1. **One JSON object per line** - No pretty printing, no multi-line JSON
2. **Append-only** - New records are always appended to the end
3. **No deletion** - Records are never removed (issues can be marked `done`)
4. **UTF-8 encoding** - All files must be UTF-8
5. **Newline terminated** - Each line ends with `\n`

## Corruption Handling

If a line cannot be parsed as valid JSON:
- Skip the malformed line
- Log a warning to stderr
- Continue processing remaining lines

This allows recovery from partial writes or corruption.

## Concurrency

All writes must acquire an exclusive file lock (flock) before modifying JSONL files.

See DESIGN.md for implementation details.
