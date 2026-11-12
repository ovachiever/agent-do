# Worked examples and reusable composition recipes

These are newly authored planning fixtures. They are not copied sites, observed corpus
measurements, human-approved designs, or executed renders. Every numerical choice below is
an **illustrative proposed parameter** unless explicitly derived. Implementation tests must
bind the choices as parameters with that authority, rather than turning them into defaults.

## 1. Eight recipes that generate relationships

These recipes compose the sixteen operators. They are optional constructions with explicit
conditions. They can coexist, nest, or be replaced. Their names are handles for an idea,
not a classification of a person, business, or aesthetic. They supply the connective tissue
between geometric rules and the model's contextual reading.

### F-01: field and anchor

Purpose: make one content group easy to locate in a larger field. Inputs are a field, an
anchor group, any supporting groups, and the task that gives the anchor priority.

Construction: `region + clearance + align + flow`. Set the anchor's normalized position
`x = field.start + a*usable_width`, with `a` proposed for the brief. Center, edge, inset and
off-center placements are all admissible. Anchor width comes from its real content/measure
contract. The remaining region is explicit clearance or assigned support, not missing design.

Expression: type contrast, isolation, an image, motion, or a distinct surface can carry the
anchor role. No minimum heading size or empty-space percentage is required. A saturated
graphic and a small isolated label can instantiate the same relationship differently.

Dependencies: changed anchor content/font invalidates extent, clearance and responsive fit.
Counterexample: a comparison task may need several equally accessible groups; forcing a
single anchor would distort the task. Review whether the intended entry is actually legible.
Rules: GEO-04/06/09, HIE-01/02, TYP-02. Algorithms: ALG-03/04/05.

### F-02: counterpoise

Purpose: let two unequal groups hold a deliberate relationship. Inputs are two task roles,
their minima, shared alignment references, and a proposed hierarchy.

Construction: `partition + align`; optional `layer`. Bounded positive shares determine space.
An optional *geometric* balance diagnostic uses `centroid = sum(area_i*center_i)/sum(area_i)`,
requiring a positive total area/weight.
If optical weights replace area, each weight is an attributed estimate and the result is an
interpretation, not an objective equilibrium or beauty test. The centroid is never forced to
the page center by default.

Expression: a narrow dense column can counter a broad image; a heavy display face can counter
several fine text groups; a dark small region can be proposed against a broad pale one.
These are hypotheses to render, not laws that ink area equals attention.

Dependencies: font, crop, image subject and surface changes invalidate different geometric
and interpretive observations. Counterexample: equal comparison items may call for symmetry.
Rules: GEO-03/04/08/09, HIE-01/03, MAT-02. Algorithms: ALG-03/05/06.

### F-03: cadence and interruption

Purpose: establish a repeated reading pattern, then give a meaningful event a different beat.
Inputs are ordered content groups, a progression and semantically named interruptions.

Construction: `repeat + sequence + flow`. Assign spacing or spans using `s_k = u + k*d`,
`u*q^k`, or an explicit sequence. Define interruptions by content key or semantic predicate,
not by a reference site's section number. A selected interruption overrides only named fields.

Expression: alternation can occur through density, image scale, type role, field color or
reading pace. It need not alternate left and right. Constant spacing is a valid recurrence.

Dependencies: changed membership recomputes sequence assignment while stable keys preserve
identity. Counterexample: a sorting table usually needs persistent row conventions; aesthetic
interruptions would interfere with comparison. Rules: RHY-01/02/03, VAR-02. ALG-03/04/08.

### F-04: nested enclosure

Purpose: make containment visible and coordinate material detail across levels.
Construction: `region + region + clearance`. A selected concentric rounded-rectangle treatment
can use `inner_radius = max(0, outer_radius - inset)` for a uniform inset. Stroke placement
and border thickness are explicit. Nonuniform insets require per-corner geometry or a different
declared construction; the scalar expression is not blindly applied.

Expression: fine rules, heavy ink borders, colored fields, shadows or no visible border can
communicate different kinds of enclosure. The formula applies only when concentric curvature
is the selected relationship. Rectilinear and deliberately mismatched corners remain possible.

Dependencies: inset or stroke changes invalidate inner bounds, radii and content fit.
Counterexample: independent floating elements are not necessarily nested visual containers.
Rules: GEO-05/06, MAT-04/05. Algorithms: ALG-03/05.

### F-05: typographic accord

Purpose: give content roles related but distinguishable voices.
Construction: `text + sequence + align`, using actual font files, language and content. An
optional progression chooses `size_k = base*q^k`; a role can instead bind an explicit size.
Weight, width, case, italics, tracking and measure can distinguish roles without changing family.

Expression: one family, several families, serif, sans, mono, lettering or an authored mixture
can be appropriate. There is no fixed correspondence between a face category and seriousness,
warmth or modernity. The frame names the subject-specific reason and available counterexamples.

Dependencies: changing a face invalidates shaping, measures, wraps, group extents and nearby
placement. An axis setting is part of the asset/style identity. Counterexample: imposing a
type scale on a diagram's labels can obscure a more important spatial grouping.
Rules: TYP-01 through TYP-06, HIE-01, COH-01. Algorithms: ALG-03/04/05.

### F-06: material infusion

Purpose: let a subject's material character enter typography, color, imagery and small details
while leaving task and content relationships explicit.

Construction: a CharacterFrame binds role tokens and asset choices to existing regions,
text, media and controls. A proposed palette family may vary OKLCH lightness/chroma/hue with
the Rulebook's expressions. A motif uses shared stroke, scale or interval parameters. The
same material parameter can affect several roles through dependency edges.

Expression: a printmaking brief might propose coarse image texture and precise navigation;
an instrument archive might propose engraved scale marks and a lucid table. Those associations
are authored readings of these particular briefs, not rules for every archive or printmaker.
Asset properties can support an association; they cannot prove a metaphysical meaning.

Dependencies: palette changes require composited contrast and state-cue review; texture changes
require paint/legibility review. Counterexample: a motif that obscures necessary instructions
does not satisfy its task contract. Richness is allowed; obstruction is a separate finding.
Rules: INT-04, COL-03/06, MAT-03/04/06, COH-02. ALG-04/05/06.

### F-07: information lattice

Purpose: support repeated comparison without demanding a visually quiet page.
Construction: `grid or component(table) + align + repeat`. Shared fields define the comparison
axes. Item count comes from real membership. Span changes and disclosure are explicit, keyed
decisions. Order follows the task's sorting/filtering contract.

Expression: the lattice may have strong color, expressive headings, illustrations or little
decoration. The invariant is reliable comparison, not low saturation or identical card height.
Equal heights are selected only when they serve the comparison and preserve content.

Dependencies: content, sort/filter state and column visibility affect membership/order and
width. Counterexample: a narrative can lose its sequence when converted into equivalent tiles.
Rules: RHY-02, GEO-04/10, INT-02, RSP-03, STA-01. ALG-03/07.

### F-08: passage and transformation

Purpose: change composition as a task, state or available space changes while preserving what
the user needs to understand and do.

Construction: `state + transform + flow/partition`. A state boundary or feasibility inequality
selects a typed variant. Required content keys, task continuity and appropriate focus are
protected invariants. Motion, when selected, connects declared endpoints and has an accessible
alternate behavior according to the project profile.

Expression: a diagram can gather into a list, an overview can reveal a concentrated reading
view, and an expressive opening can lead into precise controls. No page must become uniformly
sparse or uniformly dense. Counterexample: moving an actively used control after every small
input change can make the task harder. Rules: VAR-01, HIE-04, RSP-01/02/03, STA/MOT. ALG-07/08.

## 2. End-to-end example: a community seed library

### Brief and content

A town library needs a website where gardeners can find an available seed variety, understand
its growing conditions, and reserve a packet. The first screen must preserve the search,
seasonal availability, library collection explanation and next pickup information. The catalog
must support filters, no-results recovery, a variety detail view and the reservation status.

Proposed intent: practical exchange with the care of a field notebook. This phrase is a model
reading, not a human verdict. Candidate expression could emphasize diagrams, photographic
specimens, or predominantly text. The grammar does not select a botanical style automatically.

Content graph: `intro`, `pickup`, `search`, `filters`, `varieties`, `variety-detail`,
`reserve-action`, and `reservation-status`, with stable variety keys. The actual collection is
provided by the library; the fixture must declare its complete membership. Required fields
include common/scientific name, planting conditions, availability and pickup instructions.

The reservation handler belongs to the library application. Its binding is initially
`unbound`. The planning fixture can exercise a labeled local handler, but release cannot claim
that a packet was reserved without the real action-owner receipt.

### Proposed program

This tree is a readable expansion sketch, not a complete wire document. A full payload must
also carry every artifact reference, hash, authority and condition specified in the LLD.

```text
page(seed-library, language=en, direction=ltr)
  region(site-header)
    flow(navigation and identity)
  region(introduction)
    partition(main:aside, proposed shares 2:1, bounded minima)
      flow(main)
        text(intro)
        control(search, native search input)
      flow(aside)
        text(pickup)
        media(specimen diagram, if a permitted ready asset exists)
  region(catalog)
    flow(filters)
    state(catalog-state)
      ready: grid(repeat(varieties, stable variety key))
      empty: flow(no-results explanation and clear-filters control)
      pending: flow(status and retained controls)
      failed: flow(error and retry action)
  page(variety-detail)
    flow(required growing data and specimen media)
    control(reserve-action, bound action-owner contract)
    state(reservation-status)
```

The intro partition is selected because immediate search and secondary pickup information
have distinct roles. A different brief might make pickup the first full-width band. The host
must record that alternative rather than implying the tree follows inevitably from the topic.

### Derived partition and reflow

Illustrative fixture inputs: container width 1200 CSS px, start/end insets 48 each, one gap
24, shares `[2,1]`, child minima `[640,280]`, maxima `[unbounded,360]`.

```text
usable = 1200 - 48 - 48 = 1104
available_for_children = 1104 - 24 = 1080
unbounded_share_allocation = [1080*2/3, 1080/3] = [720,360]
conservation = 720 + 360 + 24 + 48 + 48 = 1200
minimum_container = 640 + 280 + 24 + 48 + 48 = 1040
```

These are derivations from proposed fixture values. The minima must later be justified by
real text/control/media measurements or an author requirement. They are not discovered ideal
widths. Below 1040 the selected horizontal construction is infeasible, so the program uses a
declared vertical flow. At 1000, child space is 880, less than the required 920. It must not
silently compress the minima or delete the pickup text.

Required capture conditions include the feasibility boundary, its neighbors, the selected
interior/endpoints, and relevant states. Actual CSS intrinsic sizing can still expose a
discrepancy and force a revised proposal. An equation does not certify the rendered page.

### A coupled repair

A replacement font or longer translation makes the main group require 760 instead of 640.
This is a hypothetical measurement change for the fixture; no browser measurement occurred
in this planning commission.

At width 1200 the bounded solution is `[760,320]`. At width 1100, the earlier minima still
fit, but the new minima do not. The new feasibility boundary is
`760 + 280 + 24 + 48 + 48 = 1160`.

The change invalidates font resolution, text fragments, main extent, the partition, media
position and derived responsive conditions. The repair therefore updates the font binding,
re-measures, revises the partition/condition program, renders affected conditions and checks
task access. Editing the heading font and retaining the old viewport receipts is a stale pass.

### Review and delivery trace

1. The core validates content, actions, parameter authority, assets and program shape.
2. Missing final specimen media creates an asset request if that media is required. If media
   is optional, the host can explicitly select a text/diagram-free composition with a rationale.
3. The compiler emits owned semantic HTML/CSS, bindings and a source map.
4. The browser produces actual samples and readiness/coverage receipts. DPT is archived separately.
5. Mechanical inspection reports fit, relations, state and standards obligations. A vision-capable
   reviewer separately assesses whether the field-notebook interpretation serves the task.
6. A typed revision preserves required content, then regenerates affected evidence.
7. Release requires all brief obligations, the real reservation binding, and any required reviews.
   A human preference is recorded only if one was actually supplied.

## 3. Same vocabulary, different websites

| New brief | Proposed construction | Character choice to explore | What must survive revision |
| --- | --- | --- | --- |
| A repair cooperative's searchable equipment manual | Information lattice for parts, a persistent task index, then long procedural flow | Condensed technical labels with roomy instruction text, or one neutral family with strong diagrams | Part identity, warning proximity, ordered steps, keyboard navigation, version visibility |
| An independent ceramics studio's collection and order inquiry | Media-led sequence, asymmetric partitions, detail states | Product surfaces supplying most color, or expressive graphic fields around neutral photographs | Actual scale/material information, focal crop, stock facts, inquiry handler |
| A neighborhood night market's schedule | Time/location lattice plus a prominent changing event region | Saturated surfaces, custom illustration and several type roles, if real assets support them | Schedule comparison, venue information, legibility, filter recovery, mobile task access |
| A public research archive | Dense record comparison opening into a concentrated document view | Fine rules and restrained text, or a bolder publication identity | Metadata fidelity, stable citations, reading order, accessible document controls |

These are proposed alternatives for novel briefs, not another template library. The technical
manual can contain expressive illustrations; the night market can be mostly typographic.
The ceramics inquiry could be a single column if its content calls for that. The rule engine
must not contain a predicate such as `industry == ceramics => media-led layout`.

## 4. Transformations that test generality

| Change | Expected invariant | Legitimate adaptation | Disallowed apparent success |
| --- | --- | --- | --- |
| Double an item's necessary text | Required content and readable access | Reflow, changed measure, a taller row, an explicit disclosure | Truncating required information without a route to it |
| Replace a wide image with a tall one | Protected subject and intrinsic shape | Different partition, contain fit, new asset proposal | Stretching or cropping away required subject matter |
| Change serif display to a wide sans face | Task hierarchy and actual fit | Re-measured type/geometry and revised conditions | Keeping old evidence because the CSS compiled |
| Increase an ordered collection | Exact admitted membership and usable order | Additional rows, pagination/window contract, revised cadence | Capturing only the first attractive items |
| Add strong texture and saturated fields | Content/action access and chosen role relations | Revisited surfaces, ink and detail relationships | Rejecting richness solely because a score dislikes it |
| Move from mouse to keyboard use | Reachable task path and meaningful focus | Appropriate state/focus behavior | Counting a screenshot as proof of operation |
| Reverse reading direction for supported content | Logical relationships and meaningful sequence | Logical placement plus explicit physical exceptions | Visually mirroring text while preserving a broken DOM order |

These transformations test whether the language is useful beyond its initial examples.
They do not supply automatic human dislike labels or establish that every change should
preserve the same visual appearance.
