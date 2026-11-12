# Search several languages and platforms together

See the [complete parameter reference](SECURITY_CLI_REFERENCE.md) for every
discovery and filtering option, its defaults and example commands.

Repeat `--target` on `security find` to combine curated advisory searches:

```bash
agent-do security find \
  --target java --target spring-boot --target angular \
  --target nodejs --target aks \
  --published-after 2026-10-15 --published-before 2026-10-22 \
  --cvss-min 7 --include-unscored --json
```

This is an addition to advisory discovery before the daily-monitoring milestone.
It does not scan repositories, inspect clusters, or start a recurring schedule.
OSV-Scanner and Maven/Gradle are not required for `find`.

Target names are case-insensitive. `springboot` aliases `spring-boot`, and `node`
aliases `nodejs`. Repeating an alias or target does not repeat its queries.
Targets combine with OR; score, severity, date, CVE, fix, and exploitation filters
apply to the combined findings. A fixed publication upper boundary is exclusive;
the lower boundary is inclusive. Dates are database publication dates, which may
lag vendor announcements. There is no relative `--since 7d` shorthand yet.

## What each target covers

The report records profile version 1 and every query under `searches`. These are
curated profiles, not a promise of exhaustive ecosystem coverage:

| Target | Queries | Declared scope |
| --- | ---: | --- |
| `java` | 6 | NVD Oracle Java SE, JDK, JRE, and OpenJDK CPE identities plus Java SE/OpenJDK keyword candidates |
| `spring-boot` | 20 | GitHub advisories for selected Spring Boot, Spring Framework, and Spring Security Maven packages |
| `angular` | 12 | GitHub advisories for selected modern Angular runtime, SSR, compiler, and CLI/build npm packages |
| `nodejs` | 2 | NVD Node.js CPE identity and Node.js keyword candidates |
| `aks` | 3 | NVD-indexed AKS service CPE/keyword records and upstream Kubernetes CPE candidates |

The exact list lives in `tools/agent-security/security/targets.py` and is copied
into each report's search criteria. Spring Boot does not mean every starter,
Spring Cloud component, plugin, or transitive application dependency. Angular
excludes AngularJS and third-party npm components. Java does not cover every
JDK distribution, and Node.js does not mean every npm dependency.

The AKS target searches NVD records for Microsoft's `azure_kubernetes_service`
product, the keywords `Azure Kubernetes Service`, and the upstream Kubernetes
product. It does not query a direct MSRC bulletin feed. Findings have explicit
relations:

- `product_advisory`: a product-identity query returned the advisory.
- `package_advisory`: a named package query returned the advisory.
- `keyword_candidate`: text search returned a potentially relevant advisory.
- `upstream_dependency_candidate`: an upstream Kubernetes record may be relevant
  to an AKS environment; applicability is not established.

NVD keyword searches may return advisories about tools that merely mention the
target. Newly announced advisories may also lack CPE enrichment. Each query's
basis is retained so these cases can be assessed, not silently treated as
confirmed exposure. None of these relations establishes that your repository,
Node runtime, or AKS cluster contains a vulnerable version. Cluster version,
node-image, add-on, and workload verification remains deployment-awareness work.

## Coverage, limits, and saved evidence

`--limit` defaults to 100 source records **per component query**, before local
presentation filters. The five profiles above make 43 queries, each with its own
pagination and limit. Increase the limit if appropriate and inspect truncation;
the limit is not a global combined-result cap. GitHub-reviewed package advisories
can include records without CVE identifiers. NVD rejected records and withdrawn
GitHub advisories are omitted by the existing source adapters.

Reports include:

- `searches`: each query ID, target, source, criteria, match basis, and relation.
- `coverage`: independent result status, source counts, limit, truncation, and
  request receipts for every query.
- `matched_targets` and `target_matches`: why each advisory appeared, including
  source-specific publication and revision dates.
- `target_summaries`: query statuses and finding counts per target, alongside the
  global deduplicated total/shown/excluded/unscored counts.

One failed query does not stop the others. Findings from earlier successful
pages survive a later error. Failures, truncation, and explicitly allowed stale
cache data make the assessment incomplete (exit 1). A successful zero-result
query remains distinguishable from an unavailable source. Receipts for one
query never contain another query's requests.

Aliases are deduplicated across sources/targets while preserving every match
reason. A CVE matching Java and Angular appears once with both target labels.
The aggregate publication field shows the earliest captured source date, and
the modification field shows the latest. Date filtering uses an individual
source event, so a recent GitHub publication is not discarded simply because
the same CVE was published earlier in NVD. Combined date constraints must match
one event. A saved `--target` filter uses that target's own match dates.

Filters never delete saved findings. Refilter a saved combined report without
making another network request:

```bash
agent-do security report --latest --target java --target springboot --json
agent-do security report --latest --target aks --known-exploited --json
```

The exploitation filter requires a report originally enriched with `--kev` or
`--known-exploited`. KEV enrichment runs once after all target results are merged.
Requesting a target absent from a saved report is an error, rather than an empty
result for an unassessed target. Older single-query reports have no target
provenance and cannot be filtered this way.

Named targets select their own sources and criteria. They cannot be combined
with `--source nvd|github`, `--vendor`, `--product`, `--query`, `--ecosystem`, or
`--package`; use a separate manual query for custom criteria. Shared publication,
revision, CVSS, severity, CVE, fix-availability, and exploitation filters work
normally. Scoring continues to use the maximum known base score across captured
sources, with the original scoring evidence retained.

## Network and verification

The existing HTTP cache, retries, response-byte bounds, and timeout controls
apply. NVD requests share pacing across all queries in the invocation: six
seconds without `NVD_API_KEY`, or 0.6 seconds with one, corresponding to NVD's
published 5/50 requests per 30-second quotas. Successful cache hits do not incur
request pacing. Other processes sharing the same egress address may still cause
rate limits, which remain visible as source failures. NVD API keys are optional;
GitHub public advisory reads can use `GH_TOKEN`/`GITHUB_TOKEN` for higher allowance.

```bash
python3 tests/test_security_targets.py
python3 tests/test_security.py
python3 tests/test_security_resolution.py
./agent-do harness contracts validate
./agent-do harness contracts drift --tool security
./agent-do harness bounds drift --tool security
bin/gen-tools-doc --check
```

The multi-target tests exercise the real orchestration/source adapters with
offline HTTP response doubles. They do not establish live API compatibility.
This environment still lacks usable shell network access; live verification
remains necessary before operational use.

References: [NVD API](https://nvd.nist.gov/developers/vulnerabilities),
[NVD rate limits](https://nvd.nist.gov/developers/start-here),
[GitHub global advisory API](https://docs.github.com/en/rest/security-advisories/global-advisories),
[NVD AKS product](https://nvd.nist.gov/vuln/search?cpeFilterMode=cpe&cpeName=cpe%3A2.3%3Aa%3Amicrosoft%3Aazure_kubernetes_service%3A-%3A%2A%3A%2A%3A%2A%3A%2A%3A%2A%3A%2A%3A%2A&resultType=records),
and [Node.js CPE](https://nvd.nist.gov/products/cpe/detail/1603649).
