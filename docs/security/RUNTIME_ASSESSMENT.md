# Runtime and deployment evidence

`agent-do security runtime` assesses explicit runtime evidence alongside source
scans. A POM's `java.version=17` is a declaration, not proof of production's JDK
patch. Nothing updates or deploys your project. See [collector setup](RUNTIME_COLLECTION.md),
[all parameters](SECURITY_CLI_REFERENCE.md#runtime-explicit-evidence-and-applicability)
and [accepted/deferred scope](RUNTIME_COLLECTION.md#validation-status).

For CPython interpreter checks and four-hour monitoring, see the
[Python runtime guide](PYTHON_RUNTIME.md). Python package dependency scans remain separate.

## Test a local Java project

```bash
agent-do security runtime --path ~/workspace/my-service --local-java --inventory-only --json
agent-do security runtime --path ~/workspace/my-service --local-java --cvss-min 7 --include-unscored --json
```

`--local-java` executes the selected trusted Java binary with
`-XshowSettings:properties -version`; `--java PATH` selects another executable.
Only vendor, Java/runtime versions and VM name are captured, with executable and
observation time. Raw properties/environment/output are not saved. This does not
execute Maven/Gradle or establish which JDK a build, container or deployment uses.

| Observed distribution | Assessment identity |
| --- | --- |
| Oracle Corporation HotSpot, Java 11+ | `oracle:jdk` CPE. |
| Older Oracle Java | Explicit verified JDK/JRE identity required. |
| Eclipse Adoptium | Temurin adapter using Adoptium's official VDR. |
| Other/unmapped distribution | Incomplete until a verified identity/adapter is supplied. |

For an actual Oracle JDK only:

```bash
agent-do security runtime --local-java --java /path/to/oracle-jdk/bin/java \
  --java-cpe 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*' --json
```

Oracle identities are rejected on observed non-Oracle distributions. An explicit
identity is caller-selected, not independently verified. The template requires
exact part/vendor/product and wildcard version/update; malformed templates show
an inline example. Do not substitute Oracle for Temurin, Corretto or another JDK.

## Oracle identities and negative results

Modern Oracle advisories use `oracle:jdk`/`oracle:jre`. Legacy `oracle:java_se`
queries explicitly have limited/incomplete modern JDK coverage. Verify the artifact
before changing identity; existing reports remain unchanged and identity changes
create a new monitor scope. A narrow identity returning zero is not a secure-JDK claim.

There is no default severity threshold. Unscored findings remain unless a supplied
filter excludes them. Complete means the requested scope completed, even with CVEs.

## Project declarations

`--path DIR` reads root POM/compiler properties, recognized Gradle literals,
`.java-version`, `.tool-versions` and Docker `FROM` references. Unresolved expressions
stay labeled; it does not evaluate scripts, resolve parent/property inheritance or
traverse submodules. Only Gradle version expressions are captured, not whole lines.

```bash
agent-do security runtime --path /path/to/project --inventory-only --json
agent-do security runtime --path /path/to/project --json
```

The first completes declaration collection without assessing CVEs. The second
remains incomplete without runtime evidence. Mutable image tags or compiler targets
cannot establish an installed patch. Use `scan --resolve maven|gradle` separately
for resolved libraries; library scans do not automatically assess Java/Node binaries.

## Import deployment or image inventory

Supply a versioned JSON file with verified identities and observation times. This
example shows the schema, not a recommended or secure version:

```json
{
  "schema_version": 1,
  "components": [{
    "id": "bff-prod-jdk",
    "cpe": "cpe:2.3:a:oracle:jdk:17.0.12:*:*:*:*:*:*:*",
    "evidence": {
      "kind": "deployment_inventory",
      "source": "Observed vendor/version in the selected deployment",
      "observed_at": "2026-10-22T09:00:00Z"
    },
    "deployment": {
      "environment": "production",
      "cluster": "team-cluster",
      "namespace": "services",
      "workload": "bff"
    }
  }]
}
```

```bash
agent-do security runtime --inventory ~/runtime-inventory.json --json
agent-do security runtime --inventory ~/runtime-inventory.json --cve CVE-2024-21235 --json
```

Each component requires a unique nonempty `id`, exactly one `cpe` or supported
`java` identity, and `evidence` containing exactly `kind`, `source`, `observed_at`.
CPE part/vendor/product/version must be exact. Temurin's alternative `java` shape
is in the [vendor guide](RUNTIME_COLLECTION.md#what-temurin-coverage-means).
Evidence kinds are `manual`, `deployment_inventory`, `image_inventory`; future
timestamps are rejected. Imported evidence is labeled
`user_supplied_not_independently_verified`. Reassessment does not refresh its age
or prove the deployment changed.

Optional deployment labels are `environment`, `cluster`, `namespace`, `workload`,
`image`, `image_digest`, `host`, all strings. Use actual versions/digests from your
collector; a desired configuration, GitHub URL or mutable tag is insufficient.
Import alone invokes no image/cluster/SSH collector. Keep credentials out of labels
and provenance.

Other runtime/platform CPEs can be represented when identities and version semantics
are supported. Distro backports and unsupported revision schemes remain uncertain;
this CPE path is not an OS package advisory scanner. Use Trivy-backed collection
for vendor package assessment. General CycloneDX/SPDX files are not directly accepted
as runtime inventory; convert verified evidence to the documented schema.

## Match strength and coverage

NVD product queries use bounded pagination. Original configuration evidence is
retained: AND/OR, negation, vulnerable flags, exact versions and numeric bounds are
evaluated. A version-range boundary is not inferred as a published fix.

| Result | Meaning |
| --- | --- |
| `inventory_match` | Supplied evidence satisfies supported conditions; not proof of exploitability, reachability or independent verification. |
| `candidate` | Missing evidence or unsupported semantics prevent applicability confirmation; coverage remains incomplete. |
| Nonmatch/rejected advisory | Excluded when supported evaluation establishes nonmatch, or the record is rejected. |

Environment prerequisites can use other components only with identical deployment
labels including a host, image digest, or cluster+namespace+workload. An environment
name alone is insufficient. Local Java is not implicitly co-located with imports;
OS evidence from another server cannot satisfy this target's prerequisites.

`--limit` defaults to 1000 NVD records per component; truncation is incomplete.
Increase it or use a targeted CVE query. Score/date filters apply after assessment;
failed pages, stale cache and unknown conditions remain coverage gaps. Cache freshness
is distinct from database publication and deployment observation times.

Reports use the private append-only store and existing `report` selectors/filters.
`--latest-complete` spans projects/commands, including inventory-only reports.
Check target, timestamp and scope. Exit 0 means completed, 1 incomplete, 2 invalid
input/state; an inventory-only success makes no CVE claim.

## Historical Java bounds and matcher revisions

Supported Java forms include modern patch/build versions, `7u`/`8u`, legacy
`1.x.y_N`, separate update fields and leading zeroes. For example, `1.8.0_422`
normalizes to version `1.8.0`, update `update_422`. Unsupported vendor/EA ordering
stays uncertain. Wildcard criteria still obey any supplied numeric bounds.

A non-vulnerable platform prerequisite alone does not make the JDK vulnerable.
Unrelated escaped NetApp/WebKit predicates do not contaminate Java branches;
unsupported relevant conditions remain unknown. Public regression extracts retain
historical affected-version positives and modern/patched negatives.

Reports identify matcher schema 3. Changed matching rules create a separate monitor
baseline; earlier issues remain unverified, not reported as deployment fixes.
Existing saved reports/history are not rewritten.

## Include runtimes in a recurring portfolio

```bash
agent-do security monitor init --config ~/runtime-monitor.json \
  --runtime-inventory ~/runtime-inventory.json --interval-hours 24
agent-do security monitor run --config ~/runtime-monitor.json --runtime-limit 2000 --json
agent-do security monitor report --config ~/runtime-monitor.json --json
```

Add `--runtime-inventory FILE` alongside `--path DIR` or `--repos-file FILE` at init,
or add a `runtime_inventory` target to existing config. Relative paths resolve beside
that config. Imported targets accept only that field and run no implicit local Java
probe; refresh observations through your approved collector when needed.

Stable component IDs separate issues. Version updates compare in the same scope;
absence resolves only with complete compatible evidence. Changed membership/product/
deployment/evidence kind creates a new scope. Missing files, partial queries and
unknown conditions retain unverified history. See [monitoring](PORTFOLIO_MONITORING.md)
for scheduling, execution guards and notifications.

## Validation

Run `python3 tests/test_security_runtime.py` from the repository root for offline
matcher/evidence regressions. See [collector validation status](RUNTIME_COLLECTION.md#validation-status)
for live integration limits.
