# Development evidence and learning the beauty model

## 1. Read the measurements independently of the admission labels

The original screen asked whether each particular scalar implementation could clear every
registered gate on a very small, heterogeneous corpus. Aphrodite asks which measured
relationships help predict and construct beauty, and how their interactions can improve.
The historic files remain unchanged. This is a new interpretation and development program.

The exact extracted values and comparison identities are in
[HISTORICAL-EVIDENCE.json](HISTORICAL-EVIDENCE.json). The source is
`tools/agent-dpt/research/wildhunt-verify/scores.json`, with its hash recorded there.

| Measurement | Observed result | Development use |
| --- | --- | --- |
| Three Trees | 8/10 preference pairs; 5/5 predeclared nonconditional comparisons; both Null traps pass | Strongest measured starting clue for APH-01. Repair the semantic representation and typed cross-channel correspondence. Preserve its two Library 3 misses as development cases. |
| Three Trees fixture order | Both canons above both negative fixtures; smallest gap 0.0017967146, below the registered 0.05 margin | Positive ordering and weak separation coexist. Learn where the relation is informative; do not describe this as reversed ordering. |
| Three Trees pin coverage | Historic pin DOMs unavailable, hence the pin gate incomplete | Missing measurement is not evidence of aesthetic incompatibility. Obtain matched evidence in future work; do not substitute modern DOMs into old images. |
| Size chord | 6/10 pairs, 1/5 nonconditional; one Null trap fails | Shared proportions are an ingredient to test in APH-03, not a proven sufficient ordering. Condition on semantic roles and couple channels. |
| Raster self-teaching | 6/10 pairs, 2/5 nonconditional; broken fixture outranks both canons | Reuse/compression alone does not identify coherent beauty. Measure purposeful recurrence and distinct roles, not just compressibility. |
| HTML self-teaching | 5/10 pairs, 1/5 nonconditional; both Null traps fail | Code representation can disagree with appearance. It is not an aesthetic source of truth. |
| Raw squint | 2/10 pairs; all four fixture orderings positive but below the 0.01 margin | Useful coarse-structure observations need a better contextual objective. A single slope loses configuration detail. |
| Banded squint | Fixtures, Null traps and four available pins pass; only 1/10 strict pair wins, many ties | A flat admissible band erases useful ordering. Prefer smooth contextual affinities and keep actual joint comparisons. |
| TSE feature covariance | 2/10 pairs; white image 2.406769, above both canons | Replace the image-to-random-variable mapping. Do not call descriptor covariance the functional integration of a design. APH-02 uses explicit role unity and distinction. |
| Emphasis transport | 1/10 pairs; task importance proxied by area/headings | Better semantics and perceptual inputs are needed before transport can express desired hierarchy. Transport math alone does not supply the correct target. |
| Loom rank | 3/10 pairs; both Null traps fail | Low dimensionality of a coarse layout descriptor is insufficient. Shared parameters must correspond to actual roles and visual relationships. |
| Other bands | Banded TSE 2/10; banded raster self-teaching 4/10 | Wrapping a weak feature in a pins-fitted interval does not resolve its mapping or missing interactions. |

The pairs span four feedback groups and reuse preferred specimens. They are not ten independent
randomized trials, and the nonconditional subset is a smaller disclosed subset, not a substitute
denominator chosen to claim victory. These facts limit inference; they do not erase the signal
worth developing.

For the first step of the original eleven-test Holm family, 8/10 gives raw p=0.0546875 and
adjusted p=0.6015625; 9/10 gives 0.0107421875 and 0.1181640625; 10/10 gives 0.0009765625 and
0.0107421875. Thus even 9/10 would not clear that first family threshold. The screen was
not logically impossible for every measure, but it demanded near-perfect ranking for this
sample and asked DOM measures to clear unavailable evidence. It was unsuitable as a blanket
decision to stop developing mathematical beauty.

## 2. What changes now

Historical failures become localized counterexamples: a mapping to repair, a relation that
needs conditioning, a deceptive control, an inappropriate scalar reduction, or missing
evidence. A new model is allowed to use old outcomes for development. It cannot then call
those same outcomes independent proof of the new model.

We will not salvage every formula indiscriminately. The white-image covariance result is a
real mapping problem, not merely a harsh p-value. Three Trees' two misses are real misses.
The correction is to use all of this evidence productively, including the parts that resist
the current theory, rather than treating the old binary label as a final theorem.

The twenty untested named candidates remain possible sources of feature/construction ideas.
They are not required dependencies for the first kernel. Phase congruency, second-order
deviations, voice-leading, whitespace connectivity and dimensionless groups fit specific
new feature families. Ricci curvature, sheaf cohomology, persistent homology and assembly
indices need a precise meaningful mapping before their mathematical names earn a place in
the runtime. The raw hunt remains an idea register, not an already measured law book.

## 3. The minimum learning representation

Keep the first model small and interpretable. Do not train a large graph neural network from
twelve site approvals and a handful of reused comparisons. Use the explicit APH features and
their interaction terms, with regularized coefficients. Initial kernel targets can be
mathematical constructions or declared design hypotheses; fitted targets need actual evidence.

Each feature parameter is one of:

- **Derived:** coordinate normalization, ratio identities, an exact shared-parameter relation.
- **Proposed:** a testable affinity shape, contextual mode, tolerance or coefficient prior.
- **Estimated:** a parameter fitted on a named development partition with its procedure.

Proposed is a legitimate state for a new beauty hypothesis. It must be implemented and
tested, not used as an excuse to leave the beauty seat empty. It is also not relabeled as
human-discovered truth merely because the kernel always rewards its own definition.

Context conditioning starts with explicit semantic relation types and measured role descriptors.
The model may include shared and contextual coefficients with shrinkage toward the shared
ones. It must not use pin IDs, business names, page URLs or a six-register lookup to memorize
the training examples. Supported context distinctions describe actual design obligations,
such as comparison versus narrative or an image's role, rather than the reference identity.

## 4. Pairwise learning objective

For development comparisons a preferred to b under context c:

```text
delta = B_theta(a|c) - B_theta(b|c)
P_theta(a preferred to b | c) = sigmoid(delta)
L(theta) = weighted_mean(log(1 + exp(-delta)))
           + lambda * ||theta - theta_prior||^2
```

Use stable softplus arithmetic. Weight comparison groups so one repeatedly compared winner
does not dominate merely because it appears in more rows. The group-weighting rule and
regularization selection are written before the new fit. Conditional verdicts retain their
conditions; incompatible conditions do not create an unconditional pair.

Constrain affinity coefficients to be nonnegative and conflict penalty magnitudes to be
nonnegative. Zero is allowed and informative. Revise a failed feature definition explicitly
instead of silently inverting the meaning of a named beauty law through a negative weight.

Ties require a declared ordinal/tie likelihood or a separately reported tie analysis. Silence
is not a tie or rejection. “Neither is good” is an absolute appraisal alongside the relative
choice. Do not invent decimal preference targets from qualitative remarks.

With very little independent information, estimate fewer coefficients or freeze some at
documented priors. Report the rank and conditioning of the actual feature-difference matrix.
There is no valid rule that every proposed parameter becomes statistically identified just
because an optimizer returns a vector. Keep the support diagnostic attached to the model.

Prefer normalized feature scales whose values have meaning. Fit one normalization on the
development data and retain it. Do not normalize separately on each candidate pair, which
could manufacture a favorable difference or erase cross-comparison interpretation.

## 5. Learning ingredients and joint effects

Whole-site approvals tell us that those particular complete configurations are acceptable.
They do not tell us that every detail is optimal or that every random recombination of their
parts is good. Extract actual relational descriptors from matched observation, then propose
families that could generate those relationships without copying their concrete pages.

Use three complementary development sources:

1. **Existing preferences:** initial directional evidence and known traps.
2. **Controlled reconstructions and rewrites:** same content/assets with specific relational
   changes. These supply interventions, not automatic disliked labels.
3. **New original briefs:** the main measure of whether the instrument creates beauty outside
   its examples. Freeze a model before each judged development batch.

Interventions distinguish a poor feature from a poor mapping. For example, repair Three Trees
with a semantic relation graph; compare that repair with the old DOM-partition proxy on the
same observed material, then compare generated outputs from both objectives. A relationship
that helps generation can be valuable even if it never perfectly orders every historic pin.

For emergent beauty, compare the full model against an additive parts model and a pair-only
model with matched inputs and work budgets. The higher-order terms must contribute a useful
predictive or generative improvement. A positive coefficient or a nonzero derivative is
mathematical interaction, not by itself human-validated synergy.

## 6. Calibration for construction

Learn or explicitly choose the supported high-affinity region of each joint family. Keep
separate modes when the data show different viable relationships. Smooth kernels preserve
rank information within modes; unlike the prior flat bands, they do not assign every point
inside a broad interval the same value.

Calibrate emission threshold tau for a declared model/context domain using actual outcomes.
Track both acceptance and coverage: always refusing to emit can produce no ugly outputs
while producing no useful instrument. A narrow safe-looking support region that yields
near-identical sites also misses the product objective.

The first uncalibrated implementation is a beauty hypothesis demonstrator. It still generates
and ranks with B, rather than delegating the score to a critic. A production claim requires
the observed quality, breadth and failure behavior promised by its launch profile. No rate
or success percentage is invented in this planning document.

## 7. Evaluation that develops rather than destroys the program

Use the historical material openly for development. Reserve genuinely new briefs and outputs
for prospective checks. A reference-site retrieval holdout tests dependence on supplied
references; it does not erase a general model's prior exposure to a famous site.

Track, separately: useful absolute appraisals, relative preference, difference from additive
and pair-only models, required task access, supported expressive range, unsuccessful attempts,
refusals and generation cost. Failure diagnoses the specific kernel/constructor/context. The
whole project is not rejected because every metric does not simultaneously win every test.

Hard corruption remains hard corruption: wrong labels, inaccessible required actions, a score
derived from unobserved paint, changed targets after optimization, or a leaked reference asset
must be fixed. This protects the signal without turning a promising 8/10 into “nothing here”.

Formal statistical claims, if later requested, need a sufficiently informative prospective
design and declared analysis. Development selection can proceed from meaningful controlled
improvements while reporting its small sample honestly. No requirement for p<0.05 on every
tiny iteration is part of Aphrodite.

## 8. Human and model roles

Erik's verdicts supply the intended appreciation signal. A trained, versioned mathematical
beauty model uses those signals to select new designs without requiring him to approve every
generation. This is the transfer of taste the product is meant to achieve.

The host AI may describe content, supply hypotheses, suggest graph changes and explain
evidence. Its free-form “this is beautiful” is not a ground-truth label or a hidden selection
override. A learned perceptual adapter is allowed only as a named, versioned model component
tested against the same human signal; calling it mathematical does not exempt it from the
Round-2 trap.

## 9. The two reviews and this correction

The user-supplied review and the subsequent cold review of the old plan agree on the central
failure: it omitted the requested beauty model. The cold review arrived during this work and
was read at `.handoff/design-grammar-plan/REVIEW-2026-09-14.md`. It reviews the old package,
not the Aphrodite specification, and is not represented as validation of this replacement.

| Review finding | Correction here |
| --- | --- |
| The plan preserves source files but does not learn from their measured content | This chapter names candidate outcomes, counterexamples, pair/group denominators and the small-sample threshold behavior |
| The grammar is largely a schema awaiting an LLM's design | GR-01 through GR-09 define production expansion, bounded derivations and material/reflow construction |
| Random parameter changes do not overcome the prior's repeated layouts | Structural alternatives are generated; a beauty-constrained archive distance governs requested variation |
| The AI critic can still choose what ships | The saved kernel selects; critic observations propose future hypotheses only |
| “Human” obscures whose taste is being transferred | Erik is the ratifier for this target; other populations remain separate |
| The Null traps and established rounds workflow disappear | Both are explicit development comparisons in AP-WP-04 and AP-T14 |
| Internal symbolic language can become preaching in the page | Typed content/interpretation separation and the brief's enforceable copy contract block that route |

The review recommends preserving the old ban on beauty aggregation and requiring every new
candidate to survive the old four-gate screen. Those recommendations conflict with the user's
current direction and are not adopted. Its suggestion to remove the esoteric ambition is
also not adopted: relationships and meaning remain central; internal theory stays out of
the product's public copy. The engineering criticisms sharpen the new design without restoring
the product objective the user just rejected.
