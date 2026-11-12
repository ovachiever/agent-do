# Security command and parameter reference

This reference covers every option currently accepted by `agent-do security`.
Use the [scanning guide](README.md) for installation and how to read
coverage. Commands below assume agent-do is installed; run `./agent-do` instead
from its checkout if needed. Replace example repository names and `/path/to/...`
paths with your own. Example version overrides illustrate syntax, not a
recommendation that a particular release is secure or compatible.

## Choose a command

| Command | Purpose | Requirements |
| --- | --- | --- |
| `agent-do security find` | Search published advisories, including products your team does not use. | Access to NVD/GitHub advisory APIs; no scanner required. |
| `agent-do security scan` | Match source dependency versions in a local project, GitHub repository, or repository list. | OSV-Scanner v2; remote acquisition also needs authenticated `gh` access. Explicit JVM resolution also needs Java and Maven/Gradle. |
| `agent-do security runtime` | Assess explicit runtime versions and deployment evidence, keeping project declarations separate. | NVD for assessment; optional explicit local Java executable probe or imported runtime inventory. Inventory-only skips advisories; explicit artifact/cluster collectors may contact registries/APIs. |
| `agent-do security report` | Read and filter an existing unfiltered report. | A saved report; no network or scanner required. |
| `agent-do security doctor` | Check local scanner prerequisites and credential presence. | No network requests; does not establish authentication or run project builds. |
| `agent-do security monitor` | Configure portfolios, compare evidence, export recurring jobs and explicitly request notifications through init/run/report/schedule. | Scanner/gh/build prerequisites on the scan host; POSIX locking for runs, cron for an installed recurring job. |

Put options **after the subcommand**. Unless stated otherwise, value options
accept one value, are not repeatable, and have no active restriction when omitted.
Boolean flags are off by default. Shared presentation filters combine with AND;
repeated targets combine with OR. Filters never remove findings from the saved
`find`/`scan`/`runtime` report.

## Help and output

| Parameter | Commands | Behavior and default | Example |
| --- | --- | --- | --- |
| `-h`, `--help` | Top level and all subcommands | Print help and exit; no assessment runs. | `agent-do security --help` or `agent-do security scan --help` |
| `--json` | All assessment commands and monitor subcommands | Emit one JSON document instead of human-readable output. | `agent-do security doctor --json` |

```bash
agent-do security find --help
agent-do security scan --help
agent-do security report --help
agent-do security doctor --help
```

## Shared finding filters

All parameters in this table are available on **find, scan, runtime and report**,
and on **monitor run/report**. Runtime rejects package `--ecosystem` selectors;
use `--package vendor:product`. Runtime inventory-only rejects advisory filters.
Examples use saved reports so you can experiment without repeating a scan.
On `find`, ecosystem/package flags also choose source query criteria.

| Parameter | Values, default and meaning | Example |
| --- | --- | --- |
| `--cve ID` | `CVE-YYYY-NNNN` with at least four digits in the final component; matches advisory aliases, case-insensitively. Does not accept a GHSA ID. | `agent-do security report --latest --cve CVE-2021-44228 --json` |
| `--ecosystem NAME` | One ecosystem or alias from the list below. Filters affected package ecosystems. | `agent-do security report --latest --ecosystem java --json` |
| `--package NAME` | Exact package name, matched case-insensitively during presentation. **find requires `--ecosystem`**; scan/report do not. Maven coordinates use `group:artifact`. | `agent-do security find --ecosystem pypi --package litellm --json` |
| `--cvss-min NUMBER` | Inclusive minimum base score, 0–10. Uses the highest available numeric base score. Mutually exclusive with `--cvss-gt`. | `agent-do security report --latest --cvss-min 7 --json` |
| `--cvss-gt NUMBER` | Exclusive minimum base score, 0–10; `7` excludes exactly 7.0. Mutually exclusive with `--cvss-min`. | `agent-do security report --latest --cvss-gt 7 --json` |
| `--include-unscored` | Retain records with no numeric score when using a CVSS threshold. Without a threshold, unscored records are already eligible; other filters can still exclude them. | `agent-do security report --latest --cvss-min 7 --include-unscored --json` |
| `--severity LIST` | Comma-separated values: `critical,high,medium,low,none,unknown`. Case-insensitive; use no spaces. Matches any listed severity. | `agent-do security report --latest --severity critical,high --json` |
| `--published-after DATE` | Inclusive advisory publication boundary. ISO date or timestamp; omitted timezone means UTC. | `agent-do security report --latest --published-after 2026-10-15 --json` |
| `--published-before DATE` | Exclusive advisory publication boundary; must be later than `--published-after` if both are supplied. | `agent-do security report --latest --published-after 2026-10-15 --published-before 2026-10-22 --json` |
| `--updated-after DATE` | Inclusive advisory revision boundary, using the same date format. It is not the date your repository changed. | `agent-do security report --latest --updated-after 2026-10-01T12:00:00Z --json` |
| `--known-exploited` | Keep only records matched by a CVE alias in CISA KEV. find/scan fetch the catalog automatically. report requires previously enriched evidence and rejects findings whose exploitation status is unknown. | `agent-do security scan --path . --known-exploited --json` |
| `--fix-available` | Keep advisories **with** an explicitly published fixed package version; does not remove them. If all 17 findings have fixes, all 17 remain. Does not test upgrade compatibility or infer a fix from NVD CPE bounds. | `agent-do security report --latest --fix-available --json` |

`--package` and `--fix-available` can be combined for runtime/package findings.
Fix entries without their own package identity use the finding's package;
an explicitly different package's fix is never borrowed.

Accepted ecosystem names and normalization:

| Accepted input | Package ecosystem |
| --- | --- |
| `python`, `pypi`, `pip` | pip / Python packages |
| `javascript`, `node`, `npm` | npm packages |
| `php`, `composer`, `packagist` | Composer packages |
| `java`, `maven` | Maven packages |
| `rust`, `crates.io` | Rust packages |
| `go`, `rubygems`, `nuget`, `pub`, `erlang`, `actions`, `swift` | Same named ecosystem |

An ecosystem filter refers to packages, not an installed runtime or cloud
platform. For example, `--ecosystem node` does not inventory the Node.js binary.
There are no discovery `--java`, `--python`, `--oracle`, `--since`, or `--days` flags.
Runtime has a distinct `--java EXECUTABLE` option described below.
Use `--target`, `--ecosystem`, `--vendor`/`--product`, and explicit date boundaries.

## Find: advisory sources and targets

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--target NAME` | **Repeatable.** Canonical names: `java`, `spring-boot`, `angular`, `nodejs`, `aks`. Case-insensitive aliases: `springboot` → `spring-boot`, `node` → `nodejs`. Uses curated queries; duplicate targets do not repeat searches. Cannot combine with vendor/product/query/ecosystem/package selectors or an explicit source other than `auto`. | `agent-do security find --target java --target springboot --target angular --target node --target aks --cvss-min 7 --json` |
| `--source NAME` | `auto` (default) prefers cve.now for compatible CVE/global/supported ecosystem/package discovery, falling back on error/stale data to NVD or GitHub respectively. NVD-only selectors, curated targets and unsupported aggregator ecosystems keep their original routes. Healthy capped feeds remain incomplete. Pin `nvd`, `github` or `cve-now` to disable failover. Explicit NVD rejects ecosystem/package; explicit GitHub rejects vendor/product/query. | `agent-do security find --source github --ecosystem npm --package @angular/core --json` |
| `--technology SLUG` | cve.now recent-feed selector; requires `--source cve-now`. Examples: `spring`, `log4j`, `node`, `php`, `kubernetes`. Not a repository match; bounded feed coverage remains incomplete. | `agent-do security find --source cve-now --technology spring --limit 10 --json` |
| `--feed-filter NAME` | cve.now curated `critical` or `kev` feed; requires `--source cve-now`. The curated critical category is distinct from CVSS severity. Cannot accompany direct `--cve` lookup. | `agent-do security find --source cve-now --feed-filter kev --limit 10 --json` |
| `--source-status` | Include cve.now self-reported polling/history status; requires `--source cve-now`. Unhealthy/unavailable status makes the assessment incomplete without dropping findings. | `agent-do security find --source cve-now --cve CVE-2021-44228 --source-status --json` |
| `--vendor NAME` | NVD CPE vendor component, e.g. `oracle`. Letters, digits, underscore, dot and hyphen only. Requires NVD/auto; cannot combine with ecosystem/package. No curated vendor alias conversion. | `agent-do security find --vendor oracle --product jdk --cvss-gt 7 --json` |
| `--product NAME` | NVD CPE product component, e.g. `cpython`. Same syntax/source restrictions as vendor. Can be used without vendor. | `agent-do security find --product cpython --cvss-min 7 --json` |
| `--query TEXT` | Broad NVD keyword search; quote multiple words. Not an exact product identity. Unsupported with GitHub source or curated targets. | `agent-do security find --query 'java runtime' --cvss-min 7 --json` |
| `--limit INTEGER` | Positive integer, default **100 source records examined before presentation filters**. With targets, applies independently to each component query, not the combined output. Exhausting the limit while more records exist marks coverage truncated/incomplete. Automatic fallback has its own record limit. | `agent-do security find --target spring-boot --limit 500 --json` |

Target queries and candidate relevance are documented in
[multi-target discovery](MULTI_TARGET_DISCOVERY.md). Java profiles are curated
rather than exhaustive; Spring Boot and Angular profiles search selected package
identities. AKS/Kubernetes advisory candidates do not establish that your cluster
is affected. `find` does not scan any repository or deployment.

See [cve.now discovery](CVENOW_DISCOVERY.md) for automatic preference/fallback, supported
selectors, provenance and capped-feed limitations.

### Search a seven-day or thirty-day publication window

These fixed examples end at **2026-10-22 00:00 UTC**, exclusively. Change the dates
for your run. Database publication dates can lag vendor announcements. The
following use the same lower-inclusive, upper-exclusive boundaries:

```bash
# Seven days across several platforms.
agent-do security find --target java --target springboot --target angular \
  --target node --target aks \
  --published-after 2026-10-15 --published-before 2026-10-22 \
  --cvss-min 7 --include-unscored --json

# Thirty days of Python package advisories.
agent-do security find --ecosystem python \
  --published-after 2026-09-22 --published-before 2026-10-22 \
  --limit 500 --json
```

For NVD discovery, each requested publication/modification interval must be
positive and at most **120 days**. If only the publication start is given, its
end is request time. If only the publication end is given, its start is 120 days
earlier. An update start uses request time as its end. With no date filters,
there is no automatically imposed 120-day publication window. These API window
rules do not limit local filtering of saved reports. Combined date filters must
match one captured source event, rather than mixing dates from different sources.

## Scan: choose exactly one input

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--path DIR` | Local source directory, including uncommitted dependency files. Required unless repo or repos-file is given; mutually exclusive with both. Local Git identity is recorded when available. | `agent-do security scan --path /path/to/service --json` |
| `--repo REPOSITORY` | GitHub HTTPS repository URL or `owner/repo`. Resolves the selected ref to an immutable commit and fetches dependency files through `gh`. Mutually exclusive with path/repos-file. | `agent-do security scan --repo https://github.com/my-team/backend --json` |
| `--repos-file PATH` | Local UTF-8 text or JSON repository list. Scans every unique repo/requested-ref pair sequentially; failures do not stop later repos. Mutually exclusive with path/repo. | `agent-do security scan --repos-file ~/team-repos.txt --cvss-min 7 --include-unscored --json` |
| `--ref REF` | Branch, tag or commit. Requires repo or repos-file. Default: each repo's default branch. For a list, supplies a shared default; JSON per-entry refs override it. | `agent-do security scan --repo my-team/backend --ref release/1.x --json` |
| `--scanner EXECUTABLE` | Trusted OSV-Scanner v2 command/path. Default: `osv-scanner` on PATH. Also available on doctor. | `agent-do security scan --path . --scanner /usr/local/bin/osv-scanner --json` |
| `--scanner-diagnostics DIR` | **Opt-in**, scan only. Save raw scanner invocation stderr in a unique mode-0600 file under DIR (new directory mode 0700). No raw diagnostics saved by default. Can contain credentials/private paths; inspect locally before sharing. Does not change coverage status or capture Maven/Gradle logs. Each batch repository gets a separate file. | `agent-do security scan --path . --resolve maven --scanner-diagnostics ~/private-security-diagnostics --json` |
| `--scan-timeout SECONDS` | Finite positive number. Default **300** on scan; timeout per scanner, GitHub or build subprocess invocation, including probes. Not a whole-batch deadline. Also on doctor, with a different default below. | `agent-do security scan --repos-file ~/team-repos.txt --scan-timeout 600 --json` |
| `--dependabot` | Attach separately scoped GitHub default-branch alerts. Requires repo or repos-file and the `gh alerts` provider from PR #51 or its successor. Unavailable/disabled alerts make coverage incomplete; alerts are not merged as commit-equivalent findings. | `agent-do security scan --repo my-team/backend --dependabot --json` |

A plain `team-repos.txt` can contain whole-line comments and blank lines:

```text
# My team's repositories
https://github.com/my-team/backend
my-team/frontend
my-team/shared-library
```

For different branches, use `team-repos.json`:

```json
[
  "my-team/backend",
  {"repo": "my-team/frontend", "ref": "release/1.x"},
  {"repo": "my-team/shared-library", "ref": null}
]
```

```bash
agent-do security scan --repos-file ~/team-repos.json --ref main --json
```

Here backend uses `main`, frontend uses `release/1.x`, and the library's explicit
null selects its default branch. Text files accept one repo per line, not local
directory paths, wildcards, embedded credentials, inline comments or non-GitHub
hosts. JSON objects accept only `repo` and optional `ref`. See
[repository-list scanning](REPOSITORY_LIST_SCANNING.md) for duplicate handling,
per-repository evidence, coverage and report counts.

## Scan: explicit Maven and Gradle resolution

Every option in this table is **scan-only**. `--resolve` requires a trusted
local `--path`; it executes project build code and permits build/cache writes.
It is rejected with repo and repos-file. File-only scans never enable it
implicitly. Run in the environment/settings whose selected dependencies matter.

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--resolve TOOL` | `maven` or `gradle`. Off by default. Resolve selected versions, including inherited/BOM-managed and transitive dependencies, and scan a generated SBOM. | `agent-do security scan --path . --resolve maven --json` |
| `--maven EXECUTABLE` | Requires resolve maven. Default: executable project `./mvnw`, then installed `mvn`. Overrides the selected executable. | `agent-do security scan --path . --resolve maven --maven /opt/maven/bin/mvn --json` |
| `--gradle EXECUTABLE` | Requires resolve gradle. Default: executable project `./gradlew`, then installed `gradle`. | `agent-do security scan --path . --resolve gradle --gradle /opt/gradle/bin/gradle --json` |
| `--maven-profile NAME` | **Repeatable**, resolve maven only. Explicitly activate each named profile. Default: no additional requested profiles; normal Maven implicit activation still applies. | `agent-do security scan --path . --resolve maven --maven-profile prod --maven-profile cloud --json` |
| `--maven-settings PATH`, `--settings PATH` | Aliases for an existing Maven settings.xml; resolve maven only. Forwarded as Maven `--settings`. Default: normal Maven settings, including `~/.m2/settings.xml`. Use for private Artifactory/Nexus repositories; server IDs must match repository/mirror IDs. | `agent-do security scan --path . --resolve maven --settings ~/.m2/settings.xml --json` |
| `--gradle-configuration NAME` | **Repeatable**, resolve gradle only. Default: `runtimeClasspath`. Supplying any replaces that default, so repeat runtimeClasspath explicitly if you also want it. Missing/unresolvable requested configurations are coverage gaps. | `agent-do security scan --path . --resolve gradle --gradle-configuration runtimeClasspath --gradle-configuration testRuntimeClasspath --json` |
| `--build-property NAME=VALUE` | **Repeatable**; requires resolve. Maven `-D` or Gradle `-P` property. Default: no overrides. Names are letters/digits/underscore/dot/hyphen. Quote the whole assignment if its value contains spaces. Values are not saved as property metadata; keep credentials out of command lines. | `agent-do security scan --path . --resolve maven --build-property spring-framework.version=6.1.14 --build-property skipTests=true --json` |

Profile/configuration names accept letters, digits, underscore, dot, exclamation
mark and hyphen; repeat the option instead of passing comma-separated names.
Property names `outputFile`, `outputType`, `verbose`, `appendOutput`, `skip`,
`mdep.skip`, and names starting `agentdo.security.` are reserved for inventory
capture and rejected. Maven options cannot be used with Gradle, or vice versa.
All build options require explicit resolution.

[JVM dependency resolution](JVM_DEPENDENCY_RESOLUTION.md) describes scopes,
modules, excluded configurations, wrappers, side effects and unresolved gaps.
Resolution does not establish what is packaged, installed or deployed.

## Runtime: explicit evidence and applicability

See [runtime assessment](RUNTIME_ASSESSMENT.md) for the inventory JSON schema,
match strength, vendor mappings, deployment labels and assessment limits.
At least one of path, inventory, local-java, local-python or explicit collectors is required; they may be combined.

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--path DIR` | Static root POM/Gradle/tool-version/Dockerfile hints; no build execution or parent resolution. Does not establish an installed runtime. | `agent-do security runtime --path . --inventory-only --json` |
| `--inventory PATH` | Versioned local runtime/deployment JSON with exact CPE identities and provenance; imported evidence is not independently verified. | `agent-do security runtime --inventory ~/runtime-inventory.json --json` |
| `--local-java` | Explicitly execute a trusted local Java binary to observe vendor/version/VM properties. Default off; does not select a deployed or Maven JDK implicitly. | `agent-do security runtime --path . --local-java --inventory-only --json` |
| `--java EXECUTABLE` | Requires local-java; default installed java on PATH. Select another trusted Java executable. | `agent-do security runtime --local-java --java /path/to/jdk/bin/java --inventory-only --json` |
| `--java-cpe CPE` | Requires local-java; caller-verified CPE 2.3 distribution identity with explicit part/vendor/product and wildcard version/update. Oracle Corporation HotSpot on Java 11+ maps to oracle:jdk; older JDK/JRE artifacts require an explicit identity; Eclipse Adoptium uses its separate official Temurin VDR adapter; other distributions need verified identity work and remain unmapped by default. This example is for Oracle Java, not all JDKs. An observed non-Oracle vendor rejects an Oracle Java identity before lookup; format errors include an inline example. | `agent-do security runtime --local-java --java-cpe 'cpe:2.3:a:oracle:jdk:*:*:*:*:*:*:*:*' --json` |
| `--local-python` | Explicitly probe the selected Python using `-I -S`; does not execute checkout/site startup modules. Final CPython releases map to upstream NVD identities; PyPy/prereleases remain unmapped. | `agent-do security runtime --local-python --inventory-only --json` |
| `--python EXECUTABLE` | Requires local-python; defaults to the interpreter executing agent-do. Select the trusted interpreter actually used by your environment. | `agent-do security runtime --local-python --python /path/to/venv/bin/python --json` |
| `--python-upstream` | Requires local-python; caller verifies the build follows upstream CPython patch status. Without this verification, vendor backports are unknown and version matches remain candidates. | `agent-do security runtime --local-python --python-upstream --json` |
| `--probe-timeout SECONDS` | Finite positive local Java/Python subprocess timeout, default **15** seconds. | `agent-do security runtime --local-java --probe-timeout 30 --inventory-only --json` |
| `--inventory-only` | Collect/save evidence without advisory lookup; explicit image/cluster collectors may contact registries/APIs. Rejects advisory score/date/CVE/exploitation filters. | `agent-do security runtime --inventory ~/runtime-inventory.json --inventory-only --json` |
| `--limit INTEGER` | Positive NVD record bound **per runtime component**, default **1000** before presentation filters. Truncation remains incomplete. | `agent-do security runtime --inventory ~/runtime-inventory.json --limit 2000 --json` |

Shared finding filters (except ecosystem), JSON, and the HTTP/cache/KEV controls
below also apply. Runtime package names are CPE `vendor:product`, not Maven
coordinates. Unsupported CPE/version conditions and missing environment evidence
remain labeled candidates with incomplete coverage. No published fix is inferred
from NVD version bounds. Explicit image/rootfs/Kubernetes collection and Adoptium VDR assessment are documented in [runtime collection](RUNTIME_COLLECTION.md), including every added flag and example.

## HTTP, cache and enrichment options

These options are available on **find, scan, runtime and monitor run**.
Runtime inventory-only skips advisory requests; explicit artifact/cluster collectors may contact registries/APIs. HTTP/cache flags control
agent-do's advisory and KEV client, **not** `gh`, Maven/Gradle or OSV-Scanner's
own network/cache/retry behavior. A file-only scan without KEV enrichment may
make no requests through this client. Use scan-timeout for external subprocesses.

| Parameter | Values, default and meaning | Example |
| --- | --- | --- |
| `--timeout SECONDS` | Finite positive number, default **15**. Per advisory/KEV HTTP request timeout; also bounds accepted Retry-After delays. Not a full-command deadline. | `agent-do security find --target java --timeout 30 --json` |
| `--retries INTEGER` | Nonnegative integer, default **2** retries after the first request. Retries HTTP 429/500/502/503/504; ordinary connection failures/timeouts are not automatically retried. | `agent-do security find --ecosystem npm --retries 0 --json` |
| `--cache-ttl SECONDS` | Finite positive number, default **3600** (one hour). Maximum age for a fresh client cache hit; does not change report retention. | `agent-do security find --target angular --cache-ttl 300 --json` |
| `--refresh` | Bypass fresh client cache and fetch again. Does not force upstream databases to publish new data. May still fall back to an explicitly allowed cached response if fetching fails. | `agent-do security find --target angular --refresh --json` |
| `--allow-stale` | Permit marked cached-response fallback after a fetch failure. Makes coverage incomplete (exit 1), even if findings are returned. Does not create offline OSV scanning support. | `agent-do security find --target java --allow-stale --json` |
| `--max-bytes INTEGER` | Positive integer, default **16777216** (16 MiB). Bounds each client response, input manifest, repository-list file, and captured subprocess stream/build inventory where applicable. Not a portfolio-wide total. Also on doctor. | `agent-do security scan --repos-file ~/team-repos.txt --max-bytes 33554432 --json` |
| `--kev` | Enrich all findings with CISA KEV match status without filtering to matches. Default: exploitation status unknown. `--known-exploited` already requests enrichment. Catalog failure leaves unknown status and incomplete coverage. | `agent-do security scan --path . --kev --json` |

The HTTP client caches responses under `$AGENT_DO_HOME/security/cache` (default
`~/.agent-do/security/cache`). Refresh/TTL options do not delete prior reports.
NVD requests share rate pacing. Truncation, errors, stale data and unresolved
inventory remain visible regardless of presentation filters.

## Report: choose saved evidence

Shared finding filters above and JSON/help are supported. Report has **no**
network/cache/enrichment flags; it cannot refresh a source or run a new scan.

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--latest` | Read the newest saved report, including incomplete runs; the default without a selector. Explicitly flags an incomplete assessment and suggests recovery commands. Does not silently substitute older results. | `agent-do security report --latest --cvss-min 7 --json` |
| `--latest-complete` | Explicitly select the newest report whose status is complete, skipping incomplete/unreadable reports. Searches **all projects and commands**; may select older findings for a different project, including inventory-only evidence with no CVE assessment. Shows a selection note; errors if no complete report exists. | `agent-do security report --latest-complete --severity critical,high --json` |
| `--list` | List all saved reports newest first, with timestamps, targets, assessment status, finding/unscored counts, coverage gaps and file paths. Does not display finding details or accept finding filters. Empty list exits 0; unreadable entries are shown and make listing exit 1. Incomplete assessments listed normally do not make listing fail. | `agent-do security report --list --json` |
| `--file PATH` | Read a specific saved JSON report. This is a report file, **not** a repository-list input. | `agent-do security report --file /path/to/report.json --severity critical,high --json` |
| `--target NAME` | **Repeatable**, same names/aliases as find. Only filters saved multi-target advisory discovery to targets originally searched; errors if any requested target was not searched. Does not select repository names in a batch report or initiate new searches. | `agent-do security report --latest --target java --target springboot --json` |

`find`/`scan`/`runtime` save unfiltered schema-version-1 JSON in
`$AGENT_DO_HOME/security/reports` (default `~/.agent-do/security/reports`). Report
filtering is read-only and does not save another copy. Record the printed
`saved_report` path to revisit a particular assessment rather than relying on
latest. Reports can contain private repository/package identities.

`--latest`, `--latest-complete`, `--list` and `--file` are mutually exclusive.
After a failed Gradle scan, `--latest` still shows that failure rather than an
older Maven assessment. Use `--list` to locate the earlier project's file and
then `--file` to refilter it. Listing and selection never rewrite saved evidence.
JSON selection notices appear in `selection_notes`; JSON listing uses `reports`
metadata entries rather than the single-report `findings`/`summary` shape.

## Doctor: local prerequisites

These are the complete doctor options; help and JSON behave as described above.
Doctor checks scanner availability/version and reports other feature prerequisites
and credential presence. It does not validate upstream access or execute builds.

| Parameter | Values and default | Example |
| --- | --- | --- |
| `--scanner EXECUTABLE` | Trusted scanner to probe using `--version`; default `osv-scanner` on PATH. | `agent-do security doctor --scanner /usr/local/bin/osv-scanner --json` |
| `--scan-timeout SECONDS` | Finite positive number, default **15**, for the scanner version subprocess. Scan's default is 300. | `agent-do security doctor --scan-timeout 30 --json` |
| `--max-bytes INTEGER` | Positive integer, default **16777216**, maximum captured subprocess stream size. | `agent-do security doctor --max-bytes 1048576 --json` |

## Monitor: portfolio configuration, runs and digests

See [portfolio monitoring](PORTFOLIO_MONITORING.md) for configuration fields,
comparison semantics, state recovery, cron installation and notification setup.
These verbs remain inside the existing security family. Help is available on
`agent-do security monitor --help` and each nested subcommand.

### monitor init

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--config PATH` | Required destination JSON file. Creates privately; refuses to overwrite an existing file. | `agent-do security monitor init --config ~/team-security.json --repos-file ~/team-repos.txt --json` |
| `--repos-file PATH` | Initialize targets from a text/JSON GitHub list; mutually exclusive with path; runtime-inventory may accompany it. Copies normalized entries, not a live reference to the list. | `agent-do security monitor init --config ~/team-security.json --repos-file ~/team-repos.txt` |
| `--path DIR` | Initialize one local target; mutually exclusive with repos-file; runtime-inventory may accompany it. Relative input becomes an absolute path. | `agent-do security monitor init --config ~/bff-security.json --path ~/workspace/map-managed-bff --json` |
| `--resolve TOOL` | Optional maven/gradle resolution plan; requires path. Does not execute it during initialization. Runs/scheduled jobs need allow-builds. | `agent-do security monitor init --config ~/bff-security.json --path ~/workspace/map-managed-bff --resolve maven` |
| `--local-python` | Add a local interpreter target, alone or alongside source/other runtime targets. Init saves selection without executing Python. | `agent-do security monitor init --config ~/agent-do-security.json --path /path/to/agent-do --local-python --interval-hours 4 --json` |
| `--python EXECUTABLE` | With local-python, freeze this trusted interpreter's absolute selection; default agent-do's interpreter. Re-probed on each authorized run. | `agent-do security monitor init --config ~/python-security.json --local-python --python /path/to/venv/bin/python --json` |
| `--python-upstream` | With local-python, store explicit caller verification of upstream CPython patch status; default off. | `agent-do security monitor init --config ~/upstream-python.json --local-python --python-upstream --json` |
| `--probe-timeout SECONDS` | Finite positive timeout stored with the Python probe; default **15** seconds. | `agent-do security monitor init --config ~/python-security.json --local-python --probe-timeout 30 --json` |
| `--runtime-inventory PATH` | Add a runtime inventory target, alone or alongside path or repos-file. Validate inventory without contacting NVD or executing probes. | `agent-do security monitor init --config ~/runtime-monitor.json --runtime-inventory ~/runtime-inventory.json --json` |
| `--interval-hours INTEGER` | Positive whole hours between due attempts; default **24**. | `agent-do security monitor init --config ~/team-security.json --repos-file ~/team-repos.txt --interval-hours 12` |
| `--max-bytes INTEGER` | Positive file bound, default **16777216**, for reading the repository list. | `agent-do security monitor init --config ~/team-security.json --repos-file ~/team-repos.txt --max-bytes 33554432` |
| `--json` | Structured creation result; no scan, scheduling or notification occurs. | `agent-do security monitor init --config ~/bff-security.json --path . --json` |

### monitor run

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--config PATH` | Required existing portfolio configuration. All target options are validated before scanning. | `agent-do security monitor run --config ~/team-security.json --json` |
| `--due` | Skip without scanning/notifying if the interval since the last committed attempt has not elapsed. Default: run immediately. Failed attempts also advance the due interval. | `agent-do security monitor run --config ~/team-security.json --due --json` |
| `--allow-builds` | Explicitly authorize trusted local Maven/Gradle execution configured in targets. Default off; without it build targets are incomplete and other targets continue. | `agent-do security monitor run --config ~/bff-security.json --allow-builds --json` |
| `--runtime-limit INTEGER` | Positive NVD record bound per imported runtime component; default **1000**. Source dependency scans unaffected. | `agent-do security monitor run --config ~/runtime-monitor.json --runtime-limit 2000 --json` |
| `--scanner EXECUTABLE` | Trusted OSV-Scanner v2 executable for source dependency targets; default osv-scanner. | `agent-do security monitor run --config ~/team-security.json --scanner /usr/local/bin/osv-scanner --json` |
| `--scan-timeout SECONDS` | Positive finite per scanner/GitHub/build subprocess timeout; default **300**. | `agent-do security monitor run --config ~/bff-security.json --allow-builds --scan-timeout 600 --json` |
| `--notify-recipient ALIAS` | Explicitly send filtered change counts/status/path through existing agent-do notify routing. Default: **no send**. Recipient and credentials must already be configured. Failure makes command incomplete without rolling back scan evidence. | `agent-do security monitor run --config ~/team-security.json --notify-recipient security-team --json` |
| `--notify-via LIST` | Provider order forwarded to notify, e.g. slack,email; requires notify-recipient. Default existing notify routing. | `agent-do security monitor run --config ~/team-security.json --notify-recipient security-team --notify-via slack --json` |

All [shared finding filters](#shared-finding-filters), `--json`, and HTTP/cache/KEV
options are also available on monitor run, with their existing values/defaults.
HTTP/cache controls affect KEV enrichment here, not the scanner/build's own
networking; timeout also bounds explicit notification delivery. Max-bytes bounds
the config and per scan input/stream, not total portfolio size. Filters affect
presentation/notification counts only, never persisted transitions or evidence.
Curated advisory `--target` and scan `--dependabot`/`--scanner-diagnostics` options
are not monitor-run options. Build executables/settings/profiles/properties go in
the per-target config `options`; monitor run does not accept direct --resolve.

```bash
agent-do security monitor run --config ~/team-security.json --cvss-min 7 --include-unscored --kev --json
```

Monitor run/report results include `assessment_summary`: unfiltered current
observations and prominently surfaced coverage issues, separate from lifecycle
counts. A zero-count timeout is incomplete; uncertain candidates are retained.
See [assessment diagnostics](PORTFOLIO_MONITORING.md#assessment-errors-and-zero-change-counts).

### monitor report

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--config PATH` | Required monitor identity; default reads this monitor's latest committed digest, including incomplete runs. Never selects another portfolio's latest result. | `agent-do security monitor report --config ~/team-security.json --json` |
| `--file PATH` | Specific historical digest from this monitor; rejects another monitor/schema. | `agent-do security monitor report --config ~/team-security.json --file /path/to/digest.json --json` |
| `--max-bytes INTEGER` | Positive config file bound, default **16777216**. | `agent-do security monitor report --config ~/team-security.json --max-bytes 33554432 --json` |

All shared finding filters and JSON/help are supported. This is read-only; it
neither scans nor refreshes KEV. Resolved/unverified issues use last-seen evidence.
Unknown saved exploitation status is rejected for a known-exploited filter.
Counts remain unfiltered; shown_counts reflects presentation filters.

```bash
agent-do security monitor report --config ~/team-security.json --severity critical,high --json
```

### monitor schedule

`--runtime-limit INTEGER` (positive, default **1000**) is exported into the cron
job so scheduled runtime assessment can use the same bound as manual runs:

```bash
agent-do security monitor schedule --config ~/runtime-monitor.json --runtime-limit 2000 --json
```

| Parameter | Values, default and restrictions | Example |
| --- | --- | --- |
| `--config PATH` | Required portfolio config on the scan host. Emits an hourly cron check with due gating; **does not install it**. | `agent-do security monitor schedule --config ~/team-security.json` |
| `--allow-builds` | Required if local build resolution is configured; includes that explicit authorization in the exported job. | `agent-do security monitor schedule --config ~/bff-security.json --allow-builds --json` |
| `--notify-recipient ALIAS` | Include explicit notification recipient in the exported command; sends nothing during export. | `agent-do security monitor schedule --config ~/team-security.json --notify-recipient security-team --json` |
| `--notify-via LIST` | Include provider order; requires notify-recipient. | `agent-do security monitor schedule --config ~/team-security.json --notify-recipient security-team --notify-via slack --json` |
| `--max-bytes INTEGER` | Config/scan bound forwarded to the job, default **16777216**. | `agent-do security monitor schedule --config ~/team-security.json --max-bytes 33554432 --json` |
| `--json` | Emit cron, interval, notes and installed=false as JSON. Text prints the reviewable line and notes. | `agent-do security monitor schedule --config ~/team-security.json --json` |

Review and install the exported line using crontab -e on macOS/Linux. It pins the
current Python/tool/config path, PATH and AGENT_DO_HOME, not credentials. Jobs run
when the host is awake and its cron service runs. Run schedule on the destination
host and regenerate after moving its checkout/Python environment. Other runtime
flags can be added explicitly to the reviewed monitor-run command if needed.

## Environment variables

| Variable | Purpose | Example |
| --- | --- | --- |
| `AGENT_DO_HOME` | Relocate private security cache/reports from `~/.agent-do/security` to `$AGENT_DO_HOME/security`. | `AGENT_DO_HOME=/path/to/team-agent-state agent-do security scan --path . --json` |
| `NVD_API_KEY` | Optional NVD key for higher published request allowance. | After configuring the key in your environment: `agent-do security find --target java --json` |
| `GH_TOKEN`, `GITHUB_TOKEN` | Optional GitHub advisory API authentication; GH_TOKEN takes precedence in this client. GitHub repository acquisition uses installed gh authentication and its normal configuration. | After configuring authentication: `agent-do security scan --repo my-team/backend --json` |

Use existing credential management or your shell's secure environment setup;
never put tokens in repository links or list files. No command starts interactive
GitHub login automatically.

## Interpret results and exit codes

| Exit | Meaning |
| --- | --- |
| `0` | Assessment completed within declared scope, **even if vulnerabilities were found**; or doctor passed its scanner check. |
| `1` | Incomplete: missing scanner, unsupported/unresolved input, inaccessible repo/ref, source failure, truncation or stale evidence. A batch failure does not stop other repos. |
| `2` | Invalid options, unreadable/invalid input file or unsupported saved report. |

Unscored CVSS values alone do **not** cause exit 1. They affect score filtering
and the unscored count. For an incomplete assessment, inspect `coverage` entries
whose status is not `ok` (such as scanner warnings or missing inventory), even
if dependency resolution succeeded and findings were returned.

The unknown upstream publication time field is informational and does not itself
cause exit 1. The scanner runs at `--verbosity=warn`, suppressing info logs through
OSV's native log-level filtering. The exact, verified `source` subcommand/file-name
collision notice is recorded as non-blocking; the internal staging directory was
also renamed to prevent it. Other stderr remains unclassified and keeps coverage
incomplete, including when mixed with the known notice. Warning coverage records
a reason, line count and hash. Use explicit `--scanner-diagnostics DIR` to capture
messages locally; reports record paths/hashes, not raw contents. Existing reports
retain their original assessments; rerun after updating so `--latest-complete`
can select new assessments whose inventory and source coverage completed.

A zero-findings result with incomplete coverage does not establish that a repo
is unaffected. Filtering findings does not change an incomplete status. Batch
counts represent advisory/package/version/repository targets, not globally
unique CVEs. Source scans do not inventory your machine's OS, installed runtimes,
AKS configuration, or deployed artifacts. There is no scheduler, automatic
remediation command, or vulnerability-threshold CI exit mode in this interface.

## Milestone 4 collector and Temurin parameters

`runtime` and `monitor init` accept `--image` (repeatable), `--rootfs`,
`--kube-context`, `--namespace`, `--selector`, `--syft`, `--trivy`, `--kubectl`,
`--collect-timeout` (300 seconds) and `--database-max-age` (86400 seconds).
`runtime --temurin-vdr FILE` selects a local Adoptium vendor document; otherwise
Temurin uses the digest-checked official public release. Monitor run/schedule
require `--allow-collectors` for configured collectors and local Python probes.
See [Python runtime coverage](PYTHON_RUNTIME.md) for interpreter versus dependency scope.
The [collector parameter table](RUNTIME_COLLECTION.md#collector-parameters) explains
**every flag with an example**, prerequisites, defaults and scope limitations.
Inventory-only skips advisory requests; explicitly selected image/cluster collectors
still contact registries/Kubernetes. Local/static/imported inventory-only remains offline.
