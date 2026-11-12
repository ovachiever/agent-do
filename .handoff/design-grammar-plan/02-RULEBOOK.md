# Rulebook and generative formulas

Status: proposed first-release catalog. These are construction, observation and evaluation
rules. They are not seventy-one discovered laws of beauty. The catalog count is derived from
the uniquely identified entries below and verified in the planning receipt.

## 1. Rule authority and execution

Every rule has a stable ID and version. Its application binds subject IDs, a condition,
parameter references and evidence. A rule has one of four classes:

- **H:** a structural, functional or selected standards obligation. Its authority is explicit.
- **G:** a generative construction. Its postconditions bind when the operator/frame is selected.
- **J:** a contextual judgment. It produces an attributed interpretation or review request.
- **P:** an evidence and process invariant. It protects the meaning of the other results.

Rules return `pass`, `fail`, `unknown`, or `not_applicable`, each with a scope. An unknown
precondition produces `unknown`; it cannot produce `not_applicable`. A G rule can be omitted
by choosing another valid construction. Once selected, its own declared postconditions must
hold. An H or P failure cannot be compensated by an attractive result elsewhere.

Every catalog entry below defines its applicability and required behavior. The common test
contract assigns `T-<rule-id>` to each entry: at least an applicable success, applicable
failure, unavailable-evidence case where meaningful, and inapplicable case. Each case asserts
both the result and its evidence path. These are required future tests, not executed tests.
Algorithm references identify the implementation home in [LLD algorithms](05-LLD-ALGORITHMS.md).

Each implementation record also carries `inputs`, `parameter_refs`, `authority_refs`,
`dependencies`, `repair_operations`, `implementation_version`, and `test_ids`. The canonical
shape is RuleDefinition in [LLD contracts](04-LLD-CONTRACTS.md). A missing implementation
record is a catalog-coverage failure, not permission to skip the rule.

## 2. Mathematical foundation

### 2.1 Coordinates and scale

Let a region have an inline extent `W` and block extent `H` in CSS pixels. Its usable inline
extent is `U = W - padding_start - padding_end`. For a one-dimensional partition with `n`
children and inter-child gaps `g_j`, define `A = U - sum(g_j)`. All declared extents and gaps
must be finite. Insets may not consume more space than exists in a selected fitted region.

For unconstrained positive shares `r_i`, allocate `w_i = A * r_i / sum(r)`. With lower and
upper child bounds, solve `w_i = clamp(lambda * r_i, min_i, max_i)` with `sum(w_i) = A`.
The monotone bounded solve in ALG-03 finds the common scale while respecting every bound.
If the minima do not fit, the selected partition is infeasible. It does not shrink text
or discard content to make the equation true. A separately declared reflow construction
must take over. Unbounded maxima are represented by an explicit `unbounded` variant.

Each allocation preserves `sum(widths) + sum(gaps) + insets = W`, modulo measured browser
rounding tolerance. The tolerance is an authority-bearing parameter, never an aesthetic margin.

### 2.2 Relations

For axis-aligned boxes A and B, overlap on axis x is
`ox = max(0, min(A.right, B.right) - max(A.left, B.left))`, and similarly for y.
Intersection area is `ox * oy`. Edge equality is tested as `abs(edgeA - edgeB) <= epsilon`.
Normalized distance divides by the declared containing extent, whose positivity is checked.

These describe bounding geometry. They do not establish overlap of painted glyphs, opacity,
occlusion, or psychological grouping. Those are distinct observations or interpretations.
Transforms retain both the axis-aligned bounds and the known transform/quad capability.

Containment, alignment, adjacency, precedence, similarity, repetition, exception, dependency,
semantic affiliation and contrast are typed relations. A relation states the channel it
uses: geometry, tokens, semantic role, state, or attributed visual interpretation.

### 2.3 Rhythm and progression

Available sequence constructors are arithmetic `s_k = u + k*d`, geometric `s_k = u*q^k`,
and explicit finite sequences with a declared recurrence or semantic grouping. Parameters
have domains; invalid negative sizes or nonfinite terms fail. The compiler never chooses
the golden ratio, an eight-pixel grid, or a heading progression as a universal default.

For a linear fluid parameter between measured or specified container bounds:
`t = clamp((W - W0)/(W1 - W0), 0, 1)` and `s(W) = s0 + t*(s1 - s0)`, requiring `W1 > W0`.
Endpoint values and bounds are proposals or author inputs. Rendered content determines
whether the chosen progression remains usable at intervening conditions.

### 2.4 Space and density

A clearance region specifies a boundary and which foreground roles may enter it. Its
geometric occupancy is the union of admitted foreground boxes clipped to that region.
`occupancy = area(union(boxes))/area(region)` and `geometric_clearance = 1 - occupancy`.
These are descriptors, not beauty scores. Background fields are recorded separately so a
full-page painted background does not falsely erase every space between foreground elements.

Two groups may deliberately distinguish their internal and external gaps. The optional
proximity construction binds `outer_gap >= inner_gap + separation`, where `separation` is a
selected parameter. Enclosure, shared surface, alignment and connectors are alternative
grouping channels. Proximity is never the sole definition of belonging.

### 2.5 Image fitting and cropping

For source image extent `(Iw,Ih)` and box `(Bw,Bh)`, contain uses
`s = min(Bw/Iw, Bh/Ih)` and cover uses `s = max(Bw/Iw, Bh/Ih)`; all extents must be positive.
The remaining offset positions the source according to an authored anchor. A protected focal
region is transformed by the same scale/offset and must remain inside the visible clip.
If it cannot, choose another permitted fit or composition, or request a different asset.

### 2.6 Color and character

A palette is a mapping from semantic surface/ink/action/state roles to color expressions.
A generator may use an OKLCH family such as
`L_i = L_base + deltaL_i`, `C_i = C_base * cScale_i`, and
`h_i = (h_base + deltaH_i) mod 360`. The domains and relationships are frame choices.
Achromatic colors do not receive meaningful hue-distance claims. No hue offset guarantees
harmony. The generator converts into its declared output gamut and rechecks actual contrast.

The initial emitter's canonical output colors are sRGB. OKLCH is an optional proposal space,
with standards-based conversion and explicit gamut handling. Imported pages retain their raw
CSS and color-space provenance; unsupported exact conversion remains unknown. Alpha and
overlapping surfaces must be composed before a background-dependent claim is made.

See [CSS Color 4](https://www.w3.org/TR/css-color-4/) for the color model and conversion
definitions. Those definitions supply numerical mechanics, not an aesthetic ranking.

### 2.7 Responsive feasibility

For equal-width items, the largest feasible count satisfies
`n*minimum_item_width + (n-1)*gap <= U` for positive integer n. An empty collection has zero
items and zero inter-item gaps, with its declared empty-state behavior. Cap n by the actual
remaining item count. If no item
fits, invoke a declared fallback or report infeasibility. Unequal partitions use their actual
child minima. Breakpoints are derived from these inequalities and from actual content
transitions, then verified in the browser. Width alone is not a proxy for input modality.

### 2.8 Coupled transformations

A transformation is `next_program = apply(program, patch)` followed by validation, dependency
invalidation, compilation and observation. It is not unrestricted addition to an arbitrary
vector of CSS values. The patch states which role, parameter, relation or primitive changes
and which properties must remain invariant. Meaningful variation is encoded through these
typed transformations. Sampling only proposes values inside declared domains.

## 3. Catalog

### Evidence: EVD

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| EVD-01 | P | Every fact, asset and rule parameter carries its source kind, source reference and version/hash where applicable. A screenshot estimate cannot be labeled DOM measurement. | ALG-01 |
| EVD-02 | P | Every observed or generated object has a stable scoped identity. Revisions retain lineage; transient browser selectors do not become cross-capture IDs. | ALG-01 |
| EVD-03 | P | Every capture declares page, condition, state, readiness and admitted domain. Missing bands, states and interiors remain explicit coverage obligations. | ALG-02 |
| EVD-04 | P | Missing, unsupported or inconsistent values remain typed unknowns. Numeric zero and a successful result require evidence. | ALG-01 |

### Intent and content: INT

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| INT-01 | H | Generated meaningful content and actions map to brief requirements and semantic roles. Required content cannot disappear during fitting or refinement. | ALG-04 |
| INT-02 | H | A declared reading/action order remains represented in semantic source order. Visual rearrangement must preserve a usable equivalent sequence. | ALG-07 |
| INT-03 | P | Proposed role and meaning assignments identify their author and assumptions. They never become recorded human verdicts by reuse. | ALG-01 |
| INT-04 | J | Each character choice explains its relevance to the actual subject, audience and task. A register label alone is insufficient rationale. | ALG-04 |

### Geometry and space: GEO

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| GEO-01 | H | All boxes and fragments declare coordinate space, units and condition. Invalid extents and incompatible-space comparisons fail. | ALG-02 |
| GEO-02 | H | Required generated content fits through wrapping, scrolling, disclosure or a different composition explicitly permitted by the brief. Accidental clipping is a failure. | ALG-07 |
| GEO-03 | G | A selected partition conserves available space and respects positive shares and child bounds. Infeasible bounds produce a conflict, not fabricated dimensions. | ALG-03 |
| GEO-04 | G | Selected alignment identifies the reference axis/edge and admitted offset. A baseline claim needs an actual baseline anchor or remains unmeasured. | ALG-03 |
| GEO-05 | G | A grouping construction identifies proximity, enclosure, surface, alignment or another declared channel and checks its selected relationship. | ALG-03 |
| GEO-06 | G | Reserved clearances identify permitted intrusions. Occupancy descriptors distinguish foreground boxes from full-area background surfaces. | ALG-02 |
| GEO-07 | H | Overlap affecting content or controls is either declared by a layer contract with ordering/protected regions, or reported as a collision. | ALG-07 |
| GEO-08 | G | Media fitting preserves intrinsic aspect and any required focal region. Distortion requires an explicit, asset-appropriate transform. | ALG-05 |
| GEO-09 | G | Centering or counterbalancing names its geometric reference. A visual/optical offset is an attributed proposal and is tested after rendering. | ALG-03 |
| GEO-10 | G | Regions selected to share a grid or edge use the same reference relation; a deliberate departure is represented as an exception. | ALG-03 |

### Rhythm: RHY

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| RHY-01 | G | A selected progression declares its constructor, domain and role assignments. Arithmetic, geometric and explicit sequences remain available. | ALG-03 |
| RHY-02 | H | Repetition cardinality and keys derive from the content collection or authored structure. Missing items and duplicate identities fail. | ALG-03 |
| RHY-03 | G | A selected section cadence binds its recurrence and named interruptions. Changed content can change the cadence through a new proposal. | ALG-04 |
| RHY-04 | J | Density reports text, controls, media and geometric occupancy separately. The brief determines whether the resulting density is useful. | ALG-06 |

### Hierarchy: HIE

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| HIE-01 | G | An emphasis relation names its intended leader, dependents and channels such as scale, contrast, isolation or media. Channels have explicit targets, not a universal salience sum. | ALG-04 |
| HIE-02 | J | Review the path from orientation to required information to action. A pleasing composition with an obscured or misleading task path is not approved by geometry alone. | ALG-06 |
| HIE-03 | J | Review competing emphasis in its task context. Multiple legitimate focal regions are allowed; count alone is not a defect. | ALG-06 |
| HIE-04 | G | A state or viewport change preserves the declared priority relations or explicitly changes them for a stated task reason. | ALG-07 |

### Typography: TYP

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| TYP-01 | H | Intended font files, faces, weights, axes and language coverage are available and resolved. Fallback is recorded and checked against the asset/brief contract. | ALG-05 |
| TYP-02 | H | Text layout uses actual content and shaping. Fit repair cannot silently shrink below the declared readable domain or erase text. | ALG-05 |
| TYP-03 | G | Typography maps semantic roles to deliberate treatments. One or several families and distinct scales are permitted when their use is coherent with the chosen frame. | ALG-04 |
| TYP-04 | G | A selected type progression and exceptions retain their declared relationship at actual rendered sizes. There is no mandatory display/body ratio. | ALG-03 |
| TYP-05 | G | Selected measure, leading and wrapping goals depend on language, font, task and content. Browser fragments and review validate them; characters-per-line is a descriptor. | ALG-05 |
| TYP-06 | H | Text-resize, content expansion and supported language/direction conditions preserve content and access. Required font variants cannot be inferred from a file name alone. | ALG-07 |

### Color and surfaces: COL

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| COL-01 | H | Color measurements retain raw CSS, resolved channels, color space, method and support state. Unmeasurable paint is unknown, never transparent black by default. | ALG-05 |
| COL-02 | H | Background-dependent checks use the actual composited surface or report that it is not established. Gradients, blends and image backgrounds require their own support. | ALG-05 |
| COL-03 | G | A selected palette family declares role relationships, permitted gamut transforms and domains. Hue geometry is a construction choice, not evidence of beauty. | ALG-05 |
| COL-04 | H | Applicable text contrast checks follow the selected standards profile and its exceptions. Unknown background or font classification prevents a pass. | ALG-07 |
| COL-05 | H | Information carried by a color change has the additional cues required by the selected standards and task contract. | ALG-07 |
| COL-06 | G | State color meanings stay consistent within the declared frame or have a scoped reason for changing. Meanings are contextual, not intrinsic to hue. | ALG-04 |

### Materials, imagery and detail: MAT

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| MAT-01 | H | Required assets have bytes, provenance, allowed use and dimensions/capabilities. An asset request remains incomplete until real material is supplied. | ALG-05 |
| MAT-02 | P | A media box is distinct from the image's depicted subject and visual weight. Subject/focal annotations state whether they are authored or inferred. | ALG-05 |
| MAT-03 | G | A chosen ornament or motif varies through shared parameters and a stated role, including expressive atmosphere where intended. | ALG-04 |
| MAT-04 | H | Texture and decorative layers preserve readable content, operation and the selected accessibility obligations. Decorative richness has no universal maximum. | ALG-07 |
| MAT-05 | G | A selected corner/border construction defines its nesting and stroke relationship. Consistent hierarchy can use different radii; a single global radius is not mandatory. | ALG-03 |
| MAT-06 | J | Icons, symbols and illustration are reviewed for legibility, task meaning and a coherent visual treatment in context. | ALG-06 |

### Variation: VAR

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| VAR-01 | G | A transformation preserves named invariants while varying declared parameters, topology or materials. It must survive validation and observation. | ALG-08 |
| VAR-02 | G | Exceptions identify their scope, purpose and affected relations. A local exception cannot silently redefine an entire site's rule. | ALG-08 |
| VAR-03 | P | Candidate diversity records which structural, material and task decisions differ. Randomness or rarity alone is not rewarded. | ALG-04 |

### Responsiveness: RSP

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| RSP-01 | H | Each delivered page has a declared condition domain and tested representatives, including boundaries where its selected layout changes. Untested ranges are disclosed. | ALG-07 |
| RSP-02 | G | Responsive composition changes follow fitted content and declared constraints. A breakpoint is derived or authored with a reason, not copied from a reference screenshot. | ALG-03 |
| RSP-03 | H | Reflow retains required content and action reachability. Disclosure or scroll alternatives have explicit state and interaction contracts. | ALG-07 |
| RSP-04 | H | Logical direction and supported writing modes preserve meaningful order and layout. Unsupported modes are named capability gaps. | ALG-07 |

### State and behavior: STA

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| STA-01 | H | Generated interactive components declare applicable states, events, transitions and invariants. The capture matrix derives from this declaration. | ALG-07 |
| STA-02 | H | Keyboard operation, focus and names/roles follow native semantics or a declared, verified component contract. A visual affordance is not a behavior test. | ALG-07 |
| STA-03 | H | Input labels, help, validation and status changes retain their relationship to the affected controls and task. | ALG-07 |
| STA-04 | H | Overlays declare modal/nonmodal behavior, protected controls, focus handling and dismissal where applicable. Occlusion is evaluated in that state context. | ALG-07 |
| STA-05 | H | Business actions keep their owning API/application contract. A prototype transition cannot fabricate a completed external operation. | ALG-07 |

### Motion: MOT

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| MOT-01 | G | Motion names its endpoints, timing source, trigger and informational or expressive purpose. State continuity is checked at the meaningful points. | ALG-07 |
| MOT-02 | H | Reduced-motion and motion-control obligations are represented and verified for the chosen standards/project profile. Meaning and access survive the alternate behavior. | ALG-07 |
| MOT-03 | P | A capture records whether motion was settled, sampled or intentionally frozen. A static image cannot verify an unobserved animation sequence. | ALG-02 |

### Coherence: COH

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| COH-01 | H | Each emitted style assignment has an owning token/operator and source map. Unexpected cascade overrides or stale compiled edits are reported. | ALG-09 |
| COH-02 | H | Parameter, content, font, asset and state changes invalidate dependent observations and checks before a completion claim. | ALG-08 |
| COH-03 | G | Shared role treatments and deliberate page/state variants use explicit inheritance. A section can vary without accidentally forking every shared token. | ALG-04 |
| COH-04 | H | Resource and delivery budgets are authority-bearing inputs and measured outcomes. The system does not invent global asset, word or node ceilings. | ALG-10 |

### Revision and retention: REP

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| REP-01 | H | Every accepted patch lies inside its permitted domain and preserves locked requirements. Out-of-domain proposals are rejected before compilation. | ALG-08 |
| REP-02 | P | Reports separate hard failures, selected-construction failures, unknowns and judgments. No compensating aggregate beauty score exists. | ALG-06 |
| REP-03 | P | Controlled changes record the changed variable and observed consequences. Generated perturbations receive no human preference label without a verdict. | ALG-08 |
| REP-04 | P | Prior candidates, decisions and receipts remain addressable. Resumption and export verify versions and bytes before use. | ALG-10 |

### Generalization: GEN

| ID | Class | Applicability and required behavior | Algorithm |
| --- | --- | --- | --- |
| GEN-01 | P | Core selection and defaults are independent of reference-site identity. Reference names remain evidence metadata, outside executable rule conditions. | ALG-04 |
| GEN-02 | P | Evaluation partitions respect source-site groups, new-brief boundaries and declared tuning history. Disclosed references are not called blind training holdouts. | ALG-11 |
| GEN-03 | P | Human remarks retain exact words, author and scope. Approval of a whole site is not approval of each detail; unmentioned variants remain unjudged. | ALG-01 |
| GEN-04 | P | Compilation replay pins all deterministic inputs; model generation and browser pixels have separately disclosed reproducibility limits. | ALG-10 |

## 4. Standards boundary

The recommended first-release accessibility target is WCAG 2.2 AA. The StandardsProfile
must enumerate all applicable criteria from its pinned authoritative source and carry a
disposition for each: automated, manual, not applicable with reason, or unsupported. The
checks below are implementation anchors, not a claim that this short list covers AA.

Text contrast uses the applicable 4.5:1 or 3:1 threshold and the criterion's large-text,
incidental and logotype classifications. Do not round a failing ratio into a pass.
[SC 1.4.3 explanation](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).

Target-size assessment uses the 24 CSS-pixel minimum criterion with its spacing and other
exceptions; it does not turn 44 pixels into an unexplained universal law.
[SC 2.5.8 explanation](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

Reflow assessment includes the 320 CSS-pixel width condition for horizontally read content,
with the criterion's exceptions for necessary two-dimensional layout.
[SC 1.4.10 explanation](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

Focus visibility and occlusion are tested in actual interaction states. A menu covering its
background is not automatically a failure.
[SC 2.4.11 explanation](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html).

The normative profile binds [WCAG 2.2](https://www.w3.org/TR/2024/REC-WCAG22-20241212/).
Pattern guidance from [WAI-ARIA APG](https://www.w3.org/WAI/ARIA/apg/patterns/) informs custom
controls; it does not replace native semantics or the project's conformance review.

## 5. Rules we deliberately do not encode

No global requirement for a serif, a sans, a maximum font count, a quiet background, one
focal point, equal cards, a fixed palette length, a minimum amount of whitespace, a fixed
word budget, the golden ratio, a particular level of ornament, or a penalty for familiar
patterns. These can be scoped choices if the brief calls for them. The approved corpus
already spans several conflicting choices along these axes.

No rule proves semantic compatibility merely because two colors or dimensions have a
simple numerical relationship. No high score grants aesthetic approval. No image model,
language model or automatic critic writes a verdict in Erik's name.
