#!/usr/bin/env python3
"""Normalize bounded Render evidence for an incident investigation."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

TOKEN = re.compile(r"(?i)\b(token|secret|password|api[_-]?key|authorization)([=:]\s*)(?:bearer\s+)?\S+")
MAX_LOG_RESPONSE_BYTES = 1_048_576


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return TOKEN.sub(lambda match: match.group(1) + match.group(2) + "[REDACTED]", value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): "[REDACTED]" if re.search(r"(?i)(token|secret|password|api[_-]?key|authorization)", str(key)) else redact(item)
                for key, item in value.items()}
    return value


def load_file(path: str, name: str, *, max_bytes: int | None = None) -> Any:
    if max_bytes is not None and os.path.getsize(path) > max_bytes:
        raise ValueError(f"Render {name} response exceeded the {max_bytes}-byte safety limit")
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except json.JSONDecodeError as error:
        raise ValueError(f"Render returned invalid JSON for {name}") from error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-file", required=True)
    parser.add_argument("--deploys-file", required=True)
    parser.add_argument("--events-file", required=True)
    parser.add_argument("--logs-file", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args()
    try:
        service, deploys, events, log_payload = (
            load_file(args.service_file, "service"),
            load_file(args.deploys_file, "deploys"),
            load_file(args.events_file, "events"),
            load_file(args.logs_file, "logs", max_bytes=MAX_LOG_RESPONSE_BYTES),
        )
        normalized_deploys = []
        deploy_items = deploys if isinstance(deploys, list) else []
        for item in deploy_items[:10]:
            deploy = item.get("deploy", item) if isinstance(item, dict) else {}
            commit = deploy.get("commit") or {}
            normalized_deploys.append({"id": deploy.get("id"), "status": deploy.get("status"),
                                       "commit_sha": commit.get("id"), "created_at": deploy.get("createdAt"),
                                       "finished_at": deploy.get("finishedAt"), "trigger": deploy.get("trigger")})
        normalized_events = []
        event_items = events if isinstance(events, list) else []
        for item in event_items[:100]:
            event = item.get("event", item) if isinstance(item, dict) else {}
            normalized_events.append({"timestamp": event.get("timestamp"), "type": event.get("type"),
                                      "reason": redact((event.get("details") or {}).get("reason")),
                                      "details": redact(event.get("details") or {})})
        raw_logs = log_payload.get("logs", []) if isinstance(log_payload, dict) else []
        logs = []
        for entry in raw_logs:
            labels = {label.get("name"): label.get("value") for label in entry.get("labels", []) if isinstance(label, dict)}
            logs.append({"timestamp": entry.get("timestamp"), "message": redact(entry.get("message", "")),
                         "type": redact(labels.get("type")), "level": redact(labels.get("level"))})
        encoded = json.dumps(logs, separators=(",", ":")).encode()
        truncated_bytes = len(encoded) > args.max_bytes
        while logs and len(encoded) > args.max_bytes:
            logs.pop()
            encoded = json.dumps(logs, separators=(",", ":")).encode()
        result = {"success": True, "provider": "render", "since": args.since,
                  "service": {"id": service.get("id"), "name": service.get("name"), "type": service.get("type"),
                              "url": (service.get("serviceDetails") or {}).get("url"), "repo": service.get("repo"),
                              "branch": service.get("branch"), "root_dir": service.get("rootDir"),
                              "auto_deploy": service.get("autoDeploy"), "auto_deploy_trigger": service.get("autoDeployTrigger"),
                              "build_filter": redact(service.get("buildFilter") or {})},
                  "deploys": normalized_deploys, "events": normalized_events,
                  "logs": logs, "limits": {"deploys": 10, "events": 100, "logs": 100, "max_log_bytes": args.max_bytes},
                  "truncated": {"deploys_more_available": len(deploy_items) > 10,
                                "events_more_available": len(event_items) > 100,
                                "logs_more_available": bool(log_payload.get("hasMore")) if isinstance(log_payload, dict) else False,
                                "log_bytes": truncated_bytes}, "redaction": {"applied": True}}
        print(json.dumps(result, indent=2))
        return 0
    except ValueError as error:
        print(json.dumps({"success": False, "provider": "render", "error": str(error), "code": 1}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
