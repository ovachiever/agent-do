# agent-jira

Jira Cloud and Server/Data Center plugin for agent-do. Manages connection profiles, issues, sprints, boards, and JQL search — no extra dependencies (uses Python stdlib `urllib`).

## Requirements

- Python 3.10+
- Jira Cloud or Server/Data Center instance
- API token (Cloud) or Personal Access Token / password (Server/DC)

## Credential Security

Secrets are stored in `~/.agent-do/jira/.creds/<profile>` (JSON, mode `0o600`). The `connections.json` metadata file holds only non-secret fields (URL, type, timestamps). Tokens never appear in connection listings.

Resolution order:
1. `JIRA_URL_<PROFILE>`, `JIRA_EMAIL_<PROFILE>`, `JIRA_API_TOKEN_<PROFILE>` (per-profile env vars)
2. `~/.agent-do/jira/.creds/<profile>` (saved profile)
3. `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` (global env vars — no profile needed)

## Connection Management

```bash
# Add a Jira Cloud connection (default)
agent-do jira connections add work \
  --url https://company.atlassian.net \
  --email me@company.com \
  --token <api-token> \
  --default

# Add a Server/Data Center connection
agent-do jira connections add internal \
  --url https://jira.internal.corp \
  --email admin \
  --token <pat-or-password> \
  --server

# List saved profiles
agent-do jira connections list [--json]

# Change default profile
agent-do jira connections set-default internal [--json]

# Remove a profile
agent-do jira connections remove old-profile [--json]
```

The `--connection <name>` flag on any command selects a non-default profile.

## Discovery

```bash
# Show authenticated user
agent-do jira whoami [--connection <name>] [--json]

# All projects with open issue counts
agent-do jira snapshot [--connection <name>] [--json]
```

## Issues

### View
```bash
agent-do jira issue view PROJ-123
agent-do jira issue view PROJ-123 --comments
agent-do jira issue view PROJ-123 --json
```

### List
```bash
agent-do jira issue list PROJ
agent-do jira issue list PROJ --status "In Progress"
agent-do jira issue list PROJ --type Bug --priority High
agent-do jira issue list PROJ --assignee me@company.com --label backend
agent-do jira issue list PROJ --limit 20 --json
```

### Create
```bash
# Preview first (exit code 3 = dry-run, no changes made)
agent-do jira issue create PROJ \
  --summary "Fix login bug" \
  --type Bug \
  --priority High \
  --label auth \
  --label backend \
  --dry-run

# Create for real
agent-do jira issue create PROJ \
  --summary "Fix login bug" \
  --description "Users can't log in with SSO." \
  --type Bug \
  --priority High \
  --assignee accountid-or-email \
  --parent PROJ-100 \
  --json
```

### Link
```bash
# Create a linked work item relationship
agent-do jira issue link PROJ-2 --to PROJ-1 --type blocks
agent-do jira issue link PROJ-2 --to PROJ-1 --type "is blocked by"
agent-do jira issue link PROJ-2 --to PROJ-1 --type clones
agent-do jira issue link PROJ-2 --to PROJ-1 --type relates to
```

### Delete
```bash
# Preview first, then confirm when you're ready
agent-do jira issue delete PROJ-2 --dry-run
agent-do jira issue delete PROJ-2 --confirm
```

### Comment
```bash
agent-do jira issue comment PROJ-123 --body "Confirmed on staging." [--dry-run] [--json]
```

### Assign
```bash
agent-do jira issue assign PROJ-123 --to me@company.com [--dry-run]
agent-do jira issue assign PROJ-123 --to none               # unassign
```

### Transition (move status)
```bash
# List available transitions first
agent-do jira transitions PROJ-123

# Move to a status by name (case-insensitive)
agent-do jira issue transition PROJ-123 --to "In Progress" [--dry-run]
agent-do jira issue transition PROJ-123 --to Done
```

### Label
```bash
agent-do jira issue label PROJ-123 --add frontend --remove legacy [--dry-run]
```

### Edit
```bash
agent-do jira issue edit PROJ-123 --summary "New title" [--dry-run]
agent-do jira issue edit PROJ-123 --description "Updated desc" --priority Low
```

## Search (JQL)

```bash
agent-do jira search 'assignee = currentUser() AND status != Done ORDER BY priority DESC'
agent-do jira search 'project = PROJ AND created >= -7d' --limit 100 --json
agent-do jira search 'sprint in openSprints()' --fields 'summary,status,assignee'
```

## Sprints & Boards

```bash
# List boards (optionally filter by project)
agent-do jira board list [--project PROJ] [--json]

# List sprints for a board
agent-do jira sprint list 42 [--state active|closed|future] [--json]

# Active sprint with its issues
agent-do jira sprint active 42 [--json]

# Add an issue to a sprint
agent-do jira sprint add PROJ-123 --sprint 42 [--dry-run] [--json]
```

## Cloud vs Server/Data Center

| Feature | Cloud | Server/DC |
|---------|-------|-----------|
| API version | v3 | v2 |
| Auth field | `accountId` | `name` (username) |
| Description/comment format | Atlassian Document Format (ADF) | Plain string |
| Flag | _(default)_ | `--server` on connections add |

## Global Flags

| Flag | Description |
|------|-------------|
| `--connection <name>` | Use a specific connection profile |
| `--json` | Structured JSON output |
| `--dry-run` | Preview write operations without making changes |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |

## Environment

| Variable | Description |
|----------|-------------|
| `JIRA_URL` | Jira base URL (global fallback) |
| `JIRA_EMAIL` | Email/username (global fallback) |
| `JIRA_API_TOKEN` | API token/PAT/password (global fallback) |
| `JIRA_URL_<PROFILE>` | Per-profile URL override |
| `JIRA_EMAIL_<PROFILE>` | Per-profile email override |
| `JIRA_API_TOKEN_<PROFILE>` | Per-profile token override |
| `AGENT_DO_HOME` | Config directory (default: `~/.agent-do`) |

## Regression Test Coverage

`tests/test_jira.py` — 376 assertions, fake HTTP server, zero external dependencies.

| Area | Assertions |
|------|-----------|
| connections add (creds file, mode 0o600, metadata) | 13 |
| connections list (shows profiles, hides token) | 7 |
| connections set-default | 2 |
| connections add --server flag | 3 |
| connections remove | 3 |
| connections error cases (missing flags) | 3 |
| connections add validation (profile names + URLs) | 7 |
| whoami (text + JSON + bad connection) | 10 |
| snapshot (text + JSON structure) | 10 |
| issue view (text, --comments, JSON, 404) | 18 |
| issue list (text + JSON) | 7 |
| issue create (fields, ADF, dry-run, --json) | 14 |
| issue link (payload, blocks / is blocked by, dry-run) | 12 |
| issue delete (dry-run, confirm, DELETE path) | 8 |
| issue comment (ADF body, dry-run, --json) | 9 |
| issue assign (accountId, unassign null, dry-run) | 9 |
| issue transition (by name, case-insensitive, bad name, dry-run) | 9 |
| issue label (add/remove, merge, dry-run) | 9 |
| issue edit (fields, dry-run, --json) | 11 |
| transitions (text + JSON) | 8 |
| search (text + JSON + --limit) | 9 |
| board list (text + JSON) | 6 |
| sprint list (text + JSON) | 6 |
| sprint active (text + JSON) | 7 |
| sprint add (dry-run, missing flag) | 6 |
| env var credentials (global + per-profile) | 3 |
| env var credentials (bad URL) | 2 |
| no credentials error | 2 |
| Server/DC mode (plain-text description) | 2 |
| agent-do wrapper unknown command (plain + json) | 4 |
| agent-do dispatch (--help) | 8 |
| **Total** | **376** |
