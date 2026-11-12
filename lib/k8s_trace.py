#!/usr/bin/env python3
"""Read-only Kubernetes evidence for a deployment investigation.

The module uses direct ``kubectl`` argv calls only. It never changes the active
context, opens an interactive session, or runs a command inside a container.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any
from urllib.parse import quote, urlencode

MAX_LOG_LINES = 1000
MAX_LOG_BYTES = 262144
MAX_EVENTS = 100
MAX_EVENT_SOURCES = 100
MAX_EVENTS_PER_SOURCE = 101
TOKEN_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(authorization)([=:]\s*(?:(?:bearer|basic)\s+)?)\S+"),
    re.compile(r"(?i)\b(token|secret|password|api[_-]?key)([=:]\s*)\S+"),
]


class K8sError(RuntimeError):
    pass


def kubectl(*args: str) -> str:
    binary = os.environ.get("AGENT_DO_KUBECTL_BIN", "kubectl")
    try:
        result = subprocess.run([binary, *args], text=True, capture_output=True, timeout=30, check=False)
    except FileNotFoundError:
        raise K8sError("kubectl not found") from None
    except subprocess.TimeoutExpired:
        raise K8sError("kubectl timed out after 30 seconds") from None
    if result.returncode:
        raise K8sError((result.stderr or result.stdout or "kubectl failed").strip())
    return result.stdout


def json_get(context: str, namespace: str, resource: str, name: str | None = None) -> dict[str, Any]:
    args = ["--context", context, "--namespace", namespace, "get", resource]
    if name:
        args.append(name)
    args.extend(["-o", "json"])
    try:
        value = json.loads(kubectl(*args))
    except json.JSONDecodeError:
        raise K8sError(f"kubectl returned invalid JSON for {resource}") from None
    if not isinstance(value, dict):
        raise K8sError(f"kubectl returned an unsupported JSON shape for {resource}")
    return value


def json_raw(context: str, path: str) -> dict[str, Any]:
    """Read one bounded Kubernetes API page without listing a whole namespace."""
    try:
        value = json.loads(kubectl("--context", context, "get", "--raw", path))
    except json.JSONDecodeError:
        raise K8sError("kubectl returned invalid JSON for events") from None
    if not isinstance(value, dict):
        raise K8sError("kubectl returned an unsupported JSON shape for events")
    return value


def labels_selector(labels: dict[str, Any]) -> str:
    pairs = []
    for key, value in labels.items():
        if isinstance(key, str) and isinstance(value, str):
            pairs.append(f"{key}={value}")
    return ",".join(pairs)


def redact(text: str) -> str:
    for pattern in TOKEN_PATTERNS:
        if pattern.groups >= 2:
            text = pattern.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return "".join(char for char in text if char in "\n\t" or ord(char) >= 32)


def safe_metadata_values(values: dict[str, Any]) -> dict[str, str]:
    """Redact annotation values, including values under obviously secret keys."""
    safe: dict[str, str] = {}
    for key, value in values.items():
        rendered_key, rendered_value = str(key), str(value)
        if re.search(r"(?i)(token|secret|password|api[_-]?key|authorization)", rendered_key):
            safe[rendered_key] = "[REDACTED]"
        else:
            safe[rendered_key] = redact(rendered_value)
    return safe


def safe_conditions(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": condition.get("type"), "status": condition.get("status"),
             "reason": condition.get("reason"), "message": redact(str(condition.get("message") or "")) or None}
            for condition in conditions]


def pod_summary(pod: dict[str, Any]) -> dict[str, Any]:
    status = pod.get("status") or {}
    statuses = status.get("containerStatuses") or []
    containers = []
    for item in statuses:
        state = item.get("state") or {}
        waiting = state.get("waiting") or {}
        terminated = state.get("terminated") or {}
        last_terminated = ((item.get("lastState") or {}).get("terminated") or {})
        containers.append({
            "name": item.get("name"), "ready": bool(item.get("ready")), "restart_count": item.get("restartCount", 0),
            "waiting_reason": waiting.get("reason"), "waiting_message": redact(str(waiting.get("message") or "")) or None,
            "termination_reason": terminated.get("reason") or last_terminated.get("reason"),
            "exit_code": terminated.get("exitCode", last_terminated.get("exitCode")),
        })
    return {"name": (pod.get("metadata") or {}).get("name"), "uid": (pod.get("metadata") or {}).get("uid"),
            "phase": status.get("phase"), "node": (pod.get("spec") or {}).get("nodeName"),
            "conditions": safe_conditions(status.get("conditions") or []), "containers": containers}


def deployment(args: argparse.Namespace) -> dict[str, Any]:
    dep = json_get(args.context, args.namespace, "deployment", args.name)
    metadata, spec, status = dep.get("metadata") or {}, dep.get("spec") or {}, dep.get("status") or {}
    selector = labels_selector((spec.get("selector") or {}).get("matchLabels") or {})
    rs_data = json_get(args.context, args.namespace, "replicasets")
    replicasets = [item for item in rs_data.get("items") or []
                   if any(owner.get("uid") == metadata.get("uid") and owner.get("controller")
                          for owner in ((item.get("metadata") or {}).get("ownerReferences") or []))]
    replicaset_uids = {(item.get("metadata") or {}).get("uid") for item in replicasets}
    pod_args = ["--context", args.context, "--namespace", args.namespace, "get", "pods"]
    if selector:
        pod_args.extend(["--selector", selector])
    pod_args.extend(["-o", "json"])
    try:
        pods_data = json.loads(kubectl(*pod_args))
    except json.JSONDecodeError:
        raise K8sError("kubectl returned invalid JSON for pods") from None
    images = [container.get("image") for container in (spec.get("template") or {}).get("spec", {}).get("containers", [])]
    return {"success": True, "provider": "kubernetes", "context": args.context, "namespace": args.namespace,
            "deployment": {"name": metadata.get("name"), "uid": metadata.get("uid"), "generation": metadata.get("generation"),
                           "observed_generation": status.get("observedGeneration"), "revision": (metadata.get("annotations") or {}).get("deployment.kubernetes.io/revision"),
                           "labels": safe_metadata_values(metadata.get("labels") or {}), "annotations": safe_metadata_values(metadata.get("annotations") or {}), "images": images,
                           "replicas": {"desired": spec.get("replicas", 1), "updated": status.get("updatedReplicas", 0), "ready": status.get("readyReplicas", 0), "available": status.get("availableReplicas", 0)},
                           "conditions": safe_conditions(status.get("conditions") or [])},
            "replicasets": [{"name": (item.get("metadata") or {}).get("name"), "revision": ((item.get("metadata") or {}).get("annotations") or {}).get("deployment.kubernetes.io/revision"), "images": [c.get("image") for c in ((item.get("spec") or {}).get("template") or {}).get("spec", {}).get("containers", [])]} for item in replicasets],
            "pods": [pod_summary(item) for item in pods_data.get("items") or []
                     if any(owner.get("uid") in replicaset_uids and owner.get("controller")
                            for owner in ((item.get("metadata") or {}).get("ownerReferences") or []))]}


def events(args: argparse.Namespace) -> dict[str, Any]:
    dep = json_get(args.context, args.namespace, "deployment", args.deployment)
    dep_uid = (dep.get("metadata") or {}).get("uid")
    rs_data = json_get(args.context, args.namespace, "replicasets")
    rs_uids = {(item.get("metadata") or {}).get("uid") for item in rs_data.get("items") or [] if isinstance((item.get("metadata") or {}).get("uid"), str) and any(owner.get("uid") == dep_uid for owner in ((item.get("metadata") or {}).get("ownerReferences") or []))}
    pod_data = json_get(args.context, args.namespace, "pods")
    pod_uids = {(item.get("metadata") or {}).get("uid") for item in pod_data.get("items") or [] if isinstance((item.get("metadata") or {}).get("uid"), str) and any(owner.get("uid") in rs_uids for owner in ((item.get("metadata") or {}).get("ownerReferences") or []))}
    selected = []
    source_uids = [uid for uid in [dep_uid, *sorted(rs_uids), *sorted(pod_uids)] if isinstance(uid, str)]
    source_truncated = len(source_uids) > MAX_EVENT_SOURCES
    for uid in source_uids[:MAX_EVENT_SOURCES]:
        query = urlencode({"fieldSelector": f"involvedObject.uid={uid}", "limit": MAX_EVENTS_PER_SOURCE})
        path = f"/api/v1/namespaces/{quote(args.namespace, safe='')}/events?{query}"
        data = json_raw(args.context, path)
        source_truncated = source_truncated or bool((data.get("metadata") or {}).get("continue"))
        for event in data.get("items") or []:
            involved = event.get("involvedObject") or {}
            selected.append({"type": event.get("type"), "reason": event.get("reason"), "message": redact(str(event.get("message") or "")) or None, "count": event.get("count"), "first_timestamp": event.get("firstTimestamp"), "last_timestamp": event.get("lastTimestamp") or event.get("eventTime") or (event.get("metadata") or {}).get("creationTimestamp"), "object": {"kind": involved.get("kind"), "name": involved.get("name"), "uid": involved.get("uid")}})
    selected.sort(key=lambda event: event.get("last_timestamp") or "", reverse=True)
    return {"success": True, "provider": "kubernetes", "context": args.context, "namespace": args.namespace, "deployment": args.deployment,
            "events": selected[:MAX_EVENTS], "truncated": source_truncated or len(selected) > MAX_EVENTS, "limit": MAX_EVENTS,
            "source_limits": {"objects": MAX_EVENT_SOURCES, "events_per_object": MAX_EVENTS_PER_SOURCE}}


def logs(args: argparse.Namespace) -> dict[str, Any]:
    if not re.fullmatch(r"[1-9][0-9]*[smhd]", args.since):
        raise K8sError("--since must be a positive duration such as 30m or 2h")
    if not 1 <= args.tail <= MAX_LOG_LINES:
        raise K8sError(f"--tail must be between 1 and {MAX_LOG_LINES}")
    if not 1 <= args.max_bytes <= MAX_LOG_BYTES:
        raise K8sError(f"--max-bytes must be between 1 and {MAX_LOG_BYTES}")
    command = ["--context", args.context, "--namespace", args.namespace, "logs", args.pod, "--container", args.container, f"--since={args.since}", f"--tail={args.tail}", f"--limit-bytes={args.max_bytes}"]
    if args.previous:
        command.append("--previous")
    raw = kubectl(*command)
    text = redact(raw)
    encoded = text.encode()
    # kubectl does not tell us whether an exactly-full response was naturally
    # that size or cut by --limit-bytes, so report that boundary conservatively.
    truncated_bytes = len(raw.encode()) >= args.max_bytes or len(encoded) > args.max_bytes
    if len(encoded) > args.max_bytes:
        text = encoded[-args.max_bytes:].decode(errors="ignore")
    return {"success": True, "provider": "kubernetes", "context": args.context, "namespace": args.namespace, "pod": args.pod, "container": args.container, "previous": args.previous, "log": text,
            "limits": {"tail_lines": args.tail, "max_bytes": args.max_bytes, "since": args.since},
            "truncated": {"bytes": truncated_bytes, "line_limit_applied": True, "line_truncation_known": False, "any": truncated_bytes}, "redaction": {"applied": True}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    def common(item: argparse.ArgumentParser) -> None:
        item.add_argument("--context", required=True); item.add_argument("--namespace", required=True); item.add_argument("--json", action="store_true")
    deploy = sub.add_parser("deployment"); deploy.add_argument("name"); common(deploy)
    event = sub.add_parser("events"); event.add_argument("--for-deployment", dest="deployment", required=True); common(event)
    log = sub.add_parser("logs"); log.add_argument("pod"); log.add_argument("--container", required=True); log.add_argument("--since", default="30m"); log.add_argument("--tail", type=int, default=200); log.add_argument("--max-bytes", type=int, default=65536); log.add_argument("--previous", action="store_true"); common(log)
    args = parser.parse_args()
    try:
        result = deployment(args) if args.command == "deployment" else events(args) if args.command == "events" else logs(args)
        print(json.dumps(result, indent=2))
        return 0
    except K8sError as error:
        print(json.dumps({"success": False, "provider": "kubernetes", "error": str(error), "code": 1}))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
