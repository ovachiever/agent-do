---
workflow: 2
manna: mn-652a9e
track: mn-455a88
source: session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)
base_commit: a1ff599ef4e01962454df2e2391323d2127a752c
scope: 'upstream: security-guidance plugin lists the whole shared temp dir before every baseline — report to anthropics/claude-plugins-official'
inputs:
- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)
binding: sha256:b0b4e5b5e50335530cc634d2df4132c67e86afa474ce8e7cc919438c1b38584d
---

# Handoff: upstream: security-guidance plugin lists the whole shared temp dir before every baseline — report to anthropics/claude-plugins-official

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-652a9e
```

## Scope

upstream: security-guidance plugin lists the whole shared temp dir before every baseline — report to anthropics/claude-plugins-official

## Inputs

- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19; follow-up to mn-f8add7 (agent-sessions self-recursion, fixed in 0e2271f)

## Work order

Upstream defect in Anthropic's security-guidance plugin (claude-plugins-official, installed 2.0.14 at ~/.claude/plugins/cache/claude-plugins-official/security-guidance/2.0.14, same code in 2.0.13). Before every git baseline capture, hooks/gitutil.py _hook_tmpdir (line 356) calls _sweep_stale_indexes(tempfile.gettempdir(), uid) (line 358), which runs os.listdir on the entire shared per-user temp dir (line 200). The 2 s sweep budget (line 163) is checked only after an unlink (line 214), so the listing itself is unbounded. hooks.json registers the UserPromptSubmit hook with no timeout, so Claude Code's default 30 s applies. Repos with no commits exit before the sweep and look healthy.

Incident 2026-10-18: a runaway agent-do tool (mn-f8add7) left 7,434,267 files in /var/folders/.../T; the listing alone crossed 30 s and every UserPromptSubmit in every repo with commits timed out until the files were deleted (listing of 632 entries afterwards: 0 ms; hook 0.3 s). Any other heavy temp-dir user reproduces it.

Suggested report: sweep only the plugin's own per-uid directory (claude-security-guidance-<uid>, line 378 already does) and never the shared base, or stream the base with os.scandir under the budget. Homepage: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance.

Gate: filing an issue or PR is an outward action. The claim-holder gets Erik's explicit go for the specific post before sending anything; a PR to that repo is never opened without his word. Verification: the issue URL recorded here, or Erik's decision not to file recorded and the item abandoned with that reason.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-652a9e`.
4. Commit with `Manna: mn-652a9e` and run `agent-do manna done mn-652a9e` only after the work is verified.
