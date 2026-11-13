---
workflow: 2
manna: mn-fd9577
track: null
source: null
base_commit: 019eda07c9d6578804e6e65d5812cf3ae0cc5686
scope: 'Design: repair dashboard briefs, provider preflight and publishable image ballots'
inputs: []
binding: sha256:4aa1c0d44794940a42d7f9a2d4f1aee2c86e0ced0022c669ea657f34af350458
---

# Handoff: Design: repair dashboard briefs, provider preflight and publishable image ballots

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-fd9577
```

## Scope

Design: repair dashboard briefs, provider preflight and publishable image ballots

## Inputs

- None declared.

## Work order

Repair Chris dashboard failure end to end. Preserve complete approved facts without repeated filesystem provenance; allow label-only briefs; honor viewport/framing; validate compiled provider prompt limits before freeze and send; make image ballots publishable with preserved original evidence. Execute offline regressions and real image-generation validation, diagnose irrelevant provider images through exact requests and receipts. Release coherent tested changes. No fabricated owner votes or acceptance. User authorized implementation, testing and release; no budget-saving substitutions.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-fd9577`.
4. Commit with `Manna: mn-fd9577` and run `agent-do manna done mn-fd9577` only after the work is verified.

## Verification return


Implemented label-only briefs, compact provider prompts with local-only provenance, compiled 32,000-character validation before freeze/dry-run/credential access/send, viewport-aware maximum-quality generation, preserved legacy scroll framing, and request-body hashes for diagnosis.

Ballots use an existing cwebp codec losslessly when available, retain original PNGs, and split into bounded publication parts. Candidate labels remain global; each part is independently fingerprinted. Partial and duplicate imports cannot approve unread parts; cross-part selections refuse. `--prepare-only` audits payloads without notifying another session. A single image that cannot fit losslessly still refuses explicitly. The 15 MiB envelope is a conservative target based on Chris's reported 16–20 MiB host limit, not a claim of independent host certification.

## Executed verification

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools/agent-design/test -p 'test_*.py'`: 96 passed, no failures (`tests-release.log`). Includes real browser polish, readiness, measurement, reproduction fixture and self-saving ballot runtime checks.
- Dashboard regressions: 6 passed; provider tests: 9 passed after request-body diagnostics were added. Multipart boundary regression rerun passed after exact part-key sizing correction.
- Contracts validate with repository venv: 103 tools, zero errors and warnings. Contracts drift: zero failing verbs, 419 existing advisory entries. Generated docs check passed.
- Real installed `agent-do design brief` and `imagine`: six maximum-quality gpt-image-2.5-sunburst images, 3456x2400, from a synthetic twenty-repository dashboard. All six visually inspected and relevant; input tokens: 1015, 1015, 1001, 1001, 976, 976. No eight-token anomaly reproduced. Complete request/response receipts and images remain in `live-round/`.
- Actual `agent-do design ballot images --round .dev/mn-fd9577/live-round --prepare-only`: two real browser-audited payloads, 12,951,435 and 9,736,735 bytes. No notifications sent, no owner votes fabricated, no Artifact publication claimed.
- Native lossless encode/decode comparison on a generated image: RGBA bytes identical; 5,403,798-byte PNG became 3,460,496-byte WebP (`lossless-receipt.json`).

Earlier development runs exposed a shadowed variable and an audit-filename compatibility error; both corrected before the passing release run. System Python lacked PyYAML for contract tooling; repository venv passed. Full root test.sh was not run; focused design suite and contracts were executed.

## Limits and release

Chris's original machine, requests, outputs and exact installed revision were unavailable. This validates the repaired current product path, not a retroactive diagnosis of his dog images or billing. Actual Claude Artifact publication/readback remains a host capability, not simulated by local preparation. Chris should start a new round from the full approved facts; frozen older rounds retain their original prompts.

The installed executable is /Users/erik/Custom-Coding/agent-do/agent-do; ~/.local/bin/agent-do links to it. No install is required on this host. Remote publication is separate from local activation. Main currently includes five earlier unpublished commits outside this item's scope.

## Follow-up: latest image model, November 12

User requested updating to the latest image generation family after the current round. I kept that round on 2.5 for consistency, then verified 2.6 separately. The official catalog retains "most capable" wording on 2.5 while listing 2.6 with a different description. Selection now uses the newest numbered Sunburst alias; snapshots and Flare speed tiers are excluded. The guide must explicitly document maximum quality for the selected generation. Text selection is unchanged.

Commit: 77b5546. Provider regressions: 11 passed; two new regressions fail on the prior source (old model selected and new quality unsupported). Complete design suite: 98 passed in 192.241 seconds. Contracts validate: 103 tools, zero errors or warnings. Generated tools-doc check, staged diff check and staged gitleaks passed. Full root test.sh not run.

Real provider-path validation: gpt-image-2.6-sunburst, max, 3360x1968 PNG; 1,099 input tokens, 11,576 image output tokens. Image decoded and visually inspected: relevant Holy workspace. Request, response, refreshed official authority and PNG retained in .dev/holy-ghost-design/model-2.6-live-check/. No automatic retry or fallback occurred for this request.

Original Holy design round: six 2.5 images complete, after one HTTP 520 and an explicit resume. Ballot prepared and browser-audited as two parts (13,319,086 and 6,734,376 bytes); no hosted publication or owner approval claimed. Local installed agent-do uses the changed repository. No push or PR; remote release scope remains unanswered.

## Local-only interactive review, November 12

Erik explicitly requires automatic local HTTP serving and browser opening, and bans external Artifacts entirely. This supersedes the prior Claude handoff/Artifact workflow. Commit ed12d46 implements persistent loopback review, explicit browser controls, verbatim local notes, reload persistence, confirmed candidate selections, rejection of all candidates, multipart completion gates, idempotent local imports and targeted Stop preview. Private round files are not served. External publishing flags and host receipts refuse; cloud callbacks and peer handoff code are removed. Local review has no external publishing-size cap. Existing historical records remain intact.

Executed: full design suite 103 passed in 216.170 seconds; local receipt/ban suite 8 passed; real browser local controls suite 4 passed. Real CLI fixture verified detached lifetime, same-server reuse, HTTP content and targeted shutdown. Contracts validate passed (103 tools, zero errors/warnings), drift zero failing verbs, generated docs check passed, staged diff check and gitleaks passed. Full root test.sh not run. No model requests made for this change.

Live: original Holy comparison reopened by the installed design ballot command, with default browser launch reported successful. HTTP retrieval verified the local runtime and absence of Claude API callbacks. No actual owner selections were submitted. Original six-image concepts remain unchanged. Static delivery copies were updated to remove cloud callbacks; retired source/exports are archived under repository .dev, not Transfer.

Design feedback: Erik rejected the concepts as worse than current Holy. The generation request contained text only, not the screenshot image; generic prompts also prohibited icons/gradients and imposed fixed content order. These constraints are findings, not accepted aesthetic rules for a new round. Erik clarified that only the left sidebar and overall window appearance are in design scope; Ghostty terminal rendering, content and input remain unchanged. No replacement generation round has started.

Registry/TOOLS ownership note: another lane held advisory claims. Only the design stanza and its generated documentation were edited; no other entries changed. Coordination publication records the narrow overlap. No pushes or PRs. The original item's remote-release scope is still pending.
