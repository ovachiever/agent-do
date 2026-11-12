# Planned security upgrades: milestone 5

**Planned, not implemented.** Turn supported findings into reviewable dependency
updates and draft PRs. Current scan/monitor commands do not update repositories.
Maven/Gradle resolution was added as milestone 2 after the original four-stage
plan; remediation is now milestone 5. Deferred live collectors do not block
remediation of confirmed source findings.

## Intended behavior

- Find explicitly published patched versions and the declaration controlling the
  affected dependency, retaining advisory and dependency-path evidence.
- Recommend direct, property, parent or BOM updates. For example, upgrade the
  Spring Boot parent supplying vulnerable Tomcat rather than blindly pinning it.
- Apply a selected plan in an isolated checkout/branch, run relevant build/tests,
  and rescan the same scope.
- Open a draft PR describing CVEs addressed, changes, compatibility and validation.
  Never automatically merge or deploy.

Planning changes no target files. Explicit apply authorizes its selected reviewable
plan; publishing requires an explicit PR invocation. Existing scans/monitors must
not begin updating repositories implicitly.

## First delivery: Maven and Spring Boot

Support numeric direct versions, version properties and parent/imported-BOM
ownership established from the effective graph. Group CVEs fixed by one controlling
update. Prefer the smallest supported compatible release-line change; show major
upgrades separately. Verify parent/BOM recommendations against published metadata
and the proposed resolved graph, not version-number ordering alone.

Ambiguous ownership, conflicting BOMs, unsupported expressions, unavailable private
metadata and uncertain findings require manual review. Do not infer fixed versions
from NVD bounds. Runtime/image updates need verified vendor patch information;
a Temurin candidate alone cannot justify automatic edits.

## Proposed workflow

These are design stages, **not currently available CLI commands**. Keep them in
the existing `security` family.

| Stage | Behavior and evidence |
| --- | --- |
| Plan | Read a saved assessment and matching revision; produce versioned JSON and a readable proposal without target edits. Build resolution requires explicit authorization. |
| Apply | Reject stale revision/manifest hashes; use an isolated branch/worktree; edit supported controlling declarations and regenerate inventories with native tooling. Save the diff and receipt. |
| Verify | Resolve with the same profiles/settings/configurations, run configured checks and rescan. Retain before/after assessments, commands, remaining/new findings and coverage. |
| Draft PR | Publish explicitly; create/update the matching draft PR with plan/base revision and validation receipts. Retry without duplicate PRs. |

Plan metadata: schema version/fingerprint, repository/ref/commit, assessment ID/time,
manifest hashes, package/version/CVE aliases, declaration ownership, proposed
versions, published fix sources, grouped changes, compatibility and required checks.

## Execution and failure rules

Preserve uncommitted work; never reset, overwrite or force-push the user's branch.
GitHub targets require authenticated access and a selected ref; main is not assumed
to be the deployed revision. Keep build/test/install-hook execution explicit,
following `--allow-builds`. Read-only planning must not execute newly acquired
remote project code. Use normal credential mechanisms without copying settings,
credentials or sensitive raw logs into reports/PRs.

Reuse findings/report/comparison models with separate planner, ecosystem editor,
verification and publication adapters. Reuse matching branches/PRs when plan/base
still match. A successful edit/build alone does not establish remediation: compare
resolved versions and advisory results under the same scope. Failed/incomplete
verification retains the original assessment, diff and failure summary; never
label it a verified fix or claim deployment remediation. Any deliberately published
unverified draft must state failures and remaining findings.

## Delivery and acceptance

1. **Planner:** test direct/property/parent/BOM ownership, grouped fixes, missing or
   withdrawn fixes, candidates, stale plans and private metadata failures.
2. **Maven editor:** preserve XML/comments and unrelated changes; reject ambiguous
   edits; apply only in an isolated worktree.
3. **Verification:** cover successful remediation, unchanged vulnerabilities, new
   findings, scope changes and build/resolution/scanner failures.
4. **Draft PR adapter:** use an explicitly authorized disposable repository; verify
   retry deduplication and the absence of merge/deploy operations.
5. **Later editors:** Gradle, JavaScript locks, then Python locks, each independently
   accepted. Scanner support does not imply updater support. Use native package
   managers to regenerate locks, not manual transitive-entry edits.

Container/runtime updates are later adapters once vendor fixes and declaration
ownership are verifiable. Cluster mutations, OS patch installation and speculative
framework migrations are outside the first delivery. Acceptance needs deterministic
fixtures, existing regressions and one disposable Maven project with a confirmed
update; unrelated live cluster/portfolio retests are unnecessary for focused fixes.

## Optional aggregator follow-ups

cve.now advisory discovery is now implemented separately from remediation; see
[usage and boundaries](CVENOW_DISCOVERY.md). Further options include public
GHSA/OSV-ID lookup and external RSS subscriptions. Numeric EPSS thresholds need an
API that actually supplies probabilities; `epssReached` is only a dated event.
Scheduled general advisory feeds and restricted interactive MCP access remain
future work. No lockfile uploads, stack checks or repository-derived queries are
planned for this adapter.
