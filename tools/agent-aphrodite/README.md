# Aphrodite

Aphrodite constructs original semantic web pages by varying shared geometric and material relationships, measuring their rendered consequences, and selecting under a frozen perspective. It also revises compositions, records attributed comparisons, proposes learned weights, and packages the same executable system for another session.

The operating principle is relational: a correction changes the relationship that produced an outcome. The engine does not accept a CSS patch as a revision. Content, intended roles, material sources, and perspective are explicit inputs. A site's identity is not a template selector.

Version 0.1.0 includes all nine family evaluators and the complete generation-to-export workflow. Its initial perspectives are authored hypotheses. Their numerical outputs are within-context predictions of harmony, not established measurements of human beauty. Historical WP-0 failures remain failures. This software release does not claim that the prospective human study has passed.

## Start

Requires Node 20 or newer and the existing `agent-do browse` installation. There are no npm dependencies, external model calls, or hosted services.

```bash
agent-do aphrodite doctor
agent-do aphrodite init --example tideline --out .dev/tideline-context
agent-do aphrodite compose --context .dev/tideline-context/context.json --out .dev/tideline-run --seed 1 --budget 6
agent-do aphrodite export --run .dev/tideline-run --out .dev/tideline-site
```

Open `.dev/tideline-run/index.html` to compare the measured proposals, or `.dev/tideline-site/page.html` for the selected working page. Every output path must be new. The other original example briefs are `objects` and `assembly`. They are fictional demonstrations with local original SVG materials, not approved corpus sites.

For a new project, author a brief using an example as a schema reference, replace its content, semantic structure, materials and intention, and run:

```bash
agent-do aphrodite compose --brief project-brief.json --out .dev/project-run --seed project-1 --budget 8 --steps 2
```

`budget` limits the complete run to 1–48 proposals, including refinement. `steps` reserves part of that budget for measured changes to shared coordinates. A fixed seed, context and engine reproduce the program proposals. Browser measurements depend on the actual fonts, browser and environment; they are saved, not represented as environment-independent constants.

## The design language

A brief declares:

- **Nodes:** real text, images and actions with roles and priority. Required content is never dropped to improve the result.
- **Groups:** semantic containment and allowed compositions. Groups can partition, sequence, cluster, place satellites around an anchor, or overlay a foreground on a material field.
- **Relations:** `supports`, `same-role`, `contrasts`, `aligns`, `sequence`, and `counterweight`. Each relation cites its source.
- **Constellations:** exactly three distinct relations involving at least three parts. These make an explicitly non-additive prediction.
- **Perspective:** a sourced interpretation of how these relationships should work together. `counterbalance`, `procession`, and `counterpoint` demonstrate compensating, developing, and contrasting relationships.
- **Conditions:** two to five viewports and the required base/expanded states. All must be measured before selection.

The brief owns meaning. The browser owns observation. The frozen mathematical model owns selection. A host AI can author a brief, but its authorship is explicit; it does not become an invisible judge. Intent and source notes stay in the artifacts, while only actual product content enters the rendered page.

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for equations, data contracts, architecture, limits, and the relationship to the original plan. Every target and scale used by the current perspective kernels is in [perspectives-v1.json](models/perspectives-v1.json). The constructors and descriptor methods are versioned with the engine.

## Revise and vary

```bash
agent-do aphrodite revise --run .dev/project-run --set presence=1.2 --set tempo=0.9 --out .dev/project-revision
agent-do aphrodite vary --run .dev/project-run --seed alternate-2 --budget 8 --distance 0.25 --tolerance 0.05 --out .dev/project-alternative
agent-do aphrodite observe --run .dev/project-revision --out .dev/project-reobserved
```

The five controls are `presence`, `tempo`, `balance`, `character`, and `scale`. A change can alter headline size, gap, sibling proportions, outer space, typography, stroke, curvature, and tint together. The revision receipt lists the invalidated descendants. The successor is rendered and measured before it is selectable.

Variation requests a minimum structural distance from the prior selection, within a declared affinity tolerance. There is no novelty bonus. If the bounded search cannot meet both conditions, it returns no selection. Larger budgets permit exploration; they do not promise uniqueness or a global optimum.

Changing content, a font stack, material, roles, or intention means binding a new context from the revised brief. Do not mutate an existing context or swap its model while comparing candidates. Generated CSS belongs to the constructor; change the constructor relationship for a general capability change, or use the existing shared controls for a composition change.

## Compare, learn, adopt

```bash
agent-do aphrodite study --run .dev/project-run-without-refinement --out .dev/project-study
agent-do aphrodite feedback --run .dev/project-run --left c000 --right c001 --choice left --quote 'EXACT HUMAN RESPONSE' --source 'conversation or record reference' --author 'Rater name' --group 'independent brief family' --out .dev/preference.json
agent-do aphrodite fit --records .dev/preference.json --out .dev/model-proposal
```

The feedback command records an actual response, not a response to infer or invent. `tie` and `neither` are supported. `neither` is retained but excluded from binary preference fitting. The fitter trains one rater's target at a time, normalizes contribution by declared source group, and accepts repeatable `--records` and `--holdout` arguments. Entire held-out groups stay out of optimization. It fits nine nonnegative family weights with eight free dimensions, regularization and an explicit iteration budget. It does not fit the many kernel and construction parameters from a tiny preference set.

`study` re-evaluates one frozen proposal pool under full, pair-only and part-only objectives. It requires a run with zero adaptive refinement to preserve a matched pool. Its human-response field starts empty. A different numerical ordering demonstrates a different model, not superior human taste.

Fitting proposes a new model file and never adopts it automatically. An optional `adopt` operation needs an explicit acceptance JSON containing `modelDigest`, `domainDigest`, `author`, `source`, `quote`, and a contextual `minimum`. The new model can then be bound to a new context. `export --release` requires that adopted domain and threshold. Ordinary `export` is usable immediately and carries the current exploration claim. Adoption records a person's decision; it does not certify a population-level law.

## Fresh session and artifacts

```bash
agent-do aphrodite packet --context .dev/tideline-context/context.json --out .dev/tideline-packet
agent-do aphrodite verify --run .dev/tideline-run
```

Hand the new session `START-HERE.md` from the packet. It contains the bound brief, embedded material bytes, frozen model, and executable engine. The engine in that folder can generate, evaluate, revise and export with Node and the existing browse transport. It needs no conversation history. A bound packet carries one project's context; author a new brief to change the project.

Each run retains its request, context, grammar beam, complete candidate programs, original HTML, viewport/state observations and screenshots, family/relationship decompositions, failed attempts, browser-operation receipts, selection, and SHA-256 manifest. A frozen engine accompanies each run. If installed code changes, replay with the included `engine/src/cli.js`. Verification authenticates listed artifact content against its manifest; it does not authenticate a human author's identity or prohibit additional unlisted files.

## Supported domain and verification

The current emitter supports static semantic HTML/CSS, local PNG/JPEG/WebP/passive SVG materials, font stacks available in the browser, native links, keyboard navigation and disclosures. It preserves content through a two-regime responsive reflow. The examples exercise Latin-script content. Custom application backends, form submission, canvas interfaces, arbitrary third-party pages, motion evaluation, and arbitrary writing-system quality are outside this release's demonstrated domain.

The nine families are computable proxies. Optical mass, type fingerprint, image texture, region continuity and material meaning have explicitly limited descriptors. Geometry is not a substitute for all visual perception. Originality distance describes graph structure, not copyright similarity or semantic originality.

```bash
cd tools/agent-aphrodite
npm test
node test/integration.js
```

The integration test uses the actual `agent-do aphrodite` and `agent-do browse` paths, retains evidence under `.dev/`, verifies the coupled dimensions on actual renders, exercises pointer/keyboard actions, checks a fresh packet, and refuses an unearned calibrated release. The root `./test.sh` includes both suites. Algebraic fixtures are explicitly synthetic and never enter human calibration.
