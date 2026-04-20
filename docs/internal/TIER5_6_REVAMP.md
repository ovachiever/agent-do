# Tier 5/6 Revamp Plan

> Forward plan for eliminating the current low-end tool tiers by either promoting, merging, or retiring the weakest tools in the catalog.
> This is a planning document, not a statement of current shipped behavior.

---

## Goal

Remove the current "tier 5" and "tier 6" classes from the tool surface.

That does **not** mean polishing every weak tool in place.

It means:

1. every surviving tool must reach the tier-4 floor or better
2. weak standalone tools should be merged into stronger family tools where that improves the contract
3. tools that cannot justify their existence should be retired from the public catalog

The success condition is simple:

- no public tool remains below the tier-4 floor
- the average catalog quality is materially higher
- the public surface is clearer, not larger

This plan starts from:

- the checked-in audit in [TOOL_AUDIT.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/docs/internal/TOOL_AUDIT.md)
- the current 84-tool catalog in [registry.yaml](/Users/erik/Documents/AI/Custom_Coding/agent-do/registry.yaml)
- current repo architecture and validation in [ARCHITECTURE.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/ARCHITECTURE.md), [CLAUDE.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/CLAUDE.md), and [test.sh](/Users/erik/Documents/AI/Custom_Coding/agent-do/test.sh)

---

## Floor

No tool stays public unless it can answer these questions for an agent:

1. What is the current state?
2. What can I do next?
3. Did the action work?
4. What failed?
5. How do I recover?

Concretely, every surviving tool must have:

- `--help` with at least one real workflow example
- a `snapshot` or equivalent current-state command
- structured output or `--json`
- actionable errors
- value over directly running the underlying CLI or app

Anything below that floor must either:

- be promoted
- be merged
- or be removed

---

## Scope

This plan covers the current weakest public tools:

- `figma`
- `sheets`
- `cloud`
- `burp`
- `wireshark`
- `ghidra`
- `serial`
- `bluetooth`
- `usb`
- `printer`
- `zoom`
- `meet`
- `teams`
- `voice`
- `discord`
- `lab`
- `colab`
- `3d`
- `cad`
- `midi`
- `homekit`

These are the tools most responsible for the current low-end tail described in [TOOL_AUDIT.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/docs/internal/TOOL_AUDIT.md).

---

## Decision Table

This is the binding plan-level decision table.

| Tool | Current Problem | Decision | Target Outcome |
|------|-----------------|----------|----------------|
| `figma` | Thin wrapper, weak state model | Keep standalone, promote | Real design-system and file-inspection tool |
| `sheets` | Weak snapshot and low leverage vs raw API | Keep standalone, promote | Real spreadsheet/workbook tool distinct from `excel` |
| `cloud` | Vague umbrella duplicated by stronger provider tools | Retire | Remove from public catalog; route to provider tools |
| `burp` | Thin shell over underlying app | Keep standalone, promote | Web-security workflow tool |
| `wireshark` | Thin shell over captures | Keep standalone, promote | Network-capture workflow tool |
| `ghidra` | Thin shell over decompile commands | Keep standalone, promote | Reverse-engineering workflow tool |
| `serial` | Too narrow as standalone | Merge | Fold into new `hardware` family |
| `bluetooth` | Too narrow as standalone | Merge | Fold into new `hardware` family |
| `usb` | Too narrow as standalone | Merge | Fold into new `hardware` family |
| `printer` | Too narrow as standalone | Merge | Fold into new `hardware` family |
| `zoom` | Meeting-specific leaf with weak AI value | Merge | Fold into new `meetings` family |
| `meet` | Meeting-specific leaf with weak AI value | Merge | Fold into new `meetings` family |
| `teams` | Meeting-specific leaf with weak AI value | Merge | Fold into new `meetings` family |
| `voice` | Overlaps heavily with `audio` | Merge | Fold into `audio` as speech/TTS/STT surface |
| `discord` | Important domain, but weak current implementation | Keep standalone, promote | Slack-grade comms tool |
| `lab` | Duplicative wrapper around notebook workflows | Merge | Fold into `jupyter` |
| `colab` | Duplicative wrapper around notebook workflows | Merge | Fold into `jupyter` |
| `3d` | Weak substrate, unclear value proposition | Retire | Remove from public catalog until a real substrate exists |
| `cad` | Weak substrate, unclear value proposition | Retire | Remove from public catalog until a real substrate exists |
| `midi` | Too weak standalone, but salvageable via system-level device model | Merge | Fold into new `hardware` family |
| `homekit` | Too weak, poor standalone justification | Retire | Remove from public catalog until a real local API exists |

---

## Target Public Shape

After the revamp, the public surface should look like this:

### Keep and Promote

- `figma`
- `sheets`
- `discord`
- `burp`
- `wireshark`
- `ghidra`

### Merge Into Stronger Family Tools

- new `meetings`
  - absorbs `zoom`, `meet`, `teams`
- new `hardware`
  - absorbs `serial`, `bluetooth`, `usb`, `printer`, `midi`
- existing `audio`
  - absorbs `voice`
- existing `jupyter`
  - absorbs `lab`, `colab`

### Remove From Public Catalog

- `cloud`
- `3d`
- `cad`
- `homekit`

Removed tools may still exist internally during migration, but they should not remain first-class public tools after deprecation completes.

---

## Family Redesigns

### 1. `meetings`

Purpose:
- one strong meeting/calls surface instead of three weak provider leaves

Target commands:

```bash
agent-do meetings snapshot [--provider zoom|meet|teams|all]
agent-do meetings list [--provider ...]
agent-do meetings join <meeting-id-or-link> --provider <provider>
agent-do meetings new --provider <provider>
agent-do meetings chat <target> --provider teams
agent-do meetings recordings [--provider ...]
agent-do meetings transcript <recording-id> --provider ...
```

Minimum bar:

- provider-aware meeting snapshot
- upcoming/recent meeting listing
- join/create flows
- structured status output
- one workflow example per provider

Migration:

- `agent-zoom`, `agent-meet`, `agent-teams` become thin compatibility shims for one release
- then remove from registry

### 2. `hardware`

Purpose:
- one explicit local-device surface instead of many ultra-thin leaves

Target commands:

```bash
agent-do hardware snapshot
agent-do hardware serial list
agent-do hardware serial monitor <port>
agent-do hardware bluetooth scan
agent-do hardware bluetooth connect <device>
agent-do hardware usb list
agent-do hardware printer list
agent-do hardware printer print <file>
agent-do hardware midi list
agent-do hardware midi monitor <port>
```

Minimum bar:

- machine-readable connected-device snapshot
- domain-specific subcommands for serial, bluetooth, usb, printer, midi
- structured status and errors
- clear live vs read-only distinctions

Migration:

- `serial`, `bluetooth`, `usb`, `printer`, `midi` become compatibility shims for one release
- then remove from registry

### 3. `audio`

Purpose:
- unify generic audio and speech workflows

Target additions:

```bash
agent-do audio snapshot
agent-do audio devices
agent-do audio record <file>
agent-do audio transcribe <file>
agent-do audio speak "text"
agent-do audio listen --duration 5
```

Migration:

- `voice` becomes an alias layer first
- then remove standalone public listing

### 4. `jupyter`

Purpose:
- one notebook/compute surface with local and hosted variants

Target additions:

```bash
agent-do jupyter snapshot
agent-do jupyter servers
agent-do jupyter notebooks
agent-do jupyter open <file> [--provider local|colab]
agent-do jupyter run <notebook> [--provider ...]
agent-do jupyter convert <file>
```

Migration:

- `lab` and `colab` collapse into `jupyter`
- keep compatibility aliases for one release

---

## Standalone Promotion Plans

These tools stay standalone because they have enough domain depth to justify it.

### `figma`

Must gain:

- file/page/frame snapshot
- component and style-token extraction
- comments list/reply
- selected-node export and inspect
- robust `--json`

Minimum command set:

```bash
agent-do figma snapshot
agent-do figma files
agent-do figma file <id>
agent-do figma comments <file-id>
agent-do figma tokens <file-id>
agent-do figma export <node-id>
```

### `sheets`

Must become clearly distinct from `excel`.

`excel` = local workbook automation  
`sheets` = cloud spreadsheet/workspace automation

Must gain:

- spreadsheet/sheet snapshot
- range schema and formula inspection
- sheet management
- structured updates

Minimum command set:

```bash
agent-do sheets snapshot <sheet-id>
agent-do sheets tabs <sheet-id>
agent-do sheets read <sheet-id> A1:C20
agent-do sheets write <sheet-id> A1 value
agent-do sheets formulas <sheet-id>
agent-do sheets sheet <sheet-id> add|rename|delete
```

### `discord`

Must become Slack-grade.

Must gain:

- guild/channel snapshot
- recent messages
- thread/reply support
- send/edit basic workflow
- optional presence of unread-ish recent state

Minimum command set:

```bash
agent-do discord snapshot
agent-do discord servers
agent-do discord channels <server>
agent-do discord recent <channel>
agent-do discord send <channel> "message"
agent-do discord reply <channel> <message-id> "message"
```

### `burp`

Must gain:

- project/proxy snapshot
- active target list
- scan status
- issues/finding export

### `wireshark`

Must gain:

- interface snapshot
- active capture snapshot
- filter-aware packet summaries
- conversation summary

### `ghidra`

Must gain:

- project/program snapshot
- function and symbol inventory
- decompile with structured context
- cross-reference search

For `burp`, `wireshark`, and `ghidra`, the key is:

- keep them standalone
- build one shared security/reverse substrate under `lib/security/`
- avoid a fake umbrella public tool unless a later pass proves it helps

---

## Retirements

### `cloud`

Reason:
- duplicates stronger provider tools already in the catalog (`gcp`, `cloudflare`, `render`, `vercel`, `supabase`, `namecheap`)
- no clear standalone value proposition

Action:

- remove from discovery recommendations
- replace with provider-routing suggestions
- keep optional compatibility shim briefly if needed

### `3d` and `cad`

Reason:
- current surface is too thin
- no strong shared substrate exists
- no clear AI-specific leverage over invoking external conversion tools directly

Action:

- remove from the public catalog
- keep only if/when a real scene/model/CAD substrate is built

### `homekit`

Reason:
- weak current justification
- poor local API story compared with other domains
- better handled later via a stronger Apple/home automation substrate if one actually materializes

Action:

- remove from public catalog

---

## Shared Substrates To Build First

Do not upgrade survivors one by one without a substrate.

Build these first:

1. `lib/snapshot.sh`
   - consistent envelope
   - compact vs verbose modes
   - error formatting

2. `lib/json-output.sh`
   - consistent `--json`
   - wrapper helpers for success/error payloads

3. domain helpers:
   - `lib/meetings/`
   - `lib/hardware/`
   - `lib/security/`
   - `lib/workspace/` for Sheets/Figma if needed

4. standard readiness hooks
   - credential checks
   - dependency checks
   - service reachability checks

5. migration shim pattern
   - old tool name → warning → new command

Without this substrate, the revamp becomes a pile of unrelated wrappers again.

---

## Execution Phases

### Phase 0: Freeze and Taxonomy

Goal:
- prevent more weak leaves from entering the catalog

Actions:

- freeze new standalone additions in these domains until the revamp lands
- add this plan to internal docs
- publish a survivorship table and migration map

Files:

- [docs/internal/TIER5_6_REVAMP.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/docs/internal/TIER5_6_REVAMP.md)
- [README.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/README.md) later, after implementation

### Phase 1: Shared Promotion Kit

Goal:
- make upgrades cheap and consistent

Actions:

- strengthen shared snapshot and JSON helpers
- add reusable help/example templates
- add migration shim helper for deprecations

Files:

- `lib/snapshot.sh`
- `lib/json-output.sh`
- `lib/retry.sh`
- `bin/health`
- `bin/suggest`

### Phase 2: Family Merges

Goal:
- collapse the weakest leaves into stronger family tools

Actions:

- add `tools/agent-meetings`
- add `tools/agent-hardware`
- fold `voice` into `audio`
- fold `lab` and `colab` into `jupyter`
- add compatibility aliases

Files:

- new `tools/agent-meetings`
- new `tools/agent-hardware`
- `tools/agent-audio`
- `tools/agent-jupyter`
- compatibility wrappers in old tool paths
- `registry.yaml`

### Phase 3: Standalone Promotions

Goal:
- promote the keepers above the floor

Actions:

- deepen `figma`
- deepen `sheets`
- deepen `discord`
- deepen `burp`
- deepen `wireshark`
- deepen `ghidra`

Files:

- respective tool files/directories
- `registry.yaml`
- tool-specific tests

### Phase 4: Retirement and Registry Cleanup

Goal:
- remove dead weight

Actions:

- retire `cloud`
- retire `3d`
- retire `cad`
- retire `homekit`
- remove expired compatibility aliases
- update discovery metadata and docs

Files:

- `registry.yaml`
- `README.md`
- `CLAUDE.md`
- `ARCHITECTURE.md`
- deprecated tool files

### Phase 5: Re-audit

Goal:
- prove the low-end tail is gone

Actions:

- rerun tool audit rubric for all surviving tools
- publish updated scorecard
- verify no public tool is below floor

Files:

- [docs/internal/TOOL_AUDIT.md](/Users/erik/Documents/AI/Custom_Coding/agent-do/docs/internal/TOOL_AUDIT.md)

---

## Validation Gates

Every phase must pass:

- `--help` works for every affected tool
- `--json` works or equivalent structured output exists
- `snapshot` or equivalent current-state command exists
- affected tools are discoverable via `agent-do find` / `suggest`
- root validation passes: [test.sh](/Users/erik/Documents/AI/Custom_Coding/agent-do/test.sh)

New focused tests required:

- `tests/test_meetings.py`
- `tests/test_hardware.py`
- `tests/test_figma.py`
- `tests/test_sheets.py`
- `tests/test_discord.py`
- `tests/test_burp.py`
- `tests/test_wireshark.py`
- `tests/test_ghidra.py`
- migration/alias regression tests

No merged or promoted family is considered done without:

- at least one focused test file
- one real workflow example in help text
- registry metadata updated

---

## Success Metrics

The revamp is successful when all of these are true:

1. no public tool remains below the tier-4 floor
2. there are no standalone public tools equivalent to current tier 5 or 6
3. the public catalog is smaller or equal in count, but stronger on average
4. family surfaces (`meetings`, `hardware`, `jupyter`, `audio`) are clearer than the leaf tools they replaced
5. `TOOL_AUDIT.md` no longer needs a "stub" or "bottom tier" section for these domains

Numerically:

- target minimum score for every surviving public tool: **15/30**
- target for merged family tools and promoted keepers: **18+/30**
- target zero tools below **15/30**

---

## Non-Goals

- no broad rewrite of already-strong tools
- no fake family umbrellas that merely rewrap weak leaves
- no preservation of standalone tool names purely for sentiment
- no new public tool unless it clearly raises the floor

---

## Recommendation

Do this in three aggressive moves:

1. build the shared substrate
2. merge the obvious leaf clutter
3. promote the few standalone tools that truly deserve to survive

That is how tier 5 and 6 disappear for real.
