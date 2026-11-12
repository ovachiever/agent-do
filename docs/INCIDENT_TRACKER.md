# Incident tracker

`agent-do incident` creates project-local, read-only evidence packets from explicitly mapped GitHub Actions, Kubernetes, and optional Render sources. It does not deploy, mutate providers, read secrets, or determine root cause.

Run `agent-do incident init`, replace the example mapping in `.agent-do-incident/config.yaml`, then use `agent-do incident validate` and `agent-do incident trace --service NAME`. Packets are atomically published under `.agent-do-incident/traces/` and can be reviewed with `agent-do incident show TRACE_ID`.

The tracker invokes only the established `agent-do` provider commands with `--json`; provider failures remain visible as degraded evidence and do not suppress independent sources. Spacelift is intentionally not part of v1.

## Integration prerequisites

Before merging the tracker, merge the provider read surfaces: CI #56 (after its
`--repo` prerequisite #43), GitHub correlation #57, Kubernetes trace #58, and
Render trace #59 (after its Render JSON prerequisite #40). The tracker has no
provider-specific fallback: a missing surface is an integration blocker, not a
reason to add direct API calls here.
