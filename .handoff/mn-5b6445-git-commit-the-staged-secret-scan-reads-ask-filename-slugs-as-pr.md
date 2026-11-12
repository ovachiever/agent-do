---
workflow: 2
manna: mn-5b6445
track: null
source: holy-ghostty /push prep, agent-do session c3f1ed43, 2026-11-12; blocked board commit
base_commit: 989a7fb7810e5348685e3b25916d2708177fecd2
scope: 'git commit: the staged-secret scan reads ''ask-'' filename slugs as provider keys (sk- matches mid-word)'
inputs:
- holy-ghostty /push prep, agent-do session c3f1ed43, 2026-11-12; blocked board commit
binding: sha256:98c82bf6690ba5a60ac93d7b8100e5c8ade286baca922d91f585735b47181e18
---

# Handoff: git commit: the staged-secret scan reads 'ask-' filename slugs as provider keys (sk- matches mid-word)

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-5b6445
```

## Scope

git commit: the staged-secret scan reads 'ask-' filename slugs as provider keys (sk- matches mid-word)

## Inputs

- holy-ghostty /push prep, agent-do session c3f1ed43, 2026-11-12; blocked board commit

## Work order

Observed 2026-11-12 on the holy-ghostty board commit. agent-do git commit refused 13 staged board files with five provider-key-shape findings, all false: the detector at tools/agent-git:267 is sk-[A-Za-z0-9_-]{16,} with no left boundary, so it matches inside any hyphenated slug where a word ending in 'sk' is followed by a hyphen and 16+ slug characters. The matched text was handoff paths such as .handoff/74-mn-480f8e-field-check-ask-chat-in-the-installed-holy-one-real-turn-return-s.md (ask-chat-in-the-installed...), ...ask-as-a-chatbot-live-turn..., ...ask-composer-hugs-its-draft..., ...ask-about-other-sessions..., in .handoff/README.md and in the prompt field of .manna/issues.jsonl rows. gitleaks 8.30.1 found nothing in the same files. Every board with a work order whose title contains 'ask', 'task', 'risk', 'disk' or 'desk' followed by more words hits this, and the only ways through are --no-scan or plain git, both of which bypass the scan entirely. The refusal then crashed in its own report (mn-fefa01), so the caller saw a SyntaxError and no file or line. Fix: require a left boundary so sk- is matched only when the preceding character is not a letter or digit, e.g. (?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}; consider the same boundary for the AKIA and gh[opusr]_ alternatives. Verification: (1) a staged file containing the line '.handoff/74-mn-480f8e-field-check-ask-chat-in-the-installed-holy-one-real-turn-return-s.md' commits with no finding; (2) a staged line containing a synthetic key of the real shape (sk- followed by 16+ key characters at a word start, and one after '=' and one after a quote) is still blocked; (3) the same two cases pass in tests alongside the existing git guardrail tests; (4) in holy-ghostty, the staged board commit goes through agent-do git commit without --no-scan. Related: mn-fefa01 (report crash), mn-481318 (--help taken as the message).

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-5b6445`.
4. Commit with `Manna: mn-5b6445` and run `agent-do manna done mn-5b6445` only after the work is verified.

## Builder verification (2026-11-12)

- Claim succeeded as `codex-01a1d089d67a7721`. Before editing, the canonical pointer, frontmatter binding, and normalized content SHA-256 all matched the dispatch pin `sha256:fa0ba426862df04c694c0b0fb4be4abbbff4a6df2da842d5661182c27650f9a7`. Normalization follows `tools/agent-manna/src/workflow.rs::binding_material`.
- Owned implementation: `tools/agent-git`, provider-key-shape detector only. Apply `(?<![A-Za-z0-9])` to all provider alternatives so a preceding letter or digit excludes a match while delimiters remain valid.
- Owned coverage: `tests/test_git_guardrails.py::test_provider_key_boundaries`. Commit 26 harmless lines (the exact reported path, ask/task/risk/disk/desk variants, and alphanumeric-prefixed provider shapes) without a finding. Independently block 49 synthetic keys: seven provider shapes across seven starting/delimiter positions. Verify redaction and unchanged HEAD/index for every blocked commit; preserve an unstaged sentinel on the accepted commit.
- Executed `python3 tests/test_git_guardrails.py` before the production change: exit 1, reproducing 26 false provider findings. Receipt: `.dev/mn-5b6445/guardrails-before.log`.
- Executed the same canonical command after the one-line fix: exit 0, `git guardrail tests passed`. This includes existing commit, worktree, snapshot/conflict, recovery and sweep guardrails. Receipt: `.dev/mn-5b6445/guardrails-after.log`.
- `bash -n tools/agent-git` and `git diff --check` passed. These are syntax/whitespace checks; the Python suite above executed real Git fixture operations. This CLI change has no Xcode target or compiled-only test receipt.
- The installed `agent-do` entry resolves to this checkout, so no installation is required. No installed app launch, screenshot, live session creation, push, or pull request occurred.
- Separate open work orders `mn-fefa01` (plain-text finding reporter) and `mn-481318` (commit help) are unchanged.
- Lessons logged: 2 (new), `les-7a7839` and `les-72904c`. Decisions logged: 0 (new).

## Remaining acceptance

The Holy checkout still has its owner's staged board changes. Required verification (4), a real board commit through `agent-do git commit` with scanning enabled, is pending that owner's receipt. Coordinated via agent-do drops `drp-a74739781e37` and Holy drop `drp-1dcb8c62a8b3`. The claim remains in progress until the actual command, exit status, and commit SHA are verified. Visual/app acceptance is not applicable to this CLI-only work order.
