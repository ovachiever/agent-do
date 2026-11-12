---
workflow: 2
manna: mn-fefa01
track: null
source: null
base_commit: 9fd7edc7e10cafd5778f1210177944bfbe744f54
scope: 'git commit: the staged-secret-scan report crashes (f-string with backslashes) and hides the match'
inputs: []
binding: sha256:62f0a7e9c999489eb5f7762b2aa21b5d50f3af0c3337141ee49ff0f1af0807aa
---

# Handoff: git commit: the staged-secret-scan report crashes (f-string with backslashes) and hides the match

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-fefa01
```

## Scope

git commit: the staged-secret-scan report crashes (f-string with backslashes) and hides the match

## Inputs

- None declared.

## Work order

Running 'agent-do git commit' (even 'git commit --help') in holy-ghostty on 2026-10-20 printed 'Commit blocked: staged secret scan found 1 potential secret(s); matched values are redacted.' followed by a SyntaxError from an inline python -c reporter: print(f"  {item[\"file\"]}:{item[\"line\"]} [{item[\"detector\"]}] value redacted") — f-string expression part cannot include a backslash. The file/line/detector of the match is never shown, so the agent cannot judge the finding. The staged diff held only sha256 handoff digests, claim_token_hash values, and commit ids (manual scan), so the commit was made with plain git -F. Fix: build the line without escaped quotes inside the f-string (use single quotes or str.format), and add a test that a flagged diff prints file:line [detector].

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-fefa01`.
4. Commit with `Manna: mn-fefa01` and run `agent-do manna done mn-fefa01` only after the work is verified.
