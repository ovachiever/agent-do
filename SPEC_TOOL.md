# agent-do spec

Design for a native specification and change-management tool inside `agent-do`.

This is a forward design document. It describes a proposed tool and storage model. It does not describe current shipped behavior.

## Purpose

`agent-do` already has strong surfaces for:

- external knowledge and reference retrieval via `context`
- project memory and learned decisions via `zpc`
- issue tracking and execution coordination via `manna`

What is still missing is a native surface for repo-local intended behavior and proposed change deltas:

- what the system is supposed to do
- what a proposed change alters
- what artifacts are still missing before implementation or archive
- what an agent should read next before it starts coding

`agent-do spec` fills that gap.

## Product Thesis

The tool should be:

- repo-local
- git-reviewable
- markdown-first
- brownfield-friendly
- agent-readable
- scriptable with `--json`

It should not become a second harness inside `agent-do`. It should stay a focused artifact manager and validation surface.

## Non-Goals

`agent-do spec` should not:

- replace `manna` as the issue tracker
- replace `zpc` as the experience journal
- replace `context` as the external knowledge library
- generate assistant-specific command packs or slash-command bundles in v1
- require a terminal dashboard in v1
- force a heavyweight methodology on repos that only need a light spec layer

## Why This Belongs In agent-do

This is a strong fit for `agent-do` because it extends the same outer-harness thesis:

- one stable CLI surface for agents
- one more class of work moved out of improvisation and into a structured tool
- one more area where hooks can nudge toward the native path

Without a spec tool, Claude can still improvise plans, design docs, and change proposals ad hoc. That is useful, but it is not durable. A native spec tool makes that work visible, reviewable, and queryable.

## Storage Model

The storage root should be:

```text
agent-do-spec/
```

This is preferred over bare `specs/` and `changes/` because:

- it avoids collisions with existing repo conventions
- it makes ownership explicit
- it is easy for hooks and discovery logic to detect
- it is visible in git, unlike a hidden local-only state directory

Proposed layout:

```text
agent-do-spec/
├── config.yaml
├── specs/
│   ├── auth.md
│   ├── billing.md
│   └── deployment.md
├── changes/
│   └── add-oauth-device-flow/
│       ├── proposal.md
│       ├── design.md
│       ├── tasks.md
│       └── deltas/
│           └── auth.md
└── archive/
    └── 2026-04-12-add-oauth-device-flow/
        ├── proposal.md
        ├── design.md
        ├── tasks.md
        └── deltas/
            └── auth.md
```

## Canonical Spec Files

Canonical specs live under:

```text
agent-do-spec/specs/*.md
```

Each spec file describes one durable behavior area. Examples:

- `auth.md`
- `deployment.md`
- `billing.md`
- `notifications.md`

Canonical specs are source of truth. Change deltas are temporary overlays until archive.

### Canonical Spec Shape

Each canonical spec file should be plain markdown with optional YAML frontmatter:

```md
---
name: auth
title: Authentication
owners:
  - platform
tags:
  - identity
  - security
---

# Authentication

## Requirements

### Requirement: Session creation
The system MUST create a session after valid credential verification.

#### Scenario: Password login succeeds
- GIVEN a valid email and password
- WHEN the user submits the login form
- THEN the system creates a session
- AND the user is redirected to the application home page
```

The validator should not require frontmatter in v1. The markdown sections are the important part.

## Change Directories

Each proposed change lives under:

```text
agent-do-spec/changes/<change-id>/
```

Where `<change-id>` is kebab-case and stable in git and chat.

Example:

```text
agent-do-spec/changes/add-oauth-device-flow/
```

### Required Artifacts

`proposal.md` is required.

At least one delta file under `deltas/` is required before the change can be considered implementation-ready.

### Optional But Strongly Expected Artifacts

- `design.md`
- `tasks.md`

These should be optional at file-creation time, but `instructions` and `validate` should strongly guide agents toward them when the change deserves them.

## Change Artifact Shapes

### proposal.md

The smallest required artifact. It explains intent and scope.

Suggested shape:

```md
# Change Proposal: add-oauth-device-flow

## Why
Users need a device-based login path for environments where browser redirect is not practical.

## What
- add device authorization flow support
- extend auth UI for device-code polling
- update server token handling

## Out of Scope
- social login redesign
- admin policy UI

## Impacted Specs
- auth
```

### design.md

The technical plan for non-trivial changes.

Suggested shape:

```md
# Design: add-oauth-device-flow

## Current State
...

## Proposed Design
...

## Risks
...

## Rollout
...
```

### tasks.md

Execution checklist, not issue history.

Suggested shape:

```md
# Tasks: add-oauth-device-flow

- [ ] update server auth endpoints
- [ ] add client polling flow
- [ ] add tests
- [ ] update canonical auth spec during archive
```

### deltas/<spec>.md

Temporary modifications to one canonical spec.

Suggested shape:

```md
# Delta: auth

## Add

### Requirement: Device authorization flow
The system MUST support OAuth device authorization for eligible clients.

#### Scenario: Device flow succeeds
- GIVEN a valid device authorization request
- WHEN the user completes verification
- THEN the client receives an access token

## Change

### Requirement: Session creation
Session creation MUST support both interactive browser login and device authorization.
```

## Lifecycle Model

The lifecycle should be simple and file-derived:

1. `draft`
   - `proposal.md` exists
2. `defined`
   - at least one delta file exists
3. `designed`
   - `design.md` exists
4. `planned`
   - `tasks.md` exists
5. `ready-to-archive`
   - tasks are complete and deltas validate cleanly
6. `archived`
   - change moved to `archive/` and canonical specs updated

The tool should derive this state from filesystem content, not from hidden mutable state.

## CLI Surface

The native command should be:

```bash
agent-do spec <command>
```

### v1 command set

```bash
agent-do spec init
agent-do spec list
agent-do spec show <name>
agent-do spec new <change-id>
agent-do spec status
agent-do spec validate
agent-do spec instructions
agent-do spec archive <change-id>
```

### init

Creates the root structure.

Examples:

```bash
agent-do spec init
agent-do spec init --force
```

Behavior:

- creates `agent-do-spec/`
- creates `config.yaml`
- creates empty `specs/`, `changes/`, `archive/`
- optionally seeds one example canonical spec

### list

Lists changes or specs.

Examples:

```bash
agent-do spec list
agent-do spec list --specs
agent-do spec list --changes
agent-do spec list --archived
agent-do spec list --json
```

### show

Displays one spec or one change.

Examples:

```bash
agent-do spec show auth --type spec
agent-do spec show add-oauth-device-flow --type change
agent-do spec show add-oauth-device-flow --json
```

### new

Creates a new change directory and starter artifacts.

Examples:

```bash
agent-do spec new add-oauth-device-flow
agent-do spec new add-oauth-device-flow --title "Add OAuth device flow"
agent-do spec new add-oauth-device-flow --spec auth
```

Behavior:

- validates kebab-case id
- creates `proposal.md`
- creates empty `design.md`, `tasks.md`
- creates `deltas/`
- optionally precreates `deltas/<spec>.md`

### status

Summarizes progress and missing artifacts.

Examples:

```bash
agent-do spec status
agent-do spec status --change add-oauth-device-flow
agent-do spec status --json
```

### validate

Checks structural quality, not implementation correctness.

Examples:

```bash
agent-do spec validate
agent-do spec validate --change add-oauth-device-flow
agent-do spec validate --all --json
```

Validation should check:

- required files exist
- referenced impacted specs exist
- delta files target real canonical specs or clearly declare `Add`
- task list syntax is parseable
- malformed frontmatter does not break parsing
- archive preconditions are satisfied when requested

### instructions

Returns next-step guidance for humans or agents.

Examples:

```bash
agent-do spec instructions --change add-oauth-device-flow
agent-do spec instructions tasks --change add-oauth-device-flow
agent-do spec instructions --change add-oauth-device-flow --json
```

This is the highest-leverage command for agent use. It should answer:

- what to read first
- what artifact is missing
- what command to run next
- whether the change is ready for implementation or archive

### archive

Finalizes a completed change.

Examples:

```bash
agent-do spec archive add-oauth-device-flow --yes
agent-do spec archive add-oauth-device-flow --force --yes
```

Behavior:

- validates archive readiness
- computes a canonical-spec patch plan from delta files
- applies the patch plan only when the merge is structurally unambiguous
- moves the change directory into `archive/DATE-change-id/` after canonical updates succeed
- prints changed canonical specs

Concrete v1 rule:

- if the delta can be applied deterministically, `archive --yes` writes the canonical updates and archives the change
- if the delta is ambiguous, `archive` exits non-zero with `merge_required` and prints the affected spec files plus the manual follow-up needed

This keeps v1 conservative without making `archive` vague.

## JSON Contracts

Every command above should support `--json` except where the output is already a machine-irrelevant side effect.

### list --json

```json
{
  "specs": [
    {
      "name": "auth",
      "title": "Authentication",
      "path": "agent-do-spec/specs/auth.md"
    }
  ],
  "changes": [
    {
      "id": "add-oauth-device-flow",
      "status": "planned",
      "path": "agent-do-spec/changes/add-oauth-device-flow"
    }
  ]
}
```

### status --json

```json
{
  "change": "add-oauth-device-flow",
  "status": "planned",
  "artifacts": {
    "proposal": true,
    "design": true,
    "tasks": true,
    "deltas": ["auth"]
  },
  "tasks": {
    "total": 4,
    "done": 2
  },
  "missing": [],
  "next": [
    "Finish remaining tasks in tasks.md",
    "Run agent-do spec validate --change add-oauth-device-flow"
  ]
}
```

### validate --json

```json
{
  "ok": false,
  "target": "add-oauth-device-flow",
  "errors": [
    {
      "code": "missing_delta",
      "path": "agent-do-spec/changes/add-oauth-device-flow",
      "message": "At least one delta file is required"
    }
  ],
  "warnings": []
}
```

### instructions --json

```json
{
  "change": "add-oauth-device-flow",
  "status": "defined",
  "read_first": [
    "agent-do-spec/changes/add-oauth-device-flow/proposal.md",
    "agent-do-spec/specs/auth.md"
  ],
  "missing": [
    "design.md",
    "tasks.md"
  ],
  "commands": [
    "agent-do spec show add-oauth-device-flow --type change",
    "agent-do spec validate --change add-oauth-device-flow"
  ],
  "guidance": [
    "Write design.md before implementation because the change affects auth flow behavior",
    "Add tasks.md before handing work to multiple agents"
  ]
}
```

## Boundaries With Existing Tools

This is the most important part of the design.

### spec vs context

`spec` is for repo-local intended behavior and change deltas.

`context` is for external knowledge and reference retrieval.

Use `context` when:

- fetching vendor docs
- pulling `llms.txt`
- indexing external references
- assembling budgeted context for an agent

Use `spec` when:

- defining how this repo should behave
- proposing a behavioral change
- validating whether a change is structurally ready

Future integration:

- `context scan-local agent-do-spec/` should work well out of the box
- `spec instructions` can recommend `context` when a change cites missing external references

### spec vs zpc

`spec` is normative.

`zpc` is experiential.

Use `zpc` when:

- capturing lessons
- logging decisions made during actual execution
- harvesting patterns from recent work

Use `spec` when:

- defining intended behavior before or during implementation
- tracking the artifact state of a proposed change

Future integration:

- `spec archive` can optionally emit a `zpc decide` or `zpc learn` suggestion
- `design.md` can cite relevant `zpc` decisions, but should not be replaced by them

### spec vs manna

`spec` is not an issue tracker.

`manna` is not a source of truth for behavior.

Use `manna` when:

- assigning work
- tracking dependencies
- managing claim ownership across agents

Use `spec` when:

- describing the change itself
- validating whether artifacts are complete enough to start or archive

Future integration:

- `spec instructions` can suggest `manna create` when a validated change is ready for execution
- a later `spec sync-manna` command could map checklist items into `manna`, but this should not be in v1

## Discovery And Hook Fit

This tool should participate in the `v1.1` discovery layer.

Routing metadata should cover prompts like:

- "write a spec"
- "propose this change"
- "design this feature"
- "what artifacts are missing before implementation"
- "archive this completed change"

Likely defaults:

- `agent-do spec status`
- `agent-do spec new <change-id>`
- `agent-do spec instructions --change <id>`

PreToolUse nudges should detect likely raw alternatives such as:

- ad hoc `mkdir specs changes`
- manual `touch proposal.md design.md tasks.md`

This should stay low priority until the tool exists.

## Implementation Shape

The tool should be directory-based:

```text
tools/agent-spec/
└── agent-spec
```

Suggested implementation:

- bash entrypoint
- Python helpers for markdown/frontmatter parsing and validation
- no network dependency
- no database in v1

Core modules:

- `paths.py` or shell path helpers
- `parse.py` for frontmatter and section extraction
- `validate.py`
- `archive.py`
- `json_output.sh` and `snapshot.sh` integration if the bash entrypoint stays thin

## Suggested v1 Build Order

1. `init`
2. `new`
3. `list`
4. `show`
5. `status`
6. `validate`
7. `instructions`
8. `archive`

This order gets the artifact model stable before we attempt canonical-spec merge behavior.

## Testing Strategy

Add an integration suite that uses temp repos and verifies:

- `init` creates the expected tree
- `new` creates starter files
- `status` derives lifecycle correctly
- `validate` catches missing and malformed artifacts
- `instructions --json` produces stable guidance
- `archive` refuses incomplete changes
- `archive --force` behaves predictably when explicitly requested

## Risks

### Overlap confusion

If the docs are sloppy, users will confuse `spec`, `zpc`, and `manna`.

Mitigation:

- keep their boundaries explicit in the README and help text
- keep the command set narrow

### Merge complexity during archive

Automatic canonical-spec merging can become fragile quickly.

Mitigation:

- make validation and instruction surfaces excellent first
- keep archive conservative in v1

### Methodology creep

A spec tool can become ceremony-heavy.

Mitigation:

- do not require more than `proposal.md` plus one delta file to get started
- keep `design.md` and `tasks.md` strongly recommended, not universally mandatory

## Bottom Line

`agent-do spec` is worth building.

It fills a real gap in the current `agent-do` surface:

- `context` knows what the world says
- `zpc` knows what we learned
- `manna` knows what work exists
- `spec` would know what this repo is supposed to do, and how a proposed change alters that

That is a clean addition to the outer harness, not a diversion from it.
