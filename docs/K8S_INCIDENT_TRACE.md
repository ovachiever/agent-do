# Kubernetes incident trace

`agent-do k8s` now has a small read-only surface for collecting the facts needed to understand a failed Kubernetes deployment. It is designed for an incident timeline and works with AKS because AKS supplies a normal `kubectl` context after you authenticate.

It deliberately is not a cluster-management interface. Each trace command requires both `--context` and `--namespace`, returns JSON, and invokes `kubectl` with those values directly. It never changes the active kubeconfig context, starts a shell, runs `exec`, applies a manifest, deletes anything, or reads Kubernetes `Secret` objects.

## The three evidence calls

Start with the deployment:

```bash
agent-do k8s deployment payments-api \
  --context production-aks --namespace payments --json
```

This says what version Kubernetes is trying to run: the Deployment revision and generation, container images, desired/updated/ready/available replica counts, conditions, matching ReplicaSets, and matching pods. For each pod it includes readiness, restart count, waiting reason, termination reason, and exit code. Those are the basic facts that distinguish a bad rollout from a healthy rollout that merely has noisy logs.

Then ask for events that belong to that deployment’s ownership chain:

```bash
agent-do k8s events --for-deployment payments-api \
  --context production-aks --namespace payments --json
```

The command follows the Deployment to its ReplicaSets and pods, returning only their events. It sorts newest first and caps the response at 100 events. The JSON response says when that cap was reached.

Finally, collect a small log excerpt for the affected container:

```bash
agent-do k8s logs payments-api-7df9b8c9b9-abcde --container api \
  --context production-aks --namespace payments --since 30m --tail 200 --json
```

Use `--previous` to get the prior container instance when a pod is crash-looping. Log collection is limited to a positive `--since` duration, at most 1,000 lines, and at most 256 KiB. The response records the requested limits and tells the caller whether its byte cap cut the excerpt. Kubernetes does not report whether its `--tail` limit omitted older lines, so the response identifies that fact as unknown instead of guessing.

## Privacy and safety

The tool makes no `kubectl get secret` request. It also redacts common token-like strings from logs, event messages, pod condition messages, and annotation values. An annotation whose key names a token, password, secret, API key, or authorization value is replaced wholesale. Redaction is a guardrail, not permission to put credentials in application logs; restrict who can run incident traces and avoid sharing raw evidence outside the incident.

The existing short forms such as `agent-do k8s logs POD` keep their legacy interactive behavior. The incident-safe log form is selected only when `--context` is present, which keeps compatibility while ensuring an incident workflow cannot accidentally depend on whichever Kubernetes context happens to be active.

## AKS setup boundary

This project does not log into Azure or select an AKS cluster on your behalf. Before collecting evidence, an operator must obtain a least-privileged Kubernetes context through the organization’s approved AKS authentication process and provide its exact context name. The trace command then uses that context read-only. A typical access policy grants `get` on Deployments, ReplicaSets, Pods, and Events plus `get` on `pods/log`; it does not need `exec`, write, or Secret permissions.

## Structured failures

Every trace result is JSON. On failure the command exits non-zero and still prints a small JSON error object with `success: false`, provider, message, and code. This lets the future incident tracker distinguish “no evidence due to insufficient access” from a deployment that has no recent events.
