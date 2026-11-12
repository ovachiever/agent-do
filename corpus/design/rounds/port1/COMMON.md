# Portfolio round one — common brief for every builder

You are building ONE candidate design for the **Portfolio** room of Palingenesis, an autonomous
agricultural-innovation platform (domain-general engine; agriculture is the first book). Output: a
single self-contained HTML file (inline CSS; Google Fonts links allowed; no external JS) at the path
you were given. Viewport 1440px wide; the page may scroll vertically; never horizontally.

## Read first, in this order
1. The facts: /Users/erik/Custom-Coding/palingenesis/.dev/aphrodite/portfolio-brief.json — EVERY text
   on your page must come from this file (its strings, or numbers/tick labels derived from them).
2. The dream (what the room IS; shapes what the data means, never quoted on the page):
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/portfolio-dream-2026-09-15.md
3. The ratified house identity — study these three files' HTML (palette tokens, hairline frames,
   type, spacing, how figures drill, how controls sit beside instruments):
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/approved/simulation-workstation-v2-residual.html
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/approved/engine-room-e3-v2-controls.html
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/approved/library-ask-hero.html
   Portfolio is a DARK-ground room (Today is the only light surface). One skeleton across rooms:
   the same nav strip (brand + the six rooms, Portfolio active), hairline rules, restrained type,
   a single sage accent family (sage = on thesis / good / observed; clay = below / miss / due),
   the motto line at the foot.

## Laws (a violation kills the candidate)
- **Copy contract.** No sentence, caption, tagline, help text, empty-state prose, or explanation
  that is not in the brief. The only sentences on the page are the brief's `thesis` line and the
  three `machine_lines`, verbatim, if you use them. Labels ≤ 2 words unless the brief's label is
  longer. The product never explains or justifies itself.
- **Never delete information.** All nine positions with all seven columns' worth of facts; the
  book-level instruments; the selected position's arc, reality, thesis-vs-reality, estate,
  go-to-market, money, attempts, and controls must all be present (you decide hierarchy, density,
  collapse/expansion affordances — but nothing is omitted).
- **Two-layer drill.** Every figure and name is a doorway: style figures/names as drillable (a
  consistent affordance from the approved files); no dead-end numbers. LLM-authored verdicts do
  not exist in this brief and must not be invented.
- **Helm law.** Controls (the `controls` lists) sit beside the instruments they act on, never in a
  separate settings area. Each act carries Reason · Effective date · Actor fields (may be
  collapsed).
- **Money law (Portfolio amendment).** Money may appear on faces with unit, period, and basis
  (the brief gives `basis`/`ev_basis`); it never outranks the thesis-vs-reality score in hierarchy.
- **Identity.** No invented nav rooms; no emoji; no gradients; no card-grid dashboard of tiles.
- **Charts** are hand-drawn SVG in the approved files' manner (envelopes, hairlines, tick labels
  from the brief's numbers). No chart libraries.

## Your thesis
You were given ONE structural thesis. Commit to it fully — this round is judged on structure
(what is primary, what is the spine, how the three natures of the room — the arc, the life beyond,
the helm — are arranged), not on paint. Twelve other builders have twelve other theses.

## Verify before you finish (mandatory)
Render with `agent-do browse --session <your session name> open "file://<your file>" --viewport 1440x1000`,
`agent-do browse --session <s> wait --stable`, `agent-do browse --session <s> screenshot --full <your png path>`,
then LOOK at the PNG with the Read tool. Fix overlaps, clipping, horizontal overflow, unreadable
contrast, missing sections. Iterate until clean. Then report in under 120 words: the file path, the
structural thesis in one line, and anything not achieved. Do not paraphrase these instructions.
