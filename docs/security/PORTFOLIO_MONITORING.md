# Portfolio monitoring

`agent-do security monitor` assesses saved local/GitHub/runtime targets and tracks
**new**, **ongoing**, **resolved**, and **unverified** issues. It exports recurring
jobs but installs no scheduler. Notifications are opt-in. See the
[CLI reference](SECURITY_CLI_REFERENCE.md#monitor-portfolio-configuration-runs-and-digests)
for parameters and examples.

## Start with your repository list

```bash
agent-do security monitor init --config ~/team-security.json \
  --repos-file ~/team-repos.txt --interval-hours 24 --json
agent-do security monitor run --config ~/team-security.json --json
agent-do security monitor report --config ~/team-security.json --json
```

Init copies entries from the [text/JSON repo list](REPOSITORY_LIST_SCANNING.md)
into a private config without scanning. It refuses overwrite. Later changes to
the original list are not imported automatically; edit the config's `targets`.

## Monitor your local Spring Boot project

```bash
agent-do security monitor init --config ~/bff-security.json \
  --path ~/workspace/my-service --resolve maven
agent-do security monitor run --config ~/bff-security.json \
  --allow-builds --cvss-min 7 --include-unscored --json
```

Configured resolution requires `--allow-builds` on each run and schedule export.
Without it, no build runs, that target is incomplete and earlier issues remain
unverified; other targets continue. Trusted wrappers/extensions can execute code,
contact repositories and write caches/files. GitHub targets use file snapshots,
not remote Maven/Gradle execution. See [setup](README.md) and
[JVM resolution](JVM_DEPENDENCY_RESOLUTION.md) for prerequisites.

## Create a mixed portfolio from the CLI

```bash
agent-do security monitor init --config ~/mixed-security.json \
  --path ~/workspace/my-service --resolve maven \
  --runtime-inventory ~/runtime-inventory.json --json
agent-do security monitor run --config ~/mixed-security.json --allow-builds --json
```

Imported runtime and collector selections can accompany a local path or repo list.
`--path` and `--repos-file` are mutually exclusive. Init accepts one local source
path; add further heterogeneous targets to the generated config.

## Monitor the Python running agent-do

Add `--local-python` during init, optionally alongside `--path`. The selected
interpreter is probed afresh each run; init saves its executable selection without
executing it. Both run and schedule require `--allow-collectors`. See the
[Python guide](PYTHON_RUNTIME.md#monitor-agent-do-every-four-hours) for the four-hour
workflow, build provenance and deployment limits.

## Configuration and scope

Preserve generated `schema_version: 1` and the 32-character `monitor_id`; that ID
owns history and locking. Initialize a new config for independent history.
`interval_hours` is a positive integer, default 24. Relative target/settings paths
resolve beside the config. Example `targets` entries:

```json
[
  {"repo": "my-team/backend", "ref": "main"},
  {
    "path": "/path/to/my-service",
    "resolve": "maven",
    "options": {
      "maven_settings": "/path/to/settings.xml",
      "maven_profile": ["prod"],
      "build_property": ["example=production"]
    }
  },
  {"runtime_inventory": "/path/to/runtime-inventory.json"}
]
```

Source entries select exactly one `repo` or `path`; GitHub ref defaults to the
default branch. Local build `options` accept `maven`, `gradle`, `maven_settings`
strings and `maven_profile`, `gradle_configuration`, `build_property` string arrays.
Runtime entries select `runtime_inventory` or a generated `runtime_collect` target;
see [runtime evidence](RUNTIME_ASSESSMENT.md) and [collectors](RUNTIME_COLLECTION.md).
Use `--runtime-limit N` for the per-component NVD bound, default 1000.

Unknown fields, incompatible options and duplicate identities are rejected.
Credentials belong in normal build/gh mechanisms, not URLs/properties. Property
values and settings contents are fingerprinted for comparison, not copied into
state/digests. Keep the build environment consistent: implicit profiles and ambient
credential/environment changes are not independently enumerated.

Scanner/build/matcher versions, build options, settings contents and effective
branch changes create separate baselines. Runtime membership/product/deployment
changes can also change scope. Earlier active issues in other scopes or removed
targets stay unverified. A vulnerable dependency version change alone stays ongoing
when the advisory/package identity still matches.

## Assessment errors and zero change counts

Read `assessment_summary` before lifecycle counts. It contains current unfiltered
`findings_observed`, runtime inventory-match/candidate counts, target completeness
and `coverage_issues` with source/target/status/message. Text prints source errors
before change counts. A first failed lookup can have zero lifecycle counts and a
complete comparison because no history exists, while the assessment is incomplete.

Candidates detected during incomplete scans are retained as new/ongoing; a later
timeout keeps them unverified. A cached candidate list and a failed fresh request
are different outcomes. Historical digests missing observation counts show unknown,
not an inferred zero; their source report retains original observations.

## What the changes mean

| Category | Meaning |
| --- | --- |
| `new` | First detected in this scope or reopened after resolution; not newly announced. |
| `ongoing` | Previously active and detected again in the same scope. |
| `resolved` | Absent from a complete compatible assessment; not proof of deployment remediation. |
| `unverified` | Earlier evidence retained because assessment failed, scope changed or target was not scanned. |

Aliases match transitively. Versions/occurrences of one advisory/package within a
target form one issue; different packages/targets remain separate. IDs and first
observed timestamps persist. Advisory publication dates remain distinct.

`status` reports current assessment/delivery completeness: exit 0 can include
vulnerabilities, 1 is incomplete, 2 is invalid input/state. `comparison_status`
is partial when older issues remain unverified. A current assessment can complete
without a complete historical comparison; inspect both.

## Evidence, filtering and failure recovery

Runs save unfiltered reports under `$AGENT_DO_HOME/security/reports` and digests
under `security/monitors/<monitor_id>/digests`; default home is `~/.agent-do`.
State/latest digest commit atomically under a nonblocking POSIX lock. Concurrent
runs are rejected; malformed state is not reset. Failed state writes do not advance
the baseline. If a historical digest-file write is interrupted, the latest digest
is recoverable from committed state.

```bash
agent-do security monitor report --config ~/team-security.json --cvss-min 9 --json
agent-do security monitor report --config ~/team-security.json \
  --file /path/to/older-digest.json --severity critical,high --json
```

Filters affect display and `shown_counts`, not saved evidence or `counts`.
Resolved/unverified filters use last-seen evidence. `--known-exploited` requires
KEV enrichment already collected with `--kev`. `--target` selects curated discovery,
not monitor targets. Use `monitor report --config` for this portfolio's digest;
`security report --latest` selects globally across projects/commands.

## Recurring execution on your machine

```bash
agent-do security monitor schedule --config ~/team-security.json --json
agent-do security monitor schedule --config ~/bff-security.json --allow-builds --json
```

Review the emitted cron line and install with `crontab -e` on the scan host. The
plugin installs nothing. Hourly invocations use `--due`; scans run only after the
configured interval since the last committed attempt, including failed attempts.
Run without `--due` to retry immediately.

Export pins this host's Python/tool/config paths, PATH and AGENT_DO_HOME, without
tokens. Provide the scheduler account's normal credentials/network setup. Regenerate
after moving checkout/Python or changing hosts; a laptop PATH is not portable CI
configuration. The machine must be awake with working cron and POSIX locking;
this is not a hosted scheduler or missed-job catch-up queue.

## Optional notifications

Use an existing configured notify recipient/provider explicitly:

```bash
agent-do security monitor run --config ~/team-security.json \
  --notify-recipient security-team --notify-via slack --cvss-min 7 --include-unscored
```

Messages contain filtered counts, statuses and the local digest path, not raw
findings/build logs. Delivery is best-effort, not exactly-once. Failure makes the
command incomplete without undoing committed evidence; no automatic retry occurs,
and due skips do not notify. Schedule export includes requested notification
arguments but sends nothing. Normal provider credentials/approval rules apply.

## Explicit runtime collectors

```bash
agent-do security monitor init --config ~/team-images.json \
  --path ~/workspace/my-service --resolve maven --image eclipse-temurin:21-jre --json
agent-do security monitor run --config ~/team-images.json \
  --allow-builds --allow-collectors --json
```

Init stores selections without executing collectors. Runs/schedule exports require
`--allow-collectors` separately from build authorization. Missing authorization is
an incomplete assessment, not a resolved issue. See [collector setup and limits](RUNTIME_COLLECTION.md).

## Validation and remaining scope

See [runtime validation status](RUNTIME_COLLECTION.md#validation-status) for tested
and deferred collector paths. Monitoring never automatically updates or deploys
repositories. Remediation is [planned separately](PLANNED_UPGRADES.md).
