# Fresh-session delivery and integration

Status: proposed integration. No skill, hook, registry entry or command is installed by this plan.

## 1. The fresh-session contract

The session must receive the design brief, capability requirements, rule semantics and current
run state before it generates or changes product code. It must not need this conversation,
a remembered site, or an undocumented project convention to use the instrument correctly.

A PacketManifest binds the following fields, identically defined in LLD contracts section 13:

```text
schema, packet_id, project_id, run_id?, brief_digest, ruleset_digest,
core_version, compiler_version, input_artifact_refs,
mandatory_blocks, optional_evidence_index, delivered_blocks,
required_capabilities, available_capabilities, unresolved_capabilities,
context_budget: { authority, measured_bytes, tokenizer_method?, token_count? },
unfulfilled_requirements, next_operation, expected_response_schema,
continuation_ref?, complete
```

Mandatory blocks include the exact brief requirements, content/action obligations, selected
program and source IDs where one exists, rule-class semantics, the admitted operator/type
catalog, conditions, active failures, protected relations, and the requested response schema.
For an initial proposal, the operator catalog is broad enough to make original choices.
For a revision, it includes the transitive dependencies of every affected choice.

Reference examples are optional indexed evidence. They are not the mandatory program seed.
An ablation or retrieval holdout can exclude them completely. The packet reports which files
were supplied and which remain available by reference. It never implies that an indexed file
has already been read by the host.

If mandatory material cannot fit the available context, return `capability_missing` with the
required delivery and supplied capacity. Use typed staged requests where the complete task
can safely decompose, keeping locked requirements in each applicable request. Never silently
truncate the brief, node domain or active constraints. Byte counts are exact. Token counts
are reported only with an identified tokenizer or host capability; bytes are not silently
converted into an exact token claim.

## 2. Proposed session skill

The future skill's entry instructions should be compact and executable in intent:

1. Resolve the author project's purpose, content, assets, constraints and requested outputs.
2. Check the installed design instrument, browser and required vision/coding capabilities.
3. Prepare or resume the run and read its packet. Honor its versions and coverage limits.
4. Submit typed composition proposals using general operators and context-specific choices.
5. Render the candidate through the supported tool path before evaluating its appearance.
6. Read actual observations, hard findings and attributed visual interpretations separately.
7. Revise by a typed patch; preserve protected requirements and recheck affected conditions.
8. Record human feedback exactly when provided. Keep delegated model selection distinct.
9. Verify the requested completion claim and export the selected artifacts with limitations.

The skill must explicitly forbid site-name branching, reference-asset copying, score chasing,
invented human verdicts, missing-asset placeholder passes, and direct CSS edits that bypass
the current program/source mapping. It must also permit the full expressive range: quiet,
dense, decorative, geometric, photographic, illustrated, single-family typography or more
complex type systems when appropriate. Stylistic defaults in any design skill are techniques,
not unconditional rules overriding the brief or corpus evidence.

A session can reason in symbolic language such as sanctuary or workshop if it records how
that interpretation informs the actual choices. The exported website does not expose
internal rule IDs, tooling status, or design-analysis prose to its end users.

## 3. Proposed public CLI

The proposed name is `agent-do design`. Adoption requires the normal tool taxonomy and
contracts process. These commands do not exist merely because they are documented here.

| Command | Inputs | Output and behavior |
| --- | --- | --- |
| prepare | --brief FILE --project ROOT --out RUN | Validate and bind a run; emit a composition or missing-input request |
| status | --run RUN | Read current state, coverage and next unmet obligation |
| rules | optional --id ID, --json | Read versioned catalog, operator contracts and applicability |
| packet | --run RUN --capabilities FILE --budget FILE | Emit a complete scoped host packet or an explicit capacity/capability requirement |
| respond | --run RUN --response FILE | Validate and persist a HostResponse, bind supplied artifacts/reviews, resolve the matching request and expose the next operation |
| compile | --run RUN --proposal FILE | Validate proposal, expand and compile a new immutable candidate |
| capture | --run RUN --candidate ID --conditions FILE --session NAME | Render/capture through browse, persist observations and readiness evidence |
| inspect | --run RUN --candidate ID | Evaluate available observations and emit a report/next host request |
| revise | --run RUN --patch FILE | Validate typed changes against the base; compile successor and mark required rechecks |
| verify | --run RUN --candidate ID --require mechanical or release | Verify the explicit claim and emit a gate receipt |
| export | --run RUN --candidate ID --out DIRECTORY | Copy a selected, verified version and required artifacts into a portable bundle |

All accept `--json`, expose `--help`, and return the OperationResult contract. Commands cannot
guess the current browser page or infer a project's ownership from its title. A missing
required candidate, run, project binding or session is a typed error.

`mechanical` requires all applicable machine-evaluable H/P obligations in the chosen
verification scope and all machine-evaluable selected G postconditions to pass, with no
missing required machine condition/measurement. Pending manual obligations are listed
separately. It does not create an aesthetic verdict or full standards-conformance claim.
`release` additionally requires the brief's declared visual/semantic review, complete selected
standards obligations, real application action bindings, author/delegated selection and full
required export coverage. It still reports the exact supported domain.

For intermediate exploration, inspection and a labeled candidate preview remain available
even when release verification is incomplete. An unverified preview is not an export marked
release-ready. An explicit preview export, if later added, needs a distinct claim in its
manifest; it cannot reuse the release result.

`respond` is the common ingestion path for a requested proposal, revision, asset, review or
clarification. It checks request ID, base digest, response schema, source authority and allowed
effects before updating run state. It stores artifacts but never silently executes the next
render, transaction or publication. `compile` and `revise` consume the resulting validated
proposal/patch refs; an explicitly authored program can use the same ingest contract without
a model call. A supplied review identifies its author and source. Human preference/selection
requires a trusted host-provided human source record; the model cannot assert its own output
was a human verdict. A changed locked requirement creates a new brief version, not an ordinary
clarification mutation. Asset responses create a successor manifest and invalidate affected
program/observation bindings.

## 4. Contracts and concurrency

The implementation must generate actual registry declarations through `agent-do harness
contracts propose --tool design`, then validate them against the implemented help surface.
The following is the intended effect model, not a hand-maintained substitute registry block:

| Command | Five-beat effects | Attributes / concurrency |
| --- | --- | --- |
| prepare | Snapshot, Verify, Save | Composite, own_state; per-run write |
| status | Snapshot | Per-run read |
| rules | Snapshot | Catalog read |
| packet | Snapshot, Verify, Save | Composite, own_state; packet-artifact write |
| respond | Interact, Verify, Save | Composite, own_state; per-run input/review write |
| compile | Interact, Verify, Save | Composite, own_state; per-run write |
| capture | Connect, Snapshot, Interact, Verify, Save | Composite, long_running, own_state; explicit browser/run ownership |
| inspect | Snapshot, Verify, Save | Composite, own_state; per-run report write |
| revise | Interact, Verify, Save | Composite, own_state; per-run write |
| verify | Snapshot, Verify, Save | Composite, own_state; per-run receipt write |
| export | Snapshot, Verify, Save | Composite, own_state; destination and run lock |

No command deletes a prior candidate or publishes remotely. Cleanup, if later required, is
a separate explicit operation with retention and archive behavior. Multi-agent work uses
existing coord presence/focus plus distinct run directories and browser sessions. A tool
write lock prevents accidental concurrent mutation of the same run even without coordination.

## 5. Existing browser and DPT surfaces

Current supported browser commands include `open`, `viewport`, `eval`, `snapshot`,
`screenshot --full`, `wait`, and native interactions. The adapter passes arguments as argv,
parses structured output, and pins the explicit session. It does not handcraft CDP or Unix
socket messages. Existing browse implementation details are in the source inventory.

Current DPT supports `scan`, `score`, `report`, `violations`, `baseline`, `diff` and `build`.
Its build assembles utility/layer files and embedded orchestration into an injectable bundle.
The adapter binds a scan to the exact capture/project and archives the raw report. It does
not depend on a nonexistent `src/engine.js` or an npm manifest in DPT.

The current DPT hook can emit scores after frontend edits when a project/browser baseline
matches. The future design skill treats such output as annotation. It must not turn the hook
into an instruction to maximize the aggregate. If discovery or hook changes are needed,
they are explicit integration work with regression tests for ordinary DPT audit users.
No global disabling, score fabrication or parser bypass is part of this design.

The existing `dpt baseline` guard and explicit adapter binding complement each other. The
adapter verifies the current target before capture/scan and retains the baseline project's
identity where baseline/diff is used. A changed URL or unrelated tab produces a binding error.

## 6. Discovery and installation

Implement the tool and skill together after the core vertical slice works. Add registry
capabilities for composing, designing, redesigning and refining websites, plus recommended
entrypoints and capability checks. Keep DPT audit keywords usable. Test overlapping prompts
so a creative design request reaches the composition workflow and a mechanical inspection
request can still reach DPT.

Install through the repository's existing install/bootstrap/skill mechanisms. Capability
checks should be read-only; discovery must not launch a browser or a generation run just to
decide whether the tool is available. Session-start and relevant prompt routing can expose
the compact entry protocol. Exported project packets provide a second explicit entry point
for hosts without automatic discovery hooks.

The system's claim is conditional: any fresh session with the installed entry point and
required capabilities can use the package. A session that never receives the package, lacks
vision or cannot run browser tooling is outside that demonstrated capability. Capability
failures must be apparent before it claims complete design work.

## 7. Fresh-session acceptance scenarios

Test a new project, an existing project, a resumed run, a moved/copied project, and a session
without prior conversation. Test missing vision, missing browser, too-small context, changed
ruleset, changed asset, wrong session, stale patch base, interrupted capture and moved export.
For each, the next action must follow the saved state and named missing capability.

A successful fresh session must produce a new composition from the brief, perform actual
render checks, preserve content/actions and continue a revision without reconstructing this
planning conversation. It must explain consequential choices from the packet's sources and
its own attributed interpretation. No successful test may use hidden handholding from the
planning session.
