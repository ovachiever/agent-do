# Scan your team's repositories from a local file

See the [complete parameter reference](SECURITY_CLI_REFERENCE.md) for every
scan flag, filter, default and example command.

Keep a UTF-8 file anywhere on your machine, for example `~/team-repos.txt`:

```text
# One GitHub repository per line
https://github.com/my-team/backend
https://github.com/my-team/frontend.git
my-team/shared-library
```

Replace these examples with your team's repositories, then run:

```bash
agent-do security scan --repos-file ~/team-repos.txt --json
agent-do security scan --repos-file ~/team-repos.txt --cvss-min 7 --include-unscored --json
```

This scans all listed repositories sequentially in one invocation. The file is
the local store: edit it when your team's repositories change and reuse it on
every run. It is read without modification. No server or separate database is
needed for the list. Blank lines and whole-line `#` comments are supported;
inline comments, organization wildcards and non-GitHub hosts are not supported.
Keep credentials out of the list. Acquisition uses your existing `gh`
authentication, including access to private repositories.

Install OSV-Scanner v2 and `gh` first. Run `agent-do security doctor --json` to
check local prerequisites; doctor does not establish GitHub authorization.
The list is fully validated before any repository is fetched. An invalid or
empty list is a usage error (exit 2), and is never silently partially accepted.
`--max-bytes` bounds the list as well as individual manifests and subprocess
streams. There is no fixed repository count cap.

## Branches and commits

By default, each repository's default branch is resolved to a commit, and only
dependency files from that commit are downloaded. Use `--ref main` to request
the same branch/tag/commit for all entries. For different refs, use a JSON array:

```json
[
  "my-team/backend",
  {"repo": "https://github.com/my-team/frontend", "ref": "release/1.x"},
  {"repo": "my-team/shared-library", "ref": "main"}
]
```

```bash
agent-do security scan --repos-file ~/team-repos.json --json
```

Objects accept only `repo` and optional `ref`. Omitted refs inherit `--ref` if
provided; an explicit JSON `null` selects the repository default branch.
Equivalent URL/owner-repo entries are deduplicated case-insensitively by
repository plus requested ref. Distinct refs remain separate scan targets even
if they resolve to the same commit. The saved report records the list's path,
SHA-256, normalized entries, skipped-duplicate count, and acquired commits.

## Findings, failures and saved reports

The combined report contains per-repository summaries, commit identities and
coverage. Each normalized finding has a `repository_target` identifying its
repository, entry and commit. A vulnerability affecting the same package version
in three repositories appears under all three. Totals count affected
advisory/package/version/repository targets, not globally unique CVEs.

An inaccessible repository, invalid ref, scanner error or unresolved dependency
makes that target incomplete without stopping the other repositories. Any such
gap makes the overall run incomplete (exit 1). No findings with incomplete
coverage does not establish that a repository is unaffected. A completed scan
returns exit 0 even when vulnerabilities are found; exit codes describe coverage,
not a CI vulnerability threshold. Shared KEV enrichment, if requested, happens
once across the portfolio; an enrichment failure also makes each repository's
summary incomplete.

Detailed repository records expose `source_scan_status` for the file scan and
optional Dependabot acquisition. Presentation `repository_summaries.status`
also includes shared enrichment failures.

CVSS, publication-date, package, severity and other existing filters apply to
all repository findings. The saved report retains unfiltered normalized findings,
per-repository inventory/package evidence, raw scanner responses and scoped
coverage. Only one aggregate report is saved under
`$AGENT_DO_HOME/security/reports` (default `~/.agent-do/security/reports`).
Reapply filters without fetching or scanning again:

```bash
agent-do security report --latest --cvss-min 9 --include-unscored --json
agent-do security report --file /path/to/saved-report.json --ecosystem java --json
```

`--dependabot` optionally attaches separately scoped default-branch alerts for
each repository through the existing provider; it requires PR #51 or its
successor. Those alerts do not establish exposure at a requested nondefault ref.
GitHub list scans use file snapshots and never run repository build scripts.
`--resolve maven|gradle` remains available only with a trusted local `--path`;
remote projects requiring build resolution are reported with coverage gaps.
See [JVM dependency resolution](JVM_DEPENDENCY_RESOLUTION.md).

This is the repository-list and batch-scan portion of milestone 3. For saved
portfolios, recurring cron export, change digests and opt-in notifications, see
[portfolio monitoring](PORTFOLIO_MONITORING.md). Batch `scan` itself does not start
a schedule. Deployed artifacts, OS/runtime inventory and update PRs remain later work.

## Validation

```bash
python3 tests/test_security_repositories.py
```

Tests use fixture GitHub responses and a fake OSV executable. They cover all 15
repositories in one call, immutable acquisition, separate refs, inaccessible
repositories, deduplication, saved-report filtering, shared KEV failures and
input rejection. They do not establish live upstream connectivity or scanner
compatibility on your machine.
