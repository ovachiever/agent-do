# Aphrodite WP-0: measured result

**The bounded experiment is built. Candidate aphrodite-wp0-v1 failed its readiness
checks. Do not build the full generator around this scorer.** Its numerical targets
were not changed after the result. The four-page conditional comparison is ready;
human preference remains pending in **mn-03e95e**.

Build item: **mn-75f010**. Date: 2026-09-14. Predecessor: mn-eafd32.
This report concerns one executable candidate, not the possibility of relational
beauty in general. The original wild-hunt measurements and conclusions are preserved.

## What was actually built

Four narrow feature instances now run on actual observed rectangles, type sizes,
font weights, font-family strings and foreground colors:

| Feature | Executable relationship |
|---|---|
| F01 | Repeated-role treatment plus local grouping |
| F02 | Repeated identity multiplied by role differentiation |
| F03 | Spacing relative to type size: proposed gap = half the dominant font size |
| F08 | Three-node conjunction of spacing/type fit, role differentiation and repeated support treatment |

The combined B averages these four. A product ablation replaces F02's and F08's
products with averages while preserving the rest. Both are hypotheses about fit;
neither is an established beauty scale. The code is in
[aphrodite-wp0](../../tools/agent-dpt/research/aphrodite-wp0/README.md).

There are eleven proposed kernel constants and four fixed weights, with no fitting
or numerical search. The semantic ontology, class lists, pattern matching, edge
selection, averaging and inapplicability rules are additional modeling choices.
Every one is published in [model.json](../../tools/agent-dpt/research/aphrodite-wp0/model.json).
This ledger does not pretend that only learned coefficients count as freedom.

**The graph-authoring qualification matters.** The inputs are deterministic,
agent-authored inferences from tags, classes, text, DOM containment and DOM order.
They are not hand-authored human semantic graphs. There are no model calls in the
evaluator, but the authored binding logic is still an interpretive input. All
graphs are exported; a fixed alternative removes cross-container fallback.
This therefore tests one fully specified approximation to the plan, not the
complete semantics, materials or meaning families.

## Evidence and denominators

The evaluator processed all **64** saved DOM observations. The ten fixed preference
pairs contain **14 unique designs**, four feedback groups, and five conditional
pairs. Adding the two five-page trap sets and four fixtures produces a union of
**25**, not 24 paired specimens plus controls. The other 39 observations remain
descriptive, with no invented negative labels.

The historical outcomes were already known when the targets were proposed. The
freeze precedes this implementation's first numerical scoring, but it does not
turn familiar historical data into an unseen test set. All targets, source inputs,
graphs and executable code were hashed before scoring.

## The four diagnostics

### 1. Fixture separation failed

Higher numbers mean greater affinity to this candidate's own relationships.
They are not human ratings. The fixture names "canon" identify a historically
liked direction, not an independently ratified universal standard.

| Measure | Today | Dossier | Barf | Broken | min(liked) − max(controls) |
|---|---:|---:|---:|---:|---:|
| F01 | 0.753336 | 0.526278 | 0.830820 | 0.855091 | −0.328813 |
| F02 | 0.685413 | 0.712430 | 0.518760 | 0.770482 | −0.085069 |
| F03 | 0.556295 | 0.145119 | 0.755540 | 0.882497 | −0.737378 |
| F08 | 0.313076 | 0.082439 | 0.287195 | 0.554213 | −0.471774 |
| **Combined B** | **0.577030** | **0.366566** | **0.598079** | **0.765571** | **−0.399004** |
| Product ablation | 0.709023 | 0.543961 | 0.742555 | 0.860814 | −0.316853 |

Both barf and broken exceed both liked fixtures on combined B. Every feature fails
the full fixture-separation diagnostic. The frozen stop clause fires, without a
significance test or an argument about marginal separation.

One review detail was factually wrong for these observations: the saved barf probe
contains a 32px h1 and 28px values, alongside 18px branding and other sizes. It is
not an 18/16 two-size page. Correcting that detail does not rescue the candidate.

### 2. Eight of ten fixed pairs, including both old paneldock misses

| Preferred specimen | Rejected specimen | Conditional? | B difference |
|---|---|---|---:|
| concept2/library-B | concept2/library-D | No | +0.145448 |
| concept2/library-B | concept2/library-A | No | +0.025160 |
| lib3/paneldock | lib3/market | Yes | +0.021039 |
| lib3/paneldock | lib3/deltas | Yes | +0.095578 |
| lib3/paneldock | lib3/statled | Yes | +0.231817 |
| lib3/paneldock | lib3/quiet | Yes | +0.288995 |
| eng3/oneline | eng3/ledgerfirst | No | −0.110433 |
| eng3/timetable2 | eng3/ledgerfirst | No | +0.023701 |
| eng6/M1 | eng6/MC1 | No | −0.074450 |
| eng6/D1 | eng6/MC1 | Yes | +0.056022 |

That is **3/5 unconditional** and **5/5 conditional**. By feedback group: concept2
2/2, lib3 4/4, eng3 1/2, eng6 1/2. Four wins share paneldock as their preferred
specimen. There is no claim of ten independent trials, statistical superiority,
or generalization. F01 gets 8/10, F02 5/10, F03 7/10, F08 7/10.

The two old Three Trees misses are recovered, but the new model loses two other
pairs and the controls. That is a changed pattern of errors, not an overall repair.

### 3. One Null trap passed, one failed

| Surface | Null B | Other variants' median | Difference |
|---|---:|---:|---:|
| Library | 0.548925 | 0.516294 | +0.032631 |
| Engine Room | 0.455734 | 0.703579 | **−0.247845** |

The Engine Room stop clause fires. These are the same historical trap identities,
with no relabeling of conceits as new human negatives.

### 4. Multiplication changed one ordering

Combined B gets 8/10; the product ablation gets 7/10. Only library-B versus
library-A changes sign. This establishes an effect of the algebra on these rows,
not a useful interaction law. The ablation still contains F03, which is itself a
relationship feature. It is not a pure independent-ingredient baseline.

## What the failures expose

The broken fixture has **57 retained nodes but only one dominant/support edge**.
That one relationship fits the proposed spacing and size targets. Repeated small
links also earn consistency credit. Its high score therefore describes a few
selected relations while missing much of the bad composition. Numeric eligibility
was too weak to establish substantive coverage.

The dossier has eight such edges, five obtained through fallback. Several pair a
value with the next label rather than its own preceding label. Its main prose is
also incompletely observed: the historic probe drops text blocks containing child
elements while retaining citation fragments. One heading is paired with a later
table cell more than 272 CSS pixels away. These are visible graph-binding errors,
not discoveries about the aesthetic value of dossier geometry.

This does not excuse the result. Those bindings are part of this frozen candidate.
The prespecified `local_only` sensitivity removes all **209** fallback edges across
the 64 observations. It still scores every observation, preserves all ten pair
orderings, and fails fixture separation (−0.377380) and the Engine Room trap
(−0.251876). Removing fallback alone does not fix the model.

The missing material, image, semantic and coverage terms are substantive omissions.
A blank input is correctly inapplicable, but a three-node page with a heading and
two repeated paragraphs can score. The tests document that limitation; they do not
claim that the blank-page trap has solved content poverty.

## The controlled comparison

Open [the neutral comparison](../../.dev/aphrodite-wp0/run-02/comparison/index.html)
before reading this section if you intend to give an unprimed preference.
The four original pages keep the workshop content, family, color, illustration,
width and other components fixed. Only heading size and the following gap vary.
They are experimental stimuli, not outputs certified beautiful by this model.

The browser measured all four declared interventions exactly:

| Variant | Heading | Gap | Measured F03 pair affinity | Whole-page B |
|---|---:|---:|---:|---:|
| A | 96px | 24px | 0.411112 | 0.407929 |
| B | 48px | 24px | 1.000000 | 0.650298 |
| C | 48px | 48px | 0.411112 | 0.462579 |
| D | 96px | 48px | 1.000000 | 0.464898 |

The F03 prediction, recorded before rendering or a human response, is B over A
and D over C. Whole-page B happens to agree, but D beats C there by only 0.002319.
Adding other proposed affinities nearly erases the local relationship's contrast.
All four retain required copy and have no horizontal overflow at 1440×1000.
Visual inspection found no obvious clipping or overlap. No human verdict is inferred.

The mathematical claim is narrow and testable: an independent utility
`a(size)+b(space)` cannot reverse its size preference when space changes. Neither
can a strictly increasing transform of it, or a product of separate positive size
and space utilities. A joint spacing/type residual can. The code demonstrates that
property on measured geometry. It does **not** demonstrate that a person prefers
the predicted fit.

Human verdict: **pending**. A tie or either contrary choice fails the strict
crossover prediction for this brief. Agreement would support one relationship in
one context, with no powered population or general beauty claim. A human may also
prefer one size in both contexts. That is a valid disconfirmation, not a bad rating.
Field check **mn-03e95e** preserves the exact response when one arrives.

## New observations of the twelve pinned sites

All twelve public sites were captured through isolated `agent-do browse`, with
the DOM and screenshot taken from the same page state after scroll priming.
All reached the observed DOM bottom within the forty-step bound. That fact does
not establish visual completeness or renew the original human approval.

| Pin | New B | Evidence qualification |
|---|---:|---|
| Recognition Oracle | 0.549780 | New observation; no unloaded image elements reported |
| Every | 0.650029 | Page loaded this time, 298 observed nodes |
| Pangram | 0.505620 | 9 image elements reported incomplete or zero natural width |
| Pete's Pasta | 0.636386 | 19 such image elements |
| Sneak | 0.675175 | No unloaded image elements reported |
| Teenage Engineering | Inapplicable | Product sections visible; no sufficient text-role constellations; 4 image elements flagged |
| Attio | 0.494482 | 29 image elements flagged |
| Daylight | 0.613999 | **Still mostly blank through the middle; partial evidence only** |
| Tally | 0.745211 | 1 image element flagged |
| Things | 0.713416 | No unloaded image elements reported |
| Kagi | 0.724984 | No unloaded image elements reported |
| Readwise | 0.617380 | 6 image elements flagged |

An incomplete/zero-width image can be hidden or unused, so these counts do not
measure visible missing images. The visual audit confirms that Teenage Engineering's
product sections are now visible. Daylight remains partial even after priming.
No claim of complete visual coverage is made for the other ten without a full audit.

Eleven pages yield numbers; **none exceeds the broken fixture** under B. That is a
further warning about the scorer, not a formal pin gate: these new states have no
new human labels, and the historical screenshots still have no matching historical
DOM. Do not convert capture success into aesthetic evidence.

## Validation, correction and preservation

Nine focused tests pass: scale/translation invariance, conditional reversal,
increasing-transform invariance of that reversal, empty and minimal inputs,
invalid measurements, label exclusion, typed relations across containers,
inapplicability under the strict binding, changed-input rejection and denominator
preservation (some tests cover more than one property). All Python files compile.
The four browser captures satisfy their geometry/copy contracts.

The first capture attempt exposed one CSS f-string syntax error before browser
launch. [Amendment 001](AMENDMENT-001.md) preserves the original freeze and records
the corrected capture implementation. The complete historical rerun produced
byte-identical raw scores:
`74429877045a1f5812bcce0d87d2115c007ae82e1dba44e2fc9302290790089d`.
There was no target revision, re-ranking adjustment or discarded numerical run.

All **59 protected historical inputs** from the preceding plan remain unchanged.
The current freeze additionally hashes all twelve original pin records and the
cold review. Production DPT, registry, dependencies and the old research code were
not modified. The root integration suite was not run because no production path
changed; the focused research checks and live browser observations are the applicable
validation. Repository-wide Manna lint remains non-clean, with existing board drift
and generated handoff-presentation notices reported separately in the delivery receipt.

## Decision and next boundary

**Stop this candidate's path to the engine.** The scoped WP-0 deliverables are
complete. No automatic successor, wider law catalog or learned fitting is authorized
by this result.

Needed next for the already prepared relationship experiment: the two explicit
human choices in mn-03e95e. They cannot validate the failed whole-page scorer.

Any successor would first need trustworthy content-role coverage and relations
that respect label/value order, then independent evidence for its aesthetic targets.
That is a separate research decision. Simply adding terms, coefficients or more
approved sites would leave the demonstrated failure unresolved.

**TL;DR (12th grade):** The formulas now run, and this first version fails: it likes
the ugly controls too much, even though it gets eight historical comparisons right.
We preserved that result, improved the reference captures, and prepared four pages
to test one precise claim about spacing and type. Your two choices can test that
claim; they cannot turn this failed scorer into a reliable design engine.
