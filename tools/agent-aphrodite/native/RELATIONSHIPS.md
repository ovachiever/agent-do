# Relationships a designer can compose with

These are ways of thinking and making, interpreted through a particular subject. Their equations express a chosen relationship. They do not establish that the relationship is beautiful, and they do not add up to a beauty score. Reference values come from the actual composition being developed. Coefficients are declared design decisions with a reason and a scope.

## Counterbalance: one presence changes the space around another

For a chosen heading size `H`, reference size `H0`, reference gap `G0`, and authored elasticity `e`:

`G / G0 = (H / H0)^e`

Negative `e` makes space contract as the heading grows. Positive `e` lets space expand with it. Zero keeps that gap stable. Which movement supports the page depends on its density, the heading's shape, line breaks, and surrounding material. Erik's large-headline/small-gap and small-headline/large-gap preference supports trying compensation in that specimen. It does not determine a universal exponent.

The same family can relate a product's apparent size to its surrounding field, a line's thickness to the radius it encloses, or a dense block to the pause after it. Check that those interpretations actually help the particular composition.

## Shared ancestry: a family with recognizable differences

`x_i = origin + scale * variation_i`

An alignment, stroke, hue component, spacing interval, or motion duration can share an origin while its local variation carries meaning. Changing the origin moves the family together. Changing a variation changes one member's role in the family.

For example, a publication's title, captions, rules, and folios may share one vertical rhythm while occupying very different amounts of space. Uniform cards are only one possible implementation of repeated identity.

## Counterpoint: agreement makes a difference legible

Represent a treatment as several independently meaningful axes, such as alignment, scale, weight, hue, texture, and temporal behavior. Let related elements agree on the axes that identify their relationship, and differ on the axes that express their jobs.

For a numeric axis, `x(t) = (1 - t) * a + t * b` interpolates between two authored treatments. Interpolating color components is a construction choice, not a perceptually uniform color model. Typeface families, materials, and image subjects often need a deliberate discrete choice instead.

An important number can differ greatly in scale from a label while inheriting its baseline and ink. A playful illustration can be contained by rigorous alignment. The agreement is what lets the departure feel intentional.

## Rhythm: recurrence, departure, return

`interval_i = base * phrase_i`

The phrase is authored from the sequence of reading and action. A repeated working row may use a steady interval; a change of task may introduce a larger pause; a later section may recall the earlier rhythm. The relationship is between passages, not between every pair of neighboring boxes.

When a long section feels dead, consider whether its phrasing has disappeared. When a page feels fragmented, consider whether every element announces a new phrase. Either intervention can be wrong in the opposite context.

## Partition: divide a real field without losing the relationship

`usable = container - startInset - endInset - gap`

`first = share * usable`

`second = (1 - share) * usable`

The share follows content and the desired encounter. At another width, the right expression may be a sequence, a scrollable comparison, or a different arrangement entirely. Preserve reading order and available actions when changing topology. Let real text wrapping, intrinsic media sizes, and controls reveal where reflow is needed.

Native CSS grid, flex, container queries, and intrinsic sizing often express this better than precomputed pixels. Use the graph for the shared parameters, not as a replacement layout engine.

## Density and breathing space: decide where attention is spent

`local density = occupied area / available area`

This is a descriptor only. Bounding rectangles, visible ink, and perceived occupation are different quantities. Decide which you measured before reasoning from it. A useful comparison is often within the same page: working rows against navigation, a featured passage against its supporting material, or a dense section against the pause that follows it.

Density can create clarity in an instrument and overwhelm an introduction. Sparse space can create poise or make a tool feel empty. There is no prescribed density target. Coordinate grouping, type, and breathing space around the person's task.

## Material echoes: geometry and character answer each other

A visual voice spans several media. An illustrated contour may echo a typeface's curvature. A photograph's horizon may continue a text baseline. A recurring color can identify a function or connect a distant section. A texture can provide warmth while geometry provides precision.

The host AI uses its visual knowledge to choose those correspondences. An image's average color does not determine its meaning. Record the intended correspondence, implement it through real assets and frontend code, and inspect whether the echo is actually visible.

## Whole and parts: revise the relationship that creates the symptom

If one button seems loud, examine its relationship to the primary action, the surrounding density, repeated accents, and the image's attention. The useful change might be elsewhere. If a headline feels weak, examine its setting, line break, contrast, and supporting space before making it larger.

For a proposed move, write its expected joint effect: `change A and B together → consequence C`. Render that alternative. If changing A alone or B alone seems equally useful, the joint claim may be unnecessary. This is a design comparison, not statistical evidence unless an independent study actually supplies that evidence.

## Runtime reference

The portable `runtime/relations.js` exports:

- `resolveRelations(graph, overrides)`: derive values, CSS variables, and dependencies without modifying the page.
- `reviseRelations(graph, overrides)`: return a successor graph and the affected dependency chain.
- `relationStylesheet(resolved)`: emit the bound variables under `:root`.
- `applyRelations(element, graph, overrides)`: set only those variables on an existing element after successful evaluation.

Graph shape:

```json
{
  "schema": 1,
  "kind": "native-design-relations",
  "intent": "The intended relationship in this particular design",
  "inputs": {
    "presence": {"value": 1, "why": "An authored starting coordinate"}
  },
  "relations": {
    "relativeGap": {
      "expr": {"op": "power", "args": ["presence", -1]},
      "why": "A reciprocal demonstration, not an established taste law"
    }
  },
  "bindings": {
    "--relative-gap": {"node": "relativeGap", "unit": ""}
  }
}
```

Expressions are numbers, node names, or `{op, args}` objects. Operators: `add`, `multiply`, `subtract`, `divide`, `power`, `min`, `max`, `clamp(value, low, high)`, and `mix(a, b, t)`. The runtime evaluates data, never JavaScript expressions. Cycles, missing nodes, nonfinite results, and unknown overrides fail before application. Inputs may declare a context-specific `range: [low, high]`.

Bindings accept `""`, `px`, `rem`, `em`, `vw`, `vh`, `vmin`, `vmax`, `%`, `deg`, `s`, and `ms`. Calculation uses numeric coordinates; the author is responsible for consistent units. Binding a number to `px` does not prove that its expression is dimensionally meaningful. Use dimensionless ratios to connect quantities measured in different units.

Arbitrary input names, derived nodes, CSS variables, and frontend structures are supported. Nonnumerical decisions remain in the host's design notes and code. A revision's `renderStatus` is `unobserved` until the working frontend has actually been inspected.
