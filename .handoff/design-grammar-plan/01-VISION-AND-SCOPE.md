# Vision, scope, and requirements

Status: proposed design for `mn-27e068`. Implementation is not started.

## 1. Product thesis

The instrument makes design decisions explicit and related. It can describe which element
leads, how supporting elements gather, where space creates separation, how a material or
type treatment carries meaning, and which relationships must survive a change.

The creative thesis is that coherent differences can form a meaningful whole. This is a
working design position, not a discovered equation of aesthetic value. Exact geometry can
support several valid visual readings. A character frame declares one reading and its
conditions; it never changes the underlying observations to make the reading appear true.

The AI's native working medium is a graph of content, roles, constraints, and transformations.
It can inspect that graph, construct a candidate, render it, and compare intention with
observed consequences. The human sees the resulting website and, when useful, an explanation
of consequential choices. Internal rule IDs and instrumentation do not leak into product UI.

## 2. User experience

The author supplies the site's purpose, audience, real content or an explicit content-writing
scope, target environment, existing brand obligations, and assets. The session resolves
missing information that changes the task; ordinary tunable decisions stay with the session.

The instrument then:

1. Produces an inspectable brief with locked requirements and clearly labeled assumptions.
2. Forms a content and action graph, including required pages and states.
3. Proposes distinct composition programs and character hypotheses within that brief.
4. Compiles a selected program into runnable HTML/CSS and supported interaction bindings.
5. Observes the actual output at the required conditions, including text, media, and controls.
6. Identifies precise mismatches, proposes bounded changes, and checks their consequences.
7. Delivers the website, its source, coverage receipt, unresolved limits, and decision record.

User selection of a visual direction is supported. An author may also delegate candidate
selection to the session. Such selection is recorded as model selection, never human approval.
A fresh session must be able to continue from saved artifacts without this conversation.

## 3. First-release expression domain

Included: responsive browser websites and interfaces built from semantic HTML, CSS layouts,
text, image/video assets, static or externally rendered SVG, and common native controls.
Compositions include landing pages, editorial pages, catalogs, product/detail pages, forms,
navigation, documentation, and information-dense application screens. Lists and data tables
are first-class content structures. Marketing pages alone cannot satisfy this scope.

Included state families: default, hover where meaningful, focus, active, selected, expanded,
disabled, loading, empty, success, and error. Applicability is declared per control and page;
the system does not instantiate every state on every element. Input modalities, language,
writing direction, reduced motion, zoom/reflow, and container size are conditions.

Generated layouts support horizontal LTR and RTL writing modes in the first-release gate.
Vertical writing is represented in observations and explicitly marked unsupported for
generation until its adapter and tests exist. It is an extension obligation, not silently
treated as horizontal. Custom canvas/WebGL scenes and closed third-party widgets are opaque
assets or components with declared contracts; their internal geometry is not inferred from
their host element. Their accessibility and behavior remain separate review obligations.

Excluded from the first-release implementation: native mobile layout compilers, print layout,
logo/typeface invention, 3D scene generation, a general image-generation model, autonomous
production transactions, and backend business logic. Asset briefs and action contracts are
included so these capabilities can be supplied by their existing owners.

The default compiler emits a runnable web bundle. A React or other framework adapter is an
optional subsequent adapter, selected by the owning project. The design representation and
rule engine do not depend on a frontend framework.

## 4. Explicit requirements

| ID | Requirement | Observable completion evidence |
| --- | --- | --- |
| REQ-01 | General rules independent of site identity | No site-name branches, reference assets, or reference-specific token defaults in core; new-brief trials |
| REQ-02 | Geometry and empty space represented | Box/fragment observations, relational queries, clearance regions, applicability and coverage receipts |
| REQ-03 | Meaning and visual character explicit | IntentFrame and CharacterFrame bind choices to content, audience, tasks, and assumptions |
| REQ-04 | Coupled design decisions | Typed dependency graph invalidates affected text, geometry, assets and states after changes |
| REQ-05 | Original generation | New content and permitted assets; multiple structural and material choices; copy audit |
| REQ-06 | Functional browser delivery | Compiled pages, action contracts, supported state transitions, real browser receipts |
| REQ-07 | Responsive and input-state coverage | Condition matrix includes feasible breakpoints, LTR/RTL, keyboard and applicable interaction states |
| REQ-08 | Accessibility obligations explicit | Versioned standards profile, per-criterion disposition, mechanical checks and named manual review |
| REQ-09 | Facts and judgment remain distinct | Observation, interpretation, generated proposal and human-verdict records have different types |
| REQ-10 | Partial evidence stays partial | Missing DOM, unloaded media, unsupported paint and unvisited states cannot yield a complete claim |
| REQ-11 | Fresh-session usability | Entry discovery, packet integrity and end-to-end continuation tested without thread history |
| REQ-12 | Repeatability | Saved proposals, seeds, content, assets, core and renderer versions reproduce the same compilation |
| REQ-13 | Bounded revision | Explicit budgets, conflict reports, cycle detection and durable resumable state |
| REQ-14 | Existing-tool integration | Browser runs through agent-do browse; DPT remains an annotation adapter |
| REQ-15 | Generalization tested honestly | Whole-reference holdouts, new briefs, model/version disclosure, non-pooled failure breakdowns |
| REQ-16 | Human verdicts preserved exactly | Immutable scoped events, no negative labels inferred from silence, no model self-ratification |
| REQ-17 | Portable local ownership | Versioned files and export bundle work across sessions and machines; no service dependency |
| REQ-18 | Complete first-release rule coverage | Every rule has applicability, implementation owner, tests, and an explicit result disposition |
| REQ-19 | Content and assets are substantive inputs | Real text lengths, missing assets and subject matter affect composition; no hidden placeholder pass |
| REQ-20 | Current commission ends at planning | Documents and receipts only; no installed engine, new verbs, browser runs or research changes |

## 5. The meaning layer

An IntentFrame records the work a design must do. Fields describe audience, primary and
secondary tasks, content priorities, desired experience, context, and prohibited effects.
An archetypal description such as sanctuary, workshop, observatory, or marketplace is allowed
as author language. It expands into explicit proposals about reading pace, gathering,
emphasis, material treatment and interaction. It has no universal color or geometry mapping.

A CharacterFrame records proposed expression across typography, surface, palette, imagery,
mark-making, density, cadence, and motion. These axes can overlap, vary by region, and acquire
new named values. The corpus register map is descriptive metadata outside the runtime grammar.
An expressive frame is not selected by a six-class classifier.

Every consequential aesthetic choice has a reason, a source category, a scope and a possible
counterexample. Reasons are concise and testable against the brief: a photograph carries
necessary product information; a narrow measure supports sustained reading; contrasting
surface bands distinguish task phases. A generated reason is still an interpretation.

The system does not infer personality, spirituality, or brand values from geometry as facts.
The esoteric ambition is supported through explicit symbolic readings and transformations,
with the same factual substrate available to other readings.

## 6. What is already present and what is missing

Present: twelve human-approved site pins, twenty-nine image files across the current shots
directory, older rendered design rounds and human verdicts, a browser tool, a DPT scanner,
coordination, task tracking, discovery and local document delivery. Counts are from the
planning snapshot and are not runtime constants.

Missing: a versioned composition representation; operator implementations; a relationship
observer with coverage; asset and intent contracts; a compiler with source mapping; a
dependency-aware revision protocol; the portable session packet; and evidence that the
combined process improves original designs across unfamiliar briefs.

The seven added pins broaden expression examples. They do not resolve mobile coverage,
interaction coverage, or independent generalization. Sources and caveats are itemized in
[Sources and corpus](11-SOURCES-AND-CORPUS.md).

## 7. Completion and extension rule

First-release completion requires all REQ-01 through REQ-19 within the declared domain.
An early implementation may be useful but must report its missing catalog and condition
coverage. No scalar aesthetic score can substitute for these separate findings.

New primitives require a type signature, semantic and geometric invariants, a lowering rule,
observation support, failure cases and tests. New interpretive frames require documented
scope and evidence; they may remain hypotheses. Neither kind is added merely to reproduce
a particular reference website.
