# Portfolio round three — synthesis of the five winners. Common brief.

You are building ONE candidate for the **Portfolio** room of Palingenesis. Single self-contained
HTML file (inline CSS; Google Fonts link allowed; no external JS), viewport 1440 wide, vertical
scroll only. Output path given in your task.

## Read first, in this order
1. Facts (the ONLY source of visible text): /Users/erik/Custom-Coding/palingenesis/.dev/aphrodite/portfolio-brief.json
2. The five winners of round one and Erik's note on each — study what each does well, take the
   best of all five:
   - P3 wall of small multiples — "advance, very clean, clear"
     /private/tmp/claude-501/-Users-erik-Custom-Coding-agent-do/fae1af41-26ba-4c61-9805-d261387c8a4a/scratchpad/port1/P3.html (+P3.png)
   - P7 the life beyond (attempts/sites) — "advance, will need some cleanup"
     …/port1/P7.html (+P7.png)
   - P8 capital by vintage — "advance, will need some alignment work all over the place"
     …/port1/P8.html (+P8.png)
   - P9 the machine's scorecard (calibration) — "advance, it's quite clean"
     …/port1/P9.html (+P9.png)
   - P10 clusters of exposure — "advance"
     …/port1/P10.html (+P10.png)
   The six killed candidates all died for one reason, in Erik's words: "too cluttered, everything
   is the same size", "stuffed", "cramped", "didn't use spacing well", "alignment". Do not repeat it.
3. Identity reference (palette tokens, hairlines, type, how figures drill):
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/approved/simulation-workstation-v2-residual.html
   /Users/erik/Custom-Coding/palingenesis/.dev/design-canon/approved/engine-room-e3-v2-controls.html
   Dark ground, one skeleton (nav strip: brand + Today · Pipeline · Library · Portfolio ·
   Simulation · Engine Room, Portfolio active), hairline rules, sage = good/observed/on thesis,
   clay = below/miss/due. **The motto line is dead: no "Every claim sourced…" anywhere, no
   tagline, no footer sentence.**

## Erik's instruction for this round, verbatim
"take all five winners and create three new designs taking the best of all, but much cleaner,
really paying attention to spacing, not too many words … pay HUGE attention to alignment,
spacing, etc."

## Laws (a violation kills the candidate)
- **Space and alignment.** Declare a column grid (e.g. 12 columns on a 1344px content width, 24px
  gutters) and an 8px baseline; every block edge, column start, chart axis and table column sits
  on the grid. One primary instrument at a distinctly larger scale than everything else. Minimum
  32px of air between blocks; no block may touch another. At most four type sizes on the page.
  Numbers in columns use tabular figures and right-align. Equal things get equal widths.
- **Word ration.** Labels ≤ 2 words. The only sentences allowed: the brief's `thesis` line; at most
  ONE of the three `machine_lines` (or none). No captions, no help text, no explanations.
- **Copy contract.** Every visible text is a string from the brief (or a fragment / a derived count
  / a tick label). Nothing invented.
- **Never delete information, but do not cram.** The face shows: the primary instrument, the nine
  positions (name · stage · standing · thesis-vs-reality mark, other columns as you judge), and the
  selected position's essentials (thesis line, thesis-vs-reality chart + 4 rows, standing with its
  controls). Everything else from the brief for the selected position (Arc 8, Reality, Estate 4,
  Go-to-market 5, Money, Attempts 4, World 4, Clusters 4, Vintages…) is present as COLLAPSED
  disclosure rows — one line each: label + count (+ one key figure), styled as openable — unless
  your thesis makes one of them the primary instrument. Closed positions stay, greyed.
- **Helm law.** Controls sit beside the instrument they act on; each verb group carries a collapsed
  "Reason · Effective date · Actor" line. Keep control groups small on the face (standing verbs
  beside standing; the other verb groups live inside their collapsed rows).
- **Drill.** Figures and names carry the approved files' drill affordance (dotted underline).
- **Money.** Allowed with unit/period/basis, never outranking thesis-vs-reality.
- No invented nav rooms, no emoji, no gradients, no card-grid of tiles, no chart libraries
  (hand-drawn SVG in the approved files' manner).

## Verify (mandatory, and report the numbers)
1. Render: `agent-do browse --session <s> open "file://<file>" --viewport 1440x1000`, `wait --stable`,
   `screenshot --full <png>`; READ the PNG. No overlaps, no clipping, no horizontal overflow.
2. Alignment audit via `agent-do browse --session <s> eval`: collect the left x of every section
   header, table, chart svg and control group; report the set of distinct x values — it must be a
   small set that matches your declared grid columns. Report distinct font sizes in use (≤ 4).
3. Air audit: minimum vertical gap between adjacent blocks ≥ 32px; report the smallest gap found.
Iterate until all three pass. Report in under 150 words: file path, what you took from each of
the five, the grid you declared, the three audit numbers, anything not achieved.
