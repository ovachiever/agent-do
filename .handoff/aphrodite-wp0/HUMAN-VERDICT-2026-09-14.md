# Aphrodite WP-0: Erik's spacing and typography verdict

Date: 2026-09-14, America/Chicago. Field check: **mn-03e95e**.
Experiment: **mn-75f010**, frozen candidate **aphrodite-wp0-v1**.

**Erik chooses A overall, A over D with the large headline, and C over B with
the small headline. The frozen spacing formula predicts the opposite gap choices.**
The original C/D question remains unanswered; the first original comparison
already contradicts the strict predeclared prediction.

## Human evidence

Erik's exact message:

> A is the best, if bigger headline, the smaller gap wins; if smaller headline, the bigger gaps wins, which is C

This is one respondent and one brief. Repeated messages expressing this same
judgment are one response, not additional observations. The response date is
known; an exact message timestamp was not supplied.

| Variant | Headline | Gap | Frozen F03 affinity | Human evidence |
|---|---:|---:|---:|---|
| A | 96px | 24px | 0.411112 | Best overall; preferred to D |
| B | 48px | 24px | 1.000000 | C is preferred to B |
| C | 48px | 48px | 0.411112 | Preferred small-headline combination |
| D | 96px | 48px | 1.000000 | A is preferred to D |

F03 values are affinities from the proposed equation, not measured beauty.
The global-best statement entails A over B and A over C as well. C versus D
is not established by the conditional gap statement. No complete ranking is invented.

## What the frozen prediction says

The proposed target was `gap = 0.5 * headline_size`, with an 18px body size:

`F03 = exp(-0.5 * ((gap - 0.5 * headline_size) / 18)^2)`.

It therefore favors D over A at 96px and B over C at 48px. Erik explicitly
prefers the opposite in both cases. The combined whole-page B score also orders
both of these conditional pairs incorrectly.

The predeclared primary comparisons were **A/B** and **C/D**, varying headline
size at each fixed gap. Their predicted winners were **B** and **D**. The first
is contradicted by "A is the best." The second is unreported. Because the
protocol required both predictions to hold, its strict prediction has failed;
an unanswered comparison is not being counted as a failure.

The response additionally compares **A/D** and **C/B**, varying the gap at each
fixed headline size. This useful analysis follows the response's framing. It is
reported separately, not relabeled as successful completion of the original
two-question collection or as a preregistered positive result.

## What this teaches about relationships

At 96px the response implies `U(96,24) > U(96,48)`; at 48px it implies
`U(48,24) < U(48,48)`. An independent score `U(h,g) = a(h) + b(g)` cannot
express both strict preferences: its difference between gaps is always
`b(24) - b(48)`, regardless of headline size. A strictly increasing transform
does not change that ordering. This is a logical property of the stated
preferences, not a statistical significance claim.

The assistant's interpretation is **compensation**: larger type and tighter
space form one preferred arrangement; smaller type and wider space form another.
That suggests choosing an element's setting in relation to the composition.
It does not identify a universal inverse equation or a conserved visual quantity.

The judgment concerns a full page. Changing the headline also changes its text
height and downstream placement relative to the artwork and other content.
Optical mass, grouping, and overall balance are possible explanations, not
isolated causes established by this experiment. One brief cannot determine
which mechanism transfers to other fonts, content, geometries, or registers.

The whole-page candidate remains failed. Its failure and this local interaction
can both be true. No fitting, replacement kernel, generator, or further study
was performed or commissioned by this response.

## Governing direction supplied after the verdict

Erik's next message:

> sweet, just remembrer to generalize everything into relationships, maths, rules, manifestations of perspectives and never absolutes, never "fix the problem directly" everything needs to be looked at sideways and addressed that way

This is a design-method instruction, not an additional preference label or
an answer to C/D. Its operational meaning for Aphrodite is:

1. Represent the interacting nodes, their relations, and their compositional context.
2. Name the perspective through which those relations are being interpreted.
3. Express a conditional mathematical relation or transformation, with its domain
   and predicted consequences when another part changes.
4. Address a visible symptom by revising the relationship producing it. Preserve
   the resulting insight as a transferable rule instead of a specimen-specific value.
5. Check that the relation predicts fresh compositions before treating it as
   supported. Each perspective has conditions and limits; no taste rule is absolute.

For this result, the useful question is how typographic presence and spatial
separation jointly organize the composition. "Set A's gap to 24px" would merely
restate the specimen. A rule describing that interaction would need to predict
what happens under new type, content, scale, and surrounding geometry. Those
predictions remain future work; no universal compensation formula is established.

## Record and verification

The companion `HUMAN-VERDICT-2026-09-14.json` preserves the exact quote, explicit
conditional comparisons, the global-best implication, the unanswered original
comparison, frozen numerical predictions, and SHA-256 evidence references.

The original choice sheets remain empty as delivered before the response. This
addendum records the later judgment without rewriting the frozen model, protocol,
predictions, screenshots, raw scores, or either freeze. All **493** original
iCloud bundle files match their original manifest. The source/input freeze
verification passes. This is a data and documentation update; implementation
tests and production suites were not rerun.

The report and structured record are also delivered to the existing iCloud
bundle as new files with a separate addendum manifest. The substantive note is
saved in the Obsidian vault. The original delivered report remains a record
of the pre-response state.
