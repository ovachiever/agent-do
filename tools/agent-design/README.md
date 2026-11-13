# agent-do design

Image-first design rounds. The owner supplies copy and facts, chooses images, and rules on finished pages. This tool measures and verifies; it does not compute taste.

Implementation order: polish, brief, imagine, measure, reproduce, ballot. The approved amendments are recorded under `.handoff/image-first-design/`. Retired tools are not dependencies.

## Brief and round records

```bash
agent-do design brief --copy approved.md --facts facts.json --round .dev/design/new-surface --dry-run
agent-do design brief --copy approved.md --facts facts.json --round .dev/design/new-surface
```

Facts use the node-tagged brief shape: `nodes` have stable IDs, roles and literal allowed text or structured `data`; `groups` describe content order; `frame` carries approved house tokens; `viewports` declares every required render size. Narrative lives only in the copy file; an empty copy file is valid for label-only dashboards. Source metadata, superseded sentences and forbidden examples are never an allowlist. Numeric data leaves receive stable fact IDs under their node. Supply source paths on nodes and provenance with measured house tokens.

Each prompt contains the whole copy verbatim and all labels and facts once. Absolute source paths and the duplicate flattened verification index remain local. Both brief and imagine dry runs report actual compiled character counts and refuse prompts over the Images API maximum of 32,000 characters. Validation repeats before credential access and transport. Exact records a specific two-column composition and house tokens (an optional `exact_design` replaces those design choices). Half releases numeric geometry. Open releases the complete visual design while retaining all content. These are prompt directions, not layout-engine primitives or beauty rules.

Rounds freeze inputs and prompts by hash, retain every manifest revision, and use a process-held mutation lock. Stages advance from brief to images, image ballot, ruling, measurements, pages, page ballot and final ruling. Changed approved inputs require a new round. The copy checker reads rendered text boundaries, requires every paragraph once in order, rejects even short invented lines, and binds displayed figures to specific source facts.

## Imagine

```bash
agent-do design imagine --round .dev/design/new-surface --dry-run
agent-do design imagine --round .dev/design/new-surface --per-level 2
```

Each invocation refreshes OpenAI's official model catalog, selected model page and image guide through `agent-do context`. For images it selects the latest numbered Sunburst alias in the catalog, rather than relying on an older entry retaining the words "most capable". Text selection still requires one uniquely described most capable model. It uses maximum published quality and the largest supported raster matching the first viewport aspect ratio, and freezes the source documents. Unreadable or ambiguous capability changes are reported, never replaced by guessed defaults. New briefs default to `framing: "viewport"`; use `framing: "scroll"` for a complete portrait scrolling page. Frozen legacy contracts without a framing field keep their original portrait behavior. `--size` accepts any supported dimensions for viewport briefs. Only an explicit model-availability error permits `gpt-image-2`; auth, rate-limit and server errors stop with their receipts.

Credentials resolve privately through `agent-do creds`. Every requested generation runs, without a price prerequisite or local spend limit. Each request records prompt, level, requested/returned model, dimensions, null unsupported seed, provider request ID and actual usage (or `usage not returned`). PNG checksums and dimensions are verified. Partial rounds resume without regenerating successful slots; an uncertain transport outcome requires explicit `--retry-uncertain`. Failed requests remain in the record.

## Measure

```bash
agent-do design measure --round .dev/design/new-surface --selected
agent-do design measure --round .dev/design/new-surface --regions regions.json
```

Only images selected by a recorded owner ruling can enter this stage. Original PNGs are decoded in browse; every pixel in each sampled region is counted. Tesseract TSV supplies word and line bounding boxes, with original OCR confidence retained and no guessed confidence cutoff. Exact label matches associate observed glyph bounds with fact roles. CSS font size, font family and unsupported semantic assignments stay null.

Optional region annotations are keyed by chosen image ID. Each region requires `id`, `source`, `x`, `y`, `width`, `height` in original image pixels, and may declare a `role` (`ground`, `ink`, `accent`, `column`, `section`, `diagram`) and diagram `kind`. The tool verifies real bounds and measures area, modal colors, edges, gutters and proportions. Supplied semantic names remain attributed annotations. Unannotated pixels and OCR geometry remain available without pretending that a color mode proves a semantic role. Each image gets measurement JSON, pixel samples, raw OCR and an SVG evidence overlay.

## Reproduce

```bash
agent-do design reproduce --round .dev/design/new-surface --dry-run
agent-do design reproduce --round .dev/design/new-surface
```

One isolated vision-capable frontend builder receives each selected image, observations and frozen content contract. The current strongest text model is looked up, uses maximum supported reasoning and the full published output allowance, and writes ordinary HTML/CSS/inline SVG. There is no design grammar or aesthetic score. Builders see their prior page, actual renders and independently measured failures on repair. Repairs have no iteration limit. Network failures retain their evidence and stop safely; they never select a weaker model.

This reproduction surface is inspectable static HTML with navigation, rather than executable app code. Scripts, frames, canvas, raster text and editable form values cannot stand in for auditable page content. Every viewport must pass the exact copy/fact checker and complete live polish before a page becomes a ballot candidate. Each attempt, implementation decision, audit, render and provider usage receipt is retained. A page ballot is still the owner's judgment; passing mechanical checks is not approval.

## Local review only

```bash
agent-do design ballot images --round .dev/design/new-surface
agent-do design ballot pages --round .dev/design/new-surface
# Both start local HTTP review and open the default browser automatically.
agent-do design ballot images --round .dev/design/new-surface --no-open
# Same persistent local review, URL only.
agent-do design ballot images --round .dev/design/new-surface --prepare-only
# Prepare/audit only. No server or browser launch.
```

**External Artifact hosting is forbidden.** There is no Claude publishing, peer handoff, cloud-host fallback or Artifact receipt import. Removed `--publish` and `--claude-session` flags fail rather than silently changing behavior. Historical receipts remain evidence on disk; they do not authorize new cloud activity.

The command prepares, blinds and audits the comparison, starts a persistent server bound only to `127.0.0.1`, and opens the default browser. Repeat the command to reopen the same server. The page links every existing part and has a Stop preview button. Only public comparison pages are served, never the round directory, provider receipts or blind key. The server outlives the CLI command. Browser launch failure reports the working URL instead of claiming it opened.

Notes survive reload. Save review records their exact text; candidate checkboxes plus explicit confirmation record selection, including rejecting all candidates. Notes alone never approve anything. Every part needs an explicit selection before advancing. Saved source, raw owner input and round-bound local receipts remain under `local-reviews/`. Unknown keys, foreign origins, changed candidate bytes and external-host receipts refuse. Later rounds cannot silently replace an accepted ruling. Local receipts can also be reimported idempotently with `--submitted HTML --receipt JSON`.

Image comparisons contain raster concepts with interactive review controls, not working applications reconstructed from those images. Page comparisons embed the generated HTML in sandboxed frames. Candidates retain neutral shuffled labels and original judging dimensions. Public copies remove metadata without changing pixels; optional existing cwebp encoding is lossless. No codec is installed automatically. Local hosting has no external publishing-size cap; existing multipart rounds remain supported. Page copies are independently audited after metadata removal, with source hashes, viewport dimensions and exact frame bytes checked.

The prepared HTML is a static export; its save button directs readers to the local review command. The served version supplies the local review runtime. Original candidate and ballot bytes remain immutable. Each ruling archives its exact submission, review receipt, raw owner controls and unsealed key; `labels.yaml` projects that append-only history.

## Five-beat contracts

| Verb | Connect | Snapshot | Interact | Verify | Save |
| --- | --- | --- | --- | --- | --- |
| brief | Approved copy and node-tagged facts | Original bytes and hashes | Compile three prompts | Complete copy, IDs, order and viewports | Inputs, prompts, manifest |
| imagine | Refreshed official model authority and private creds | Request and capability evidence | Each requested image generation | PNG content, dimensions and request outcome | Images, errors, raw usage and provider receipts |
| measure | Owner-selected images | Original pixels and sourced regions | Canvas samples and TSV OCR | Real bounds, confidence and unavailable fields | JSON measurements, OCR, SVG overlay |
| reproduce | Image ruling, measurements and strongest text model | Isolated image/content packet | Frontend construction and uncapped repair | Independent copy, facts and live polish at every viewport | All attempts, final HTML, renders and usage |
| ballot | Passing candidates and local review or saved local input | Shuffled key and immutable public payload | Serve/open local review or import saved input | Candidate identity, audits, local receipt, origin and explicit choices | Persistent preview or append-only ruling and unsealed key |
| polish | Dedicated browse session | Actual viewport, fonts and rendered text | Read-only geometry measurement | Sourced/relative thresholds and coverage | Complete clean/findings/incomplete audit |

## Polish

```bash
agent-do design polish page.html --viewport 1440x1000 --out audit.json --render page.png --json
agent-do design polish https://example.com/today --viewport 1440x1000 --ready-text 'Today is ready' --settle-timeout-ms 45000 --out today-audit.json --json
agent-do design polish https://example.com/today --viewport 1440x1000 --ready-js 'window.todayReady === true' --out today-audit.json --json
```

Uses `agent-do browse`, explicitly sets the viewport after navigation, checks the actual viewport, waits for network idle, and awaits fonts before measuring. For client-rendered pages, supply either `--ready-text` (a literal substring of rendered body text) or `--ready-js` (a read-only JavaScript expression returning the boolean `true`). Network idle alone cannot prove that delayed application work is finished. When a ready condition is supplied, polish waits for it, waits for network idle again, and rechecks the condition before measuring. All waits share `--settle-timeout-ms`, an operational budget of 60000 milliseconds by default, starting after navigation and viewport setup.

Every audit records `settle`: the requested condition, total timeout, actual elapsed milliseconds, and each native browser wait and readiness recheck's outcome and duration. Each wait receives the remaining budget; CLI transport overhead is included in elapsed time and can delay failure reporting past that budget. A timeout or predicate error prevents measurement and rendering, exits 2, and saves an unsuccessful receipt to `--out` with `clean: false`, `complete: false`, and `measurement: not_run`. A loading skeleton is never measured after a failed readiness check. The same options can be supplied in `--config` as `{"settle":{"ready_text":"Today is ready","timeout_ms":45000}}` or with `ready_js`; explicit CLI options override their config counterparts. Dry runs validate and report these options without opening a browser.

Handles inline text, SVG text, orphan tails, protected phrase wraps, duplicate sentences, control alignment, hidden clipping, and horizontal overflow. It reports incomplete coverage for frames, shadow roots, and failed fonts.

Threshold provenance:

- Orphans and duplicate sentences: Erik's Home polish ruling, 2026-09-18, in `corpus/design/rounds/home1/round2` and the Palingenesis canon. A one-word last line is a finding; there is no minimum sentence length.
- Phrases: semantic label/action roles or explicit brief phrases, never a character-count heuristic.
- Control alignment: difference between the paired centers must fit within the maximum computed line-height of the two neighbors. The tolerance changes with the rendered type scale. A sourced brief relationship can specify top or bottom alignment instead.
- Clipping and overflow: browser geometry, with one physical pixel of resolution converted to CSS pixels through `devicePixelRatio`.

Optional `--config` JSON has `phrases` (strings or `{text, source}`) and `alignments` (`{selector, mode: center|top|bottom, source}`). Measurements and their sources appear in every finding. Exit 0 means complete and clean, 1 means findings or incomplete coverage, and 2 means the audit could not run. Existing receipts are never overwritten.

## Validation

```bash
python3 tools/agent-design/test/test_settle.py          # No browser or app launch
python3 tools/agent-design/test/test_settle_browser.py  # Requires coordinated browser acceptance
python3 tools/agent-design/test/test_polish.py
agent-do harness contracts validate
./test.sh
```

The browser tests use the real browse command against local synthetic pages. Provider responses and synthetic owner inputs are clearly marked test fixtures; their receipts are never owner approval evidence. Tests do not spend tokens or publish ballots. A rehearsal requires a new surface and owner-approved copy/facts. Home remains evidence and regression material. No-spend dry runs emit prerequisites and planned work; they never invent images, votes or successful audits.
