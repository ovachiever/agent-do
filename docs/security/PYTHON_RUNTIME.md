# Python interpreter coverage

agent-do uses Python. Its Python package dependencies and the interpreter itself
are separate inventories: source scans check supported dependency files through
OSV-Scanner, while `runtime --local-python` observes a selected interpreter and
checks NVD's CPython interpreter/standard-library advisories.

```bash
# Observe without contacting an advisory service.
agent-do security runtime --local-python --inventory-only --json

# Assess the Python executing agent-do (default), or explicitly select another.
agent-do security runtime --local-python --json
agent-do security runtime --local-python --python /path/to/venv/bin/python --json

# Only after verifying the build follows upstream CPython release patch status:
agent-do security runtime --local-python --python-upstream --json

# Check one CVE or refilter by severity/date with the shared finding options.
agent-do security runtime --local-python --cve CVE-2024-7592 --json
```

The subprocess runs a fixed probe with `-I -S`: no checkout modules, user site,
`PYTHONPATH`, `.pth`, `sitecustomize` or `usercustomize` startup code is loaded.
It reports implementation, exact release tuple, prerelease stage, executable and
platform. `--probe-timeout` defaults to 15 seconds; output uses `--max-bytes`.
Selecting a trusted executable authorizes its execution, not arbitrary repo code.

Final CPython releases map to `python:cpython`. NVD's historical `python:python`
identity is treated as the same reference implementation; one bounded vendor
namespace query covers both. Normal configuration predicates/version ranges are
evaluated locally. Other products/vendors are excluded independently; unsupported
bounds, prerequisites or missing configurations remain uncertain. PyPy and
alpha/beta/RC interpreters stay unmapped rather than being rounded to final CPython.
Matcher revision 4 separates comparison baselines from older matching rules.

## Interpret the result

By default, **vendor backport status is unknown**. Upstream version matches are
candidates and coverage is limited, even when no CVEs match. A Linux distribution,
Homebrew, Conda or custom build may have patches that its upstream version number
does not describe. Use vendor OS/image assessment where available. Set
`--python-upstream` only after verifying the selected build follows upstream CPython
release patch status; this is caller-supplied verification, not automatic proof.
Only supported, satisfied NVD predicates can then establish an inventory match.

This does not audit PyPI packages, bundled OpenSSL/libexpat, interpreter build
options, EOL/support status, application exploitability, remote processes or every
Python on the machine. NVD can lag disclosures; service failures/truncation remain
incomplete. Scan dependencies separately and keep the interpreter's distribution
updated. A complete assessment is not a guarantee of protection.

## Monitor agent-do every four hours

Run this on the machine that actually executes agent-do. Choose the real checkout
and interpreter; the cloud workspace's Python is not evidence about your laptop
or production host.

```bash
agent-do security monitor init --config ~/agent-do-security.json \
  --path /path/to/agent-do --local-python --python /path/to/python3 \
  --interval-hours 4 --json
agent-do security monitor run --config ~/agent-do-security.json \
  --allow-collectors --include-unscored --json
agent-do security monitor schedule --config ~/agent-do-security.json \
  --allow-collectors --json
```

Install OSV-Scanner v2 for the source target. Init stores a `runtime_probe` target
without executing it; each authorized run re-observes the executable's current
version. `--python-upstream`, if verified, can be stored at init; otherwise
uncertainty remains visible. Execution requires `--allow-collectors` independently
of any `--allow-builds` required by source build resolution. The schedule command
prints a reviewable hourly cron entry using `--due` to enforce the four-hour
interval; it installs nothing. Install the entry on an always-available scan host.

Source and interpreter targets keep separate statuses and lifecycle evidence.
A complete compatible assessment may resolve earlier evidence after a patch;
failed/missing probes, advisory timeouts, unknown patch status and changed scopes
retain it as unverified. Version constraints such as `pyyaml>=6.0` are not an exact
resolved Python dependency inventory: the source scan reports that coverage gap
rather than claiming it assessed the versions deployed with agent-do.
