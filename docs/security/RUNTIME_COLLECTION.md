# Runtime collection and Temurin advisories

## What Temurin coverage means

Temurin contains OpenJDK and shares many OpenJDK CVEs with other distributions.
It does not need its own separate CVE numbering system. The plugin uses
[Adoptium's official VDR](https://github.com/adoptium/temurin-vdr-generator),
published as a CycloneDX vulnerability disclosure report. It does not substitute
Oracle's identity for Temurin. The upstream generator derives per-major patch
listings from OpenJDK Vulnerability Group tables and enriches advisory details.
These listings are not proof of exploitability for every build or operating system.

```bash
agent-do security runtime --local-java --inventory-only --json
agent-do security runtime --local-java --cvss-min 7 --include-unscored --json
```

An observed `java.vendor=Eclipse Adoptium` maps to Temurin. Exact security-patch
listings become inventory matches. Earlier unlisted or unsupported version forms
remain candidates; the plugin does not invent vulnerability introduction dates
or patched releases. Build numbers and LTS designations remain evidence. A newer
patch absent from those listings is not a general security guarantee.

The default source is the latest public release of
`adoptium/temurin-vdr-generator`. Its asset SHA-256 must match GitHub release
metadata. Only that repository's JSON release assets and the GitHub release asset
host are allowed for downloads. API credentials are never sent to asset redirects.
Reports retain the release tag, canonical source, digest and HTTP receipts;
signed redirect URLs are not stored. Fetch failures remain incomplete.
The normal timeout/cache/stale controls apply. A locally obtained VDR can be read
with `--temurin-vdr PATH`; it is labeled user-supplied, not independently verified.

```bash
agent-do security runtime --local-java --temurin-vdr ~/temurin-vdr.json --json
```

Imported Temurin evidence uses this alternative to a CPE:

```json
{
  "schema_version": 1,
  "components": [{
    "id": "bff-temurin",
    "java": {
      "vendor": "eclipse_adoptium",
      "product": "temurin",
      "version": "21.0.8",
      "runtime_version": "21.0.8+9-LTS"
    },
    "evidence": {
      "kind": "deployment_inventory",
      "source": "approved production inventory",
      "observed_at": "2026-10-22T09:00:00Z"
    },
    "deployment": {"environment": "production", "workload": "bff"}
  }]
}
```

Use exactly one `java` or `cpe` identity per component. Imported observations retain
their original timestamps and are not refreshed by scanning. Schedule imported
Temurin evidence with the existing `monitor init --runtime-inventory FILE` path.

## Install helpers explicitly

`security doctor --json` reports helper presence; it does not test registry access,
RBAC, advisory freshness or helper compatibility. Install maintained current
releases separately. On macOS:

```bash
brew install syft trivy kubectl
agent-do security doctor --json
```

Syft must support `scan --output syft-json` and the `java-jvm-cataloger` release-file
metadata. Trivy must support JSON schema 2, `image`, `rootfs`, `--list-all-pkgs`,
`--image-src remote` and `version --format json` with `VulnerabilityDB.UpdatedAt`.
Missing or unsupported output fails visibly. Helpers use the invoking user's
normal registry/Kubernetes credentials; the plugin does not save those credentials.
Checkout/user helper config files and ambient Syft/Trivy filter/output settings are
suppressed so they cannot silently hide findings or redirect output. Registry auth
variables and Trivy cache selection are retained.
Syft and Trivy receive a private temporary `empty.yaml` containing `{}`. Its YAML
extension supports Syft 1.55.0/Viper format detection; `/dev/null` is not used as
a configuration file. The file is removed after success, failure or timeout. No
wrapper script is required. Trivy's empty ignore file remains separate.
No Docker daemon or execution of image binaries is used.

Relative helper paths (for example `--syft ./bin/syft`) and relative PATH entries
are resolved from the invoking directory before collection switches to its private
working directory. Output is bounded per stdout/stderr stream while reading;
overflow or timeout terminates the command process group and leaves coverage incomplete.

## Image and mounted filesystem assessment

```bash
agent-do security runtime --image eclipse-temurin:21-jre --inventory-only --json
agent-do security runtime --image eclipse-temurin:21-jre --json
agent-do security runtime --image registry.example/team/bff@sha256:REPLACE_WITH_64_HEX_DIGEST --json
agent-do security runtime --rootfs /mnt/approved-host-root --json
```

Replace the digest placeholder before running. Repeat `--image` for multiple
images. A mutable tag must resolve to one immutable repository digest. Syft and
Trivy must both confirm the pinned digest; a changed/missing digest is an error.
For multi-platform images, ambiguous identities remain incomplete; use a verified
platform-specific immutable reference when necessary.

Syft reads installed JVM `release` metadata without starting Java. Its automatically
generated generic Oracle CPEs are ignored. Verified Oracle release metadata uses
the Oracle adapter; Eclipse Adoptium uses the Temurin adapter. Other vendors stay
unmapped. Trivy assesses OS/library packages through its maintained vendor sources,
including vendor backport versions; this plugin does not order Linux revisions.

`--rootfs` inspects only the explicitly selected directory; it does not discover
remote hosts. A live mutable filesystem can change during scanning; prefer an
approved consistent snapshot. Image scans do not inspect writable running-container
layers, attached volumes, running processes or cluster node filesystems.

The report keeps package/advisory evidence, helper versions, database timestamps,
OS support state and immutable image identity. Raw image configuration/environment,
Syft metadata and helper diagnostics are not persisted. Unknown/stale DB metadata,
end-of-life OS, missing package inventory and helper diagnostics prevent complete
coverage. A zero-finding complete result is scoped to supported observed packages.

`--inventory-only` skips advisory calls and Trivy. Explicit image/Kubernetes
collection still contacts registries/APIs. Local Java/static/imported inventory-only
remains offline.

## Kubernetes and AKS pod images

```bash
agent-do security runtime --kube-context team-aks --namespace services \
  --selector app=bff --inventory-only --json
agent-do security runtime --kube-context team-aks --namespace services \
  --selector app=bff --json
```

Context and namespace are mandatory together; the plugin never chooses the ambient
context. Read-only `kubectl get pods` emits only pod/container/image metadata, not
pod environment or arbitrary annotations. Normal, init and ephemeral container
statuses are checked. Pending/missing statuses, empty discovery, non-pullable image
IDs, RBAC failures and registry failures remain incomplete. A local config-image
digest or mutable tag is not silently treated as a deployed manifest digest.

Each observed image is inspected without `kubectl exec`, changing a workload or
installing anything. Deployment context/namespace/pod/container evidence stays
attached. This assesses pod image artifacts; it does not audit Azure/AKS control
planes, host nodes, network reachability or runtime exploitability.

## Monitor collected artifacts

```bash
agent-do security monitor init --config ~/image-security.json \
  --image eclipse-temurin:21-jre --interval-hours 24 --json
agent-do security monitor run --config ~/image-security.json --allow-collectors --json
agent-do security monitor schedule --config ~/image-security.json --allow-collectors --json

agent-do security monitor init --config ~/mixed-security.json \
  --path ~/workspace/bff --resolve maven \
  --kube-context team-aks --namespace services --selector app=bff --json
agent-do security monitor run --config ~/mixed-security.json \
  --allow-builds --allow-collectors --json
```

Init stores selections but executes no collectors. Each run needs explicit
`--allow-collectors`; schedule export requires it too and still installs nothing.
Collector targets may accompany source and imported-runtime targets. The generated
cron entry is specific to that host's PATH, Python, tools and credentials; review
and regenerate it on a different host or CI runner.

Lifecycle history retains earlier evidence as unverified on collection/registry/
advisory failure. Changed product/deployment/membership/helper matching scopes may
create separate baselines; no absence in an incomplete scan resolves an issue.
Matcher revision 4 additionally unifies historical/current CPython identities; revision 3 corrected unrelated complex-CPE contamination. Earlier matcher
baselines remain unverified rather than being described as patched deployments.

## Collector parameters

These flags apply to `runtime` and `monitor init`. Monitor init saves their values.
Use `--allow-collectors` on monitor run/schedule rather than repeating selections.

| Parameter | Meaning/default | Example |
| --- | --- | --- |
| `--image REF` | Explicit registry image; repeatable | `runtime --image eclipse-temurin:21-jre --json` |
| `--rootfs DIR` | Explicit mounted/unpacked filesystem | `runtime --rootfs /mnt/snapshot --json` |
| `--kube-context NAME` | Explicit Kubernetes context | `runtime --kube-context team-aks --namespace services --json` |
| `--namespace NAME` | Required with context | `runtime --kube-context team-aks --namespace services --inventory-only` |
| `--selector EXPR` | Optional pod label selector | `runtime --kube-context team-aks --namespace services --selector app=bff --json` |
| `--syft PATH` | Trusted helper; default `syft` on PATH | `runtime --image eclipse-temurin:21-jre --syft /opt/homebrew/bin/syft --json` |
| `--trivy PATH` | Trusted helper; default `trivy` on PATH | `runtime --image eclipse-temurin:21-jre --trivy /opt/homebrew/bin/trivy --json` |
| `--kubectl PATH` | Trusted helper; default `kubectl` on PATH | `runtime --kube-context team-aks --namespace services --kubectl /usr/local/bin/kubectl --json` |
| `--collect-timeout SECONDS` | Positive per-helper timeout; **300** | `runtime --image eclipse-temurin:21-jre --collect-timeout 600 --json` |
| `--database-max-age SECONDS` | Maximum accepted Trivy DB age; **86400** | `runtime --image eclipse-temurin:21-jre --database-max-age 43200 --json` |
| `--temurin-vdr FILE` | Runtime-only local VDR override | `runtime --local-java --temurin-vdr ~/temurin-vdr.json --json` |
| `--allow-collectors` | Monitor run/schedule execution opt-in | `monitor run --config ~/image-security.json --allow-collectors --json` |

Prefix examples in this table with `agent-do security`.

## Validation status

Live checks verified authenticated Temurin VDR downloads and digest verification,
rootfs JVM identity with Syft 1.55.0, registry image digest collection, and monitor
new/ongoing/unverified retention. Positive live Kubernetes collection and a complete
remote Trivy image assessment remain **deferred** because the test cluster and
registry transport were unavailable. Offline fixtures cover these paths; they do
not establish live integration success.
