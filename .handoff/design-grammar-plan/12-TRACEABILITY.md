# Requirements, implementation and validation traceability

All implementation and test references in this table are **planned**. Planning validation
checks reference integrity and coverage; it does not certify future executable behavior.
The primary catalog is [Rulebook](02-RULEBOOK.md), contracts are in
[LLD contracts](04-LLD-CONTRACTS.md), procedures in [LLD algorithms](05-LLD-ALGORITHMS.md),
and acceptance in [Evaluation](07-EVALUATION-AND-GENERALIZATION.md).

## 1. Requirements to acceptance

| Requirement | Rule families | Principal contract | Procedure | Required evidence | Work packages |
| --- | --- | --- | --- | --- | --- |
| REQ-01 | GEN, VAR, INT | RuleDefinition, FrameRecipe, EvaluationManifest | ALG-04/11 | Source-identity branch audit, prospective new-brief results | WP-02/05/08 |
| REQ-02 | GEO, EVD | ObservationGraph, QueryResult, CaptureManifest | ALG-02/03 | T-RELATION, T-CAPTURE, complete scoped geometry/clearance queries | WP-03 |
| REQ-03 | INT, HIE, COH | IntentFrame, CharacterFrame, Interpretation | ALG-04/06 | Attributed purpose and character decisions on real content | WP-02/05 |
| REQ-04 | COH, REP, VAR | DependencyEdge, Patch, SourceMap | ALG-05/08 | T-REPAIR, controlled changes with recomputed dependent evidence | WP-04 |
| REQ-05 | GEN, VAR, MAT | CompositionProgram, AssetManifest | ALG-04/09/11 | New-brief/copy audit, permitted original assets and substantive content | WP-05/08 |
| REQ-06 | INT, STA, GEO | ActionContract, ActionBinding, StateMachine | ALG-07/09 | T-STATE, real bundle/actions and browser receipts | WP-02/06 |
| REQ-07 | RSP, STA, MOT | ConditionManifest, StateMachine | ALG-03/07 | T-RESPONSIVE, T-STATE, required conditions and transition paths | WP-06 |
| REQ-08 | COL, TYP, STA, RSP, MOT | StandardsProfile, RuleResult, CoverageRecord | ALG-06/07 | T-PAINT/T-TEXT/T-STATE plus all applicable selected-profile dispositions | WP-06 |
| REQ-09 | EVD, INT, GEN | Authority, Observed, Interpretation, PreferenceEvent | ALG-01/06 | T-CONTRACT, distinct source kinds and immutable human words | WP-01/04 |
| REQ-10 | EVD, GEO, COL, MOT | CaptureManifest, Observed, CoverageRecord | ALG-02/06 | T-CAPTURE, unsupported/incomplete cases cannot yield false pass | WP-03/04 |
| REQ-11 | GEN, REP | PacketManifest, CapabilityManifest, HostRequest | ALG-10 | T-PACKET, cold-session completion and continuation | WP-07 |
| REQ-12 | EVD, REP | ArtifactRef, CompositionProgram, SourceMap | ALG-01/04/09 | T-REPLAY, deterministic compilation and pinned inputs/runtime | WP-01/02/07 |
| REQ-13 | REP, VAR | BudgetProfile, Patch, OperationResult | ALG-08/10 | T-REPAIR, stale/cycle/budget refusal with preserved continuation | WP-04/07 |
| REQ-14 | EVD, REP | CaptureManifest, DPTAnnotation, CapabilityManifest | ALG-02/10 | T-INTEGRATION, supported browser/DPT bindings and current repo gates | WP-03/07 |
| REQ-15 | GEN, VAR | EvaluationManifest | ALG-11 | Frozen scope, whole-site retrieval holdouts, novel briefs and honest denominators | WP-08 |
| REQ-16 | EVD, INT, GEN | PreferenceEvent, Authority | ALG-01/11 | Exact source/hash preservation and human-only verdict creation | WP-01/08 |
| REQ-17 | EVD, REP | ArtifactRef, PacketManifest, export manifest | ALG-01/09/10 | T-EXPORT, paths/digests/asset resolution on another admitted machine | WP-01/07 |
| REQ-18 | All catalog families | RuleDefinition, RuleApplication, RuleResult | ALG-01 through ALG-11 | Every rule and operator implemented/tested; complete application census | WP-01 through WP-09 |
| REQ-19 | INT, TYP, MAT, STA | ContentGraph, AssetManifest, ActionContract | ALG-01/05/07 | T-TEXT/T-STATE, missing assets/actions prevent the corresponding delivery claim | WP-02/05/06 |
| REQ-20 | Commission boundary | This package and delivery receipt | Planning validation only | Repo/Transfer/vault documents, preserved inputs, no runtime implementation | Current planning commission |

## 2. Complete rule-family ownership

`T-<rule-id>` is a required test family for every individual row in the Rulebook. These IDs
are not satisfied merely by a same-named test file: assertions must test a real independent
invariant or the correct boundary of an attributed judgment. The Evaluation chapter defines
positive, falsifying, unknown and inapplicable cases where meaningful.

| Family | IDs | Count | Primary implementation packages | Supporting suites |
| --- | --- | ---: | --- | --- |
| EVD | EVD-01 through EVD-04 | 4 | WP-01/03 | T-CONTRACT, T-CAPTURE, T-REPLAY |
| INT | INT-01 through INT-04 | 4 | WP-01/02/04/06 | T-CONTRACT, T-OPERATOR, T-STATE |
| GEO | GEO-01 through GEO-10 | 10 | WP-02/03/05/06 | T-RELATION, T-OPERATOR, T-RESPONSIVE |
| RHY | RHY-01 through RHY-04 | 4 | WP-02/04/05 | T-OPERATOR, T-REPAIR |
| HIE | HIE-01 through HIE-04 | 4 | WP-02/04/06 | T-OPERATOR, T-STATE, attributed visual review |
| TYP | TYP-01 through TYP-06 | 6 | WP-02/03/05/06 | T-TEXT, T-RESPONSIVE |
| COL | COL-01 through COL-06 | 6 | WP-03/05/06 | T-PAINT, T-STATE |
| MAT | MAT-01 through MAT-06 | 6 | WP-02/05/06 | T-PAINT, T-OPERATOR, attributed visual review |
| VAR | VAR-01 through VAR-03 | 3 | WP-02/04/05/08 | T-REPAIR, matched comparison audit |
| RSP | RSP-01 through RSP-04 | 4 | WP-02/06 | T-RESPONSIVE, T-STATE |
| STA | STA-01 through STA-05 | 5 | WP-06 | T-STATE |
| MOT | MOT-01 through MOT-03 | 3 | WP-03/06 | T-CAPTURE, T-STATE |
| COH | COH-01 through COH-04 | 4 | WP-02/04/05 | T-OPERATOR, T-REPAIR |
| REP | REP-01 through REP-04 | 4 | WP-01/04/07 | T-REPAIR, T-REPLAY, T-PACKET, T-EXPORT |
| GEN | GEN-01 through GEN-04 | 4 | WP-01/07/08 | T-CONTRACT, T-PACKET, prospective evaluation |
| Total | 15 families | 71 | All required packages | No unimplemented row can count as a pass |

## 3. Operator closure

| Operator | Primary lowering/procedure | Primary package | Required distinctive test |
| --- | --- | --- | --- |
| page | Semantic document/landmarks, ALG-09 | WP-02 | Page identity, reachable required content and per-page conditions |
| region | Surface/logical inset ownership, ALG-03/09 | WP-02 | Insets, nested scope and source-map property ownership |
| flow | Native intrinsic flow, ALG-03 | WP-02 | Order, wrap and zero/one/many children |
| partition | Bounded monotone allocation, ALG-03 | WP-02 | Feasible bounds, mixed limits, infeasibility versus search exhaustion |
| grid | Count/spans/placement, ALG-03 | WP-02 | Empty/single collection, last row, minima and exceptional spans |
| align | Shared reference/owned offset, ALG-03 | WP-02 | Cross-sample rejection, valid edges, unavailable baseline evidence |
| layer | Explicit stacking/protection, ALG-03/07 | WP-05 | Intended overlap and protected hit/focus regions |
| repeat | Content-key expansion, ALG-03/09 | WP-02 | Membership conservation and stable IDs after insertion |
| sequence | Typed recurrence, ALG-03 | WP-05 | Domain limits, keyed interruptions and arithmetic/geometry errors |
| clearance | Logical insets/reserved region, ALG-02/03 | WP-05 | Union overlap, excluded background surfaces and explicit intrusion |
| text | Actual content/font rendering, ALG-05/09 | WP-02 | Shaping/fallback, expansion and forbidden hidden truncation |
| media | Asset/crop/fit binding, ALG-05 | WP-02 | Intrinsic size, protected focal region and unavailable asset |
| control | Native/registered behavior, ALG-07/09 | WP-06 | Labels, keyboard, state, real versus fixture-only action binding |
| state | Finite transitions and view variants, ALG-07 | WP-06 | Guards, recovery, pending/error/success and focus continuity |
| transform | Typed scoped patch, ALG-08 | WP-05 | Invariants, dependency invalidation and base-digest refusal |
| component | Registered lowering/observation contract, ALG-07/09 | WP-05/06 | Unknown component refusal and exact supported observation boundary |

## 4. Planning validation

The planning check counts and resolves the twenty requirements, seventy-one rule IDs,
eleven algorithm IDs, sixteen operators, eight example recipes, sixteen architecture decisions
and ten work packages. It checks relative document links, fenced content, example arithmetic,
source-byte preservation and three-destination delivery. Its receipt records actual checks.

It does not run future tests, render prospective websites, certify standards conformance or
establish an aesthetic preference benefit. Those claims require the implementation and
evidence mapped above. The planning commission ends after this package is delivered.
