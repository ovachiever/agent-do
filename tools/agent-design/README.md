# agent-do design

Image-first design rounds. The owner supplies copy and facts, chooses images, and rules on finished pages. This tool measures and verifies; it does not compute taste.

Implementation order: polish, brief, imagine, measure, reproduce, ballot. The approved amendments are recorded under `.handoff/image-first-design/`. Retired tools are not dependencies.

## Brief and round records

```bash
agent-do design brief --copy approved.md --facts facts.json --round .dev/design/new-surface --dry-run
agent-do design brief --copy approved.md --facts facts.json --round .dev/design/new-surface
```

Facts use the node-tagged brief shape: `nodes` have stable IDs, roles and literal allowed text or structured `data`; `groups` describe content order; `frame` carries approved house tokens; `viewports` declares every required render size. Narrative lives only in the copy file. Source metadata, superseded sentences and forbidden examples are never an allowlist. Numeric data leaves receive stable fact IDs under their node. Supply source paths on nodes and provenance with measured house tokens.

Each prompt contains the whole copy verbatim and all labels and facts. Exact records a specific two-column composition and house tokens (an optional `exact_design` replaces those design choices). Half releases numeric geometry. Open releases the complete visual design while retaining all content. These are prompt directions, not layout-engine primitives or beauty rules.

Rounds freeze inputs and prompts by hash, retain every manifest revision, and use a process-held mutation lock. Stages advance from brief to images, image ballot, ruling, measurements, pages, page ballot and final ruling. Changed approved inputs require a new round. The copy checker reads rendered text boundaries, requires every paragraph once in order, rejects even short invented lines, and binds displayed figures to specific source facts.

## Imagine

```bash
agent-do design imagine --round .dev/design/new-surface --dry-run
agent-do design imagine --round .dev/design/new-surface --per-level 2
```

Each invocation refreshes OpenAI's official model catalog, selected model page and image guide through `agent-do context`. It selects the uniquely described most capable model, uses maximum published quality and portrait area, and freezes the source documents. Unreadable or ambiguous capability changes are reported, never replaced by guessed defaults. Only an explicit model-availability error permits `gpt-image-2`; auth, rate-limit and server errors stop with their receipts.

Credentials resolve privately through `agent-do creds`. Every requested generation runs, without a price prerequisite or local spend limit. Each request records prompt, level, requested/returned model, dimensions, null unsupported seed, provider request ID and actual usage (or `usage not returned`). PNG checksums and dimensions are verified. Partial rounds resume without regenerating successful slots; an uncertain transport outcome requires explicit `--retry-uncertain`. Failed requests remain in the record.

## Measure

```bash
agent-do design measure --round .dev/design/new-surface --selected
agent-do design measure --round .dev/design/new-surface --regions regions.json
```

Only images selected by a recorded owner ruling can enter this stage. Original PNGs are decoded in browse; every pixel in each sampled region is counted. Tesseract TSV supplies word and line bounding boxes, with original OCR confidence retained and no guessed confidence cutoff. Exact label matches associate observed glyph bounds with fact roles. CSS font size, font family and unsupported semantic assignments stay null.

Optional region annotations are keyed by chosen image ID. Each region requires `id`, `source`, `x`, `y`, `width`, `height` in original image pixels, and may declare a `role` (`ground`, `ink`, `accent`, `column`, `section`, `diagram`) and diagram `kind`. The tool verifies real bounds and measures area, modal colors, edges, gutters and proportions. Supplied semantic names remain attributed annotations. Unannotated pixels and OCR geometry remain available without pretending that a color mode proves a semantic role. Each image gets measurement JSON, pixel samples, raw OCR and an SVG evidence overlay.

## Polish

```bash
agent-do design polish page.html --viewport 1440x1000 --out audit.json --render page.png --json
```

Uses `agent-do browse`, explicitly sets the viewport after navigation, checks the actual viewport, and awaits fonts before measuring. Handles inline text, SVG text, orphan tails, protected phrase wraps, duplicate sentences, control alignment, hidden clipping, and horizontal overflow. It reports incomplete coverage for frames, shadow roots, and failed fonts.

Threshold provenance:

- Orphans and duplicate sentences: Erik's Home polish ruling, 2026-09-18, in `corpus/design/rounds/home1/round2` and the Palingenesis canon. A one-word last line is a finding; there is no minimum sentence length.
- Phrases: semantic label/action roles or explicit brief phrases, never a character-count heuristic.
- Control alignment: difference between the paired centers must fit within the maximum computed line-height of the two neighbors. The tolerance changes with the rendered type scale. A sourced brief relationship can specify top or bottom alignment instead.
- Clipping and overflow: browser geometry, with one physical pixel of resolution converted to CSS pixels through `devicePixelRatio`.

Optional `--config` JSON has `phrases` (strings or `{text, source}`) and `alignments` (`{selector, mode: center|top|bottom, source}`). Measurements and their sources appear in every finding. Exit 0 means complete and clean, 1 means findings or incomplete coverage, and 2 means the audit could not run. Existing receipts are never overwritten.

## Validation

```bash
python3 tools/agent-design/test/test_polish.py
agent-do harness contracts validate
./test.sh
```

The browser tests use the real browse command against local synthetic pages. They do not spend tokens or publish ballots.
