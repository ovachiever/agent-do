---
workflow: 2
manna: mn-fa0e85
track: mn-b7a0cc
source: null
base_commit: c946237d65f2d39e5cd4ca6dc62619935a38dd71
scope: 'Bootstrap dialog: nested package.json beats the git root, dialog dies with the 10s hook timeout, re-fires on every compact'
inputs: []
binding: sha256:4fd00284978d4972b2d366d33152b157a92b83ae3d636ff91803439981f91a22
---

# Handoff: Bootstrap dialog: nested package.json beats the git root, dialog dies with the 10s hook timeout, re-fires on every compact

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-fa0e85
```

## Scope

Bootstrap dialog: nested package.json beats the git root, dialog dies with the 10s hook timeout, re-fires on every compact

## Inputs

- None declared.

## Work order

Evidence 2026-09-02 19:14: the vms.io session's tracked cwd sits in apps/web (1668 transcript lines vs 1119 at the repo root). Auto-compact at 19:14:46 and 19:14:56 re-fired SessionStart; the screenshot of the dialog is stamped 19:14:54. Three defects, three fixes. (1) bin/bootstrap find_project_root stops at the first marker walking up, and apps/web/package.json wins before vms.io/.git, which already carries .manna/.handoff/.zpc. Boards are per-repo: when git rev-parse --show-toplevel succeeds, that is the root; the marker walk is the fallback for non-git dirs only. (2) hooks/claude/agent-do-session-start.sh append_bootstrap_prompt runs on every SessionStart source (startup, resume, clear, compact). Gate the ask on source=startup (clear at most) and reuse the session baseline pattern at ~line 685 so one session asks once. (3) The modal osascript dialog runs inside a hook registered with timeout 10 in ~/.claude/settings.json; Claude Code kills the hook and the dialog vanishes unread. Detach the dialog plus the bootstrap run into their own process group so the hook returns at once, or fall back to context mode. Also: Not now writes nothing, so nothing remembers a decline; a per-root snooze would close that. Side note: tests/test_v11_routing.py leaves bootstrap-*.log files in ~/.agent-do/logs for temp dirs (five today); harmless, but the log dir should be redirected under the test tmp.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-fa0e85`.
4. Commit with `Manna: mn-fa0e85` and run `agent-do manna done mn-fa0e85` only after the work is verified.
