# Home page — trial round two (approved copy). Common brief for both arms.

You are building ONE candidate for the **Home** page of Palingenesis — the first thing a user sees:
the tour of the platform, the promise, the how, the seven rooms. Single self-contained HTML file
(inline CSS; Google Fonts links allowed; no external JS), viewport 1440 wide, vertical scroll only.
Output path in your task.

## Read first, in this order
1. THE COPY — the ONLY source of visible sentences, verbatim, in this order, every paragraph used once:
   /Users/erik/Custom-Coding/palingenesis/docs/design-canon/briefs/home-copy-2026-09-18.md
   Plus the facts file for figures, room names, step names and labels (its `sentences` are SUPERSEDED
   by the copy file and must not appear): /Users/erik/Custom-Coding/palingenesis/docs/design-canon/briefs/home-brief.json
2. The four registers this page must combine into one cohesive whole — study each file's HTML:
   - warm paper, the morning edition: /Users/erik/Custom-Coding/palingenesis/docs/design-canon/approved/today-paper-broadsheet.html
   - the auction-lot serif: /Users/erik/Custom-Coding/palingenesis/docs/design-canon/approved/dossier-auction-lot.html
   - dark institution with controls: /Users/erik/Custom-Coding/palingenesis/docs/design-canon/approved/engine-room-e3-v2-controls.html
   - monospace workstation: /Users/erik/Custom-Coding/palingenesis/docs/design-canon/approved/pipeline-evolutionary-register-q3.html
   The page may cross from paper to dark once, as the product does between Today and the working
   rooms. One skeleton across the boundary: same nav strip, hairlines, single sage accent family.
3. The laws: /Users/erik/Custom-Coding/palingenesis/docs/design-canon/rulings-2026-08.md — no motto
   (the "Every claim sourced…" line is banned), word ration on labels (≤ 2 words), the space-and-
   alignment law (one primary instrument at a larger scale, declared grid + 8px baseline, ≤ 4 type
   sizes, ≥ 32px between blocks), never a card-grid of tiles, no emoji, no gradients, no stock imagery.

## Copy contract (a violation kills the candidate)
Every sentence on the page is a paragraph of home-copy-2026-09-18.md, verbatim and complete, in the
file's order; all eleven paragraphs appear; nothing is rewritten, trimmed, or added. Round one was
killed for copy ("sounds like a shitty manifesto") — the words are now Erik's and are not yours to touch. Step names, rooms, lines and details from `steps`; figures from
`figures`; labels from `labels`. Nothing invented — no headline of your own, no adjectives, no calls
to action beyond "Sign in" and "Open Today".

## What the page must do
Tell the promise, show the how (the six steps as one continuous instrument — a river, a rail, a
descent, whichever your thesis makes primary), name the seven rooms as doorways (each step opens
its room; Today is the edition), show the record figures, and end on the owner. Small excerpts of
the rooms themselves may appear (drawn in their own register at reduced scale) if your thesis calls
for it — as instruments, never as screenshots in device frames.

## Verify (mandatory, report the numbers)
Render at 1440 (`agent-do browse --session <yours> open … --viewport 1440x1000`, `wait --stable`,
`screenshot --full`), READ the PNG; no overlaps, clipping, or horizontal overflow. Audit: distinct
left-x of blocks (must match your grid), distinct font sizes (≤ 4 per register, ≤ 6 on the page),
smallest gap between blocks (≥ 32px). Iterate until clean. Report in under 120 words: path, thesis
in one line, grid, audit numbers, anything not achieved.
