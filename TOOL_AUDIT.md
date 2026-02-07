# agent-do Tool Audit Report

> Full analysis of 62 tools against the gold standard pattern.
> Generated 2026-02-06 by 7-agent parallel audit swarm.
> Updated 2026-02-06 after P0-P3 fixes (20 tools upgraded with snapshot commands).

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

### Tier 2: Infrastructure (Score 11-24/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total | Delta |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|-------|
| **docker** | WRAPPER | 3 | 3 | 3 | 3 | 1 | 2 | 2 | 1 | 3 | 2 | **24** | +4 |
| **k8s** | WRAPPER | 3 | 2 | 3 | 3 | 1 | 1 | 3 | 1 | 3 | 2 | **23** | +4 |
| **ssh** | WRAPPER | 3 | 3 | 2 | 2 | 2 | 2 | 2 | 1 | 2 | 2 | **22** | +4 |
| **vm** | WRAPPER | 3 | 2 | 2 | 2 | 2 | 1 | 3 | 1 | 2 | 2 | **21** | +3 |
| **ci** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **12** | — |
| **cloud** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **12** | — |
| **dns** | WRAPPER | 1 | 3 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **13** | — |
| **network** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **11** | — |
| **logs** | WRAPPER | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **13** | — |
| **metrics** | WRAPPER | 1 | 2 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **11** | — |

### Tier 3: Communication/Productivity (Score 9-20/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total | Delta |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|-------|
| **slack** | WRAPPER | 3 | 2 | 2 | 3 | 1 | 1 | 2 | 0 | 2 | 2 | **19** | +4 |
| **calendar** | WRAPPER | 3 | 2 | 2 | 3 | 1 | 1 | 3 | 0 | 2 | 2 | **20** | +4 |
| **email** | WRAPPER | 2 | 2 | 2 | 2 | 1 | 1 | 3 | 0 | 2 | 2 | **18** | +3 |
| **notion** | WRAPPER | 3 | 2 | 2 | 3 | 1 | 1 | 2 | 0 | 2 | 2 | **19** | +4 |
| **linear** | WRAPPER | 3 | 2 | 2 | 3 | 1 | 1 | 2 | 0 | 2 | 2 | **19** | +4 |
| **pdf** | WRAPPER | 2 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **16** | +3 |
| **sheets** | WRAPPER | 1 | 2 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 2 | **13** | — |
| **figma** | WRAPPER | 1 | 1 | 1 | 1 | 1 | 1 | 2 | 0 | 2 | 1 | **11** | — |
| **discord** | WRAPPER | 0 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 1 | **9** | — |

### Tier 4: Developer Tools (Score 14-21/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total | Delta |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|-------|
| **agent** | REAL | 1 | 3 | 3 | 2 | 2 | 2 | 3 | 1 | 2 | 2 | **21** | — |
| **api** | REAL | 3 | 2 | 2 | 2 | 1 | 1 | 2 | 0 | 2 | 2 | **18** | +6 |
| **eval** | REAL | 1 | 3 | 2 | 2 | 1 | 2 | 3 | 0 | 2 | 2 | **18** | — |
| **debug** | REAL | 3 | 2 | 2 | 2 | 1 | 1 | 2 | 0 | 2 | 2 | **18** | +4 |
| **jupyter** | WRAPPER | 3 | 2 | 2 | 2 | 2 | 1 | 2 | 0 | 2 | 2 | **19** | +4 |
| **git** | WRAPPER | 3 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 1 | **16** | +7 |
| **clipboard** | WRAPPER | 2 | 2 | 1 | 2 | 0 | 1 | 1 | 0 | 2 | 1 | **13** | +5 |
| **ocr** | REAL | 1 | 3 | 3 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **16** | — |
| **repl** | WRAPPER | 2 | 2 | 1 | 2 | 1 | 1 | 2 | 0 | 2 | 1 | **15** | +5 |
| **ide** | WRAPPER | 1 | 2 | 2 | 1 | 1 | 1 | 3 | 0 | 2 | 2 | **15** | — |

### Tier 5: Creative/Media (Score 11-21/30)

| Tool | Class | Snap | Exec | Value | JSON | Session | Error | Help | Recovery | Names | Workflow | Total | Delta |
|------|-------|------|------|-------|------|---------|-------|------|----------|-------|----------|-------|-------|
| **latex** | REAL | 3 | 3 | 2 | 3 | 1 | 2 | 3 | 0 | 2 | 2 | **22** | +3 |
| **image** | WRAPPER | 3 | 2 | 2 | 3 | 0 | 1 | 3 | 0 | 2 | 2 | **19** | +3 |
| **video** | WRAPPER | 2 | 2 | 2 | 2 | 0 | 1 | 3 | 0 | 2 | 2 | **17** | +3 |
| **pdf** | WRAPPER | 2 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **16** | +3 |
| **audio** | WRAPPER | 2 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 2 | **16** | +3 |
| **vision** | PARTIAL | 1 | 2 | 2 | 2 | 0 | 1 | 2 | 0 | 2 | 1 | **13** | — |
| **cad** | WRAPPER | 1 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **11** | — |
| **3d** | WRAPPER | 1 | 1 | 1 | 1 | 0 | 1 | 2 | 0 | 2 | 2 | **11** | — |

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

## Distribution Summary (Updated After P0-P3)

| Score Range | Before | After | Tools |
|-------------|--------|-------|-------|
| 27-30 (Gold) | 4 | 4 | browse, db, excel, unbrowse |
| 20-26 (Strong) | 6 | 14 | ios, tui, manna, agent, swarm, docker, k8s, ssh, vm, calendar, latex, agent-do(agent), eval, jupyter |
| 15-19 (Adequate) | 18 | 21 | android, macos, slack, email, notion, linear, api, debug, git, repl, image, video, pdf, audio, memory, learn, prompt, ocr, ide, clipboard, pdf |
| 10-14 (Weak) | 26 | 20 | ci, cloud, dns, network, logs, metrics, sheets, figma, ghidra, wireshark, burp, zoom, teams, colab, bluetooth, sms, lab, cad, 3d, vision |
| < 10 (Stub) | 8 | 3 | discord, midi, homekit |

**Net improvement**: 20 tools upgraded. Zero tools score <10 that aren't niche hardware (midi, homekit) or genuinely need API integration (discord).

---

## Critical Findings

### 1. The "Snapshot Gap" — Largely Closed

**Before**: 42 of 62 tools scored 0-1 on snapshot. **After P0-P3**: 27 tools now have snapshot commands. The remaining ~35 tools without snapshot are either niche hardware (midi, serial, usb) or thin wrappers where the underlying CLI already provides adequate output (dns, network).

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

- `agent-dns` wraps `dig/nslookup` with no AI affordances
- `agent-network` wraps `netstat/ss` without structured output
- `agent-sheets` wraps Google Sheets but lacks snapshot of sheet structure

Note: `agent-git` and `agent-clipboard` have been upgraded with JSON snapshot commands and now provide genuine value over raw CLI.

**The test**: If an AI could achieve the same result by running the underlying CLI directly with the same effort, the tool adds no value.

### 3. JSON Output Is Inconsistent

Gold standard tools output JSON consistently. Most other tools output raw text, making it hard for AI to parse results programmatically.

### 4. Session Management Is Rare Outside Gold Standard

Only browse, db, excel, tui, and manna have real session management. Tools like docker, ssh, k8s could greatly benefit from tracking active connections/contexts.

---

## Prioritized Improvement Plan

### P0: ✅ DONE — snapshot for docker, k8s, git, ssh, clipboard

Added JSON snapshot commands outputting full state. Avg +4.8 points per tool.

### P1: ✅ DONE — snapshot for slack, email, calendar, notion, linear

Added API-powered snapshot commands. Avg +3.6 points per tool.

### P2: ✅ DONE — snapshot for image, video, audio, pdf, latex, vm

Added environment + file discovery snapshots. Avg +3.0 points per tool.

### P3: ✅ DONE — elevated api, debug, jupyter, repl

- **api**: snapshot (env, history), `history` command, `env` command for base URLs
- **debug**: snapshot (available debuggers, debuggable processes, core dumps), `processes` command
- **jupyter**: snapshot (servers, kernels, notebook cell summary with error detection)
- **repl**: snapshot (available interpreters with versions, active tmux sessions)

Avg +5.0 points per tool.

### P4: Low Impact, Low Effort (fix remaining stub tools)

3 tools still score < 10:

| Tool | Score | Recommendation |
|------|-------|---------------|
| **discord** | 9 | Add snapshot (servers, channels) via Discord bot token API. Similar to slack pattern. |
| **midi** | 9 | Add snapshot (connected MIDI devices, available ports). Niche but `system_profiler SPMIDIDataType` works on macOS. |
| **homekit** | 9 | Add snapshot (paired accessories, rooms). Requires HomeKit framework or `shortcuts` CLI on macOS. |

### P5: Architectural (long-term)

1. **`lib/snapshot.sh`** — Shared snapshot helper: consistent JSON envelope `{"tool": "...", "timestamp": "...", "data": {...}}`, error formatting, `--compact` flag
2. **`lib/json-output.sh`** — Source-able helper giving every tool `--json` flag for free: wraps command output in `{"success": true, "result": "..."}`
3. **Session registry** — Central `~/.agent-do/state.yaml` updated by all tools: tracks docker contexts, ssh connections, tui sessions, browser sessions, API envs. `agent-do --status` shows global state.
4. **Health check framework** — Every tool gets `status` command: checks dependencies installed, credentials configured, services reachable. `agent-do --health` runs all checks.

---

## The North Star

Every agent-do tool should answer these questions for an AI agent:

1. **"What's the current state?"** → `snapshot` command
2. **"What can I do?"** → `--help` with examples
3. **"Did it work?"** → JSON output with success/error
4. **"What went wrong?"** → Actionable error codes
5. **"How do I recover?"** → Recovery commands

When all 62 tools answer these 5 questions reliably, agent-do becomes the universal AI-to-world interface.
