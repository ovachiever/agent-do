# Image-first design implementation

Build item: `mn-7de24f`. Implementation is complete and integrated into local `main` through source commit `ad4da1d50507c78450d5b18abfc26678cab24043`. Repository validation passed. The item stays open for the new-surface rehearsal and Erik's two rulings. Nothing has been pushed or published.

## Delivered behavior

`agent-do design` exposes the six approved verbs, with five-beat contracts in `registry.yaml`:

1. `brief` freezes approved copy and facts in the node-tagged brief shape. It emits exact, half and open prompts, each containing the complete copy and factual labels. The old layout productions and taste settings do not enter the contract.
2. `imagine` refreshes official model authority, privately resolves the credential through `agent-do creds`, and generates every requested slot. Each original response, image, error, usage receipt, prompt and model record stays in the round. Only a genuine unavailable-model response permits the approved image fallback.
3. `measure` samples actual image pixels and records Tesseract word/line geometry. Sourced region annotations identify semantic color, column, section and diagram roles; unsupported roles and CSS typography values remain null. The chosen image itself also goes to the builder.
4. `reproduce` uses one isolated, strongest-model frontend builder per selected image. It restores owner copy and fact bindings, then repairs against independent live browser audits at every declared viewport. All attempts remain. Only complete passing pages reach the page ballot.
5. `ballot images|pages` prepares and checks shuffled, self-saving ballots, then hands off through `agent-do coord drop add` to an active Claude Code session. It returns `ballot pending`. Claude's `/ballot` must publish and read the actual Artifact. Imports preserve Erik's notes verbatim, receipt evidence, unsealed keys and ruling revisions.
6. `polish` measures live rendered text, SVG, clipping, protected phrase wraps, orphan tails, duplicate sentences, paired controls and overflow. Tolerances cite the trial's stated defect classes or derive from measured line-height and physical pixel resolution. It reports incomplete coverage rather than an invented pass.

There are no prices, cost gates, generation ceilings, repair-count limits or local token/timeout limits. The image request uses the provider's published maximum quality and portrait area. Text requests use the published maximum reasoning and output allowance. Missing usage is recorded as `usage not returned`.

## Verification

- Forty-nine focused design tests pass on the final implementation, in 119.424 seconds, exit 0. These exercise the real browse process, canvas sampling, OCR, copy verification, repair checks and ballot runtime. Paid-provider and Artifact transports are labeled test doubles and are not live-rehearsal evidence.
- `agent-do harness contracts validate`: 103 tools declared, zero errors, zero warnings.
- `agent-do harness contracts drift --tool design --json`: no declared-only or help-only verbs.
- `agent-do find image-first --json` discovers the tool and its entry points.
- `git diff --check`: clean.
- Python compilation and JavaScript syntax checks: clean.
- Full `./test.sh`: 126 passed, zero failed, exit 0. After its design portion ran, the final prompt-width and invalid-image recovery changes were covered by a complete rerun of all 49 design tests.

Validation uses the repository's existing Python environment:

```sh
PATH=/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH \
AGENT_DO_PYTHON=/Users/erik/Custom-Coding/agent-do/.venv/bin/python3 \
./test.sh
```

The fresh worktree also needed the existing Manna release binary built before the session-start bootstrap fixture. Its first run stopped at the missing-binary failure dialog. That failed prerequisite and the interrupted test log are preserved, not counted as a pass. `cargo build --quiet --release --manifest-path tools/agent-manna/Cargo.toml` completed before the new full run. The browse package's existing locked dependencies were installed in the worktree. No dependency or framework was added.

The unchanged `H3-polished.html` was audited at 1440 by 1000 and its saved full-page render was inspected. The audit is complete and clean, with zero orphans, phrase wraps, duplicate sentences, floating controls, clipped text or horizontal overflow. This is regression evidence only, not a new aesthetic ruling or a rehearsal. The HTML source SHA-256 is `ed90f031db4527e39a71458021aa15229e5516d9a036f0779fe4bcecda1ae04a`.

## Provider authority observed

Fresh official model catalog, model pages and image guide resolve to:

- Image: `gpt-image-2.5-sunburst`, quality `max`, maximum portrait output `2160x3840`.
- Text: `gpt-6-astra`, reasoning `max`, published output maximum 128,000 tokens.

These are observed current capabilities, not frozen model choices in the implementation. Every live invocation repeats the authority lookup. Ambiguous or changed documentation is reported instead of silently selecting a weaker model.

The complete authority documents, hashes and timestamps are saved under `.dev/design-authority-2026-09-18/`. Sources are the [official catalog](https://developers.openai.com/api/docs/models.md), [Sunburst model page](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst.md), [image-generation guide](https://developers.openai.com/api/docs/guides/image-generation.md), and [Astra model page](https://developers.openai.com/api/docs/models/gpt-6-astra.md).

No real image-generation or builder request has been made during implementation. There is no provider usage or dollar total to report for a rehearsal that has not run. Credentials are available through `agent-do creds`; secret values are absent from code and receipts.

## Evidence and delivery

The primary repository retains these implementation receipts under `.dev/`:

- [Full repository test log](../../.dev/design-root-tests-ready-2026-09-18.log).
- [Final 49-test design run](../../.dev/design-final-focused-tests-2026-09-18.log).
- [Validation receipt](../../.dev/design-validation-2026-09-18.json) and [source manifest](../../.dev/design-source-manifest-2026-09-18.json).
- [Home audit](../../.dev/home-regression-2026-09-18/audit.json), [render](../../.dev/home-regression-2026-09-18/render.png) and [source receipt](../../.dev/home-regression-2026-09-18/regression-receipt.json).
- [Live model authority summary](../../.dev/design-authority-2026-09-18/summary.json), with full archived source documents beside it.

Earlier interrupted repository runs remain beside the passing logs with their explanations. They are not presented as successful checks.

This report and its evidence are mirrored to `~/Library/Mobile Documents/com~apple~CloudDocs/Transfer/agent-do-design-build-2026-09-18/`. The report is also saved through `agent-do obsidian save` to `+/2026-09-18 agent-do design implementation.md` in Erkverse.

## Practical limits

- Reproductions are self-contained inspectable HTML/CSS/inline SVG with ordinary navigation. This release does not build a general scripted application. Rasterized text, editable fields, canvas and executable app code cannot substitute for auditable content.
- Raster glyph height is observable; exact CSS font size/family/weight usually is not. Semantic region names require sourced annotations. Null observations do not prevent the builder from seeing and reproducing the whole chosen image.
- Copy checks verify exact words/order and declared fact values. Quantitative SVG marks carry fact IDs and literal values. This is not proof that every plotted coordinate is semantically correct.
- Complex clips, masks, shadow roots and other unsupported text surfaces make polish incomplete. They do not enter a passing page ballot.
- Claude's actual Artifact read capability remains the publication and read authority. This CLI cannot independently fetch or authenticate an Artifact receipt supplied by that host.

## Rehearsal boundary

Erik must name a new surface and approve its copy and node-tagged facts. Home stays evidence and regression material. No new surface or content has been presumed approved.

```sh
agent-do design brief --copy APPROVED_COPY --facts APPROVED_FACTS --round ROUND --dry-run
agent-do design brief --copy APPROVED_COPY --facts APPROVED_FACTS --round ROUND
agent-do design imagine --round ROUND --dry-run
agent-do design imagine --round ROUND --per-level 2
agent-do design ballot images --round ROUND --claude-session CLAUDE_SESSION
```

Stop for Erik's real image ruling. Claude imports its exact submitted page and real receipt. Then:

```sh
agent-do design measure --round ROUND --selected
agent-do design reproduce --round ROUND --dry-run
agent-do design reproduce --round ROUND --selected
agent-do design ballot pages --round ROUND --claude-session CLAUDE_SESSION
```

Stop for Erik's real page ruling. Report the HTML, renders, audit numbers and actual returned usage from that round. Any unknown provider outcome requires explicit retry reconciliation; successful slots are never silently regenerated.

## Local commits

- `5328059`: live polish and browser regressions.
- `4217514`: frozen content contracts and resumable round state.
- `4924cce`: image provider authority, requests and receipts.
- `7d0d04f`: image measurement and OCR evidence.
- `ccddf30`: frontend reproduction and measured repair.
- `d6c1908`: Claude ballot handoff and verbatim readback.
- `7ac948e`: integrated the completed retirement cleanup from main.
- `47e0d37`: clarified ballot readings resume while retaining both receipts.
- `d94ef1b`: image prompts preserve the brief's CSS viewport separately from raster dimensions.
- `ad4da1d`: invalid image responses remain archived and their slots can resume on a later invocation.

All implementation commits carry `Manna: mn-7de24f`. The original proposal and source prompts remain unchanged; `APPROVED-AMENDMENTS-2026-09-18.md` records the current authority.

**TL;DR (12th grade):** The six design commands are built and integrated locally. All 49 design tests and the full 126-check repository suite passed; contracts have zero errors and warnings. The method carries your exact words and facts through generated pictures, your image choice, measured HTML construction and your page ruling. The new-surface rehearsal awaits your chosen surface and approved content.
