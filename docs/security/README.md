# Security plugin

`agent-do security` finds published advisories, scans dependency inventories and
saves attributable evidence. Use the [CLI reference](SECURITY_CLI_REFERENCE.md)
for every parameter, default and example. Related workflows:

- [Advisory source selection](CVENOW_DISCOVERY.md): cve.now-first discovery with NVD/GitHub fallback, no repository uploads.
- [JVM resolution](JVM_DEPENDENCY_RESOLUTION.md): effective Maven/Gradle versions.
- [Repository lists](REPOSITORY_LIST_SCANNING.md) and [monitoring](PORTFOLIO_MONITORING.md): team portfolios and recurring scans.
- [Python interpreter assessment](PYTHON_RUNTIME.md): explicit CPython probing and recurring host checks.
- [Runtime evidence](RUNTIME_ASSESSMENT.md) and [collectors](RUNTIME_COLLECTION.md): installed/deployed versions.
- [Planned upgrades](PLANNED_UPGRADES.md): future remediation; not implemented.

## Setup

Install [OSV-Scanner v2](https://google.github.io/osv-scanner/installation/)
separately; it is required for source scans. On macOS:

```bash
brew install osv-scanner
agent-do security doctor --json
```

GitHub acquisition requires authenticated `gh` access. `NVD_API_KEY` and
`GH_TOKEN`/`GITHUB_TOKEN` are optional for public advisory reads; GitHub API limits
can still block unauthenticated requests. Doctor checks local prerequisites and
credential presence without testing network access or authorization.

Optional vector scoring uses the maintained CVSS library:

```bash
python3 -m pip install -r tools/agent-security/requirements.txt
```

Without it, numeric scores still work and uncomputed vectors remain unscored.
Score filters exclude unscored findings unless `--include-unscored` is supplied.

## Find published advisories

```bash
agent-do security find --vendor oracle --product jdk --cvss-gt 7 --json
agent-do security find --ecosystem pypi --package litellm --json
agent-do security find --target java --target springboot --target angular \
  --target node --target aks --published-after 2026-10-15 --json
agent-do security find --cve CVE-2021-44228 --json
```

NVD is the default for vendor/product/keyword queries; GitHub is the default for
ecosystem/package queries. Package searches require an ecosystem. `pypi`/`python`
normalize to `pip`, and `php`/`packagist` to `composer`. Interpreter/runtime products
are separate from packages: searching Python CVEs does not establish exposure to
LiteLLM or a repository. Keywords and [curated targets](MULTI_TARGET_DISCOVERY.md)
identify advisory relevance, not confirmed application impact.

Discovery omits rejected NVD and withdrawn GitHub records. It is limited to the
selected source and criteria. `--limit` defaults to 100 source records examined
before presentation filters; multi-target limits apply per component query.
Truncation remains incomplete. NVD filtered date windows are at most 120 days;
see the [date examples and rules](SECURITY_CLI_REFERENCE.md#search-a-seven-day-or-thirty-day-publication-window).

## Scan source dependencies

```bash
agent-do security scan --path . --json
agent-do security scan --path ~/workspace/my-service --resolve maven --json
agent-do security scan --repo owner/repo --ref main --json
agent-do security scan --repos-file ~/team-repos.txt --cvss-min 7 --include-unscored --json
```

File scans copy recognized manifests/lockfiles into an isolated temporary
snapshot. They do not execute target scripts or install dependencies. Local
snapshots include uncommitted files; GitHub refs resolve to immutable commits.
Reports record inventory fingerprints and available Git evidence. Symlinks,
nonregular files and truncated remote trees are rejected or reported as gaps.

Supported file families include JavaScript, Composer, Python, Maven/Gradle, Cargo,
Go, Ruby, NuGet, Dart and Elixir. Actual extraction depends on OSV-Scanner.
Unpinned requirements, manifests without resolved inventories, POM-only transitive
versions and files the scanner did not assess remain unresolved. Nested projects
are included except dependency/build/cache directories listed in the report.

OSV runs with an empty config and all-package inventory, so repository config
cannot hide findings. Reports retain scanner version, package inventory, raw JSON
evidence and normalized findings; the temporary snapshot is removed.
`--resolve maven|gradle` separately authorizes trusted local build execution and
build/cache writes. Use the [resolution guide](JVM_DEPENDENCY_RESOLUTION.md) for
profiles, settings, configurations and dependency paths. Remote scans do not
execute Maven/Gradle; clone and select a trusted local checkout first.

Source findings do not establish installed PHP/Java/Node versions, exploitability,
or deployment state. Use the runtime workflows for explicit runtime evidence.

### Dependabot provider integration

```bash
agent-do security scan --repo owner/repo --dependabot --json
```

This optional adapter uses the `gh alerts` provider from
[PR #51](https://github.com/ovachiever/agent-do/pull/51). If unavailable, coverage
says so. Alerts stay separately scoped to the default branch; they are not merged
into commit-specific findings. Access errors and disabled alerts are not zero findings.

## Filters and saved reports

```bash
agent-do security report --list --json
agent-do security report --file /path/to/report.json --severity critical,high
agent-do security report --latest-complete --cvss-min 7 --include-unscored --json
agent-do security scan --path . --kev --json
```

Filters change the displayed view, not saved findings. Reports include total,
shown, excluded and unscored counts. Scores use the maximum available base score,
preserving rating sources/vectors; aliases merge transitively while distinct
installed versions retain their evidence. There is no default severity threshold.

`--fix-available` keeps findings **with** explicitly published fixes. If all 17
findings have fixes, all 17 remain. A published fix is not a tested upgrade plan;
NVD range boundaries are not inferred fixed versions.

`--kev` enriches using CISA's known-exploited catalog; `--known-exploited` also
filters. A fetch failure leaves exploitation unknown and coverage incomplete.
Saved reports need prior enrichment to support that filter.

Unfiltered JSON is saved under `$AGENT_DO_HOME/security/reports/`, defaulting to
`~/.agent-do/security/reports/`. Unique filenames preserve earlier assessments.
`report` reads without network access or changing the evidence:

- `--file PATH`: select a specific assessment.
- `--list`: list timestamps, targets, status, counts, gaps and paths.
- `--latest`: newest assessment, including explicitly flagged failures.
- `--latest-complete`: newest complete assessment across **all projects and commands**,
  possibly older or inventory-only. Check target, scope and timestamp.

| Exit | Meaning |
| --- | --- |
| 0 | Requested assessment completed, possibly with vulnerabilities. |
| 1 | Incomplete: unresolved inventory, truncation, stale data or source/scanner failure. |
| 2 | Invalid input/state or unreadable/unsupported saved report. |

Unscored CVSS alone does not cause exit 1. Inspect non-`ok` coverage entries;
`--include-unscored` changes filtering, not completeness. Zero findings means no
known matches in the successfully assessed scope, not a general security guarantee.

## Scanner diagnostics

OSV informational logs are suppressed with `--verbosity=warn`. The full verified
`source` subcommand/file-name notice is non-blocking; other remaining diagnostics
stay unclassified and make coverage incomplete. Unknown upstream database
publication time alone does not trigger a warning. Existing reports keep their
original status; a new scan creates new evidence.

Capture actual scanner stderr only when troubleshooting:

```bash
agent-do security scan --path ~/workspace/my-service --resolve maven \
  --scanner-diagnostics ~/private-security-diagnostics --json
```

Capture files are uniquely named, mode 0600, in a newly created mode-0700 directory.
Their path appears in the report; raw text is never embedded. This captures scanner
invocations, including failures, not version probes or build logs. Review/redact
locally before sharing: paths, URLs or credentials may appear. Capture does not
change coverage classification.

## Network, cache, and data disclosure

Advisory services receive search criteria; OSV receives package identities and
versions and may contact ecosystem metadata services. `gh` reads the selected
repository. Explicit build resolution contacts configured repositories and may
write project files/caches. Private reports contain repository/package identities.

HTTP responses cache privately for one hour by default, partitioned by credential
hash without saving credentials. `--refresh` bypasses fresh entries. Stale fallback
requires `--allow-stale`, is marked and remains incomplete. Receipts record source
URL/fetch time, not inferred database publication or deployment observation time.
Timeouts, retries and byte/record limits are operator-controlled; oversized data
fails explicitly. Advisory API redirects are refused to protect credentials;
Temurin's narrowly scoped public asset download is described in the collector guide.

## Validation

Run these checks from the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_security*.py'
./agent-do harness contracts validate
./agent-do harness contracts drift --tool security
./agent-do harness bounds drift --tool security
bin/gen-tools-doc --check
```

The suite uses offline fixtures and executable doubles; real upstream/tool
compatibility is a separate host check. Full repository validation is `./test.sh`.
