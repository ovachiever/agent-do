# Aphrodite 0.2.0: native design and legacy engine

The default workflow equips the host AI to design in its existing frontend. An open dependency graph carries chosen numerical relationships through revisions; native code and visual judgment remain with the designer. See [Version 0.2: native frontend authorship](#version-02-native-frontend-authorship) for the implementation and its limits.

The architecture below describes the preserved 0.1 experimental generator, available through explicit engine commands and `packet --mode engine`.

Work item: `mn-da6e1b`. This describes executable behavior, not a promise that all human beauty has been solved. The historical Aphrodite plan and WP-0 artifacts remain unchanged. The user's authorization to build the complete instrument supersedes the earlier planning-only stop; it does not change any earlier experiment's result.

## High-level architecture

```text
Attributed brief + material files + versioned perspective model
                         |
                   bind and validate
                         |
             immutable semantic/material context
                         |
     bounded grammar beam + shared coordinates + exact relations
                         |
                  semantic HTML/CSS
                         |
                  agent-do browse
                         |
          actual viewport/state measurements and captures
                         |
        nine family descriptors -> contextual affinities
                         |
       complete conditions + functionality + bounded selection
                         |
                 working page / fresh packet

Attributed human comparisons -> grouped offline fit -> model proposal
Explicit adoption + exact domain -> separate adopted model version
```

No model service or critic sits on the evaluation or selection path. Meaning enters as sourced brief data. The generator may choose only within the frozen brief's obligations, grammar and control domains. More proposals cannot change the target or silently discard a failed viewport. The current architecture separates software capability, proposed aesthetic hypotheses, attributed observations and empirical validation.

## Ownership and contracts

| Module | Responsibility | Principal contract |
| --- | --- | --- |
| `core.js` | Canonical JSON, hashes, immutable artifacts, faults | Finite data; exclusive writes; manifest paths stay inside bundles |
| `contracts.js` | Brief, model and material binding | Closed semantic vocabulary, meaningful content, acyclic containment, sourced roles/materials |
| `math.js` | Kernels, affine nullspace, unions, color and geometry | Pure functions with analytic and numerical tests |
| `construct.js` | GR-01–09, seeded beam, shared variables, revision dependencies | Reconstructible program; fixed context/model/engine digests |
| `render.js` | Native semantic document and responsive CSS | Escaped content, embedded materials, real actions, no public design rationale |
| `probe.js` | Browser measurement program | Explicit semantic bindings; actual text geometry and raster measurements |
| `browser.js` | Existing browse transport and isolated session | Required states exercised by native browser actions; failures retained |
| `evaluate.js` | Typed relations, nine families and fixed-domain objectives | Missing observations cannot become passing features |
| `engine.js` | Compose, vary, revise, observe, select, export, packet | Measured selection only; failed runs have no selected export |
| `learn.js` | Attributed comparisons, grouped fitting, adoption | Development fitting and human adoption remain separate |
| `cli.js` | Structured public interface | JSON receipts and meaningful nonzero exits |

`Context.digest` binds the complete normalized brief, embedded material bytes, model and descriptor version. `domainDigest` binds the semantic brief and material hashes independently of model version so adoption is not circular. `Program.digest` additionally binds shared coordinates, topology, derived frames, decisions and dependencies. `engineDigest` binds all source modules. Observation and evaluation records carry their program and context provenance.

The model is frozen before proposals. The browser environment is measured, not inferred from CSS declarations. A changed font or image requires a new context and observations. Existing runs include their source engine for reproducible numerical replay after installed code changes.

## Relational mathematics

For a measured descriptor vector `z`, a declared contextual target `mu`, and positive scales `s`, the primitive affinity is:

```text
K(z | mu,s) = exp(-0.5 * sum(((z_i - mu_i) / s_i)^2))
```

It peaks at a relationship, rather than rewarding unlimited size, contrast or empty space. The math module also implements alternative modes as a maximum over their affinities, preserving distinct arrangements instead of averaging their targets. Current seed perspectives each bind one mode per cue.

Identity and support have different cue contracts. `same-role` compares size, weight, paint and a glyph-shape fingerprint. `supports` combines separation relative to type, priority-dependent distinction and paint compatibility. `sequence` compares measured order and interval with the declared transition. `aligns` measures shared horizontal alignment; it does not claim arbitrary baseline or rotated-axis alignment. `counterweight` compares relative optical mass and spatial centroids.

The primary constructive chord is:

```text
log(g/b) = log(k * tempo) + elasticity * log(h/b)
```

Here `h` is the lead type size, `b` the body size, `g` the separating gap, and `k` belongs to the perspective. Common scale cancels from both ratios. Negative elasticity models compensating presence and space; positive elasticity models their co-development. Erik's A/D and C/B judgment motivates testing a compensating relation in that context. It does not identify an exact coefficient or make inverse spacing universal.

In log coordinates `x=(log b,log h,log g)`, the constraint is:

```text
C = [elasticity - 1, -elasticity, 1]
C x = log(k * tempo)
x = particular + nullspace * free_coordinates
```

The implementation computes the affine space, instantiates it and checks its residual. This proves constructive closure of that relation only. Other observed affinities use bounded search because browser wrapping, region shapes and crop geometry are not all affine.

| Family | Actual computed quantity | Construction influence |
| --- | --- | --- |
| APH-01 Typed consonance | Mean typed relation affinity; each relation combines its own channels geometrically | Shared roles and support structure |
| APH-02 Differentiated unity | Same-role identity multiplied by priority distinction | Common frame plus differentiated type roles |
| APH-03 Proportional chord | Gaussian affinity of log gap/body to the elastic type/body target | Exact shared log-dimension block |
| APH-04 Figure and ground | Rectangle-union complement relative to region area, multiplied by internal grouping | Nested regions, padding, separating intervals and explicit pair voids |
| APH-05 Counterpoint | Relative fragment/raster mass proxy and centroid counterweight | Lead/support proportions and typographic presence |
| APH-06 Development | Same-role recurrence and ordered transition affinities | Ordered sequences and per-group trajectory |
| APH-07 Material resonance | Palette/surface, curvature, measured type ink density and linked image texture | Character-linked type, tint, stroke/curvature and material treatment |
| APH-08 Constellation | Product of exactly three distinct relation affinities | Coupled three-relation configurations |
| APH-09 Viewpoint continuity | Preservation of role ratios, membership and regional mass fractions across viewports | Content-preserving reflow |

For APH-08, `F = a*b*c` has a nonzero mixed difference, whereas an additive sum does not. Multiplication is an explicit conjunction hypothesis: several relations support one configuration together. It is not a theorem that all beauty behaves as a weakest-link system. Only that family uses the three-relation conjunction. The complete objective is a contextual weighted mixture of the eligible families; one weak family does not automatically erase every other strength.

Eligibility comes from the frozen semantic graph and declared state. If a family has no relevant entities it is structurally inapplicable; if its declared entities cannot be measured the candidate is incomplete. Family weights are normalized over the predeclared applicable set. They are never renormalized around a failed feature. Selection takes the minimum objective across required conditions, then the mean as a tiebreaker. This minimum is a declared requirement to support every promised viewport/state, not an absolute definition of beauty.

## Parameters, learning and what is not learned

The seed model has 21 numeric settings per perspective across three perspectives, six shared descriptor scales, nine family weights, and five control domains with min/max/default values: 93 numeric settings in JSON. The family weights have eight free dimensions. Constructor constants, measurement resolutions and implementation limits are additionally explicit in source and frozen by `engineDigest`; the JSON is not a claim that these are the only design choices in the system.

Every seed setting is authored. None is presented as an estimate supported by the small WP-0 comparison set. The current fitter changes only family weights. It does not pretend to identify all 93 settings from a handful of correlated preferences. It uses a regularized pairwise logistic loss, equal total contribution per declared group, simplex-constrained weights, analytic gradients, backtracking and a bounded iteration count. The worst required condition is recomputed under candidate weights. Held-out groups never enter the optimization.

The fit report gives training pairs, independent-group declarations, held-out pairs, `neither` records, eight free weight dimensions, loss and iteration count. It makes no significance or statistical-power claim. A genuine transfer experiment still requires frozen future briefs, real human responses, appropriate sample size and predeclared success/failure criteria. The executable `study` command provides a matched-pool full/pairs/parts comparison; it does not simulate a fresh host or invent its taste verdict.

## Generation, revision and diversity

Semantic containment is finite and acyclic. Each group expands once, with one terminal per original node. The derivation beam enumerates applicable productions per group and keeps a bounded, deterministically seeded set of prefixes. Its prefix priority is exploration, not a partial beauty estimate. Final ranking uses actual measured complete pages. Up to 48 proposals are allowed, including reserved shared-coordinate refinement moves. Search is bounded, deterministic in its proposals and explicitly incomplete; it does not prove a global optimum.

GR-01 binds page regions; GR-02 partitions complementary lanes; GR-03 sequences siblings; GR-04 clusters lead and support; GR-05 places an anchor with satellites; GR-06 overlays material and an opaque readable foreground; GR-07 emits real terminals; GR-08 shares role treatments; GR-09 reflows while retaining content. Topology has no approved-site names or stored site skeletons.

`presence`, `tempo`, `balance`, `character`, and `scale` act through shared formulas. The dependency graph propagates changes through tokens, nodes, relations, constellations, geometry, material and viewpoint evaluation. Invalidation is deliberately conservative: the renderer remeasures every required condition. The system does not claim minimal incremental recomputation.

Structural distance is Jaccard distance over semantic production signatures, excluding copy and IDs. Repeated identical substructures collapse in that set representation. `vary` enforces a minimum distance within a fixed affinity tolerance. Distance is a separate condition, never added to affinity. Every bounded miss is returned as no selection.

## Actual observation and limits

The probe waits for fonts and images, then records bound node/group rectangles, mixed-content text fragments, computed type, actions and visibility. Type shape uses a fixed glyph sample at 32px with measured advance, ascent, descent and raster ink density. It observes the resulting stack; it does not identify the resolved font file or model the entire typeface.

Materials use a 32x32 sample of the centered image crop, variance, edge energy and five dominant quantized color bins. This describes local image material, not semantic image understanding or occlusion-aware screenshot segmentation. Complex CSS background paint is unsupported and withholds selection. Passive local SVGs and embedded raster bytes are checked against their declared hashes.

Figure/ground uses exact union arithmetic over approximate occupied rectangles. Optical mass combines fragment area, weight, contrast and raster variance. Viewpoint continuity compares roles and region mass distribution, not a neural squint detector. Meaning comes from an attributed perspective binding, with no hidden model adapter.

The emitted page has native links/disclosures, visible keyboard focus, a skip link, reduced-motion CSS and responsive content retention. Functional selection rejects horizontal overflow, changed content/actions, clipped content, unreadable measured text and actions below the declared minimum height. This is focused functional verification, not a claim of comprehensive accessibility certification.

## Plan correspondence and stop boundary

The implementation covers AP-WP-00 model binding, AP-WP-01 kernel/relationship evaluation, AP-WP-02 generation/revision, AP-WP-03 all nine families in the documented domain, and AP-WP-05 portable operation. AP-WP-04 has executable comparisons, source attribution, grouped fitting and separate adoption. Its prospective human study is **not completed** by building those capabilities. Historical datasets remain historical; their thresholds and verdicts were not rewritten.

Tests establish numeric interaction, affine closure, typed-contract distinctions, duplicate rejection, missing-evidence refusal, immutable provenance, context isolation, dependency invalidation, deterministic proposals, constrained diversity, native interaction, actual geometry and fresh-package operation. Synthetic observations are test fixtures only. A mathematical non-additivity result is not evidence of human-perceived emergent beauty.

The first release is a complete working relational instrument for its declared semantic HTML domain. Additional adapters and larger models are optional expansion. Evidence that its choices improve human appreciation is still required before claiming dependable learned taste or universal beauty.
## Version 0.2: native frontend authorship

The recommended path is now `packet --mode native`, the default. The host AI keeps the project's existing frontend and its normal design capabilities. The packet provides `native/START-HERE.md`, a vocabulary of conditional relationships, an initially empty graph, and a portable runtime. It does not include the legacy renderer or nine-family model. `packet --mode engine` preserves the earlier implementation documented below.

`src/relations.js` is a browser-compatible numerical dependency evaluator. Inputs have names, values, explanations, and optional authored ranges. Derived nodes contain expression trees with references to other nodes. Bindings attach values to arbitrary CSS custom properties. It uses a topological traversal, rejects cycles/missing references/nonfinite arithmetic, and evaluates the entire graph before application. There are no default aesthetic constants or selected layouts. Units are applied at bindings; dimensional consistency remains the author's responsibility.

`src/native.js` packages the workflow and records native revisions. `describe --relations` resolves a graph without modifying a page. `revise --relations` changes declared inputs and emits a successor graph, CSS, resolved values, and a transitive dependency receipt. It marks the resulting page as unobserved. `src/relation-cli.js` calls the same revision implementation inside portable packets. `applyRelations` changes only the named custom properties on a supplied element. Host code retains markup, layout, assets, interactions, and responsive topology.

The design workflow begins with the intended encounter, uses normal AI composition, then makes consequential relationships explicit and revises through them. The host supplies semantic and visual interpretation openly. Numerical calculation verifies that a chosen relationship executes correctly; it does not rank the result's beauty. The practical saved-before/saved-after comparison is not a blinded baseline experiment.

Validation must distinguish two claims: preservation and propagation can be tested mechanically, while an improvement over normal AI design requires actual comparable designs and judgments. No result from the earlier generator or this module's software tests establishes the latter. This release also does not implement the separately proposed arbitrary-page bench adapter, `mn-74982c`.

---
