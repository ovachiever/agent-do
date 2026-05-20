# AppleEvents Tool Plan

## Decision

Create a new canonical tool named `appleevents`.

`appleevents` is the public name because the user-facing capability is controlling scriptable macOS applications through their automation interface. `osa` is accurate as an implementation layer, but it is less discoverable and reads like a runtime detail. The tool should route `osa`, `osascript`, `AppleScript`, `JXA`, `sdef`, and `AppleEvents` intents to `agent-do appleevents`.

Do not fold this into `agent-do macos`. The existing `macos` tool controls visible UI through Accessibility and System Events. The new tool should control applications through scriptable dictionaries and AppleEvents. The distinction matters for permissions, observability, reliability, and failure modes.

## Product Boundary

`agent-do appleevents` answers:

- Is this app scriptable?
- What commands, classes, properties, and suites does it expose?
- Can this host send AppleEvents to that app, when explicitly allowed to perform a live permission probe?
- Can I compile this AppleScript or JXA without running it?
- Can I run a bounded AppleEvent script through the intended macOS automation path?
- What exactly was sent, to which app, with what result?

It should not be a GUI automation fallback. If an app has no useful scripting dictionary, report that and recommend `agent-do macos` or `agent-do screen` only as the explicit alternate path.

## Proposed Commands

Read-only commands:

```bash
agent-do appleevents apps
agent-do appleevents probe <app-or-bundle-id>
agent-do appleevents dictionary <app-or-bundle-id> [--format json|markdown|raw]
agent-do appleevents terms <app-or-bundle-id> [query]
agent-do appleevents compile --language applescript|javascript (--file <path>|--stdin)
agent-do appleevents cache status
agent-do appleevents cache clear [<app-or-bundle-id>]
```

Live/control commands:

```bash
agent-do +live(scope=desktop,ttl=5m) appleevents permissions <app-or-bundle-id> [--launch|--no-launch]
agent-do +live(scope=desktop,ttl=5m) appleevents run --language applescript|javascript (--file <path>|--stdin|--script <inline-script>) [--target <app-or-bundle-id>] [--launch|--no-launch]
agent-do +live(scope=desktop,ttl=5m) appleevents tell <app-or-bundle-id> --script <inline-script> [--language applescript|javascript] [--launch|--no-launch]
```

`run` is the general execution path. `tell` is terse sugar for `run --target <app> --script ...`; it must share the same compile, app identity, launch-policy, and permission preflight path. Preflight behavior should never depend on which command spelling the user picked.

Default launch policy should be `--no-launch`. AppleEvents can silently launch non-running apps, which is a side effect. `--launch` is the explicit opt-in.

## Output Contract

All commands should support `--json`.

Successful `probe` output:

```json
{
  "app": "Xcode",
  "bundle_id": "com.apple.dt.Xcode",
  "path": "/Applications/Xcode.app",
  "scriptable": true,
  "dictionary": {
    "available": true,
    "suites": 8,
    "commands": 42,
    "classes": 31,
    "cached": true
  },
  "permissions": {
    "automation": "unknown",
    "reason": "macOS does not expose reliable read-only Automation grant state"
  }
}
```

`probe` should not send an AppleEvent. It can report static facts: app resolution, bundle metadata, scriptability hints, and dictionary availability. Automation grant state remains `unknown` until a live `permissions` probe or execution attempt sends an event and classifies the result.

Live permission probe output:

```json
{
  "target": {
    "app": "Xcode",
    "bundle_id": "com.apple.dt.Xcode"
  },
  "probe_event": "get name",
  "launch_policy": "no-launch",
  "sent_event": true,
  "automation": "allowed|denied|not_running|object_error|event_not_handled|unknown_error",
  "osstatus": -1743,
  "stderr": "...",
  "duration_ms": 87
}
```

Execution output:

```json
{
  "target": {
    "app": "Xcode",
    "bundle_id": "com.apple.dt.Xcode"
  },
  "language": "applescript",
  "script_sha256": "<hash>",
  "compiled": true,
  "ran": true,
  "stdout": "...",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 123
}
```

Do not log full scripts into telemetry by default. Log target app, language, script hash, command, duration, and exit status.

## Implementation Shape

Create a directory tool:

```text
tools/agent-appleevents/
  agent-appleevents
  appleevents_ops.py
  test/
    fixtures/
      finder.sdef.xml
      xcode.sdef.xml
    test_dictionary_parse.py
```

The bash entrypoint should match existing tool conventions:

- `set -euo pipefail`
- `--help` support
- delegate to Python backend
- no new dependencies unless required

The Python backend should use standard macOS tools first:

- `mdfind` or Launch Services metadata for app resolution where practical
- Info.plist metadata for cheap scriptability discovery, especially `NSAppleScriptEnabled` and `OSAScriptingDefinition`
- `osascript` for AppleScript/JXA execution
- `osacompile` for compile-only validation
- `sdef` for scripting dictionary extraction
- `xml.etree.ElementTree` for dictionary parsing

Avoid PyObjC for the first version unless direct AppleEvent descriptors become necessary. The initial invariant is useful, inspectable app scripting through system-provided CLI surfaces.

Do not bulk-run `sdef` across every installed app for `apps`; it is too slow and too invasive. Use cheap Info.plist and bundle metadata for inventory, then run `sdef` lazily for `probe` and `dictionary`.

## Safety Model

Read-only commands do not require a live lease:

- `apps`
- `probe`
- `dictionary`
- `terms`
- `compile`
- cache commands

Commands that send AppleEvents must require the shared live-control gate:

- `permissions`
- `run`
- `tell`

`permissions <app>` is a live probe, not a read-only query. macOS TCC Automation state is not reliably readable from a normal process because TCC.db is protected and implementation-dependent. The honest way to learn Automation state is to send a benign event, usually `get name`, and classify the result. That can prompt the user, fail with a permission error, or launch the app unless launch policy blocks it, so it belongs behind the live gate.

Execution must:

- compile before running when possible
- require a target app when the script can be scoped
- use explicit timeouts
- fail closed on denied permissions, missing target app, compile failure, or ambiguous app resolution
- surface macOS TCC/Automation denials as actionable state, not generic script failure
- preserve stdout/stderr separately
- avoid alternate GUI fallbacks unless the user explicitly invokes a different tool

Compile expectations:

- AppleScript compile checks are meaningful for syntax and many static terminology errors.
- JXA compile checks catch parse errors but are shallower; many failures still occur only at runtime.

Initial OSStatus classifier:

- `-1743` / `errAEEventNotPermitted`: Automation denied, not granted, or blocked by TCC
- `-600` / `procNotFound`: target process is not running under `--no-launch`, or the target cannot be addressed
- `-1728` / `errAENoSuchObject`: script ran but the addressed object/reference does not exist
- `-1708` / `errAEEventNotHandled`: target does not handle the requested event
- anything else: preserve raw status, stderr, and command context as `unknown_error`

## Registry Entry

Add `appleevents` to `registry.yaml` with:

- description: Control scriptable macOS apps through AppleEvents, AppleScript, and JXA
- capabilities:
  - inspect app scripting dictionaries
  - compile AppleScript/JXA safely
  - run live-gated AppleEvent scripts
  - diagnose macOS Automation permission state
- commands:
  - `probe`
  - `dictionary`
  - `terms`
  - `compile`
  - `permissions`
  - `run`
  - `tell`
- discover keywords:
  - appleevents
  - apple events
  - applescript
  - javascript for automation
  - jxa
  - osa
  - osascript
  - sdef
  - scripting dictionary
  - xcode automation
- raw CLI equivalents:
  - `osascript` -> `agent-do appleevents run`
  - `osacompile` -> `agent-do appleevents compile`
  - `sdef` -> `agent-do appleevents dictionary`
- project signals:
  - macos
  - desktop
  - automation
  - native
- readiness:
  - check: `agent-do +live(scope=desktop,ttl=5m) appleevents permissions <app>`
  - note: macOS Automation permission is target-app specific and can only be confirmed by a live AppleEvent probe
- concurrency: `mixed`

## Relationship To Existing Tools

Use `appleevents` when:

- the app exposes a scripting dictionary
- the goal is semantic app control rather than visible UI interaction
- compile-time validation and app dictionary inspection matter
- Xcode/Finder/Calendar/Mail/UTM-style app automation is the target

Use `macos` when:

- the action is visible UI control
- the app has no useful scripting dictionary
- the required action is a button, menu, field, dialog, or window operation

Use `screen` or `vision` when:

- Accessibility does not expose useful semantics
- visual matching or OCR is the only practical observation layer

Use service-specific API tools when:

- service credentials are available
- the intended product path is API messaging, deployment, data access, or another non-GUI integration

Do not use `appleevents` as a workaround for missing service credentials unless the target app exposes a real scriptable path for the needed operation. If an app has no useful dictionary for the requested workflow, the AppleEvents tool should say so and recommend the appropriate API, `macos`, `screen`, or `vision` path explicitly.

## Milestones

1. Skeleton and routing
   - add `tools/agent-appleevents/agent-appleevents`
   - add `--help`
   - add registry entry
   - confirm `agent-do --list`, `agent-do find osascript`, and `agent-do suggest` route correctly

2. Read-only introspection
   - implement app resolution
   - implement cheap `apps` inventory from bundle metadata without bulk `sdef`
   - implement `dictionary`
   - parse SDEF into suites, commands, classes, properties
   - implement `probe` and `terms`
   - cache dictionaries by bundle id plus app version, including `CFBundleShortVersionString` where available
   - add fixture tests for parser behavior

3. Compile path
   - implement `compile`
   - support AppleScript and JXA
   - support `--file` and `--stdin`
   - preserve compile diagnostics

4. Live-gated execution
   - wire `permissions`, `run`, and `tell` through `lib/live/`
   - compile before execution
   - enforce timeout, launch policy, and target-app preflight
   - implement `tell` as sugar over the same `run` execution path
   - return structured stdout/stderr/exit code

5. Permission diagnostics
   - classify common TCC Automation and AppleEvent errors by OSStatus code
   - report host app and target app
   - document the System Settings path without claiming it can be fixed automatically
   - add classifier tests for `-1743`, `-600`, `-1728`, and `-1708`

6. Validation and docs
   - add targeted tests
   - run `./test.sh`
   - update `README.md`, `ARCHITECTURE.md`, and `CLAUDE.md` only with current-state facts after implementation

## Acceptance Criteria

- `agent-do appleevents --help` documents all commands.
- `agent-do --list` includes `appleevents`.
- `agent-do find osascript` recommends `appleevents`, not `macos`.
- `agent-do appleevents probe Finder --json` identifies Finder as scriptable on macOS.
- `agent-do appleevents dictionary Finder --format json` returns parsed suites and commands.
- `agent-do appleevents compile --language applescript --stdin` validates a simple script without running it.
- `agent-do appleevents probe Finder --json` reports Automation permission as `unknown` without sending an event.
- `agent-do appleevents permissions Finder` is rejected without a live lease.
- `agent-do +live(scope=desktop,ttl=5m) appleevents run ...` is required for execution.
- `agent-do +live(scope=desktop,ttl=5m) appleevents tell Finder --script ...` goes through the same implementation path as `run --target Finder --script ...`.
- `--no-launch` is the default for live commands, and a non-running target is reported instead of launched.
- Denied Automation permission is reported as a permission state with the target app named.
- Non-macOS hosts fail with a clear unsupported-platform result.
