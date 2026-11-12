# Generative Design Grammar: complete planning package

Planning commission: `mn-27e068`. Date: 2026-09-14. Status: **PROPOSED FOR IMPLEMENTATION**.
The planning package is the deliverable. Product implementation, installation, new tool
registration, deployment, and changes to the frozen taste study are outside this commission.

## The outcome

A fresh AI session receives a brief and a portable instrument. It can construct an original
website, inspect its actual rendered relationships, and revise the composition coherently.
The instrument supplies a general language of roles, space, typography, color, materials,
state, and transformation. The model supplies contextual interpretation and proposals.
Human preference remains an independently recorded verdict.

The twelve approved sites are evidence of expressive range. They are not templates,
training labels for universal aesthetic laws, or a closed list of styles. A generative rule
cannot branch on a reference site's identity. A rule may cite a reference in its evidence.

## Read this package

Start with [the complete design document](DESIGN.md) for one continuous book, or use the
chapters below. [Completion and validation](COMPLETION.md) records the delivery boundary.

| Document | What a builder gets |
| --- | --- |
| [Vision and scope](01-VISION-AND-SCOPE.md) | Product behavior, requirements, completeness boundary, meaning model |
| [Rulebook](02-RULEBOOK.md) | Complete first-release rule catalog, formulas, applicability, exceptions |
| [HLD](03-HLD.md) | Components, ownership, architecture, data flow, deployment and trust boundaries |
| [LLD: contracts](04-LLD-CONTRACTS.md) | Wire types, states, schemas, identifiers, errors, storage and function contracts |
| [LLD: algorithms](05-LLD-ALGORITHMS.md) | Operators, observation, generation, dependency propagation, revision and determinism |
| [Fresh-session integration](06-FRESH-SESSION-AND-INTEGRATION.md) | Portable packet, skill entry, proposed CLI, discovery and existing-tool integration |
| [Evaluation](07-EVALUATION-AND-GENERALIZATION.md) | Mechanical tests, preference trials, holdouts, ablations and anti-copy safeguards |
| [Build plan](08-BUILD-PLAN.md) | Ordered work packages, dependencies, deliverables, acceptance and stopping conditions |
| [Worked examples](09-WORKED-EXAMPLES.md) | New briefs, parameter derivations, composition traces and repair cases |
| [Decisions and risks](10-DECISIONS-AND-RISKS.md) | Chosen architecture, alternatives, recommendations, unresolved empirical questions |
| [Sources and corpus](11-SOURCES-AND-CORPUS.md) | Live repo evidence, official specifications, exact corpus coverage and source limits |
| [Traceability](12-TRACEABILITY.md) | Requirements to rules, contracts, algorithms, tests and build packages |

[SOURCE-INVENTORY.json](SOURCE-INVENTORY.json) binds local inputs and protected evidence for this plan.
The package's machine-readable verification and delivery receipts accompany the final bundle.

## The architectural decision

Use a deterministic composition core with a declarative relational representation, native
browser layout, and a host-model proposal loop. Retain `agent-do browse` as the browser
control surface and DPT as versioned annotation. The core creates no network model calls.
It produces structured requests that the current capable session can answer.

The recommended implementation home is a new `tools/agent-design/` package in this repo,
with Node ES modules and a thin CLI. `agent-do design` is a **proposed** tool name, not a
command installed by this plan. The only proposed new runtime dependency is Ajv for
JSON Schema validation. No general optimization solver, database, vector service, model
fine-tuning pipeline, or new browser harness is required for the initial product.

The first useful build runs the entire brief → composition → render → observation → revision
loop with a bounded subset of operators. The remainder of the catalog then expands that
same working path. The final first-release gate covers every catalog obligation within the
declared scope; an early vertical slice is explicitly partial.

## Meaning of complete

This is a complete implementation plan for the first release described here. It does not
claim an exhaustive theory of beauty or guarantee approval for every future brief.
Its scope is finite, its rule and state coverage is countable, and its learning claims have
separate tests. The rule grammar is extensible without changing the distinction between
facts, hypotheses, preferences, and standards.

Implementation starts only after Erik commissions it. Planning delivery does not ratify
the proposed aesthetic hypotheses or authorize installing dependencies or registering tools.

**TL;DR (12th grade):** Build a reusable language for composing and revising websites.
Use the examples to test its range. Keep the layout machinery precise and the claims about
beauty honest. This package specifies the machinery, its interfaces, and how to test it.
