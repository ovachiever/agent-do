# Worked mathematics and generative examples

The numbers below are exact illustrative fixtures for the proposed model. They are not
measurements from the twelve pins, fitted coefficients or observed human preferences.

## 1. The same ingredients, a different whole

Consider a heading, supporting paragraph and image. Keep the inventory of content, imagery,
type treatments and palette fixed. Manipulate three relational qualities:

- g: how the geometry groups and distinguishes the roles;
- t: how the available type treatments are assigned to those roles;
- c: how the available material/color relationships support that grouping.

This factorial example changes arrangements or assignments, not the inventory. The stricter
placement-only experiment in chapter 4 preserves every node's complete appearance while
moving it. These are related but different tests and must not be reported interchangeably.

Give the independent-parts baseline an arbitrary constant value 10. Define a configuration
feature with coefficient 2:

```text
B(g,t,c) = 10 + 2*g*t*c
```

For each relational affinity, use 0.2 for its lower state and 0.9 for its higher state:

| Geometry | Type assignment | Material relationship | B |
| --- | --- | --- | ---: |
| 0.2 | 0.2 | 0.2 | 10.016 |
| 0.9 | 0.2 | 0.2 | 10.072 |
| 0.2 | 0.9 | 0.2 | 10.072 |
| 0.2 | 0.2 | 0.9 | 10.072 |
| 0.9 | 0.9 | 0.2 | 10.324 |
| 0.9 | 0.2 | 0.9 | 10.324 |
| 0.2 | 0.9 | 0.9 | 10.324 |
| 0.9 | 0.9 | 0.9 | 11.458 |

Improving one quality in isolation gains 0.056. Summing those three isolated gains gives
0.168. Improving all three together gains 1.442. The additional 1.274 is the improvement
beyond that sum; it contains both pair and third-order interaction contributions over these
finite changes.

The pure third-order mixed difference isolates the three-way contribution:

```text
I_gtc = B111 - B110 - B101 - B011 + B100 + B010 + B001 - B000
      = 2 * (0.9 - 0.2)^3
      = 0.686
```

Any model of the form `f(g)+h(t)+j(c)` gives zero for this difference. So does a model with
only pair interactions. The proposed three-way feature is mathematically different from
adding independent ratings, even though the final feature combiner is a dot product.

This is a place to encode emergent beauty, not evidence that this particular product is the
right human beauty law. Its coefficient and context must earn their place through the actual
comparison. If the interaction does not help, replace its mapping or structure rather than
claiming victory because 0.686 is nonzero.

## 2. A transformation that preserves a relationship by construction

Let x contain the logarithms of display size H, body size T and related gap Q, expressed
relative to the same unit. Select ratios r and k for a bound construction:

```text
log(H) - log(T) = log(r)
log(Q) - log(T) = log(k)

C = [[1,-1,0], [0,-1,1]]
d = [log(r), log(k)]
x0 = [log(r), 0, log(k)]
N = [[1], [1], [1]]
x = x0 + N*z
```

`C*N = 0` and `C*x0 = d`. Therefore every allowed z preserves the two relations. With
`u=exp(z)`, the generated dimensions are `H=r*u`, `T=u`, `Q=k*u`.

An illustrative choice `r=3`, `k=2`, `u=18` gives H=54, T=18 and Q=36. Changing u to 20
gives H=60, T=20 and Q=40. The whole moves together. These ratios are fixture values, not
mandated ratios for every website or estimates from the corpus.

The browser can introduce line wrapping, different glyph extents and layout limits. Those
are observed constraints. If a wrap changes the constellation, derive a compatible reflow
or choose another allowed construction. Do not preserve the equation by clipping a heading,
shrinking text secretly or dropping its supporting information.

The exact proof is about the two chosen relations. It is not a proof that r=3 is intrinsically
beautiful. B evaluates their contribution in the complete context, including type/material
and the other relationships. Exact construction and beauty prediction have distinct jobs.

## 3. Why perfect sameness is not the objective

APH-02's `Q_UD=U*D` joins common identity with appropriate role distinction. For illustration:

| Arrangement | U | D | Q_UD |
| --- | ---: | ---: | ---: |
| Every role given the same treatment | 1.0 | 0.0 | 0.0 |
| Every role unrelated to the others | 0.0 | 1.0 | 0.0 |
| Clear role differences inside a common system | 0.8 | 0.8 | 0.64 |

D measures the affinity of role distinctions, not a count of different styles. These are
input fixtures chosen to show behavior, not human labels attached to actual pages. A repeated
comparison row can legitimately give equivalent roles identical treatment while distinguishing
its title, values and controls. It need not invent decorative exceptions to achieve D.

This directly addresses the self-teaching/size-chord failure pattern: low variance and a
simple ladder do not by themselves win. Shared order must cooperate with meaningful variety.

## 4. Repairing the Three Trees relationship

Use four parts: heading A, body A, heading B and body B. Their semantic relations are:

```text
belongs_to(heading A, body A)
belongs_to(heading B, body B)
same_role(heading A, heading B)
same_role(body A, body B)
contrasts_with(heading role, body role)
```

A good configuration may use close within-group spacing and repeated typography across
groups. Its spatial groups and style groups therefore cross. Forcing their partitions to
be identical destroys the intended design.

The repaired kernel evaluates each typed edge against its own cue contract: affiliation
through proximity/enclosure, role identity through repeated treatment, and hierarchy through
appropriate contrast. A configuration feature binds those successes. An intervention swapping
body A's visual affiliation toward heading B should reduce the relevant affinities without
pretending that all repeated headings must sit next to one another.

The old Three Trees score remains an observable comparator. It is not overwritten with this
new quantity, and the historical 8/10 is not claimed as the repaired model's result.

## 5. Three original briefs, one mathematical vocabulary

These are proposed demonstrations of the generator, not rendered designs or approved recipes.
Their content and asset requirements must be supplied before implementation can run them.

### A community night market

The task graph connects stalls, opening times, locations, food photographs and directions.
Equivalent stall roles need comparison; a featured event can have a different priority.

One possible derivation is `Page -> Sequence(event anchor, Partition(stalls, visit support))`.
Another is a field organized around the venue, if wayfinding is the central task. GR productions
generate both. APH-01 binds each item to its location/time, APH-02 keeps distinct vendors inside
one market identity, and APH-07/08 can coordinate emphatic lettering, photographic warmth,
colored fields and generous internal spacing. Density is purposeful, not a penalty.

The material mode determines multiple variables together. Making the identity louder can
change type width, color relationships, border/stroke rhythm and the spaces carrying them.
The result must earn a high B in its context, not obtain points simply for being colorful.

### A ceramics archive

The task graph connects objects, makers, material, dimensions, acquisition details and essays.
The image is evidence; text supports inspection rather than competing with every object.

Possible derivations include a repeated comparison sequence or an object-led field with
supporting annotations. A shared proportional map relates the image window, caption measure,
column interval and display treatment. Negative shape and object silhouette become a coupled
APH-04 problem. Material modes may connect restrained interface strokes with clay texture,
or use an intentional graphic contrast. Neither choice is prescribed by the brief's noun.

Adding a wide shallow object can change crop, neighboring clearance and caption measure
together. Copying a pin's hero layout would not solve that relationship problem.

### A neighborhood repair service

The task graph contains urgent contact, repair categories, availability, evidence of work
and a booking path. Priority differs from an archive because access to the action matters.

Possible derivations include a lead/support cluster followed by a comparison sequence, or
a compact field with services and availability as counterweights. APH-05 governs prominence
and counterpoint. APH-06 carries a visual identity from the first decision through evidence
and booking without giving every section the same arrangement.

The service can use a warm illustrated identity or a precise functional one. Those are
alternative relational/material modes, not fixed “SaaS” and “maximalist” categories. B and
the actual task contract decide among admissible candidates. The page displays real repair
information, not the phrase “counterpoint of care” because an internal rationale used it.

## 6. What the first demonstration must show

Show a generated original design, its graph, its computed relational contributions, and a
coupled edit with the resulting render. Include the additive and pair-only comparisons.
Show a counterexample when the objective gets something wrong. Record Erik's response without
using it to retroactively alter the already recorded model run.

The intended demonstration is simple: the instrument sees a relationship that isolated
ingredient ratings miss, creates a stronger configuration through that relationship, and
preserves its coherence when the design changes. That is the beauty claim this plan commissions
the future implementation to pursue.
