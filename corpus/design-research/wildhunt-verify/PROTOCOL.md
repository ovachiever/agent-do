# Wild-hunt verification: frozen screening protocol

Issue: mn-c2d546. Written before computing any candidate score, 2026-09-08.
This is a local preregistration, not an independently registered study. `freeze.json`
records this file and the input/code hashes before evaluation; the run refuses drift.
`wild-hunt.md` is a frozen generation artifact with zero evidential standing.

## Scope and authority

Report only. No production DPT, registry, command, dependency, or model changes.
Run #17, #18, #1 first, then #10, #23, #13, #14. A pins-only #27 retest is
precommitted for the raster scores #17, #1, #10, whether they pass or fail.
The remaining generation candidates are NOT TESTED, not killed by association.
No commits until Erik authorizes a commit. No change to the task's Manna lifecycle
to imply accepted delivery while that boundary is pending.

Published mathematics motivates these operationalizations; it does not establish
that any of them measures taste. A killed proxy does not disprove its parent field.

## Corpus and labels

`corpus.json` and each `corpus/rounds/<round>/labels.yaml` contain the exact quotes,
source paths, original gallery keys, and file hashes. JSON syntax is YAML 1.2.
Preserve all specimens, including missing, unnoted, conditional, and conflicting ones.

Original saved gallery pixels take precedence over transcript Read thumbnails.
Transcript HTML is recovered only from successful tool results and exact edits,
without executing recorded shell commands. Native full-page and viewport captures
remain distinct. Captured DOM is a present renderer's view of the recovered HTML,
not a claim that its font rasterization or script state matches historical pixels.
DOM probes use the archived image width and retain only nodes intersecting that
image's extent. No live-site DOM is substituted for an old pin screenshot.

Grounding corrections made before scoring:

- Paper Broadsheet = today-C; Auction Lot = dossier-D, verified against gallery
  card titles and IMG placeholders, plus the round's blind key. Named `canon-*`
  fixtures are a liked direction, not ratified final designs (fixture README).
- Library Round 3 has a provisional paneldock winner and four explicit rejections;
  askhero wins Library Round 4. These are different rounds, not interchangeable wins.
- Engine Round 5 has no winner. Its 14 candidates stay in the corpus, but cannot
  manufacture a within-round winning pair. B1 remains a targeted structural kill.
- M2, M3, MC2 and other silent entries are unnoted, not invented negative votes.
- Round 7 is entirely excluded: E2 chat ruling conflicts with E3 page feedback.
  Reground A/B/C has no recovered final ruling and is also excluded from scoring.
- Five pins remain declared. Four have screenshots; 002/every.to is unavailable.
  Pin 005's original signup overlay remains part of its captured specimen.

### Fixed primary comparisons

These ten ordered comparisons are selected from human feedback, before scores:

| Round | Preferred/advanced | Rejected comparators | Pairs |
|---|---|---|---:|
| Concept 2, Library | library-B, The Null | library-D, library-A | 2 |
| Library 3 | paneldock, provisional winner | market, deltas, statled, quiet | 4 |
| Engine 3 | oneline and timetable2, both advanced | ledgerfirst | 2 |
| Engine 6 | M1 and D1, conditional winner | MC1's explicitly rejected arrangement | 2 |

These test **advancement/preference over an explicitly rejected arrangement**, not
ten unconditional final-winner decisions. The exact quote always outranks that role.
Also report the subset without provisional/conditional preferences. Round 1 and
Library 4 winners have unselected siblings, not explicit negative quotes; any
winner-vs-unselected ordering is descriptive only and never enters the primary test.

The work order's cross-round D1 > B1 prediction for #1 is a separate falsifier,
never smuggled into the within-round denominator. Different native capture lengths
are a confound for that pair, reported alongside the result.

## The four gates, fixed for every score

Higher score is always better. `config.json` gives each practical margin. Margins
are declared experimental screening choices, not published beauty thresholds.

1. **A, fixtures:** min(score(canon-today), score(canon-dossier)) minus
   max(score(barf), score(broken)) must meet the declared margin. Report all four
   values and the gap; a tie does not pass.
2. **B, rounds:** all ten fixed pairs must be measurable. A strict preferred >
   rejected is one success; a numerical tie counts as failure. Compute the exact
   one-sided binomial tail against p=0.5, alpha=0.05 (work-order authority).
   Apply Holm correction across the eleven predeclared score tests, including
   both #1 channels and three #27 retests. Missing tests receive p=1, never leave
   the family. Report raw p, adjusted p, accuracy and exact binomial interval.
   Reused specimens make pairs dependent: these are screening diagnostics, not
   independent population trials. Report per-round rates and an exact round-level
   sign-flip sensitivity (all 2^R flips of each round's centered success sum).
   That sensitivity is a limitation check, not a post-hoc replacement gate.
3. **C, trap:** in EACH of Library and Engine, its Null must score at least the
   median of the four non-Null conceits. Require all ten trap specimens. Equality
   passes this gate only. A fail instantly kills the operationalization as a taste
   candidate; it does not by itself prove the psychological cause is novelty bias.
4. **D, register:** all four available archived pins must exceed the maximum of
   barf/broken by the candidate's declared margin. Always report 4/5 screenshot
   availability. DOM-dependent scores have 0/4 matched pin DOMs and this gate is
   INCOMPLETE, not vacuously true and not evidence of a style failure.

No missing datum becomes zero or disappears from a required denominator.
Any observed gate failure yields KILLED for that tested implementation, even if
another gate is incomplete. A score with no failure but incomplete coverage is
INCOMPLETE, never SURVIVED SCREENING. Only complete passage of all gates can yield
SURVIVED SCREENING. BANDED-RETEST names only the predeclared pending #27 operation;
once run, its actual pass/fail replaces that pending status. No threshold changes.

## Implementations and declared numerical authority

All experimental settings live in `config.json` and cite this section. They are
chosen before data scores, not claimed natural constants. No output/result caps.
Source image sizes, DOM counts, subset counts, compressor windows and permutation
enumerations derive from measured input or the fixed design below.

Shared raster: white-composite alpha; RGB bytes decoded from the original PNG/JPEG.
The common analysis width is the minimum available archived evaluation width
divided by the grid's column count, preserving aspect ratio. No screenshot crop,
popup cleanup, aesthetic model, OCR, or learned preference score. `uint8` range
derives from the image representation. Float tolerance = 64 machine epsilons,
a numerical equality convention, not an effect margin.

### Wave 1

**#17 TSE Gaussian feature proxy.** Grid = 4 columns x 6 rows = 24 regions, meeting
the work-order minimum. Normalize each region to 32 x 32 samples (experimental
spatial resolution). Feature vector = RGB and finite-difference luminance gradient
magnitude, concatenated at corresponding relative positions. Mean RGB defines
luminance here; this is a deterministic texture descriptor, not a vision model.
Each region is a variable, descriptor positions/channels are the ensemble. Form
the correlation matrix, zero-variance regions independent, and shrink toward the
identity by 1/descriptor_length (one pseudocount per observed feature). Gaussian
integration I(S) = -0.5 log det R(S). Score = mean over k=1..N-1 of
`(k/N)*I(all) - mean(I(S_k))`. For each k, use N subsets drawn without replacement
within each subset, fixed RNG seed derived from SHA-256 of the issue ID. The same
subsets apply to all pages. This is a sampled, static-image covariance proxy;
descriptor coordinates are not time observations, and no causal integration or
neuroscientific interpretation is inferred. Emit the whole subset-size curve.
Checks: identity correlation gives zero; block-correlated variables give positive
complexity; constant-image computation remains finite. Report cloned texture and
independent noise controls as diagnostics without using them to tune the score.

**#18 Three Trees proxy.** Visible leaf text nodes and visual leaves (img/svg/canvas),
not nested double-counted ancestors. Geometry = normalized box center. Style =
font size, weight, foreground RGB, background RGBA and categorical family one-hot;
standardize nonconstant columns within the page. Semantic partition = nearest
structural ancestor (section/article/nav/aside/header/footer/form/table), else the
element's parent. This is DOM containment, **not ground truth about meaning**.
Ward clustering for geometry/style with K=round(sqrt(N)), derived from node count.
Compare their two partitions and the DOM partition using arithmetic normalized MI
`2*MI/(H1+H2)`. Primary score = minimum of the three agreements. Single-group or
all-singleton semantic partitions are uninformative and produce missing, not a
perfect score. Also emit each raw MI and entropy. MC1 and B1 are targeted probes,
but human semantic truth about a connector is not guaranteed by its DOM ancestry.

**#1 Self-Teaching.** Split the normalized raster into top and bottom halves, dropping
only a possible unmatched final row so both strips have equal dimensions. On decoded
RGB strip bytes, score `[C(top)+C(bottom)-C(top||bottom)]/C(bottom)` using installed
zstd's default compression level, single thread, with back-reference window derived
as ceil(log2(total bytes)) so the compressor can reach the prefix. Store component
sizes. Separately report the same calculation on PNG-encoded strips as a diagnostic:
compressing already compressed PNG bytes is not the primary visual signal.
The HTML channel uses the captured leaf outerHTML in document order, split by
vertical midpoint of the historical image extent. Scripts/head/CSS are excluded;
there is no arbitrary byte-midpoint split through a stylesheet. Empty halves are
missing. Both channels are reported separately; #1 survives only if BOTH pass.
Additional kill: D1 must exceed B1 in each channel, per generation record #1.

### Wave 2

**#10 squint trajectory proxy.** Gaussian blur at 0 and dyadic pixel scales from 1
through half the region sampling width (32/2). For each level, pool gradient mass
into the fixed region grid, normalized to a probability distribution. Score = 1
minus mean Jensen-Shannon divergence between adjacent levels, normalized by log(2).
Uniform zero-gradient fields get a uniform distribution, explicitly a possible
blankness confound. No response-dependent scale selection.

**#23 emphasis transport proxy.** Spectral-residual saliency: FFT log amplitude minus
a 3 x 3 local mean, retain phase, inverse FFT, squared magnitude, Gaussian smooth
sigma=1. The local mean kernel follows Hou/Zhang's spectral-residual construction;
this implementation is a fixed proxy, not a claim to reproduce their benchmarks.
Pool saliency into the region grid. Target mass = visible text/image box area times
heading importance (1/heading level, body = 1/(number of HTML heading levels + 1)).
That importance rule is an experimental target, not a human meaning oracle.
Compute optimal transport exactly via linear programming between grid centroids,
cost = Euclidean distance / page diagonal. Score = 1 - transport cost. Requires
matched DOM availability and fails closed when either distribution is empty.

**#13 loom rank proxy.** Binary incidence of visible leaf boxes at rounded CSS-pixel
top/left coordinates, no cap on rows/elements. Effective rank = exp(entropy of
normalized singular values). Score = negative effective rank / sqrt(node count).
This tests low-dimensional layout organization, with simple/blank structure a known
confound; no claim that rank alone establishes intentionality.

**#14 size chord proxy.** Font-size ratios between all distinct text sizes, weighted
by their DOM frequency products. Roughness is absolute log2 distance to the nearest
positive rational p/q with p,q from 1 through 8 (fixed low-order harmonic vocabulary,
an experimental assumption). Score = negative weighted mean roughness. One unique
size has zero roughness, an explicit monotony confound. No fonts means missing.
Column-width and gap chords are outside this narrow operationalization.

**#27 pins-only bands.** For #17, raster #1, #10 independently, freeze a closed
interval from the min/max of the four pin scores. Banded score = negative distance
to that interval divided by its width. Zero-width pin intervals are incomplete.
Run the unchanged four gates, margin 0.01 in normalized interval-distance units.
No round or fixture value sets, expands or centers a band. This is calibration on
pins, so pin passage is not independent validation. Report endpoints and the
membership of both negative controls. No genre bands can be estimated from these
four specimens; do not fabricate them.

## Primary-source receipts

- [Tononi, Sporns, Edelman (1994)](https://pubmed.ncbi.nlm.nih.gov/8197179/):
  integration and segregation across subsets motivate #17, not a web-aesthetics theorem.
- [Barnett, Buckley, Bullock (2010)](https://arxiv.org/abs/1011.5334):
  Gaussian neural complexity and interpretation limits.
- [Meila, Comparing Clusterings (2005)](https://sites.stat.washington.edu/mmp/Papers/icml05-compare-axioms.pdf):
  partition comparison is mathematical agreement, not semantic correctness.
- [Zstandard manual](https://facebook.github.io/zstd/zstd_manual.html):
  lossless compression, prefix/window mechanics, default compression level.
- [Hou and Zhang (2007)](https://bcmi.sjtu.edu.cn/home/zhangliqing/Papers/2007CVPR_Houxiaodi_04270292.pdf):
  spectral-residual saliency, not aesthetic preference.
- [SciPy binomtest](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html):
  exact binomial test. The actual installed SciPy version is recorded in run receipts.

## Delivery and verification

`RESULTS.md`, complete specimen scores, each pair/gate, coverage, hashes, settings,
runtime versions, and checks. Reproduce through the research scripts, using
`agent-do browse` for capture/probes. Preserve originals and disclose failed paths.
Hash-check the protected DPT source tree, registry and `wild-hunt.md` before/after.
Copy the report/bundle to `.dev/`, iCloud Transfer and the report to Obsidian.
Log instructive kills in ZPC; positions only for survivors, with falsifiers.
