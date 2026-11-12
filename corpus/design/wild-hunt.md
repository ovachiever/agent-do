# WILD HUNT — the mathematics of beauty, hunted for the taste instrument

**GENERATION ARTIFACT.** Zero evidential standing until each candidate passes downstream
verification. Every number and citation herein is trained recall awaiting a receipt. Marking
convention: plain statement = recalled published result (verify anyway) · *vision:* = conjecture,
the wager this rite exists to produce · *contested:* = live dispute · *corpse:* = known failure,
kept for calibration.

**Seated ground (not re-tilled):** DPT's floor rules (contrast, size, touch targets, palette
counts, spacing grids, alignment guides, whitespace density) — the checklist stratum, already
built, already honest. The learned-preference comparator — set aside by Erik as "the training AI
already got." Ngo-style screen metrics — the corpse DPT was built from. Where a candidate below
touches these, an adjacency flag is planted and the border respected.

**The standard kill-test** (available NOW, from our own corpus): a candidate metric must
(a) separate the canon fixtures from barf/broken, (b) rank round winners above their killed
siblings better than chance across the seven rounds, (c) survive the Round-2 Trap — it must NOT
crown the heavy conceits Erik hated, and (d) read all five pins as high-structure despite their
wildly different registers. Any candidate that fails (c) is a novelty detector, not a taste
instrument. Any that fails (d) is a style prejudice.

**The one meta-pattern that organizes the whole hunt:** DPT measured absolutes — each rule reads
one property and votes. Nearly every candidate below measures RELATIONS — between parts, between
scales, between perceptual channels, between the page's own beginning and end. *vision:* beauty
is not a property of measurements; it is a property of the agreements among measurements. The
taste tensor is an interaction tensor. DPT 2.0 keeps DPT's primitives and scores their RESONANCE.

---

## HOUSE OF COMPRESSION — beauty as what the codec feels

### 1. The Self-Teaching Index
**THE PATTERN.** A coherent page establishes a visual vocabulary in its first viewport and then
speaks it. So: compress the bottom of the page *conditioned on* the top (any real compressor:
concatenate top||bottom, subtract standalone costs). Beautiful pages show a steep conditional
gain — the page taught you its language, then reused it. Erik's own rulings rhyme exactly: D1
won round six for "one repeated block anatomy"; B1 died as "schizo" — a page whose bottom shares
no code with its top. Music rhymes: theme-and-variation; prose rhymes: a book that teaches you
how to read it.
**WHERE IT LIVES.** MDL/two-part coding literature; PPM/LZ conditional compression; our gallery
HTML + renders.
**WHAT IT WOULD MEAN.** Coherence — Erik's #1 kill-word — becomes one number computed by `zstd`
in a for-loop. No rules, no rubric, no learned preferences.
**DIG FIRST.** Compute NCD-style conditional gain for all round-six candidates (D1 vs B1 is the
decisive pair) on both PNG strips and HTML. If B1 ≥ D1, the index is dead. One afternoon.

### 2. The Rate–Distortion Signature
**THE PATTERN.** Compress the screenshot at 20 quality levels; plot bytes vs perceptual error
(SSIM). Noise dies catastrophically, emptiness never degrades, and *vision:* designed pages
degrade *gracefully* — a smooth, convex R-D curve because they carry structure at every scale
that the codec can trade in order. The curve's SHAPE (convexity, knee position, tail) is the
signature, not any point on it.
**WHERE IT LIVES.** Rate-distortion theory; JPEG quality ladders; Machado & Cardoso's
image-complexity/processing-complexity ratio (published, partially validated).
**WHAT IT WOULD MEAN.** "Substance vs decoration" becomes a curve geometry question.
**DIG FIRST.** R-D curves for barf, broken, canon, five pins. If barf's curve is as smooth as
canon's, dead. Hours.

### 3. Scale-Stratified Two-Part Codes ("designed all the way down")
**THE PATTERN.** Kolmogorov's structure/noise split, done per octave: at each downsampling
level, how much of the image is model and how much residual? Great pages hold a high
structure-fraction across 4–5 octaves (the poster works across the street, the caption works in
the hand). Barf is structure-poor at every scale; "clean but dead" pages (Erik's T1: "clean…
but does it tell a story?") are structure-rich at ONE scale and empty above it.
**WHERE IT LIVES.** Algorithmic statistics; sophistication/logical depth (Bennett); multi-scale
texture analysis.
**WHAT IT WOULD MEAN.** A computable form of "it rewards attention at every distance."
**DIG FIRST.** Structure-fraction-vs-octave curves for T1 (clean, no story) against D1 (dense
story). If they match, dead.

### 4. The Scroll as Melody (surprisal contour)
**THE PATTERN.** Feed the page to an incremental compressor viewport by viewport, top to
bottom; record surprisal per step. Music-expectation research (IDyOM family) finds pleasure in
moderate surprisal with resolution — tension arcs, not flat lines, not white noise. A page has a
melody line: masthead (theme), body (development), footer (cadence). Erik killed "boring" (flat
contour) and "schizo" (noise contour) in the same round — the two failure modes of one curve.
**WHERE IT LIVES.** Information dynamics of music; sequential prediction; our full-page renders
sliced into scroll windows.
**WHAT IT WOULD MEAN.** Pacing — the most "unmeasurable" editorial property — as a 1-D signal
with computable shape statistics.
**DIG FIRST.** Surprisal contours for L4 ("boring but the cards work") vs B1 ("schizo") vs M1
("good"). Prediction: flat / jagged / arced respectively. Wrong order kills it.

### 5. The Styling-Work Meter
**THE PATTERN.** *vision:* Render the page twice — once with its stylesheet, once with CSS
stripped (browser-default render of the same DOM). The compression distance between the two
renders is the *work styling did*. Beauty correlates not with the amount of work but with the
work's EFFICIENCY: styled-render structure gained per byte of CSS. Pete's Pasta spends enormous
CSS and gains an enormous world (efficient); AI-slop gradient pages spend much and gain noise.
**WHERE IT LIVES.** NCD; our candidate HTML files, both renders one `browse` session apart.
**DIG FIRST.** Efficiency ratio for pins vs the round-2 heavy conceits (the trap set). If the
conceits score as efficient as the pins, dead.

---

## HOUSE OF SPECTRA — beauty as what the frequency domain knows

### 6. The 1/f Corridor
**THE PATTERN.** Natural scenes carry ~1/f² power spectra; human vision is tuned to them; art
across centuries and cultures statistically converges toward natural-scene spectra (Graham &
Field; Redies — published). Compute the radial power-spectrum slope of the screenshot. *vision:*
good pages live in a corridor of slopes; barf sits shallow (too much high frequency = clutter),
dead-minimal pages sit steep (nothing but DC).
**WHERE IT LIVES.** Natural image statistics; empirical aesthetics of spectral slope
(contested: correlation strength varies by medium).
**WHAT IT WOULD MEAN.** "Feels alive" gets a spectral address — Erik's exact word for Pangram.
**DIG FIRST.** Slopes for all 5 pins + barf + broken + the round-six eight. Pins should
cluster; barf/broken should sit outside the pin band. If pins scatter as widely as candidates,
dead.

### 7. Phase Congruency vs Phase Noise
**THE PATTERN.** Structure lives in Fourier phase, not amplitude (swap phases between two
images: identity follows phase). Phase congruency (Kovesi) marks perceptually real edges.
*vision:* beauty = high phase congruency concentrated on few, long, agreeing contours; ugliness
= congruency dust. The measure: congruency mass ÷ congruency perimeter — long coherent bones
beat scattered fragments.
**WHERE IT LIVES.** Phase congruency literature; V1 physiology; our renders.
**DIG FIRST.** Bone-vs-dust ratio on canon vs barf. Then the subtle pair: MC2 (81, unloved) vs
M1 ("good") — does the measure track Erik or track dpt? Either answer teaches.

### 8. Gabor Sparsity — beauty as the observer's cheap code
**THE PATTERN.** The efficient-coding hypothesis of aesthetics: images are pleasing when the
visual cortex can encode them sparsely (few active V1-like units at matched fidelity).
Published for faces (sparse-codability tracks attractiveness — Renoult) — port it to pages: fix
a Gabor dictionary, sparse-code the screenshot, measure L1 at matched reconstruction error.
This is AI-native in the deepest sense: beauty as the energy bill of seeing.
**WHERE IT LIVES.** Olshausen & Field sparse coding; facial-beauty sparse-coding results;
scikit-image + a fixed Gabor bank.
**WHAT IT WOULD MEAN.** A physiological, non-learned, non-rule number under everything else —
the thermodynamics below the aesthetics.
**DIG FIRST.** Sparse-code cost for pins vs barf at matched SSIM. Also the trap set — heavy
conceits were *visually expensive*; the measure should notice.

### 9. The Diffraction Test (quasicrystal order)
**THE PATTERN.** Take element centroids as a point set; compute its structure factor S(q) — the
physicist's diffraction pattern. Perfect grids give Bragg peaks; chaos gives diffuse haze; and
between them lives the interesting kingdom: sharp peaks WITHOUT full periodicity (quasicrystal
order — long-range order, no repetition). *vision:* Erik's "never the same thing twice" is a
demand for quasicrystalline pages: unmistakable order that never tiles.
**WHERE IT LIVES.** Condensed-matter structure factors; Penrose tilings; our DOM box geometry
(dpt already extracts every box).
**DIG FIRST.** S(q) for a broadsheet (near-periodic), Pete's (patterned maximalism), barf
(haze). If Pete's and barf are indistinguishable, dead.

### 10. The Squint Trajectory (renormalization fixed point)
**THE PATTERN.** Blur is coarse-graining is renormalization. Track a feature vector (edge
density, palette, saliency layout) as the page is progressively blurred: canon pages move
SMOOTHLY and keep their identity for many steps (near a renormalization fixed point); barf
shatters early; empty pages never had identity. We accidentally piloted this: the P1 blur
probes (canon-blur vs barf-blur) already exist in the transcript. Designers' oldest tool — the
squint — is an RG flow.
**WHERE IT LIVES.** Renormalization group; scale-space theory (Lindeberg); P1 probe artifacts.
**WHAT IT WOULD MEAN.** "Holds together" becomes trajectory length and smoothness in feature
space under blur — one of Erik's invariants (conviction) made kinematic.
**DIG FIRST.** Re-run blur ladders on round-six candidates; correlate trajectory smoothness
with his verdicts. The winner set is known; the test is cheap.

### 11. Fractal Dimension Band + Lacunarity of the Breath
**THE PATTERN.** Preference peaks for fractal dimension D ≈ 1.3–1.5 are published (Taylor on
Pollock; *contested*). More interesting here: compute D not on ink but on WHITESPACE — and add
lacunarity (gappiness texture). *vision:* the "breath spectrum": pages breathe well when their
whitespace has coherent texture across scales (low lacunarity variance), and suffocate or gape
when it doesn't. Erik's "air" praise and "word spam" kills are breath diagnoses.
**WHERE IT LIVES.** Box-counting; lacunarity in landscape ecology (they measure habitat
gappiness — same math, different forest).
**DIG FIRST.** Breath spectra for L3 ("word spam ×100") vs S1 (rationed spine). If
indistinguishable, dead.

---

## HOUSE OF BROKEN SYMMETRY — beauty as law plus deliberate transgression

### 12. Second-Order Intentionality (the pattern of the deviations)
**THE PATTERN.** Fit the page's best grid/symmetry; collect the residuals — every edge that
breaks the law. Then measure the residuals' OWN structure. *vision:* in masterful pages the
deviations form their own pattern (all breaks are the pull-quotes; all breaks lean the same
way); in sloppy pages deviations are white noise. Physics rhyme: broken symmetry is where mass
comes from; design rhyme: broken grid is where interest comes from — but only if the breaking
is itself lawful. This is Erik's "conviction" as mathematics: deviation-with-structure =
intention; deviation-without = accident.
**WHERE IT LIVES.** Crystallography of defects (defects order into their own lattices!);
residual analysis; dpt's alignment extractor gives the residuals today.
**WHAT IT WOULD MEAN.** The single word "deliberate" — the heart of taste judgments — becomes
compressibility of the residual set.
**DIG FIRST.** Residual-set compressibility for pins vs round-2 conceits vs barf. The trap set
matters most: conceits break grids loudly — is their breaking lawful? Erik said no. Does the
math?

### 13. The Loom Number (layout rank)
**THE PATTERN.** Collect every box edge coordinate; find the minimum set of anchor lines
covering them (set cover), or the effective rank (singular-value entropy) of the edge matrix.
Beauty = few lines weaving many elements — a low-rank loom. Then recurse: the OFF-loom edges
must themselves be low-rank (see 12). Adjacency flag: dpt's sr07 counts guides — seated; the
rank formalism and the recursion are the unlit part.
**WHERE IT LIVES.** Matrix rank/sparse recovery; set cover; the DOM.
**DIG FIRST.** Loom number (normalized by element count) across all round-six candidates vs
verdicts; D1 should be low-rank, B1 high. Fast.

### 14. The Size Chord (consonance of proportions)
**THE PATTERN.** Take all pairwise ratios among the page's characteristic lengths (type sizes,
box widths, gaps) in log space. Music: consonance = simple ratios; Plomp–Levelt roughness
curves compute dissonance for arbitrary intervals. *vision:* run the page's length-ratios
through a roughness model — the page plays a chord, and you can compute whether it's consonant,
and (better) whether the WHOLE page plays in one key (few interval classes, reused) or in
none. Kills the golden-ratio corpse properly: no magic ratio — any consistent chord works,
which is exactly what typography's modular-scale practice believes.
**WHERE IT LIVES.** Psychoacoustic consonance models; pitch-class set theory; modular scale
practice; dpt's box extractor.
**DIG FIRST.** Chord roughness for pins (five different keys, all should be internally
consonant) vs barf (atonal). If pins don't separate from barf, dead.

### 15. Assembly Index of the Layout
**THE PATTERN.** Assembly theory (Cronin/Walker): objects that require many construction steps
AND appear in many copies indicate selection — "designedness" in molecules. Port: decompose the
layout into a build sequence with reuse (define a card, stamp it six times, vary one slot).
High assembly index with high copy-number = crafted world (Pete's mascot-and-badge system);
high index, copy-number one = schizo (every element bespoke); low index = template slop.
**WHERE IT LIVES.** Assembly theory papers; shape grammars; the DOM tree hands you the
decomposition half-free.
**WHAT IT WOULD MEAN.** A single axis separating THE three failure modes Erik keeps naming:
slop (too little assembly), schizo (no reuse), craft (deep assembly, rich reuse).
**DIG FIRST.** Crude assembly proxy: (distinct component classes) vs (instances per class) vs
(variation within class) across round-six. D1 should sit in the crafted corner.

### 16. The Zipf of Boxes
**THE PATTERN.** Rank component areas by size; plot rank–size. Cities, words, incomes,
craters — robust power laws. *vision:* well-composed pages hold a stable rank–size slope with
few breaks; slope breaks are the seams the eye feels ("why are there suddenly nine same-sized
things?"). The hierarchy Erik demands ("lead ruling at display scale, second candidate
subordinate") IS a rank-size discipline.
**WHERE IT LIVES.** Zipf/Pareto literature; urban scaling; dpt box areas.
**DIG FIRST.** Rank–size plots for the ratified broadsheet (strong hierarchy) vs the round-2
"Null" (Erik liked it — flat hierarchy?). If the Null breaks the prediction, price that
honestly — it may reveal the measure is genre-conditional (Wundt banding, see 27).

---

## HOUSE OF UNITY-IN-VARIETY — the oldest definition of beauty, finally computable

### 17. TSE Complexity of the Page (THE BIG ONE)
**THE PATTERN.** "Uniformity amidst variety" (Hutcheson, 1725) is the most durable definition
of beauty ever proposed — and neuroscience formalized exactly that quantity: Tononi–Sporns–
Edelman complexity, high only when a system is simultaneously INTEGRATED (parts predict each
other) and DIFFERENTIATED (parts are not copies). Segment the page into regions; extract per-
region feature vectors (color, type, density, geometry); compute TSE complexity over the
region ensemble — mutual information among subsets summed across subset sizes. Slop pages =
differentiated, unintegrated (low). Template pages = integrated, undifferentiated (low).
Pete's AND Pangram AND every.to = both at once (high) despite opposite registers — which is
precisely the register-independence a taste instrument needs and no style rule can have.
**WHERE IT LIVES.** Neural complexity literature (TSE 1994+); integrated-information proxies
(Φ*, geometric IIT — the tractable ones); image segmentation.
**WHAT IT WOULD MEAN.** Beauty's oldest philosophical definition and its newest neural
mathematics agree on one computable number, evaluated over a page. If the corpus confirms it,
this is DPT 2.0's spine and the moon program's flag in the ground.
**DIG FIRST.** TSE proxy over 24-region grids for: 5 pins, barf, broken, round-six eight,
round-2 trap set. Required: pins high, barf/template low, trap set NOT above the pins. This
single afternoon of compute is the most valuable experiment available to the program.

### 18. The Three Trees Theorem
**THE PATTERN.** Every page has three partitions of its elements: the GEOMETRIC tree (who
clusters with whom in space), the STYLE tree (who shares color/type/shape), and the SEMANTIC
tree (who belongs together in meaning — the DOM/heading structure). *vision:* beauty of the
load-bearing kind = the three trees agree (high pairwise partition mutual information);
Erik's "schizo" = style tree fighting semantic tree; "meaningless connectors" (his MC1 kill) =
geometric tree asserting edges the semantic tree denies. We can compute all three trees today:
clustering on coordinates; clustering on computed styles; the DOM. Then three numbers: MI(G,S),
MI(G,Sem), MI(S,Sem).
**WHERE IT LIVES.** Consensus clustering / variation of information (Meilă); Gestalt cue-
combination; the DOM as ground-truth semantics (a luxury natural images never had!).
**WHAT IT WOULD MEAN.** The web page is the ONE aesthetic artifact whose semantic structure
ships machine-readable alongside its appearance — the three-trees measure is only possible
here. AI-native for real: no human rater, no learned prior, pure structure agreement.
**DIG FIRST.** Tri-tree MI on MC1 (connectors Erik called "ill if taken literally") — the
geometric tree claims relations the semantic tree lacks; the measure must flag exactly that.
Then B1 (schizo). Two known kills; if the measure misses both, dead.

### 19. Voice-Leading Between Sections
**THE PATTERN.** Tymoczko's geometry of music: chords are points in an orbifold; good music
moves between them by short voice-leading paths. Port: each page section's palette+type is a
chord in style space; measure the path the page walks as you scroll. *vision:* coherent pages
modulate smoothly (short voice-leadings, occasional deliberate leap at a section boundary —
and the leap coincides with a semantic boundary, see 18); schizo pages teleport constantly.
C's ruled two-ground identity (daylight Today, dark Engine) is a single long modulation the
skeleton must carry — this measure would price exactly whether it does.
**WHERE IT LIVES.** Tymoczko's *A Geometry of Music*; color-space geodesics; scroll-sliced
renders.
**DIG FIRST.** Voice-leading path lengths per scroll for canon vs B1. Then the killer case:
direction C's two pages — the boundary leap should be LARGE and SINGULAR, everything else
smooth. If the measure can't tell C's lawful leap from B1's teleporting, dead.

### 20. Sheaf Consistency (H¹ of the style sheaf)
**THE PATTERN.** Deep cut. Local style decisions are sections over neighborhoods of the page;
coherence is whether local sections glue into a global one. Obstructions to gluing are
cohomology — *vision:* "schizo" is literally H¹ ≠ 0: every local pair of neighbors agrees, yet
no global style assignment exists (the page is an aesthetic Penrose staircase). Computable via
consistency graphs: nodes = regions, edges = pairwise style compatibility, obstruction = cycles
whose compatibility products don't close.
**WHERE IT LIVES.** Sheaf theory for data fusion (Robinson's *Topological Signal Processing*);
constraint-graph cycles.
**WHAT IT WOULD MEAN.** The difference between "each part is fine" and "the whole is wrong" —
the reviewer's hardest sentence — gets an exact address.
**DIG FIRST.** Build the compatibility graph for B1; hunt one non-closing cycle. Existence
proof first, metric later. If B1's graph closes globally, the vision dies.

### 21. Persistent Homology of the Layout ("the persistence gap")
**THE PATTERN.** TDA barcodes over filtrations of the page (density, color distance,
whitespace distance): long bars = real structure, short bars = noise. *vision:* beauty
correlates with a clean GAP between long and short bars — confident structure, clean texture —
while muddle shows a barcode without a gap (structure and noise blur together). Bonus: H₁
loops in the whitespace = enclosures and frames; Pete's checkered fields and every.to's
column voids have signature loops.
**WHERE IT LIVES.** Persistent homology (Ripser is fast enough); TDA-on-art attempts
(published, scattered).
**DIG FIRST.** Barcodes for canon vs barf: is the gap statistic separable? Then MC2-vs-M1
again as the taste-vs-floor discriminator.

---

## HOUSE OF FIELDS AND FLOWS — beauty as navigable space

### 22. Space Syntax of Whitespace
**THE PATTERN.** Architecture's space-syntax (Hillier) computes integration/intelligibility of
buildings from their void structure — how easily any room reaches any room. Treat whitespace
as the page's circulation: medial-axis skeleton of the void, then integration statistics.
*vision:* pages Erik calls readable have "streets" (wide, few-branched, connected voids);
word-spam pages have slums (fragmented capillary whitespace). The lacunarity candidate (11)
measures the texture of air; this measures its TOPOLOGY.
**WHERE IT LIVES.** Space syntax literature; medial axis transforms; ecology's corridor
connectivity (same math again).
**DIG FIRST.** Integration stats for L3 (word spam) vs S1 (rationed). Then the pins — Pete's
is maximalist yet navigable; the measure must not punish density itself, only broken
circulation. That's test (d) from the standard kill-test.

### 23. The Emphasis Transport Cost
**THE PATTERN.** Two distributions live on every page: where the SALIENCY mass is (bottom-up,
computable: spectral-residual or Itti–Koch) and where the IMPORTANCE mass should be (the DOM
hierarchy again — h1 > h2 > body; the lede outranks the footer). Compute the Wasserstein
(earth-mover) distance between them. Beauty of the working kind = low transport cost — the
page's physics agrees with its politics. Erik's T4 "junk" and aa02's blindness both live here;
adjacency flag: dpt's aa01 crudely ranked weight — seated; the transport formulation and the
DOM-as-target are unlit.
**WHERE IT LIVES.** Optimal transport (POT library); saliency models chosen deliberately OLD
and un-preference-trained (Itti–Koch is 1998 physiology, not web-trained aesthetics — keeps
Erik's objection out).
**DIG FIRST.** Transport cost vs verdicts across round-six. Cheap, decisive, and it upgrades
an existing floor into a relation.

### 24. Ricci Curvature of the Style Graph
**THE PATTERN.** Build the element graph (edges = adjacency), weight by style distance;
compute Ollivier–Ricci curvature per edge. Positive curvature = community (rooms of like
elements), negative = tree-sprawl/bridges. *vision:* good pages show a curvature PROFILE:
strongly positive inside components, cleanly negative on the few deliberate bridges between
sections — rooms and doors. Muddle is flat-curved everywhere: no rooms, all corridor.
**WHERE IT LIVES.** Graph Ricci curvature literature (used on brains, markets, cancer — every
field but this one); networkx implementations exist.
**DIG FIRST.** Curvature histograms, canon vs B1. Bimodal vs unimodal is the prediction.

### 25. Spectral Gap of the Page Laplacian
**THE PATTERN.** Same graph, Laplacian eigenvalues. Fiedler value = how much the page holds
together; spectral gap sequence = how cleanly it decomposes into modules (rooms again, in
spectral clothing). Random-matrix wildness, priced accordingly: *vision:* eigenvalue spacing
statistics distinguish crystalline (Poisson-degenerate), chaotic (GOE repulsion), and DESIGNED
pages — which may sit in a recognizable intermediate ensemble, the way quantum systems between
integrable and chaotic do.
**WHERE IT LIVES.** Spectral graph theory; RMT universality; one `scipy.linalg.eigh` away.
**DIG FIRST.** Fiedler + gap sequence across corpus; if verdict correlation is nil, keep the
Fiedler value as a cheap coherence prior and bury the RMT flourish in the Reliquary.

---

## HOUSE OF INVARIANTS — the numbers that shouldn't recur but do

### 26. The Dimensionless Groups of Design (Buckingham-π mining)
**THE PATTERN.** Physics reduces every law to dimensionless groups (Reynolds, Mach). *vision:*
mine the pin corpus + ratified surfaces for dimensionless ratios that hold ACROSS registers —
ink-to-air ratio per octave, accent-area fraction, loom-number-per-element, breath lacunarity,
chord roughness. The taste instrument is then not one score but a small vector of invariants
with corridors, discovered rather than legislated. Meta-method: it eats every other candidate
in this file as a feature and asks which are conserved across everything Erik loves.
**WHERE IT LIVES.** Dimensional analysis; our corpus (the five pins span registers on
purpose — exactly the variation needed to see invariants).
**DIG FIRST.** Compute candidates 1–25 over the pins; hunt low-variance ratios. Needs ≥10
pins to mean anything — argues for growing the pin corpus NOW.

### 27. Wundt Banding (the inverted-U made honest)
**THE PATTERN.** Berlyne's inverted-U: liking peaks at intermediate arousal/complexity —
published, old, half-corpse. The honest revival: never score complexity monotonically; locate
the page ON the complexity axis and learn the BAND per genre from ratified examples. Pete's
band (maximalist commerce) and the broadsheet's band (morning paper) are different corridors of
the same axis. Every candidate above becomes banded, not directional. This is the
mathematical form of the round-2 lesson: the judges' sin was monotone taste ("more novel =
better"); bands cannot commit it.
**WHERE IT LIVES.** Berlyne; the corpus's genre labels (rooms! Today vs Engine Room are
different bands by ruling).
**DIG FIRST.** Any candidate that failed its kill-test monotonically — re-test banded before
burying it.

### 28. Prototype Distance with the Sign Flipped
**THE PATTERN.** Facial-beauty mathematics: averageness attracts, but the MOST attractive
faces sit slightly OFF the prototype in specific directions. *vision:* pages have genre
prototypes (the median dashboard, the median morning paper); beauty = small distance from
prototype along MOST axes plus large deliberate distance along ONE (the conviction axis —
Pete's is a normal shop radically committed to one world; every.to is a normal magazine
radically committed to black). Measurable in any fixed feature space as: distance profile
shape — flat-small with one spike — rather than total distance.
**WHERE IT LIVES.** Facial attractiveness literature; the corpus for prototypes. Flag: needs a
feature space; use un-preference-trained descriptors (Gabor stats, the candidates above) to
respect Erik's constraint.
**DIG FIRST.** Distance profiles for pins vs their genre medians (scrape 20 median specimens
per genre). One-spike shape present in ≥4/5 pins, absent in slop, or dead.

---

## RELIQUARY — sang on the table, died on the table

- **Birkhoff's M = O/C** (1933). *corpse.* Failed empirically for a century, yet every candidate
  above secretly carries its skeleton (order term over complexity term). Kept as the ancestor
  shrine and the warning: a RATIO of two vague quantities is astrology; ratios of two MEASURED
  quantities are instruments.
- **Golden-ratio hunting.** *corpse.* Markowsky's debunking stands; φ appears in good design at
  chance rates. Its living descendant is candidate 14 — any consonant chord, not one sacred
  interval.
- **Ngo's 13 screen metrics.** *corpse* by adoption — DPT already IS this stratum; adding more
  absolute metrics thickens the floor, never reaches taste. Seated ground.
- **NIMA-style learned aesthetic scorers.** Excluded by the client's own ruling — that's the
  training the AI already has, and it's exactly the judge that crowned what Erik hated.
- **Thermodynamic depth.** Beautiful idea (value = history embodied), no computable proxy for a
  rendered page surfaced in this hunt. Left on the table with respect.
- **Peak-shift / supernormal stimulus.** Real neuroscience, too thin here — needs a
  discriminative axis per element role we couldn't define without smuggling rules back in.
- **Phyllotaxis / growth-order layouts.** The rhyme (reading order = growth order) never became
  a measurement. May return the day layouts animate.
- **Eye-tracking-fitted models.** Not AI-native — they import human raters through the side
  door. Validation instruments, not the instrument.

---

## THE THREE I WOULD BET ON

**1. TSE Complexity (17) — because it is the 300-year-old definition wearing modern
mathematics.** Unity-in-variety survived every aesthetic regime change since 1725; TSE is its
exact formal twin, already battle-tested on brains; and it is the only candidate that
explains, with one mechanism, why Pete's Pasta and every.to — visual opposites — both made
Erik's hands point. Integration × differentiation is register-blind, which is the property his
corpus DEMANDS and no style rule can fake. If one number goes on DPT 2.0's masthead, it is
this or nothing.

**2. The Three Trees (18) — because the web page is the only art form whose meaning ships
machine-readable, and nobody has cashed that cheque.** Geometric, style, and semantic
partitions, mutually informed — it computes the exact sentence Erik keeps saying ("don't be
schizo, be coherent") with no learning and no rules, and it can only exist for our medium.
Natural-image aesthetics never had ground-truth semantics; we get them free in the DOM. When a
measure names the client's own kill-word as a cohomology-adjacent agreement failure, you bet
on it.

**3. The Self-Teaching Index (1) — because it is embarrassingly computable and it made three
verdicts in a row make sense.** D1's win ("one anatomy repeated"), B1's death ("schizo"), and
the word-ration law are all the same statement: a beautiful page teaches its language early
and then speaks it. Conditional compression measures precisely that, with zstd, tonight,
against verdicts we already hold. It is the fastest possible falsification in the whole file —
and an instrument you can run in a pre-commit hook if it lives.

*And the hunt's confession: all three bets are the same wager stated at three depths — that
beauty is agreement-between-parts made measurable, that DPT failed not by measuring wrong
things but by never asking its measurements to talk to each other. The taste instrument is not
a longer checklist. It is the resonance of the checklist with itself.*
