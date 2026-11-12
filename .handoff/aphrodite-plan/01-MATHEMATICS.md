# The mathematics of Aphrodite

Status: executable mathematical design for a proposed beauty model. The equations define what
to implement and test. Their connection to human appreciation is a development objective,
not a result already obtained by writing the equations.

## 1. The first principles

1. **Beauty belongs to configurations.** A typeface, color or rectangle has no context-free
   beauty value sufficient to determine the value of its placement in a page.
2. **Unity needs distinction.** Parts can belong to the same whole while doing different jobs.
   Perfect sameness and arbitrary variety are different ways to lose that relationship.
3. **Relationships have kinds.** Belonging, contrast, repetition, support, sequence and exception
   do not demand the same geometry or styling. Agreement sometimes requires difference.
4. **The whole acts back on the part.** A local choice changes its neighbors, the region and
   the page. A beautiful transformation must preserve or deliberately recompute those bonds.
5. **Beauty can be operationalized as a predictive generative model.** Its variables and
   interactions must produce testable rankings and constructive changes, not only prose.

These are chosen foundations for the instrument. They direct mathematical work toward beauty
instead of pretending that validity checks have already solved it.

## 2. The object being composed

Let `G = (V, E, H, R)` be an attributed visual hypergraph.

- `V`: semantic visual parts, including explicit empty regions. Text fragments belong to a
  meaningful text object; arbitrary DOM wrappers are not additional aesthetic parts.
- `E`: typed pair relationships, each with a scope and measurable descriptors.
- `H`: configurations involving three or more parts, or jointly binding several relationship
  channels. Examples include a heading/body/image constellation and a repeated sequence
  whose interruption announces a different task.
- `R`: nested perceptual/semantic regions and the page, with cross-region correspondences.

An element has geometry, type/paint/material descriptors, content role and observed visual
features. A relation can carry dimensionless separation, log size ratio, shared-edge residual,
relative hue/lightness, stroke relationships, direction, recurrence phase and semantic role
correspondence. Unsupported observations are marked unknown rather than numerically zero.

The context `c` contains the real content, tasks, brand constraints, intended character and
supported conditions. Character is a continuous/structured set of choices, not one of six
site classes. The reference names are not features available to the beauty evaluator.

The graph includes the **negative shape**: the space between groups, its connected passages,
and its relation to the foreground. Background color filling the screen does not erase that
space. The foreground and its surrounding field are composed together.

## 3. A concrete beauty functional

For a fixed context and model version, define a feature vector from the actual composition:

```text
F(G,c) = [local relational qualities,
          pair compatibility qualities,
          higher-order configuration qualities,
          continuity across regions and scales,
          unresolved relational conflicts]

B_theta(G | c) = theta^T F(G,c)
```

The final dot product is an interpretable combiner. **Its features are nonlinear relational
functions**, including products and configuration residuals. This is not a sum of independent
font, color and spacing grades. A linear combiner of nonlinear joint features is a nonlinear
model of the original page variables.

For clarity, its decomposition is:

```text
B_theta = B_parts + B_pairs + B_configurations + B_cross_scale - B_conflicts
```

`B_parts` is an explicit additive baseline retained for comparison. It contains contextual
material/role suitability, never a universal ranking of typefaces or colors. The product must
demonstrate useful gain from the other terms over this baseline. A model that learns all
configuration weights as zero has not fulfilled this design's central objective.

Every feature is aggregated over a declared eligible set with normalized weights. Region
weights sum to one within their level; relationship weights sum to one within their family.
An empty eligible set is inapplicable, not a perfect score. Required content missing from the
graph makes the composition ineligible. Cloning wrappers or redundant nodes cannot increase B.

Different briefs need not share an absolute beauty-number scale. B ranks alternatives under
the same bound context/model. Cross-context calibration is a separate learned capability.
The UI may show relational contributions and predictions without inventing a universal 0–100.

## 4. The compatibility kernel

For a relation descriptor vector `r`, use a contextual target `mu` and positive-definite
covariance `Sigma`:

```text
K(r; mu, Sigma) = exp(-0.5 * (r-mu)^T inverse(Sigma) * (r-mu))
```

K is a smooth affinity in `(0,1]`. It rewards the intended relationship, not maximal magnitude.
A contrast relationship has a nonzero target; an equality relationship has zero residual.
Circular angles use a wrapped circular distance, not linear subtraction across 0/360.
Invalid or unknown input does not evaluate to zero affinity; it remains unmeasured.

For more than one compatible arrangement, use a finite set of compatibility modes:

```text
K_family(r | c) = max_m K(r; mu_m(c), Sigma_m(c))
```

The family can represent several harmonic arrangements. It must not average two distinct
good arrangements into one mediocre midpoint. These are **relationship modes**, not stored
site layouts. Mode count is fixed before evaluation and penalized/selected during development
to prevent a separate perfect mode for every specimen. A generation prior over modes is
separate from beauty affinity: popularity or corpus frequency is not a beauty reward.
Their parameters omit site identity and are supported by explicit measurements,
authored mathematical proposals or learned preferences. No covariance or mode family is estimated
from too few examples and then called measured fact.

An initial diagonal covariance uses declared per-descriptor scales. A full covariance is an
optional learned successor only when the data support its additional parameters. The model
record identifies which values were proposed, derived or fitted.

## 5. The beauty-law catalog

Each law below defines a feature family and a generative action. These are the core of
Aphrodite. Mechanical accessibility, transport and schema checks remain supporting constraints.

### APH-01: relational consonance

**Claim to develop:** a coherent page makes its different visual channels tell compatible
stories about the same relationships.

For each semantic relation e, a **typed cue contract** predicts appropriate geometric, type,
paint and material cues. Compute channel affinities `k_e,g`, `k_e,t`, `k_e,p`, `k_e,m` against
that contract. Applicable channels form a joint affinity using their product or weighted
geometric mean, with its definition fixed in the model.

`belongs_to` may use proximity or enclosure while allowing different heading/body typography.
`same_role` may call for repeated typography across distant sections without spatial proximity.
`contrasts_with` may call for deliberate differences. Therefore the three original trees are
repaired into **typed relational correspondence**, not three partitions forced to be identical.

Generator action: choose a relationship, then derive its coordinated cues. Repair a broken
cue by moving the related choices together. Never score semantic truth from DOM nesting alone.

### APH-02: differentiated unity

**Claim to develop:** distinct roles become stronger when their differences belong to a common
system. Unity without differentiation becomes cloning; difference without unity becomes noise.

Let U be affinity to shared identity relations. Let D be affinity to **role-appropriate
distinctions**, not the raw amount of variation. Define the feature `Q_UD = U*D`.
Its mixed derivative with respect to U and D is 1: their joint payoff cannot be represented
as independent functions of U and D. The model weight sets its learned influence on B.

Generator action: bind a shared material/type/spacing identity, then derive distinct treatments
for roles inside that identity. A dense illustrated page and a spare textual page can both
have high U and D. There is no requirement for a particular amount of decoration.

### APH-03: proportion as a shared chord

**Claim to develop:** related proportions across several channels create a stronger order
than independently reasonable dimensions.

A chord is a small latent vector z and a declared map into dimensions:

```text
log(s_i / u) = a_i^T z + b_i + epsilon_i
```

`u` is a positive scale reference. The rows `a_i`, offsets and tolerances belong to a bound
relation program, not a free parameter per element fitted after rendering. The mapped values
can include display/body measures, group spacing, image proportions and internal boundaries.
The affinity is the residual of the selected correspondence after removing permitted overall
scale. Absolute task/legibility constraints are checked separately.

This need not use integer harmonic ratios or the golden ratio. If integer-note progressions
are used, note assignments and their finite range are fixed before the fit. Otherwise any
dimensions could obtain a perfect score by inventing a bespoke chord.

Generator action: change z once and recompute all bound dimensions. Feasible responsive
constructions preserve the chord or make an explicit coherent transition to another one.

### APH-04: figure and ground as reciprocal shapes

**Claim to develop:** a composition's occupied and empty regions strengthen each other.

Construct the foreground graph and its clearance-region adjacency graph. Measure ordered
ratios of inner/outer gaps, connected clearances, enclosure, alignment of passages and
foreground boundaries. Evaluate contextual kernels over these descriptors. There is no
global reward for more empty area or fewer nodes.

The joint feature couples a foreground grouping affinity with its supporting clearance
affinity: `Q_FG = K_foreground * K_ground`. A pleasing outline with clogged internal space,
or attractive emptiness around meaningless content, loses the joint benefit.

Generator action: a new cluster consumes and reshapes specific empty regions; spacing changes
recompute both graphs. Background surface, geometric void and perceptual negative shape
remain distinct observation channels.

### APH-05: counterpoint and hierarchy

**Claim to develop:** attention is organized by purposeful differences and counterweights,
not by maximizing one focal point or making every region equally strong.

The context specifies priority relations, including equal-priority comparisons. The observer
supplies declared salience descriptors or a pinned perceptual adapter. Affinities compare
relative emphasis, spatial counterweight and task order with the chosen hierarchy. Optical
mass estimates carry the adapter version; rectangle area is only a geometric baseline.

Tension uses a smooth target affinity for the intended difference. Too little and too much
can both lose affinity. A nonzero target can reward asymmetric balance and strong contrast.
No monotonic “more contrast”, “more symmetry” or “more uniqueness” reward is present.

Generator action: change the lead/support relationship jointly through position, measure,
type, field or material. Multiple foci remain possible when the task requires them.

### APH-06: recurrence, development and resolution

**Claim to develop:** recognizable relationships can develop across a page without either
mechanical repetition or unrelated changes from section to section.

Represent each recurring role's descriptor trajectory as `y_0,...,y_n`. The composition program
binds intended changes `d_k` to semantic transitions. A continuity residual is
`sum_k ||(y_(k+1)-y_k)-d_k||^2`, evaluated with typed scales and normalized eligible weights.
An interruption is a declared developmental event, not an automatically penalized deviation.

A sequence that repeats perfectly can still serve a comparison task. A narrative may require
different d values. Generator action: vary the shared trajectory, then derive local states.
The target trajectory cannot be rewritten to match every observed accident after the fact.

### APH-07: material and meaning resonance

**Claim to develop:** geometry, type, color, texture and depicted material become more beautiful
when their expressive relationships reinforce the subject and one another.

Use measurable descriptor channels where possible: type width/x-height/stroke contrast,
surface lightness/chroma, motif curvature/stroke, image palette/crop, texture frequency and
geometric density. Symbolic/semantic descriptors may be supplied by an attributed host or
pinned model adapter, but the beauty weights and evaluation kernels are saved mathematical
objects. A free-form critic does not turn its opinion into the score.

Evaluate joint affinities over these descriptors conditioned on the chosen intention and
real material. Literal similarity is one possible relation; a deliberate complementary
contrast is another. A strong graphic frame around soft photography may be a compatible mode.

Generator action: move a shared character variable through several channels at once. Color
is not an independent finishing pass after geometry. A richer palette or expressive type
can require a different spacing, surface and hierarchy solution.

### APH-08: higher-order constellation

**Claim to develop:** some aesthetic value exists only when several relationships hold together.

For a declared configuration h with applicable affinity values k, define a feature:

```text
Psi_h = product_e_in_h k_e
```

An optional configuration descriptor can also have its own multivariate kernel. Its scope,
normalization and relation count are fixed in the model. Do not compare raw products of
arbitrarily different numbers of factors as though their scales were equal. Configuration
families have separate normalization or a fixed-arity signature.

Use products for explicit conjunction benefit; use geometric means for scale-comparable
affinity summaries. They are different features and must not be silently substituted.
Compute in log space when necessary, preserving exact zero and underflow policy.

For three independently manipulated relational qualities g,t,c, the term `gamma*g*t*c`
has a nonzero mixed finite difference. It provides the mathematical place where the whole
can gain something no isolated node receives. Chapter 5 calculates an example.

Generator action: optimize or construct a whole constellation. A step that improves one
relationship while destroying the others can reduce the joint value even if that local
relationship becomes individually stronger.

### APH-09: coherence across scale and viewpoint

**Claim to develop:** a strong composition retains useful organization at page, section,
component and text-detail scales, while allowing different information at each scale.

Use a region hierarchy plus rendered scale-space descriptors. Correspondences preserve
which groups and priorities should remain visible at each scale; local detail may disappear.
Use contextual trajectory kernels, not a universal blur slope or a flat acceptable interval.

Generator action: adjust the coarse composition and its fine relations together. Squint
measurements become an input to this family, not a standalone verdict about beauty.
Viewport transformations also rebind the appropriate hierarchy; pixel identity is unnecessary.

## 6. Constructing beauty rather than appending a score

A generator `Gamma_c` maps a small set of independent variables z into a full composition:

```text
G = Gamma_c(z; theta)
M_c = { Gamma_c(z;theta) : z in Z_c and construction constraints hold }
```

The controls in z describe joint decisions: a proportional chord, hierarchy, density strategy,
material inflection or rhythm development. They do not expose every CSS property as an
independent aesthetic dial. Constructors expand these decisions through the relation graph.

For a linear log-dimension relation `C*x=d`, parameterize `x=x0+N*z`, where columns of N
span C's null space. Then `C*x=d` holds for every z in the admitted domain. Exponentiation
recovers positive dimensions; bounds restrict z. This is an exact example of a constructive
guarantee. Nonlinear/color/state relationships use their declared coupled constructors and
post-render checks rather than an unsupported claim of a global analytic solution.

The emitted set is:

```text
E_c = { G in M_c : required content/function holds,
                  actual-render B_theta(G|c) >= tau_c,
                  required model/observation support is present }
```

For several required conditions q, apply the beauty/support requirement to each
`B_theta(G_q|c_q) >= tau_q`. A high desktop value cannot compensate for a missing or poor
required narrow layout. Cross-condition relationships also contribute to APH-09.

`tau_c` is calibrated or explicitly selected for a declared context/support domain. It is not
the historical all-corpus kill threshold. Exploration can inspect lower-scoring and unsupported
proposals with their status; it cannot stamp them as belonging to E_c. The model, thresholds,
cue contracts and parameter domains are fixed before the candidate is optimized. Otherwise
the generator could make every candidate pass by moving its own target.

This is the engineering meaning of “cannot build anything but beauty”: the ordinary generation
path emits only compositions constructed within, and verified against, its beauty model.
Calling that model an adequate account of human beauty requires evidence. A mathematical
membership proof cannot by itself guarantee everyone's response to every possible future
brief. The research and build must earn a broad reliable domain instead of abandoning the
ambition or presenting a circular definition as a discovery.

## 7. Required invariances and anti-degeneracy

The beauty representation must be invariant to DOM wrapper insertion, source-code minification,
stable ID renaming and unpainted metadata. Appropriate dimensionless relationships survive
uniform geometric scaling while absolute usability obligations remain separate. Empty content,
duplicated boxes, invisible text and independently reset per-node targets cannot manufacture
high scores. More relationships do not mean more beauty unless the declared eligible structure
actually changes meaningfully.

Repeated components share parameters but retain their genuine content differences. A new
image, font or language changes the measured graph and can require a different z or constructor.
The engine predicts the resulting beauty gain or loss, constructs a repair, and recomputes
it on the render. It does not merely ask a reviewer to invent a replacement verdict.

## 8. Mathematical provenance

The architectural analogy to Aldebaran is specific: preserve measured relationships in a
record and apply named, versioned interpretive rules without rewriting those observations.
The live `../aldebaran-group/ORCHESTRATOR-MAP.md`, especially sections 0 and 3, is the entry
source for that split. Aphrodite adds a numerical beauty model and a generative inverse:
instead of only reading a given configuration, it constructs a configuration that satisfies
and strengthens the desired relationships. No astronomical doctrine or estate acceptance
gate is imported as a law of visual beauty.

Shape grammars supply a precedent for generating families from structural and material
relationships; they do not already solve this website beauty model.
[Stiny and Gips, author-posted paper](https://www.researchgate.net/publication/221329330_%27Shape_Grammars_and_the_Generative_Specification_of_Painting_and_Sculpture%27).

The distinction between redundant and synergistic information has a formal information-theory
literature. Aphrodite's mixed differences are explicit model interaction tests; they are not
claimed to be a partial-information decomposition or a measured neural-complexity quantity.
[Williams and Beer](https://arxiv.org/abs/1004.2515).

The proposed kernels, feature decomposition, typed correspondence repair and constructive
parameterization above are the implementation design here. Their empirical authority comes
from the development/evaluation program specified next, not from borrowing a theorem's name.
