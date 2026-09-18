# agent-do design

Image-first design rounds. The owner supplies copy and facts, chooses images, and rules on finished pages. This tool measures and verifies; it does not compute taste.

Implementation order: polish, brief, imagine, measure, reproduce, ballot. The approved amendments are recorded under `.handoff/image-first-design/`. Retired tools are not dependencies.

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
