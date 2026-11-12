# Simulation — design note

**Encounter:** an operator opens the Simulation room to get today's verdict at a glance and to check, in the same view, whether the model earning that verdict is still trustworthy — then drops down through runs, receipts, hindcast ledger, and cores as evidence.

**Relationships encoded (relations.json → revision-1/relations.css, embedded in page.html):**
- `titlePresence` → `titleSize` (direct) and, via counterbalance (`power`, e=−0.6/+0.35), `verdictGap` (contracts) and `standingGap` (expands) — the room title, its verdict, and the standing panel share one first view without collapsing into each other.
- `figurePresence` → `figureSize` (shared ancestry across the five standing figures), `labelGap` (counterbalance, e=−0.5, so a bigger figure binds tighter to its caption), and `rowInterval` (direct, so cells never collide).
- `rowPresence` → `hindcastInterval` and `hindcastBracket` move together — the ledger's rhythm and its inside/outside bracket accent belong to one family.

**Alternative:** revision-2 set `figurePresence=1.25`, pushing the five standing figures to 3.25rem — the same size as the room title. Rendered at 1440 and 390 (`alternative.html`, `alt-1440.png`, `alt-390.png`): the standing panel then competes with "Simulation" as a second headline, and a plain fact (the calibration date) reads with the same force as the scored verdict it's meant to support. Kept the baseline: the instrument row should confirm the verdict, not out-shout it.

**Verified:** `agent-do browse --session simT1`, 1440 and 390 — 63/63 nodes present, no horizontal scroll, floor is 12px exactly (bumped the figure-label, ledger flag tag, and footer paragraphs off violations found in the first pass), text contrast 6.2–13.7:1 (faint-on-bg 3.14:1, used only at ≥14px per identity).
