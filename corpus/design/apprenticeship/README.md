# Visual apprenticeship packet

Every design candidate Erik has judged, as an IMAGE beside its PURPOSE and his VERDICT VERBATIM.
Built 2026-09-15 for the Aphrodite design-tool session; 124 candidates across 17 rounds
(101 with recorded words, 124 images, missing images: 0).

## What is here

- `index.json` — the machine-readable packet: `rounds[]` (surface, brief, fixture, laws in force, sources) and
  `candidates[]` (id, round, surface, purpose, image, source_html, arm, verdict, notes, status_basis, sha256s).
- `images/` — one render per candidate, `<round>-<id>.png` (`.jpg` where the only original is a JPEG: pins-002, sim3-erik-sketch; bytes preserved, never re-encoded).
- `PURPOSES.md` — one paragraph per round: surface, brief, fixture, laws in force (laws quoted verbatim from the rulings file or round record).
- `VERDICTS.md` — every verdict quote with its source and date, grouped by round, plus the round-level chat lines and "overall" page notes.

## The rule

Verdict text is Erik's and is never paraphrased or interpreted. Every quote is byte-copied from its named source:
artifact page notes were parsed out of each gallery file's `fb-state` JSON; round-record quotes in `labels.yaml`
were cross-checked against those page notes; chat verdicts were re-read at their transcript line (`fae1af41-26ba-4c61-9805-d261387c8a4a.jsonl`,
line numbers in each source string) and the build refuses to run if any chat quote is not found verbatim at its line.
Typos are his ("dont'", "relaly", "contect", "aweful"). The `status` field is the packet's coarse tag, not a verdict;
`status_basis` says how it was assigned, and `corpus_label` carries the round record's own label where one exists.
A candidate with no recorded words carries `verdict.quote: null` and `status: unjudged` — silence is not a verdict.

Two things are not his words and are labelled as such: the ≤30-word `purpose` (the builder's compression of the round's
brief) and the agent's readings inside the pin files. Judge rankings from the blind rounds are annotation and are not in this packet.

## How a builder should use it

Retrieve a SMALL, VARIED selection per task — never one favorite as a template. The corpus README states the training
signal: what Erik advanced and what he killed, together. A useful pull for one task is on the order of four to eight cards:

1. Take the ratified design of the surface you are building (Today concept-today-C · Dossier concept-dossier-D ·
   Library lib4-askhero · Engine Room eng7-E3v2 · Simulation simw-W3, with simg-G1 as the advanced graft base on W3) and read its verdict and the laws in `rounds[]`.
2. Add two or three KILLED candidates from the same surface whose verdict names the failure you are most likely to
   repeat (word spam: eng5-L3, concept2-library-E; preaching: sim1-S1..S5; wrong grammar for the room: sim3-N1..N11;
   meaningless connectors: eng6-MC1; identity drift: reground-*).
3. Add one or two LIKED-but-not-advanced candidates carrying a part he named (eng5-L5 metro map, eng6-M4 volume flow,
   lib3-broadsheet header, reground-C-today morning edition) — grafts, not templates.
4. Add one pin from a DIFFERENT register than the surface's own (see the register map in `../README.md`): the pins
   span quiet-editorial through maximalist, and "a taste instrument must not collapse his eye to one register".
5. Vary the pull between tasks. Rotate which killed and liked cards you show; keep the ratified card as the anchor,
   not the pattern to copy — "beautiful, unique designs … but never the same thing twice" (pin 001).

Do not average the cards into a house style. Read each verdict as the specific thing he saw in that specific image.

## Provenance of the images

Most images are the round's own gallery renders (`gallery-renders/` or `renders/`), the same pixels Erik judged.
Twelve candidates had no clean single render in the corpus (eng7 E1/E2/E3/E3v2; reground A today/engine/dossier/library,
B today/engine, C today/engine — the galleries embed them as srcdoc iframes); these were rendered on 2026-09-15 with
`agent-do browse` at viewport 1440×900, full page, from the corpus html whose sha256 is recorded on the card
(`image_provenance` names them). Aphrodite 0.1 images are the run's own `observed/wide-base.png`. Pin shots carry
their capture caveats on the card (`image_caveat`). Every image path in `index.json` exists and its sha256 is recorded.

## Corrections to the commissioning brief, found while building

- concept-2 chat line is longer than relayed; full line 2844 quoted.
- sim1 kill line is timestamped 2026-09-14T20:34Z (transcript line 6421), not 2026-09-15; the rulings file agrees (ruled 2026-09-14).
- the concept-1 gallery artifact is not 783013fb (that file is Engine Room Round Three); the concept-1 gallery is a different artifact and its verdict came in chat, as the brief said.
- lib4 "the very obvious winner here" is a page note (d0f5068d), not a separate chat line; no chat line with those words exists in the transcript.
- pins 001 and 003 words exist only in their pin files (their chat lines predate this transcript); the pin file is cited as source.

## Not included

- fixtures/canon-today, canon-dossier, barf, broken — instrument fixtures for dpt, not candidates Erik judged (rounds/fixtures/labels.yaml labels are the agent's: liked_direction / negative_control)
- reground/approved/*.png — ratified pixels reused for the A-vs-canon comparison; the candidates they depict are already present (concept today-C, dossier-D, lib4 askhero, eng7 E2)
- simg/MERGE-G1+G2+G4.html — the merge built after the ruling, not a candidate Erik judged in the round
