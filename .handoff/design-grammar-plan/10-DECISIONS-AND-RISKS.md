# Architecture decisions, limits and risks

All decisions below are **recommended implementation decisions**, documented under the
planning commission. They are not recorded human ratifications, shipped features or claims
that the proposed instrument has already improved design quality. Implementation may adopt
them together or amend a named decision before its dependent work begins.

## 1. Decision record

| ID | Recommendation and reason | Alternative considered and tradeoff | Implementation point |
| --- | --- | --- | --- |
| ADR-01 | Use a typed relational composition program as the source of truth. Changes can preserve requirements and invalidate dependent evidence. | Free-form CSS is expressive but loses explicit decision/dependency lineage. Framework adapters can consume the program later. | WP-01/02 |
| ADR-02 | Use native browser layout plus small mathematically defined constructions. This keeps actual HTML/CSS behavior authoritative. | A universal optimization solver would require choosing a global objective and modeling browser intrinsic behavior. Add a specialized solver only for a demonstrated missing construction. | WP-02 |
| ADR-03 | Let the current host model propose and interpret; keep the core deterministic and provider-neutral. | Internal model calls add credentials, model selection, cost and orchestration that already belong to the host. An explicit later host adapter may supply them. | WP-01/07 |
| ADR-04 | Use a new package, proposed name `tools/agent-design/`, with proposed command `agent-do design`. Keep DPT's existing audit interface intact. | Extending `dpt score` would blur construction, preference and the existing mixed scanner. No name is registered by this document. | WP-00/07 |
| ADR-05 | Use Node ES modules and built-in test facilities for the new core, plus proposed Ajv for JSON Schema 2020-12 validation. | Python/Rust are viable but add cross-language browser artifact handling; custom schema validation risks an incomplete standard implementation. Version and approve Ajv before installing it. | WP-00/01 |
| ADR-06 | Use versioned local JSON files, immutable artifacts and atomic pointers. | A database or hosted service is unnecessary for a session-local first release and makes portability harder. Large-scale indexing can be an adapter later. | WP-01 |
| ADR-07 | Reuse the supported `agent-do browse` interface with explicit session/project binding. | A new Playwright/CDP harness duplicates ownership, auth, lifecycle and capture behavior. A missing browser capability must be fixed in the owning tool. | WP-03 |
| ADR-08 | Preserve DPT raw reports as annotations and require independent authority for any blocking finding. | A single score is convenient but conflates paint support, mechanical obligations, style assumptions and taste. Its old study is preserved. | WP-03/04 |
| ADR-09 | Use a conditional versioned standards profile, including applicable manual checks. | A small scanner cannot certify an entire accessibility standard. Mechanical findings, unknowns and manual obligations have different statuses. | WP-06 |
| ADR-10 | Use optional frame recipes and open character axes, never a classifier over six corpus registers. | Site templates and rigid mood-to-palette maps reproduce examples and suppress combinations absent from the corpus. | WP-02/05 |
| ADR-11 | Use an HTML/CSS bundle as the first emitter and declare ownership in a source map. | Shipping several framework emitters immediately multiplies behavior and verification surfaces before the language works. | WP-02 |
| ADR-12 | Treat assets and behavior contracts as first-class inputs. | Beautiful placeholders and unbound purchase/reservation controls can falsely imply completed design. Asset acquisition and business logic remain with their actual owners. | WP-02/06 |
| ADR-13 | First-release scope includes LTR/RTL, declared browser conditions and semantic native/registered components. Vertical writing generation and unobserved opaque internals are named extensions. | Claiming every medium and browser without observation contracts creates fictitious completeness. Extension remains possible through the same typed boundary. | WP-00/06 |
| ADR-14 | Separate mechanical correctness, expressive review, generalization evidence and human selection. | A pooled scalar can conceal failures and manufacture universal authority from contextual preferences. Separate findings still support decisive selection by the authorized actor. | WP-04/08 |
| ADR-15 | Preserve exact human verdicts and use prospective new briefs for the strongest transfer claim. | Repeatedly evaluating familiar pinned sites can measure familiarity and copying. Whole-site retrieval holdouts help but cannot erase exposure already present in the model or conversation. | WP-08 |
| ADR-16 | Stop revision at the requested claim or an explicit budget/conflict boundary. | An unbounded critique loop can consume work indefinitely and drift toward the critic's favorite style. A stopped run keeps useful artifacts and actionable gaps. | WP-04/07 |

## 2. Parameters and authority

Three kinds of values must not be mixed. Mathematical values derive from inputs and equations.
Standards values retain their source, version and applicability. Design choices are authored or
proposed parameters with explicit domains and mutability. The example's 2:1 partition and
48-pixel inset are in the third category; they are not calibration constants for the product.

Runtime budgets, capture settling procedures, supported browser versions, context allocation
and experiment sizes are launch configuration. They must have concrete values before their
operation runs, but this planning document should not invent a universal browser wait or a
scientifically justified sample size from no measurements. WP-00 supplies operational budgets;
WP-08 freezes the evaluation budget and inference policy before prospective runs.

The implementation can ship documented engineering presets after measuring its real path.
Presets identify their provenance and failure conditions. A timeout or unknown observation
remains visible even when the preset usually works. A user's explicit locked values override
a merely proposed frame choice.

## 3. Risks with actionable detection

| Risk | Observable trigger | Required response and evidence | Owning work |
| --- | --- | --- | --- |
| Rule catalog becomes disguised taste doctrine | Predicate, default or repair always demands a particular font, layout, palette or reference identity | Reject the universal binding; retain a scoped optional recipe with counterexamples; copy/branch audit | WP-02/05/08 |
| Many valid designs still look mediocre | Matched new-brief trials show no useful preference benefit despite mechanical success | Report unestablished benefit, inspect specific failed decisions and revise a frozen successor; do not raise a scalar score by retuning | WP-08 |
| Geometry is mistaken for visual perception | Empty-space or centroid descriptors are presented as beauty or salience facts | Keep geometric methods separate from visual interpretations; test media/transparent/shaped counterexamples | WP-03/04 |
| Lazy loading creates false evidence | Captures omit admitted bands, assets or states | Preserve partial result; fix the capture procedure or request missing evidence through the intended browser path | WP-03 |
| Font substitution changes the composition | Loaded assets, glyph coverage or observed wraps differ from the declared contract | Mark the affected measurements invalid; resolve or explicitly approve a replacement and re-measure | WP-03/05 |
| Strong material expression breaks access | Background paint unknown, obscured focus, unreadable content or missing alternate cues | Keep the expressive proposal while repairing the specific failed relationship; required unknowns prevent the relevant claim | WP-04/06 |
| General relationship queries become too costly | Candidate pair count or output exceeds the declared budget | Use complete indexes, pagination and continuations; expose the exact unfinished denominator | WP-03 |
| Revision oscillates or damages good relationships | Repeated program digest, conflicting constraints, stale patch base or regression | Preserve best verified artifacts, return scoped conflict and request a changed decision/budget | WP-04 |
| A fresh session cannot consume the packet | Mandatory context exceeds host capacity or required vision/tools are absent | Return the missing capability/context requirement; do not silently omit obligations | WP-07 |
| Compiler and program drift apart | Emitted artifact hash or owned properties change outside compilation | Refuse stale verification; regenerate or perform an explicit supported import with new lineage | WP-02/07 |
| Reference identity leaks into generation | Site-specific assets/tokens/topology branches appear in the emitted source without explicit legitimate input | Remove the accidental dependency and rerun the copy/generalization audit on a new brief | WP-05/08 |
| A fixture is mistaken for a live business action | Action binding is fixture-only but delivery says transaction complete | Mark action incomplete until its owning implementation and verification are bound | WP-06 |

## 4. Unanswered empirical questions

The architecture is specified. The following questions require the future build and evidence:
whether the packet changes host behavior usefully; which recipes transfer across tasks; how
much real visual observation helps; whether dependency-aware revision saves work; and whether
the resulting original websites are preferred under matched conditions.

The twelve approved sites cannot answer those questions by themselves. They are examples of
range and human approval, with incomplete measurement/state coverage. Their agent-authored
grammar notes are candidate explanations. The earlier failed scalar study answers its own
tested questions and remains frozen; it neither certifies nor automatically forbids this
different system.

## 5. Adoption and amendment

An implementation commission should name this package version and any changed ADR/requirement.
Builders implement the closed contracts and catalog, report a missing capability instead of
silently substituting a different architecture, and file amendments with impact on tests and
dependent packages. Evaluation amendments preserve the old manifest and label any post-result
changes. Human instructions retain their original attribution.

No rule or roadmap item becomes established truth merely by appearing in a document. Planning
is complete when these decisions, interfaces, dependencies and checks are specified and
delivered. Production readiness and aesthetic benefit belong to later verified work.
