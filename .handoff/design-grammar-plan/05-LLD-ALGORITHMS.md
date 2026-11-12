# Low-level design: algorithms and execution

Status: proposed algorithms. Pseudocode defines future implementation behavior and has not
been installed as a runtime. Rule IDs refer to the [Rulebook](02-RULEBOOK.md).

## ALG-01: ingest, bind, validate and preserve

Input: a brief, content, assets, frames, rules and source records. Output: validated immutable
artifacts and a dependency manifest, or field-level typed errors.

1. Validate schema/version and reject unknown fields outside namespaced extensions.
2. Resolve artifact references inside the admitted project/evidence roots; verify hashes.
3. Check ID uniqueness, reference existence, units, numeric domains and graph invariants.
4. Classify every source: mathematical, standard, measured, author, proposed or experiment.
5. Preserve human words exactly. Store parsing/interpretation as separate attributed records.
6. Canonicalize generated JSON, hash it, write an immutable object, then atomically update
   the referencing pointer after checking its prior digest.

The source membership is conserved. There is no implicit dropping of difficult content,
unreadable references or disputed human labels. Missing data can prevent a specific
operation while unrelated records remain available with their correct status.

A migration reads an old version and creates a new artifact with `migrated_from` lineage.
It does not overwrite the old record or reinterpret its verdicts. A missing schema version
is not guessed from field resemblance. Imported numerical measurements retain original
units, precision and capture scope before any derived normalization is stored.

## ALG-02: observe a rendered composition

### Acquisition contract

Use the supported browser adapter, with explicit project/run/session and allowed URL binding.
For an owned generated bundle, serve through the package's loopback preview server or an
explicitly bound existing project server. The preview server exposes only the selected
artifact root, resolves paths beneath it, supports read requests, and reports its actual
origin. Its lifecycle belongs to the run. It is not an alternate browser or auth stack.

External reference capture takes an explicit target and capture plan. It does not fill or
submit live forms as a side effect of measuring a page. Navigation, scrolling and specifically
authorized menu/disclosure exploration are recorded. A capture plan cannot contain hidden
production transactions.

```text
observe(capture_plan, browser_binding, budget):
    validate binding, allowed actions, conditions, budgets
    record initial URL, viewport, browser/platform and asset manifest
    apply declared environment and state via supported browse operations
    collect readiness and consistency samples
    for each declared scroll region and band:
        move through supported browser evaluation or scroll capability
        wait according to the capture profile and remaining budget
        check fonts, media readiness, DOM and layout changes
        record sample_id, scroll, observations and viewport screenshot
        discover further extent within the declared finite scope
    take the requested full-page image as an additional artifact
    reconcile band coverage, loaded assets and state obligations
    emit capture, observations and explicit gaps
```

Scroll stride, settling interval, stable-sample count and deadline come from the capture
profile/run budget. A profile is an engineering procedure, not a proof of complete loading.
Stop only at its declared finite boundary or an explicit budget/capability failure. A page
that keeps expanding yields `coverage_incomplete` for the unobserved extent. An unchanged
document height does not prove that virtualized or scroll-triggered sections were observed.

`document.fonts.ready` and loaded face checks are readiness inputs. They are not sufficient
proof of the exact face used for every glyph. Generated font contracts carry intended files,
variants and declared language coverage; shaping/fallback uncertainties receive a named
visual or language review. Media readiness includes image completion, positive intrinsic
dimensions and decoding where supported, plus background/asset-manifest obligations.
See [CSS Font Loading](https://www.w3.org/TR/css-font-loading-3/).

Motion is either sampled at declared points, settled according to the state contract, or
frozen as an explicitly altered capture condition. Preserve that distinction. Never hide a
failed animation or unloaded section behind a clean static capture claim.

### Nodes and coordinates

Traverse admitted document roots and open shadow roots, and same-origin frames when the
adapter supports their coordinate chain. Record opaque roots separately. Collect DOM
semantics, computed values, element boxes and actual text-fragment boxes from ranges.
Record borders, padding, overflow, transforms, clip ancestry and stacking information.

Generated source IDs map observations directly to AST nodes and content. For external pages,
derive capture-scoped locators from the admitted DOM structure and record their stability.
Do not infer cross-capture identity from a mutable sibling index alone.

Viewport and document coordinates are related by the recorded scroll offset for the given
sample; sticky and fixed positions remain sample-dependent. Each observation contains a
`sample_id`. A node observed in several scroll samples has several records, not one overwritten
box. Comparisons require a common sample or a justified transform for position-stable nodes.
Browser box geometry follows [CSSOM View](https://www.w3.org/TR/cssom-view/); it is distinct
from the pixel shape and optical weight of the painted content.

### Relationships and empty space

Build parent/ancestry indexes and sorted interval indexes by axis. Query explicit program
relations first; then relevant neighbors, shared reference lines and semantic affiliations.
Exact predicates recheck candidates returned by the indexes. A brute-force predicate path
is retained for reference tests and small domains. Index and brute-force answers must agree.

For a requested region, clip admitted foreground rectangles to its bounds. Sweep sorted x
edges, maintain the union of y intervals per slab, and integrate union area. Complement
spans form a disjoint geometric clearance description; adjacent compatible spans may merge.
Do not call it the unique perceptually meaningful whitespace decomposition. Container
surfaces, shadows, glyph ink, and transparent media have separately recorded paint semantics.

Full pair queries can cost quadratic work. The query contract exposes the exact candidate
domain and completed count. If its work/byte budget is insufficient, return a continuation
and incomplete status. Never silently restrict the node domain to the first N elements.

## ALG-03: layout constructions and native lowering

### Bounded weighted partition

```text
partition(available, shares, minima, maxima, tolerance, budget):
    validate finite available >= 0, nonnegative minima, maxima >= minima
    validate equal array lengths, positive finite shares, tolerance and budget
    if no children: require declared empty/remainder behavior; return that result
    if sum(minima) > available: return scoped constraint_infeasible
    if all maxima finite and sum(maxima) < available:
        require declared alignment space or return constraint_infeasible
        return maxima plus explicitly allocated alignment remainder
    if available == sum(minima): return minima
    if all maxima finite and available == sum(maxima): return maxima
    g(lambda) = sum(clamp(lambda * shares[i], minima[i], maxima[i]))
    lo = 0; hi = 1
    while g(hi) < available:
        check budget and representable arithmetic; hi = 2 * hi
    repeat within budget:
        mid = lo + (hi - lo) / 2
        widths = clamp(mid * shares, minima, maxima)
        if abs(sum(widths) - available) <= tolerance:
            return widths with actual conservation residual
        if g(mid) < available: lo = mid
        else: hi = mid
        if no representable interior midpoint remains: stop search
    return search_incomplete with final bracket and residual
```

The function g is continuous and nondecreasing, so the feasible bracket has a root. Initial
bracket seeds 0 and 1 and the doubling factor 2 are algorithm constants, not design ratios.
Normalize shares by their maximum when necessary to avoid arithmetic overflow; this changes
lambda's units, not the allocation. Budget exhaustion or inadequate numeric precision is
`search_incomplete`, not a proof of infeasibility. Termination tolerance and iteration budget
have explicit authority. Never permanently clamp both lower and upper violators from the
same unconstrained guess without a correct active-set derivation. Tests compare conservation,
bounds, free-share proportionality and independent small enumerated cases. Unused remainder
is explicit alignment space. Browser rounding is checked separately after rendering.

Native Grid/Flexbox lowers the selected construction, including intrinsic minima, wrapping
and ordering. Calculated widths are placement intentions where browser intrinsic layout
participates; the render verifies the actual result. A browser discrepancy invalidates the
expected relation rather than being patched into the observation.
[CSS Grid](https://www.w3.org/TR/css-grid-2/) and
[Flexbox](https://www.w3.org/TR/css-flexbox-1/) supply browser layout semantics.

### Other operator procedures

- `flow`: preserve keyed order; use intrinsic sizing and the selected axis/gap/wrap behavior.
- `grid`: derive feasible count from actual minimums, gaps and item count. Apply exceptional
  spans through explicit relations. Zero items yield zero gaps and the declared empty state;
  one item yields zero inter-item gaps. Each row's content remains accounted for.
- `align`: prefer shared native grid/flex references; otherwise emit an owned offset. Baseline
  alignment lowers to native semantics and is measured only with supported baseline anchors.
- `clearance`: lower to logical insets/gaps or an inert reserved region with an observation ID.
- `repeat`: expand exactly once per admitted stable content key; preserve key-derived source IDs.
- `sequence`: evaluate the chosen recurrence in its domain and apply only to bound properties.
- `layer`: emit explicit stacking and clipping with a list of permitted overlaps and protected
  content/controls; verify the real hit-testing and visibility where relevant.
- `region` and `page`: own semantics, scope and surface; they do not impose a site theme.

Logical start/end and inline/block semantics are retained until lowering. LTR and RTL share
the same relational declarations where possible. A physical placement such as an illustration
anchored to the left is an explicit physical choice with a direction-aware alternative.

Responsive breakpoints are the roots/boundaries of selected feasibility conditions. Include
the boundary and neighboring representable CSS conditions in validation; also test the
profile's required endpoints and interior cases. Container size may be the relevant input,
as described by [CSS Containment](https://www.w3.org/TR/css-contain-3/). Unsupported container
features use a declared compiler capability choice, not a falsely equivalent silent fallback.

## ALG-04: contextual generation and expression

The host proposes an AST and frames from the brief, content graph and available operator
contracts. Its proposal must name task priorities, intended gathering/emphasis, material
roles, source assumptions and the alternatives considered. No reference-site name or pin ID
is admitted in a rule predicate, topology selector, parameter default or sampler key.

The frame library supplies techniques such as shared edges, isolated anchors, rhythmic
sequences, changes of field, dense repetition, optical counterweights and material continuity.
Each technique has a purpose, applicability, parameters, dependencies and counterexamples.
It contains no mandatory mappings from an industry, mood or archetype to a particular font
or palette. A subject-specific choice is a host interpretation recorded with its rationale.

Example frame dependency: changing a display font invalidates text measurement, wrapping,
headline extent, its containing partition, adjacent media placement and affected responsive
conditions. Changing a hero asset invalidates its intrinsic/focal constraints and any
attributed emphasis assessment. These dependencies are explicit edges, not buried prompt prose.

Candidate exploration varies declared decision dimensions: topology, lead channel, density
strategy, material treatment, typography treatment and state behavior. A budget and requested
candidate count come from the run manifest. Diversity is reported as changed decisions;
there is no novelty reward. The host can propose several incomparable feasible designs.

Deterministic sampling uses a versioned hash stream keyed by `(seed, stable_choice_id, counter)`.
For a uniform fraction, interpret the leading 53 bits of SHA-256 as an integer and divide by
`2^53`. The bit width derives from exact integer representation in the chosen number model.
Map into an explicitly declared finite choice or continuous domain. Sampling order is stable
under unrelated AST insertion because choices have stable IDs. Pin the sampling algorithm.
Repeatability of the host model's original proposal is a different, unpromised property.

## ALG-05: typography, color and asset coupling

### Text

Bind real content before computing fit. Resolve font assets and style declarations, then
measure the browser's actual fragments and overflow in the target container. Canvas text
metrics may guide proposals but do not replace multiline shaping, ligatures, fallback or
line-breaking observations. Re-measure when content, font, width, tracking, leading, locale,
direction or relevant browser conditions change.

Fit repair has a declared menu: adjust an allowed measure, change the composition, wrap or
reorder through an approved responsive construction, adjust tunable typography, or request
edited content. It cannot delete text, choose a smaller-than-permitted treatment, or make an
action inaccessible merely to achieve a target box. Measure and leading goals are contextual
parameters. Unsupported shaping/fallback facts remain unknown with a review obligation.

### Color and surfaces

Generated canonical colors use sRGB channels and explicit alpha. Optional OKLCH proposals
use the pinned standards-based conversion equations. The frame selects `reject_out_of_gamut`
or an explicit `clip_srgb` policy. Clipping records original and emitted values and requires
rechecking relationships; it is not claimed to preserve hue or appearance. A different gamut
mapping can be added as a versioned operator with tests.

Imported CSS preserves its original syntax and space. Browser-supported normalization or a
verified converter can produce resolved channels with a stated method. Unsupported input
produces `paint_unmeasurable`. No `lab()`/P3/gradient value becomes a guessed RGB value.
Quantized browser pixel readings are labeled quantized and never presented as exact source
colors. The generated emitter and imported observer have different assurance boundaries.

For simple stacked surfaces with established sRGB colors, compose alpha in paint order using
the chosen standards-defined space and record the result. Complex blend modes, filters,
gradients or text over media require supported paint analysis or manual review. The checker
cannot prove contrast over a changing image from a single average background sample.

Palette adjustment varies only tunable parameters, emits new colors, then recomputes the
affected foreground/background and state relationships. A text-contrast repair cannot
silently change a locked brand color; it may instead propose an allowed backing surface,
placement or typography change. Numeric contrast does not establish the aesthetic suitability
of the new palette.

### Media and detail

Use intrinsic dimensions and the contain/cover/focal formulas in the rulebook. A requested
crop derives from a content function and a protected subject region, where provided. Focal
annotations from a model retain their attribution. A replacement asset invalidates all such
annotations and the dependent layout/interpretation.

Borders, radii, marks and textures are coupled token families. A nested-radius construction
may use `inner_radius = max(0, outer_radius - inset)` for concentric corner geometry. It is
selected only when that geometric relationship is intended; no universal corner style is
imposed. Icons and illustrations require both asset readiness and contextual visual review.

## ALG-06: inspect without a beauty score

Compute the expected RuleApplications from the chosen program, standards profile, brief
requirements and condition matrix. Evaluate H/G/P applications with their admitted methods.
Emit J applications as attributed interpretations or requests for a capable reviewer.

Maintain separate lists: hard failures, selected-construction failures, unknowns, inapplicable
obligations, and judgments. Preserve all denominators. The report may rank an actionable
repair by declared severity and dependency reach; those rankings are operational priorities,
not taste measurements. DPT's report remains a linked annotation with source/version.

The visual review request includes the brief's purpose and content, rendered images,
relevant factual relations, protected requirements, and a fixed response schema. The critic
identifies a concrete observation, its task consequence, a proposed change, and evidence that
would challenge the interpretation. It does not output a binding numerical beauty verdict.
Conflicting interpretations can coexist until the author or delegated selector chooses.

Review should ask whether the composition expresses the brief, makes its content intelligible,
uses its materials convincingly, and retains a coherent character across pages and states.
The result is still attributed judgment. A rhetorical explanation cannot erase a failing
mechanical obligation or create a missing human preference event.

## ALG-07: conditions, behavior and release checks

Derive the required state/environment matrix from the program and brief. Transition paths
cover applicable controls, including recovery from error and return from overlays. Reachable
state inventory can be enumerated for generated finite machines. Explicitly distinguish
unreachable states, unvisited reachable states and states outside the configured domain.

Use supported browse input commands to exercise owned generated controls. Check semantic
names, source order, focus location, visibility, target relation, state changes and required
content/action reachability. Native control behavior is preferred; custom components must
provide their own APG-informed contracts and verification. Real backend effects require
their owning application's tests and are never manufactured by a fixture handler.

Resource readiness and render consistency precede layout assertions. Standards checks use
the profile's applicability and exceptions. Missing manual review remains a named obligation.
Automated inspection does not itself issue a blanket accessibility-conformance claim.

When a condition changes, compare invariant relations rather than requiring identical
coordinates. A compact navigation disclosure can preserve task access while changing its
topology. A product gallery can become a vertical sequence while preserving media and action
priority. Cross-state comparison checks the specified invariant, not pixel equality.

## ALG-08: dependency-aware revision

```text
revise(base, patch, brief, evidence, budget):
    require patch.base_digest == hash(base)
    validate target IDs, prior digests, field permissions and parameter domains
    apply the typed patch to a new immutable candidate
    check required content, actions and locked invariants
    compute affected dependency closure
    mark affected observations and results stale
    expand, compile and capture affected required conditions
    evaluate relevant applications and all protected completion obligations
    compare the new failure vectors and attributed design judgments
    keep the candidate, request another patch, or return a named conflict
```

Dependency kinds are value, layout, paint, state and interpretation. Value cycles in a
calculation are rejected unless owned by a specified solving operator. Layout/paint feedback
can form strongly connected components; recompute the complete component after a change.
It is never valid to reuse an unaffected-looking screenshot whose dependency hash changed.

Hard requirements remain constraints on any deliverable. Selected construction choices can
be replaced by a new valid program. The system does not silently weaken them while retaining
the old selection record. No accepted patch writes directly into the source corpus.

Detect oscillation using program/parameter digests and a revision transition ledger. If a
prior state repeats, return the cycle and the constraints driving it. Budget exhaustion
retains all candidates and requests; it is not an aesthetic rejection. Conflict reporting
uses a locally reduced incompatible constraint set where possible. Such a set is not called
globally minimal unless the minimization procedure was exhaustive.

Before committing a selected generated result into its owning application, replay the
required integration checks through the same emitter/adapter path. A manual CSS workaround
that bypasses the representation is not a valid verified revision.

## ALG-09: compile and preserve source ownership

Validate and expand the program, resolve frame/condition assignments, then lower each node
into semantic HTML, scoped CSS and registered state bindings. Escape all text and validate
URLs/asset roots. Arbitrary script/style strings from model output are rejected. Native
HTML semantics are the default; CSS does not fabricate headings or control behavior.

Emit stable `data-design-id` attributes where DOM nodes exist. The SourceMap links each
operator, content node, token assignment and conditional rule to emitted files/selectors.
Wrapper-free operations map to the actual parent property or native layout rule. Scope
classes avoid unrelated project CSS; the owning project adapter declares its cascade boundary.

CSS assignments resolve through explicit frame specificity and variant conditions. Conflicts
are diagnosed before emission where possible. Observed unexpected computed overrides produce
a source-mapping mismatch. An adapter importing a changed component must supply its new
mapping and test the original invariant rather than hiding the drift.

The compiler outputs a content/action coverage manifest and asset-use manifest. Build bytes
are deterministic for a pinned program, content, assets, ruleset, emitter and runtime. Browser
pixels additionally depend on browser/OS/fonts/device conditions and are compared only with
that provenance. DOM semantic behavior and tolerance-bounded geometry support cross-platform
verification where pixel equality is inappropriate.

## ALG-10: budgets, progress, continuation and export

Required budgets are supplied by the run or resolved through an authority source. They cover
candidate count, revision count, deadline, model context/delivery, browser actions, query
work and artifact bytes where applicable. `none` is an explicit absence of a governing cap,
not an implicit hardcoded fallback. Model ceilings resolve from the current host capability
or agent-do quantity authority and retain that source version.

Before an operation, validate its prerequisites and budget. During work emit progress events
with completed and remaining obligations and exact counts available so far. A count of an
unbounded external domain is unknown, not estimated as an exact total. Chunked artifacts and
relation queries include a continuation tied to the domain digest and deterministic order.

On interruption, preserve the last completed immutable step and the incomplete attempt.
Resumption verifies project binding, digests, schema versions and available capabilities;
then continues from the next unmet obligation. It does not rerun completed expensive steps
unless a dependency changed.

Export collects the selected program, brief, required content/assets, source map, compiled
bundle, captures, review and verification records. Reference-only assets are excluded from
the product bundle and remain clearly identified in research evidence if included there.
Verify every copied digest and relative link. Export does not publish or deploy the site.

## ALG-11: evaluation accounting

Freeze the evaluation manifest before generating evaluation outputs. Separate calibration
from withheld retrieval groups and new briefs. Track model/version and any known exposure.
Already familiar public sites are not called training-unseen merely because their files
were omitted from a prompt.

Generate baseline and instrument runs under matched declared conditions. Preserve failures,
unjudged outputs and ties in the ledger. Randomize presentation labels and positions without
changing the artifacts. Ingest actual human feedback and keep its scope. Count wins, losses,
ties, conditional verdicts, failures and missing judgments separately.

Report task/register/condition breakdowns before any pooled summary. Use paired preference
analysis only on the explicitly defined eligible pairs, with denominators and exclusion
reasons. Study size and any effectiveness threshold derive from a stated decision/precision
target and available evaluation budget in the manifest. No significance threshold is tuned
after seeing the outcome. Mechanical build acceptance and evidence of aesthetic benefit
remain different claims. Full protocol: [Evaluation](07-EVALUATION-AND-GENERALIZATION.md).

## Complexity and performance acceptance

Expansion and basic validation scale with the generated AST, content and edge counts.
Sorting-based indexes add logarithmic factors; full pair output has quadratic cardinality
by definition. Clearance sweeps and browser sampling expose their actual work and byte totals.
Budgets bound expensive operations with continuations or explicit partial status.

Benchmark a content-derived small/medium/large corpus profile at implementation time, record
hardware/browser conditions and freeze release budgets from those measured requirements.
Do not add arbitrary node caps to make the benchmark pass. The release must identify the
largest admitted tested domain and its behavior when budget is insufficient.
