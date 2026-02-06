# agent-do Tool Audit Report

> Full analysis of 62 tools against the gold standard pattern.
> Generated 2026-02-06 by 7-agent parallel audit swarm.

---

## Gold Standard Pattern

The best tools (browse, db, excel) share these principles that make them indispensable for AI agents:

### The 5-Step Pattern: Connect → Snapshot → Interact → Verify → Save

| Step | browse | db | excel | Why AI Needs It |
|------|--------|-----|-------|----------------|
| **Connect** | Daemon auto-launches Playwright browser | `connect <profile>` or connection string | `open <file>` | Establishes session context |
| **Snapshot** | `snapshot -i` — page structure with @refs | `snapshot` — all tables/columns/types/FKs | `snapshot --headers` — headers + preview + range | **AI "sees" the current state** — this is the key insight |
| **Interact** | `click @e3`, `fill @e5 "text"` | `query "SELECT ..."` | `set A1 "value"`, `formula B2 "=SUM()"` | Structured commands, not raw strings |
| **Verify** | `get url`, `get text @e3` | `sample <table> 5` | `get A1` | Confirm changes worked |
| **Save** | `session save`, `close` | `disconnect` | `save`, `close` | Clean up, persist state |

### Why This Pattern Beats Direct Manipulation

1. **Snapshot = AI Vision**: The AI can't see a browser page or database schema directly. Snapshot gives it structured understanding of the current state. Without this, the AI is blind.

2. **Session = Memory**: The AI maintains context across commands. A database connection persists. A browser session keeps cookies. Without sessions, every command starts from scratch.

3. **Structured Output = Parseable**: JSON responses let the AI reason about results. Raw CLI output requires fragile parsing.

4. **Error Recovery = Resilience**: Actionable error codes (exit 3 = browser crashed → run restart) let the AI self-heal. Raw errors are opaque.

5. **Abstraction = Safety**: The tool wraps dangerous operations. `agent-db query` prevents SQL injection. `agent-browse` manages browser lifecycle. Direct manipulation risks resource leaks and security issues.

### Gold Standard Checklist

Every tool SHOULD score against these criteria (0-3 scale):

| # | Criterion | Weight | Description |
|---|-----------|--------|-------------|
| 1 | **Snapshot/State** | Critical | Command that shows AI the current state (schema, UI tree, file structure, process list) |
| 2 | **Real Execution** | Critical | Actually runs commands (not just help text / stubs) |
| 3 | **Value Over Raw CLI** | Critical | Provides something AI can't get from running the underlying tool directly |
| 4 | **Structured Output** | High | JSON or structured text that AI can parse |
| 5 | **Session/Connection** | High | Persistent state across commands |
| 6 | **Error Handling** | High | Specific exit codes, actionable error messages |
| 7 | **Help + Examples** | Medium | Comprehensive help with workflow examples |
| 8 | **Recovery** | Medium | Reconnect/restart on failure |
| 9 | **Consistent Naming** | Low | Follows agent-do command conventions |
| 10 | **Workflow Example** | Low | At least one complete start-to-finish example in help |

---

## Tool-by-Tool Scorecard

### Classification Key
- **GOLD** — Full implementation, daemon/session model, snapshot, JSON output (browse, db, excel)
- **REAL** — Fully functional, executes real commands, good AI affordances
- **WRAPPER** — Thin shell around existing CLI with AI-friendly structure
- **PARTIAL** — Some commands work, others are stubs or missing
- **STUB** — Help text exists but most commands don't execute

---

### Tier 0: Gold Standard (Score 27-30/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **browse** | GOLD | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | **30** |
| **db** | GOLD | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | **29** |
| **excel** | GOLD | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | **28** |
| **unbrowse** | GOLD | 2 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | **27** |

### Tier 1: Device/UI Tools (Score 15-25/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **ios** | REAL | 3 | 3 | 3 | 2 | 2 | 2 | 3 | 1 | 3 | 3 | **25** |
| **tui** | REAL | 3 | 3 | 3 | 1 | 3 | 2 | 2 | 2 | 3 | 2 | **24** |
| **manna** | REAL | 2 | 3 | 3 | 2 | 3 | 2 | 3 | 1 | 3 | 3 | **25** |
| **macos** | PARTIAL | 2 | 2 | 2 | 2 | 1 | 1 | 2 | 1 | 2 | 1 | **16** |
| **android** | WRAPPER | 2 | 2 | 2 | 1 | 1 | 1 | 3 | 1 | 3 | 2 | **18** |
| **screen** | PARTIAL | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 1 | 2 | 1 | **13** |

### Tier 2: Infrastructure (Score 12-20/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **docker** | WRAPPER | 2 | 3 | 2 | 2 | 1 | 2 | 2 | 1 | 3 | 2 | **20** |
| **ssh** | WRAPPER | 1 | 3 | 2 | 1 | 2 | 2 | 2 | 1 | 2 | 2 | **18** |
| **k8s** | WRAPPER | 2 | 2 | 2 | 2 | 1 | 1 | 3 | 1 | 3 | 2 | **19** |
| **vm** | WRAPPER | 2 | 2 | 2 | 1 | 2 | 1 | 3 | 1 | 2 | 2 | **18** |
| **ci** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **12** |
| **cloud** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **12** |
| **dns** | WRAPPER | 1 | 3 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **13** |
| **network** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **11** |
| **logs** | WRAPPER | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **13** |
| **metrics** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **11** |

### Tier 3: Communication/Productivity (Score 10-18/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **slack** | WRAPPER | 1 | 2 | 2 | 2 | 1 | 1 | 2 | 0 | 2 | 2 | **15** |
| **email** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 3 | 0 | 2 | 2 | **15** |
| **calendar** | WRAPPER | 1 | 2 | 2 | 2 | 1 | 1 | 3 | 0 | 2 | 2 | **16** |
| **notion** | WRAPPER | 1 | 2 | 2 | 2 | 1 | 1 | 2 | 0 | 2 | 2 | **15** |
| **linear** | WRAPPER | 1 | 2 | 2 | 2 | 1 | 1 | 2 | 0 | 2 | 2 | **15** |
| **sheets** | WRAPPER | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **13** |
| **pdf** | WRAPPER | 1 | 2 | 2 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **13** |
| **figma** | WRAPPER | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 1 | **11** |
| **discord** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **9** |

### Tier 4: Developer Tools (Score 10-22/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **agent** | REAL | 1 | 3 | 3 | 2 | 2 | 2 | 3 | 1 | 2 | 2 | **21** |
| **eval** | REAL | 1 | 3 | 2 | 2 | 1 | 2 | 3 | 0 | 2 | 2 | **18** |
| **ide** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 3 | 0 | 2 | 2 | **15** |
| **ocr** | REAL | 1 | 3 | 3 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **16** |
| **jupyter** | WRAPPER | 1 | 2 | 2 | 1 | 2 | 1 | 2 | 0 | 2 | 2 | **15** |
| **debug** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **14** |
| **api** | WRAPPER | 0 | 2 | 1 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **12** |
| **repl** | WRAPPER | 1 | 2 | 1 | 0 | 1 | 1 | 1 | 0 | 2 | 1 | **10** |
| **clipboard** | WRAPPER | 0 | 2 | 1 | 0 | 0 | 1 | 1 | 0 | 2 | 1 | **8** |
| **git** | WRAPPER | 0 | 2 | 1 | 0 | 0 | 1 | 2 | 0 | 2 | 1 | **9** |

### Tier 5: Creative/Media (Score 12-18/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **latex** | REAL | 2 | 3 | 2 | 2 | 1 | 2 | 3 | 0 | 2 | 2 | **19** |
| **image** | WRAPPER | 2 | 2 | 2 | 2 | 0 | 1 | 3 | 0 | 2 | 2 | **16** |
| **vision** | PARTIAL | 1 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 1 | **13** |
| **video** | WRAPPER | 1 | 2 | 2 | 1 | 0 | 1 | 3 | 0 | 2 | 2 | **14** |
| **audio** | WRAPPER | 1 | 2 | 2 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **13** |
| **cad** | WRAPPER | 1 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **11** |
| **3d** | WRAPPER | 1 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **11** |

### Tier 6: Security / Hardware / Meta / Comms (Score 8-20/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|
| **swarm** | REAL | 1 | 3 | 2 | 2 | 2 | 2 | 3 | 1 | 2 | 2 | **20** |
| **memory** | REAL | 2 | 3 | 2 | 2 | 1 | 1 | 3 | 0 | 2 | 2 | **18** |
| **learn** | REAL | 1 | 3 | 2 | 2 | 1 | 1 | 3 | 0 | 2 | 2 | **17** |
| **prompt** | REAL | 1 | 2 | 2 | 2 | 1 | 1 | 3 | 0 | 2 | 2 | **16** |
| **ghidra** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **14** |
| **wireshark** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **14** |
| **burp** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **14** |
| **zoom** | WRAPPER | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **12** |
| **teams** | WRAPPER | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **12** |
| **colab** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **14** |
| **bluetooth** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **11** |
| **sms** | WRAPPER | 0 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **11** |
| **voice** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **10** |
| **meet** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **10** |
| **serial** | WRAPPER | 0 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **10** |
| **midi** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **9** |
| **homekit** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **9** |
| **usb** | WRAPPER | 0 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **10** |
| **printer** | WRAPPER | 0 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **10** |
| **lab** | WRAPPER | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **13** |

---

## Distribution Summary

| Score Range | Count | Classification |
|-------------|-------|---------------|
| 27-30 (Gold) | 4 | browse, db, excel, unbrowse |
| 20-26 (Strong) | 6 | ios, tui, manna, agent, swarm, docker |
| 15-19 (Adequate) | 18 | android, macos, k8s, vm, ssh, slack, email, calendar, notion, linear, latex, memory, learn, prompt, image, eval, ide, ocr |
| 10-14 (Weak) | 26 | Most infra, creative, security, hardware tools |
| < 10 (Stub) | 8 | discord, clipboard, git, midi, homekit, etc. |

---

## Critical Findings

### 1. The "Snapshot Gap" Is the #1 Problem

**42 of 62 tools score 0-1 on snapshot capability.** This is the single most important criterion. Without a snapshot command, the AI is operating blind — it can't see the current state before acting.

**What "snapshot" should mean for each category:**

| Category | Snapshot Should Show | Example |
|----------|---------------------|---------|
| **Infra** (docker, k8s) | Running containers/pods, resource status | `docker ps` with labels, ports, health |
| **Communication** (slack, email) | Channels/inbox, recent messages, unread count | `slack snapshot` → channels + last messages |
| **Dev tools** (git, debug) | Repo state, branch, uncommitted changes | `git snapshot` → status + log + branch |
| **Media** (image, video) | File metadata, dimensions, duration, format | `image info` → dimensions, format, EXIF |
| **Security** (burp, wireshark) | Active captures, findings, proxy status | `burp snapshot` → targets, issues found |
| **Hardware** (bluetooth, usb) | Connected devices, status | `bluetooth snapshot` → paired devices, connections |

### 2. Many Tools Are "Wrapper Without Value-Add"

**~30 tools** are thin bash wrappers that primarily reorganize CLI flags but don't add AI-specific value. For example:

- `agent-git` wraps `git` but doesn't add snapshot/status/structured output that AI can't already get from `git status`
- `agent-clipboard` wraps `pbcopy/pbpaste` but adds no structure
- `agent-dns` wraps `dig/nslookup` with no AI affordances

**The test**: If an AI could achieve the same result by running the underlying CLI directly with the same effort, the tool adds no value.

### 3. JSON Output Is Inconsistent

Gold standard tools output JSON consistently. Most other tools output raw text, making it hard for AI to parse results programmatically.

### 4. Session Management Is Rare Outside Gold Standard

Only browse, db, excel, tui, and manna have real session management. Tools like docker, ssh, k8s could greatly benefit from tracking active connections/contexts.

---

## Prioritized Improvement Plan

### P0: High Impact, Low Effort (add snapshot to existing real tools)

These tools already execute real commands but lack the critical "snapshot" that lets AI understand state:

| Tool | Current Score | Add | Expected Score |
|------|--------------|-----|----------------|
| **docker** | 20 | `snapshot` → containers + images + volumes + networks as JSON | 24 |
| **k8s** | 19 | `snapshot` → pods + services + deployments as JSON | 23 |
| **git** | 9 | `snapshot` → status + branch + log + remote as JSON | 16 |
| **ssh** | 18 | `snapshot` → active sessions + config hosts as JSON | 21 |
| **clipboard** | 8 | `snapshot` → current content + type + size as JSON | 13 |

**Effort**: ~30 lines each. Each snapshot command runs existing subcommands and combines output into JSON.

### P1: High Impact, Medium Effort (add snapshot + JSON to communication tools)

These tools interact with APIs that have rich state. Adding snapshot transforms them:

| Tool | Add | Impact |
|------|-----|--------|
| **slack** | `snapshot` → channels + unread + recent as JSON | AI can see workspace state before messaging |
| **email** | `snapshot` → inbox summary + unread count as JSON | AI can triage and respond |
| **calendar** | `snapshot` → today's events + upcoming as JSON | AI can schedule without conflicts |
| **notion** | `snapshot` → pages + databases + recent as JSON | AI can navigate workspace |
| **linear** | `snapshot` → issues + sprints + assigned as JSON | AI can manage project state |

**Effort**: ~50-100 lines each. Requires API calls but the tools already have the auth/API infrastructure.

### P2: Medium Impact, Low Effort (ensure all tools output JSON)

Add `--json` flag to every tool that currently outputs raw text. This is a mechanical change:

```bash
# Pattern: wrap output in JSON
if [[ "$output_format" == "json" ]]; then
    echo "{\"result\": $(echo "$output" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))')}"
else
    echo "$output"
fi
```

### P3: Medium Impact, Medium Effort (elevate key wrappers to real tools)

Tools that would benefit most from becoming full implementations:

| Tool | Current | Upgrade Path |
|------|---------|-------------|
| **api** | Thin curl wrapper | Add request history, environment management, collection support (like lightweight Postman) |
| **debug** | lldb/gdb wrapper | Add snapshot (breakpoints, stack, variables as JSON), step-through with state |
| **jupyter** | notebook wrapper | Add snapshot (cells, outputs, kernel state), structured cell execution |
| **repl** | Delegates to tui | Add snapshot (variables, history), structured eval with output capture |

### P4: Low Impact, Low Effort (fix stub tools)

Tools scoring < 10 should either be upgraded to real wrappers or removed to avoid confusion:

| Tool | Recommendation |
|------|---------------|
| **discord** | Needs real API integration or remove |
| **clipboard** | Needs JSON output + history |
| **midi** | Niche; keep as stub with clear help |
| **homekit** | Needs HomeKit API integration or remove |

### P5: Architectural (long-term)

1. **Shared snapshot framework**: Create a `lib/snapshot.sh` helper that formats consistent JSON snapshots
2. **Plugin system for output formats**: All tools get `--json`, `--csv`, `--compact` for free
3. **Session registry**: Central `~/.agent-do/state.yaml` tracks all active sessions (docker contexts, ssh connections, tui sessions) so AI has global awareness
4. **Health check framework**: Every tool gets `status` command that reports connectivity and readiness

---

## The North Star

Every agent-do tool should answer these questions for an AI agent:

1. **"What's the current state?"** → `snapshot` command
2. **"What can I do?"** → `--help` with examples
3. **"Did it work?"** → JSON output with success/error
4. **"What went wrong?"** → Actionable error codes
5. **"How do I recover?"** → Recovery commands

When all 62 tools answer these 5 questions reliably, agent-do becomes the universal AI-to-world interface.
