# Image-first design: verb proposal

Status: PROPOSED, awaiting Erik's taxonomy approval. No implementation authorized by this document.

Work already on the board: `mn-7de24f` (image-first workflow) and `mn-d8b267` (polish audit). Neither is being closed or treated as approved. This proposal replaces the taste-instrument direction for this task.

## Decision requested

Approve one new tool namespace, `agent-do design`, with five verbs: `brief`, `imagine`, `ballot`, `measure`, and `reproduce`. Approve one new mechanical verification verb on the existing tool: `agent-do dpt polish`.

`ballot` has image and page stages, and explicit publish/read operations. It is one verb used twice in the workflow. `dpt polish` produces findings and measurements, with no taste score, ranking, or aesthetic judge. Existing Aphrodite generation and DPT scoring are not dependencies.

The workflow is:

approved copy + facts → three prompts → generated pictures → Erik's image ballot → measurements → one builder per chosen picture → copy/fact/polish checks → Erik's page ballot → archived ruling.

## Record read and verified

Read `tools/agent-dpt/corpus/rounds/home1/round2/labels.yaml`, `COMMON.md`, `check_home.py`, `polish_audit.js`, `blind-key.json`, and `gallery-submitted.html`; inspected all six candidate HTML files and renders, `H3-polished.html` and its render, and all three source images in `home1/`. The approved copy is actually in the parent directory, `home1/copy-approved-2026-09-18.md`, rather than `round2/`.

Also read the Palingenesis canon from “Trial pre-registered” to its end and the facts at `docs/design-canon/briefs/home-brief.json`. Recovered the original exact and half prompts, the replacement full-content/open-design prompt, and the untruncated task instruction from Claude transcript `fae1af41-26ba-4c61-9805-d261387c8a4a`. Relevant messages are `2e375661-3718-41b3-add3-1aec681bc472`, `72dbfabe-7921-44d8-9441-ba4359bacdef`, and `5c95d98b-824b-4fc6-8df4-28d835608dbf`.

The three exact prompt excerpts are preserved in [SOURCE-PROMPTS-2026-09-18.md](SOURCE-PROMPTS-2026-09-18.md), with source message IDs and excerpt hashes.

The archived ballot's six notes and Overall match `labels.yaml` exactly. All six HTML hashes match the hashes recorded there. The ruling remains:

| Label | Source | Erik's words |
| --- | --- | --- |
| H1 | B1 | good, other than the bottom section, that need rework; advance |
| H2 | A1 | no, it's only ok-ish |
| H3 | B3 | great; advance |
| H4 | A3 | no, very basic, kill |
| H5 | A2 | garbage; kill |
| H6 | B2 | it's serviceable; advance |

Overall: “let me know which were you and which were based off my images! I am rooting for H3 I may just go ahead and lock that in after some minor changes”

This is the recorded 3/3 versus 0/3 result on Home. The recorded blindness limit stays attached: Erik selected the source images and could recognise their reproductions. H3 is the favourite from the open-design image, not an already ratified final page.

Two checks need to become stronger production checks without rewriting the trial record:

- The existing copy checker prints failures but returns success. Running it on the unchanged files today reports A2 with one stray fragment and B2 with paragraph 2 missing plus two stray fragments. B2's paragraph result involves text-node whitespace around an inline span; this demonstrates why the production checker must understand rendered text boundaries. B3 passes the old checker despite repeated opening sentences. These are checker observations, not replacement human rulings.
- The existing polish script checks leaf text, skips SVG text, and has no caption-clipping test. Production coverage must include inline text runs, SVG text, clipping ancestors, and element overflow, including overflow hidden by CSS.

## Proposed command surface

These are proposed interfaces, not commands implemented today. `ROUND`, file paths, and budgets below are caller inputs.

```text
agent-do design brief --copy COPY --facts FACTS --round ROUND
agent-do design imagine --round ROUND --per-level 2 --budget-usd BUDGET --size WIDTHxHEIGHT --quality QUALITY
agent-do design ballot images --round ROUND --publish
agent-do design ballot images --round ROUND --read ARTIFACT_URL
agent-do design measure --round ROUND --selected
agent-do design reproduce --round ROUND --selected --budget-usd BUILDER_BUDGET
agent-do design ballot pages --round ROUND --publish
agent-do design ballot pages --round ROUND --read ARTIFACT_URL
agent-do dpt polish [URL] --session SESSION --viewport WIDTHxHEIGHT --out REPORT --json
```

All design verbs support structured JSON results. `--dry-run` checks prerequisites and emits the planned operations without paid requests, builder launches, or Artifact publication. It does not simulate a successful generation, ruling, or audit. A run needs a dedicated round directory; existing source files are never overwritten.

## Five-beat contracts

The descriptions below show the full operation. A beat without an external action is stated explicitly. Registry declarations will use the existing beat and attribute vocabulary, with no new contract categories.

| Command | Connect | Snapshot | Interact | Verify | Save |
| --- | --- | --- | --- | --- | --- |
| `design brief` | Open the caller-approved copy, facts, and cited house files. | Freeze bytes, hashes, paragraph order, fact IDs, token provenance, and target viewports. | Assemble exact, half, and open prompts. No network or generation. | Full copy appears verbatim in each prompt; all required labels/facts are included; forbidden content and source conflicts are rejected. | Three prompts, input snapshots, and a round manifest. |
| `design imagine` | Resolve credentials through `creds`; resolve model capabilities and quantity-authority prices; check the explicit budget. | Freeze request inputs, model, quality, size, price records, and permitted request count. | Call the Images API for the requested generations at each level. | Decode each image, verify returned dimensions/count, reconcile usage and costs, and identify partial or uncertain calls. | Every image, request/response metadata, prompt, level, seed status, error, and usage/cost receipt. |
| `design ballot images/pages --publish` | Require a working Claude Code Artifact publisher and its self-publish capability. | Freeze candidate hashes, stage, display sizes, and a shuffled private key. | Publish the self-saving ballot with `capabilities: {"artifact": {}}`. | Read back the actual Artifact; verify candidate identity, state block, note keys, Submit runtime, and absence of the private key. Pages require current passing copy/fact/polish receipts. | Ballot HTML, URL/version receipt, private key, and pending-ruling state. |
| `design ballot images/pages --read` | Read the published Artifact using the supported Artifact capability. | Archive the returned HTML and version before interpreting anything. | No candidate edits or automatic voting. Interpret only submitted notes tied to the known ballot. | Validate `fb-state`, timestamp, known note keys, and candidate mapping. Missing notes remain unlabeled; ambiguous selection stays unresolved. | Exact notes, submitted page, ruling revision in `labels.yaml`, selection provenance, and the unsealed key after a submitted ruling. |
| `design measure` | Open each image selected by the image ruling and the frozen facts. | Record image hash, pixel dimensions, color profile, and available region/role evidence. | Sample colors and measure boxes, edges, spacing, text extents, and diagram regions. | Every measured value has units, method, and image-region evidence. Unknown values remain `null`; source facts stay separate. | One measurement JSON and annotated evidence image per selected picture. |
| `design reproduce` | Check the image ruling, measurements, frozen inputs, builder runtime, browser, and builder budget. | Freeze one isolated work packet per chosen image. | Launch one builder per image; reproduce the look in HTML/CSS/SVG; repair copy, fact, and polish findings within the budget. | Independently run the copy/fact contract and `dpt polish` on the actual render; verify the viewport and loaded fonts. | Every attempt, final HTML, full render, source-to-text/fact map, audit numbers, and usage receipts. Only passing attempts become ballot candidates. |
| `dpt polish` | Attach to a dedicated `browse` session and establish the requested viewport. | Record page/asset identity, actual viewport, loaded fonts, text ranges, and element rectangles. | Read-only DOM and layout measurement; never edit the page. | Check orphan tails, protected-phrase wraps, duplicates, control alignment, clipped captions, and overflow. | Structured findings with selectors, text, rectangles, coverage, and a pass/fail/incomplete receipt. |

Registry intent: all stateful design verbs are `composite`; `ballot` is also `polymorphic` because flags choose publish versus read. Outputs in a round are tool-owned state. `imagine` and `reproduce` are finite operations with progress, not indefinite daemons. Publication is a world write. Reading credentials internally is not permission to emit or persist secrets; no secret material enters receipts. The generated registry proposal, coverage validation, and drift check will run after approval, once a real declared surface exists.

## Prompt shapes

All three receive the same complete copy, paragraph order, allowed content labels, actions, and authoritative figures. A frozen content block is included verbatim, not replaced by summaries or “paragraph beginning…” references. The historical exact and half prompts did not include the entire copy; the requested implementation deliberately closes that gap while retaining their shapes.

| Level | Shape to preserve | Design freedom |
| --- | --- | --- |
| exact | Browser-page framing; explicit ground/ink/type/grid; ordered section-by-section placement and diagram instructions; closing arrangement; full copy/facts block. | Pin details to the supplied house facts and an explicit recorded design specification. Layout decisions can be authored as design decisions, but invented figures or prose cannot. Missing required identity inputs are reported. |
| half | Browser-page framing; a loosely described house character and palette; complete ordered content and diagram purposes; full copy/facts block. | Leave layout, proportions, section treatments, and scroll rhythm open within that loose direction. |
| open | Browser-page framing; intended audience/job; navigation; opening; every section with its full paragraph and factual content; closing/actions. | Explicitly release palette, typefaces, light/dark treatment, grid, spacing, section treatment, and diagram form. Do not quietly reimpose the exact prompt's house geometry or color targets. |

Every prompt forbids icons, gradients, stock imagery, device frames, decorative logos, mottos, taglines, and invented text; requires sharp, correctly spelled text; and permits drawn diagrams of the subject. An approved product name remains ordinary text, as it did in the trial. The original one-paragraph, almost-empty Prompt 3 is superseded and must not become the open template.

The prompt's requested page dimensions and the API's actual pixel dimensions are separate recorded fields. The latter obey the model's current supported dimensions. Never crop away content or silently shorten copy to fit a prompt or image limit.

## Content and fact ownership

- The copy file is immutable input. Every paragraph must be present once and in order. A paragraph may span a heading and body text, as in polished H3, provided its ordered text is preserved once. The checker must reconstruct text across inline nodes correctly; HTML entity decoding and layout whitespace do not authorize word or punctuation changes.
- Text outside those paragraphs must bind to explicitly allowed labels, room names, actions, or figure displays in the facts file. No six-word threshold exempts a short slogan. The old brief's superseded `sentences`, its instructions, and its forbidden examples are not an allowlist.
- Every displayed figure carries a fact ID, value, unit, and source. Data-bound SVG marks, chart points, axes, dates, identifiers, and table rows need the same lineage. A permitted number elsewhere in the facts does not authorize a new claim using that number.
- An image supplies appearance. Text and numerical values extracted from it are evidence of appearance only. Image-invented figures from the trial, including calibration points and ledger rows absent from the facts, are not silently promoted into the new contract.
- Where the chosen image depicts a quantitative chart for which facts are missing, reproduction reports the missing data. It may use a diagram supported by the approved content only when that diagram makes no new quantitative claim; it cannot fabricate a plotted series to match the picture.
- A builder cannot make an audit pass by deleting copy, hiding required content, substituting an image of text, clipping overflow, shrinking text beyond the recorded role constraints, or weakening the checker. Copy changes require a new owner-approved input revision and invalidate dependent receipts.

## Measurement honesty

Color records include sampled region, pixel count, observed color/profile, method, and area coverage. Geometry records include original image coordinates plus normalized proportions, column boundaries, gutters, section order and extents, and diagram bounds.

Typography records distinguish observable glyph/line heights in image pixels from CSS font size. Exact CSS size, family, or weight may be unavailable from raster evidence. Those fields are `null` unless a source supplies them. A builder's eventual font choice is recorded as an implementation choice, not retroactively relabeled a measurement.

Role and diagram-kind assignments require traceable region evidence and a supported association with the facts. Unresolved associations remain `null`; a model's guess is not a measured value. The selected image remains in the builder packet so measurement JSON does not flatten it into a small template vocabulary.

## Ballot protocol and stage boundaries

Follow `/Users/erik/.claude/skills/ballot/SKILL.md`: self-contained HTML, `fb-state` directly after the title, neutral labels, one note box per candidate plus Overall, and one Submit that republishes a template captured at load. Publishing on load is forbidden. The submitted HTML is the authority for the ruling.

Images appear at their declared judging size; page iframes render at the actual target viewport. Maintain separate image and page ballot keys. Prompt levels, model identities, candidate filenames, and mappings stay outside published HTML, comments, asset names, and embedded metadata. Archive both original sources and the exact public payload; never edit original candidates just to remove metadata.

Candidate frames cannot edit the ballot or its saved state. Publication must return a real URL/version receipt and pass readback. Artifact conflicts or missing capabilities remain explicit failures. A local HTML file, an unrelated hosting service, or a fabricated receipt cannot count as a published Claude Artifact.

The trial transcript proves an Artifact-capable Claude host was used. This Codex session exposes no Claude Artifact tool, and the reviewed agent-do surfaces contain no Artifact adapter. After approval, the supported Claude host integration is an explicit implementation prerequisite to test through the existing agent orchestration path. If it cannot expose publish/read, the tool stops at that prerequisite and reports it; no alternate publishing path is implied.

Reading a ruling preserves strings exactly, including spelling and whitespace. Blank notes do not become rejections. Rereading the same Artifact version is idempotent; later submissions create additional archived ruling revisions. A selection must trace to an explicit owner choice. Publishing returns pending; it never waits forever or treats elapsed time as an answer.

DOM polish applies to the ballot chrome and every HTML candidate before publication. A generated raster's internal text is not DOM-auditable and must not receive a fabricated polish-pass receipt. Image copy errors remain recorded; the chosen look receives the authoritative copy and facts during reproduction.

## Browser verification and repair

Use an isolated `agent-do browse` session. Open the candidate, then call `browse viewport 1440 1000` for the trial's desktop target and read back `innerWidth`, `innerHeight`, and device pixel ratio. For other surfaces, use their declared viewport. Do not rely on `open --viewport`. Wait for fonts and layout stability before measurement and the full-page capture.

`dpt polish` checks all six defect classes requested. Findings carry the element, exact text, expected relationship where one is declared, measured rectangles/line fragments, and the viewport. SVG labels and text split over inline elements remain in coverage. Protected phrases are declared from allowed labels and figure displays; alignment checks apply to declared control/content relationships rather than banning every asymmetric layout.

The trial's thresholds are versioned defaults with provenance, not universal taste laws. The audit exposes incomplete coverage. `reproduce` requires passing copy/fact verification and a complete clean polish result for every declared target viewport. If repair cannot finish within the authorized budget, retain the candidate and findings as incomplete; it does not enter the page ballot. Finishing a repair reruns both checks against the final bytes and render.

## Images API, budget, and costs

The official [image-generation guide](https://developers.openai.com/api/docs/guides/image-generation) confirms `gpt-image-2.5-sunburst`. Request that model by default; use the explicitly requested `gpt-image-2` fallback only for an account/model-availability failure, after validating its capabilities and prices. Authentication failures, rate limits, and arbitrary server errors are not fallback triggers. Account access has not been tested in this proposal turn.

Default count is two generations for each of three levels, as requested. Use one image per API request so an actual request's usage can be attributed to its image without dividing a batch total and calling it exact. Persist requested and returned model information, level, quality, dimensions, prompt hash, request ID, original image bytes, and every error. An uncertain timeout is not silently retried as though it were free.

The current [Images generation API reference](https://developers.openai.com/api/reference/resources/images/methods/generate) documents neither a generation seed nor a per-request output-token cap. Record `seed: null` with the reason when unsupported; do not invent one. Ballot shuffle randomness is separate. Record actual usage when returned; missing usage makes cost incomplete, never zero.

Prices must resolve through `agent-do harness quantity`, with source and verification date. The existing authority currently has no image-price keys. Add provenanced entries after approval using the existing `models.yaml` quantity mechanism, not numeric rates in tool code. Proposed key family for both models:

```text
openai.<model>.text_input_usd_per_million_tokens
openai.<model>.cached_text_input_usd_per_million_tokens
openai.<model>.image_input_usd_per_million_tokens
openai.<model>.cached_image_input_usd_per_million_tokens
openai.<model>.image_output_usd_per_million_tokens
```

Use the applicable standard synchronous schedule, not the Batch schedule, from [official pricing](https://developers.openai.com/api/docs/pricing#image-generation). Freeze the resolved rates alongside raw usage and calculate cost with decimal arithmetic. Include actual builder/repair usage and its applicable pricing authority separately; a subscription allowance is not a fabricated dollar cost. If any component is unpriced, withhold a claimed exact whole-run total and state the missing component.

Preflight reports the authorized request count, exact rate schedule, and budget. It must not present an estimated per-image charge as an exact total. A dollar ceiling requires an enforceable provider limit or an authoritative upper bound for the next request. Where neither exists, refuse with the missing bound named before spending. Merely checking the remaining balance before an unbounded request is not a hard cap. Resolving this constraint is part of implementation readiness, not permission to bypass the budget rule.

## Durable round state

Keep the round's sources, prompts, generations, measurements, builder attempts, audits, renders, ballots, submitted pages, private keys, rulings, and receipts. Never delete unsuccessful work. Retries append attempts; changes append revisions. Hash links connect the exact inputs and outputs at every stage. Resume from the last complete stage without regenerating or republishing completed work.

Stage sequence: `briefed` → `images_ready` → `image_ballot_pending` → `images_ruled` → `measured` → `pages_ready` → `page_ballot_pending` → `ruled`. Partial failures retain their attempt state and cannot impersonate the next stage. Round mutation is locked so two processes cannot both spend the same budget or replace the same ballot state.

`labels.yaml` stores verbatim notes separately from any interpreted disposition, the submitted Artifact URL/version, timestamp, candidate hashes, and the unsealed mapping. The original blind key and submitted page remain preserved. A later revision does not erase an earlier ruling.

## Build and acceptance after approval

1. Claim the existing work items through Manna and isolate the code lane from current foreign work. Implement the five design verbs and reusable polish verb, their contracts, and the normal agent-do discovery/help surface. Reuse `creds`, quantity authority, agent orchestration, and `browse`; no new framework or dependency is silently introduced.
2. Tests cover complete copy in all three prompts; no superseded sentences; duplicates/reordering/short invented lines/hidden copy; wrong fact values and unsupported chart data; immutable source inputs; null measurements; budgets and missing prices; fallback only on model availability; partial and uncertain API calls; exact usage accounting; and preservation of every attempt.
3. Browser fixtures cover each polish fault, including nested inline text, SVG clipping, hidden horizontal overflow, font-loading changes, real viewport verification, and intentional asymmetry. Ballot tests cover escaping, key leakage, frame isolation, submit-only publication, exact note round trips, conflicts, pending state, rereads, and new ruling revisions.
4. Run relevant unit/browser integration tests, registry contracts with zero warnings, contract drift, discovery/help checks, and the repository's required validation commands. Test doubles are unit-test evidence only; they cannot satisfy live Artifact or paid-generation acceptance.
5. Erik names a new surface, supplies or approves its copy/facts, and sets the run budgets. Home is evidence and regression material only. First execute the no-spend dry run on that surface. A live rehearsal then follows the real Images API, real image ballot, measured reproduction, real audits, and real page ballot, stopping at each human ruling. Report the resulting HTML, renders, audit numbers, and actual cost receipts.

Approval of the taxonomy permits implementation of this scoped method. It does not select a new surface, invent its copy/facts, allocate an unspecified budget, or pre-approve either ballot outcome. The method is complete only when those production paths and the new-surface rehearsal work; publishing a local preview is not enough.

**TL;DR (12th grade):** Approve `design brief`, `imagine`, `ballot`, `measure`, and `reproduce`, plus `dpt polish`. The tool will carry approved words and facts through pictures, your choices, measured reproduction, and mandatory checks. The current turn delivers this proposal and stops before implementation.
