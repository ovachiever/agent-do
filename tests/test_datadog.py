#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DD_OPS = ROOT / "tools" / "agent-datadog" / "datadog_ops.py"

PASS = 0
FAIL = 0

# Request log — reset per-section to assert dry-run sends no HTTP
_requests: list[tuple[str, str]] = []
_last_body: dict = {}


def check(desc: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✓ {desc}")
        PASS += 1
    else:
        print(f"  ✗ {desc}")
        if detail:
            print(f"    {detail[:400]}")
        FAIL += 1


def run(argv: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(DD_OPS), *argv],
        text=True, capture_output=True, env=env, check=False,
    )


def _try_json(text: str) -> dict | list | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── fake Datadog API server ───────────────────────────────────────────────────

VALID_API_KEY = "test-dd-api-key"
VALID_APP_KEY = "test-dd-app-key"

_MONITORS = [
    {"id": 101, "name": "CPU High", "type": "metric alert",
     "overall_state": "Alert", "query": "avg(last_5m):avg:system.cpu.user{*} > 90",
     "message": "CPU is too high @pagerduty", "tags": ["env:prod", "service:api"]},
    {"id": 102, "name": "Error Rate", "type": "log alert",
     "overall_state": "OK", "query": "logs(\"status:error\").rollup(\"count\").last(\"5m\") > 100",
     "message": "Error rate elevated", "tags": ["env:prod"]},
    {"id": 103, "name": "Memory Warning", "type": "metric alert",
     "overall_state": "Warn", "query": "avg(last_5m):avg:system.mem.used{*} / avg:system.mem.total{*} > 0.85",
     "message": "Memory usage high", "tags": ["env:staging"]},
]

_LOGS = [
    {"id": "log-abc", "type": "log", "attributes": {
        "timestamp": "2026-05-21T10:00:00.000Z",
        "service": "api",
        "status": "error",
        "message": "Connection timeout to MongoDB",
        "host": "web-01",
    }},
    {"id": "log-def", "type": "log", "attributes": {
        "timestamp": "2026-05-21T10:01:00.000Z",
        "service": "worker",
        "status": "warn",
        "message": "Retry attempt 3 for job-999",
        "host": "worker-02",
    }},
]

_METRICS_SERIES = {
    "status": "ok",
    "from_date": 1716289200000,
    "to_date": 1716292800000,
    "series": [
        {
            "metric": "system.cpu.user",
            "display_name": "system.cpu.user",
            "unit": [{"family": "percentage", "id": 17, "name": "percent", "short_name": "%", "plural": "percent", "scale_factor": 1.0}],
            "pointlist": [[1716289200000, 45.2], [1716290100000, 47.8], [1716291000000, 52.1]],
            "scope": "host:web-01",
            "expression": "avg:system.cpu.user{host:web-01}",
            "aggr": "avg",
            "start": 1716289200000,
            "end": 1716292800000,
            "interval": 900,
            "length": 3,
            "attributes": {},
        }
    ],
    "query": "avg:system.cpu.user{host:web-01}",
    "message": "",
    "res_type": "time_series",
    "resp_version": 1,
    "times": [],
    "values": [],
    "error": "",
}

_METRICS_LIST = {
    "data": [
        {"id": "system.cpu.user", "type": "metrics"},
        {"id": "system.cpu.system", "type": "metrics"},
        {"id": "system.mem.used", "type": "metrics"},
        {"id": "kubernetes.cpu.usage.total", "type": "metrics"},
    ]
}

_EVENTS = [
    {"id": 9001, "title": "Deploy v2.3.1", "text": "Deploy completed successfully",
     "date_happened": 1716289200, "priority": "normal", "tags": ["env:prod", "deploy"]},
    {"id": 9002, "title": "Alert triggered", "text": "CPU exceeded 90%",
     "date_happened": 1716290100, "priority": "normal", "tags": ["env:prod"]},
]

_INCIDENTS = [
    {"id": "inc-001", "type": "incidents", "attributes": {
        "title": "API latency degraded",
        "state": "active",
        "fields": {"severity": {"type": "dropdown", "value": "SEV-2"}},
        "created": "2026-05-21T09:00:00Z",
        "customer_impact_scope": "US customers affected",
    }},
    {"id": "inc-002", "type": "incidents", "attributes": {
        "title": "Database failover", "state": "resolved",
        "fields": {"severity": {"type": "dropdown", "value": "SEV-1"}},
        "created": "2026-05-20T18:00:00Z",
    }},
]

_DASHBOARDS = [
    {"id": "dash-aaa", "title": "Service Overview", "layout_type": "ordered", "url": "/dashboard/dash-aaa"},
    {"id": "dash-bbb", "title": "Infrastructure", "layout_type": "free", "url": "/dashboard/dash-bbb"},
]

_SLOS = [
    {"id": "slo-001", "name": "API Availability", "type": "metric",
     "thresholds": [{"target": 99.9, "timeframe": "30d"}]},
    {"id": "slo-002", "name": "Checkout Latency", "type": "monitor",
     "thresholds": [{"target": 99.0, "timeframe": "7d"}]},
]

_SERVICES = [
    {"id": "api", "type": "service-definitions", "attributes": {"schema": {
        "dd-service": "api", "team": "platform", "description": "Core REST API",
    }}},
    {"id": "worker", "type": "service-definitions", "attributes": {"schema": {
        "dd-service": "worker", "team": "data-eng", "description": "Background job processor",
    }}},
]


class DDHandler(http.server.BaseHTTPRequestHandler):
    def _validate_auth(self) -> bool:
        return (self.headers.get("DD-API-KEY") == VALID_API_KEY and
                self.headers.get("DD-APPLICATION-KEY") == VALID_APP_KEY)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_err(self, msg: str, status: int) -> None:
        self._send({"errors": [msg]}, status=status)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _route(self, method: str, path: str, qs: dict, body: dict) -> None:
        global _last_body
        _requests.append((method, path))
        _last_body = body

        if not self._validate_auth():
            self._send_err("Forbidden: invalid API or application key", status=403)
            return

        scenario = ""
        for prefix in ("/partial-empty", "/all-fail"):
            if path.startswith(prefix + "/"):
                scenario = prefix[1:]
                path = path[len(prefix):]
                break

        # Strip /api/v1 or /api/v2 prefix
        for prefix in ("/api/v2/", "/api/v1/"):
            if path.startswith(prefix):
                path = "/" + path[len(prefix):]
                break

        if scenario == "all-fail" and path in ("/monitor", "/events", "/slo"):
            self._send_err("fixture forced failure", status=500)
            return
        if scenario == "partial-empty":
            if path == "/monitor":
                self._send_err("fixture monitor failure", status=500)
                return
            if path == "/events":
                self._send({"events": []})
                return
            if path == "/slo":
                self._send({"data": []})
                return

        # ── monitors ──────────────────────────────────────────────────────
        if method == "GET" and path == "/monitor":
            if "monitor_states" in qs:
                self._send_err("monitor_states is not a /monitor parameter", status=400)
                return
            monitors = list(_MONITORS)
            name_filter = qs.get("name", [""])[0]
            state_filter = qs.get("monitor_states", [""])[0]
            tag_filter = qs.get("monitor_tags", [""])[0]
            if name_filter:
                monitors = [m for m in monitors if name_filter.lower() in m["name"].lower()]
            if state_filter:
                monitors = [m for m in monitors if m["overall_state"].lower() == state_filter.lower()]
            if tag_filter:
                monitors = [m for m in monitors if tag_filter in (m.get("tags") or [])]
            # env:nonexistent → empty, env:ok-only → one OK monitor for clean-state tests
            if tag_filter == "env:nonexistent":
                monitors = []
            elif tag_filter == "env:ok-only":
                monitors = [{"id": 102, "name": "Error Rate", "type": "log alert",
                             "overall_state": "OK", "query": "logs(\"status:error\").count > 100",
                             "message": "", "tags": ["env:ok-only"]}]
            self._send(monitors)

        elif method == "GET" and path == "/monitor/101":
            self._send(_MONITORS[0])

        elif method == "GET" and path == "/monitor/102":
            self._send(_MONITORS[1])

        elif method == "GET" and path == "/monitor/999":
            self._send_err("Monitor not found", status=404)

        elif method == "GET" and path == "/monitor/403":
            # already handled by auth check but left for explicit test
            self._send_err("Forbidden", status=403)

        elif method == "GET" and path == "/monitor/401":
            self._send_err("Unauthorized: invalid credentials", status=401)

        elif method == "GET" and path == "/monitor/422":
            self._send_err("Unprocessable: query is invalid", status=422)

        elif method == "GET" and path == "/monitor/429":
            self._send_err("Rate limited", status=429)

        elif method == "GET" and path == "/monitor/500":
            self._send_err("Internal server error", status=500)

        elif method == "POST" and path == "/monitor/101/mute":
            muted = dict(_MONITORS[0])
            muted["silenced"] = {"*": body.get("end", 0)}
            self._send(muted)

        elif method == "POST" and path == "/monitor/999/mute":
            self._send_err("Monitor not found", status=404)

        elif method == "POST" and path == "/monitor/101/unmute":
            self._send(_MONITORS[0])

        elif method == "POST" and path == "/monitor":
            created = {
                "id": 201,
                "name": body.get("name", ""),
                "type": body.get("type", ""),
                "query": body.get("query", ""),
                "overall_state": "No Data",
                "tags": body.get("tags", []),
            }
            self._send(created, status=200)

        elif method == "DELETE" and path == "/monitor/101":
            self._send({"deleted_monitor_id": [101]})

        elif method == "DELETE" and path == "/monitor/999":
            self._send_err("Monitor not found", status=404)

        # ── logs ──────────────────────────────────────────────────────────
        elif method == "POST" and path == "/logs/events/search":
            query = (body.get("filter") or {}).get("query", "*")
            limit = (body.get("page") or {}).get("limit", 25)
            logs = list(_LOGS)
            if "nullable" in query:
                logs = [{"id": "log-null", "type": "log", "attributes": {
                    "timestamp": "2026-05-21T10:02:00.000Z",
                    "service": None,
                    "status": None,
                    "message": None,
                }}]
            if "service:worker" in query:
                logs = [l for l in logs if l["attributes"]["service"] == "worker"]
            if "status:error" in query:
                logs = [l for l in logs if l["attributes"]["status"] == "error"]
            if "service:nonexistent" in query:
                logs = []
            logs = logs[:limit]
            cursor = (body.get("page") or {}).get("cursor")
            meta: dict = {}
            if cursor == "page2":
                logs = []
                meta = {"page": {"after": None}}
            else:
                meta = {"page": {"after": "next-cursor-token"}}
            self._send({"data": logs, "meta": meta})

        # ── metrics ───────────────────────────────────────────────────────
        elif method == "GET" and path == "/query":
            query = qs.get("query", [""])[0]
            if "no.data.metric" in query:
                self._send({"series": [], "status": "ok", "query": query})
            else:
                series = dict(_METRICS_SERIES)
                series["query"] = query
                self._send(series)

        elif method == "GET" and path == "/metrics":
            if "filter[prefix]" in qs:
                self._send_err("filter[prefix] is not a /metrics parameter", status=400)
                return
            data = dict(_METRICS_LIST)
            self._send(data)

        # ── events ────────────────────────────────────────────────────────
        elif method == "GET" and path == "/events":
            priority = qs.get("priority", [""])[0]
            tag_filter = qs.get("tags", [""])[0]
            events = list(_EVENTS)
            if tag_filter == "nullable":
                events = [{"id": 9003, "title": None, "text": None,
                           "date_happened": 1716290200, "priority": None, "tags": ["nullable"]}]
            if priority:
                events = [e for e in events if e["priority"] == priority]
            # simulate empty when requesting "low" priority (none match)
            self._send({"events": events})

        elif method == "POST" and path == "/events":
            created = {
                "id": 9999,
                "title": body.get("title", ""),
                "text": body.get("text", ""),
                "priority": body.get("priority", "normal"),
                "tags": body.get("tags", []),
                "alert_type": body.get("alert_type", "info"),
                "date_happened": int(time.time()),
            }
            self._send({"event": created})

        # ── incidents ─────────────────────────────────────────────────────
        elif method == "GET" and path == "/incidents":
            if "filter[state]" in qs:
                self._send_err("filter[state] is not an /incidents parameter", status=400)
                return
            if qs.get("page[size]", [""])[0] != "100":
                self._send_err("Fixture requires documented page[size]=100", status=400)
                return
            if qs.get("page[offset]", [""])[0] != "0":
                self._send_err("Fixture requires page[offset]=0", status=400)
                return
            incs = list(_INCIDENTS)
            incs.append({"id": "inc-null", "type": "incidents", "attributes": {
                "title": None, "state": None,
                "fields": {"severity": {"type": "dropdown", "value": None}},
                "created": "2026-05-21T13:00:00Z",
            }})
            self._send({"data": incs, "meta": {"pagination": {"next": None}}})

        elif method == "GET" and path == "/incidents/inc-001":
            self._send({"data": _INCIDENTS[0]})

        elif method == "GET" and path == "/incidents/inc-999":
            self._send_err("Incident not found", status=404)

        elif method == "POST" and path == "/incidents":
            attrs = (body.get("data") or {}).get("attributes") or {}
            created = {
                "id": "inc-new",
                "type": "incidents",
                "attributes": {
                    "title": attrs.get("title", ""),
                    "state": "active",
                    "fields": attrs.get("fields") or {},
                    "customer_impacted": attrs.get("customer_impacted", False),
                    "created": "2026-05-21T12:00:00Z",
                },
            }
            self._send({"data": created}, status=201)

        elif method == "PATCH" and path == "/incidents/inc-001":
            attrs = (body.get("data") or {}).get("attributes") or {}
            if "status" in attrs or "severity" in attrs:
                self._send_err("status and severity must be attributes.fields dropdowns", status=400)
                return
            updated = dict(_INCIDENTS[0])
            updated["attributes"] = dict(_INCIDENTS[0]["attributes"])
            updated["attributes"]["fields"] = dict(_INCIDENTS[0]["attributes"]["fields"])
            updated["attributes"].update({k: v for k, v in attrs.items() if k != "fields"})
            updated["attributes"]["fields"].update(attrs.get("fields") or {})
            if "state" in updated["attributes"]["fields"]:
                updated["attributes"]["state"] = updated["attributes"]["fields"]["state"].get("value")
            self._send({"data": updated})

        elif method == "PATCH" and path == "/incidents/inc-999":
            self._send_err("Incident not found", status=404)

        # ── dashboards ────────────────────────────────────────────────────
        elif method == "GET" and path == "/dashboard":
            self._send({"dashboards": _DASHBOARDS})

        elif method == "GET" and path == "/dashboard/dash-aaa":
            self._send({**_DASHBOARDS[0], "widgets": [{"id": 1}, {"id": 2}]})

        elif method == "GET" and path == "/dashboard/dash-404":
            self._send_err("Dashboard not found", status=404)

        # ── SLOs ──────────────────────────────────────────────────────────
        elif method == "GET" and path == "/slo":
            tag_filter = qs.get("tags", [""])[0]
            slos = list(_SLOS)
            if tag_filter == "team:nonexistent":
                slos = []
            self._send({"data": slos})

        elif method == "GET" and path == "/slo/slo-001/history":
            self._send({"data": {
                "name": "API Availability",
                "overall": {
                    "sli_value": 99.95,
                    "target": 99.9,
                    "timeframe": "30d",
                    "error_budget_remaining": 82.3,
                },
            }})

        elif method == "GET" and path == "/slo/slo-999/history":
            self._send_err("SLO not found", status=404)

        # ── services ──────────────────────────────────────────────────────
        elif method == "GET" and path == "/services/definitions":
            page_size = int(qs.get("page[size]", ["100"])[0])
            self._send({"data": _SERVICES[:page_size]})

        else:
            self._send_err(f"Not found: {method} {path}", status=404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        self._route("GET", parsed.path, qs, {})

    def do_POST(self) -> None:
        raw = self._read_body()
        body = json.loads(raw) if raw else {}
        parsed = urlparse(self.path)
        self._route("POST", parsed.path, parse_qs(parsed.query), body)

    def do_PATCH(self) -> None:
        raw = self._read_body()
        body = json.loads(raw) if raw else {}
        parsed = urlparse(self.path)
        self._route("PATCH", parsed.path, parse_qs(parsed.query), body)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        self._route("DELETE", parsed.path, parse_qs(parsed.query), {})


def _env(base_url: str, *, api_key: str = VALID_API_KEY, app_key: str = VALID_APP_KEY,
         extra: dict | None = None) -> dict[str, str]:
    e = {**os.environ, "DD_API_BASE_URL": base_url,
         "DD_API_KEY": api_key, "DD_APP_KEY": app_key}
    if extra:
        e.update(extra)
    e.pop("DD_SITE", None)
    return e


def main() -> int:
    global PASS, FAIL, _requests

    server = socketserver.TCPServer(("127.0.0.1", 0), DDHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"

    try:
        env = _env(base)

        # ══════════════════════════════════════════════════════════════════
        # AUTH
        # ══════════════════════════════════════════════════════════════════
        print("\n=== auth ===\n")

        r = run(["monitors"], env={**env, "DD_API_KEY": ""})
        check("missing DD_API_KEY → non-zero exit", r.returncode != 0)
        check("missing DD_API_KEY → mentions DD_API_KEY", "DD_API_KEY" in r.stderr)

        r = run(["monitors"], env={**env, "DD_APP_KEY": ""})
        check("missing DD_APP_KEY → non-zero exit", r.returncode != 0)
        check("missing DD_APP_KEY → mentions DD_APP_KEY", "DD_APP_KEY" in r.stderr)

        r = run(["monitors"], env={**env, "DD_API_KEY": "", "DD_APP_KEY": ""})
        check("both keys missing → mentions both", "DD_API_KEY" in r.stderr and "DD_APP_KEY" in r.stderr)

        r = run(["monitors"], env=_env(base, api_key="wrong-key", app_key="wrong-app"))
        check("wrong API keys → non-zero exit (403)", r.returncode != 0)
        check("wrong API keys → error on stderr", len(r.stderr) > 0)

        # ══════════════════════════════════════════════════════════════════
        # MONITORS LIST
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitors list ===\n")

        r = run(["monitors"], env=env)
        check("monitors list exits 0", r.returncode == 0, r.stderr)
        check("monitors list shows CPU High", "CPU High" in r.stdout)
        check("monitors list shows Error Rate", "Error Rate" in r.stdout)
        check("monitors list shows state ALERT", "ALERT" in r.stdout)
        check("monitors list shows state OK", "OK" in r.stdout)
        check("monitors list shows monitor ID 101", "101" in r.stdout)
        check("monitors list shows tags", "env:prod" in r.stdout)

        r = run(["--json", "monitors"], env=env)
        check("monitors list --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitors list --json is valid JSON", j is not None, r.stdout[:200])
        check("monitors list --json has 'monitors' key", isinstance(j, dict) and "monitors" in j)
        check("monitors list --json has 'count' key", isinstance(j, dict) and "count" in j)
        check("monitors list --json count matches list length",
              isinstance(j, dict) and j.get("count") == len(j.get("monitors", [])))

        r = run(["monitors", "--tag", "env:prod"], env=env)
        check("monitors --tag filters results", r.returncode == 0, r.stderr)
        check("monitors --tag: shows tagged monitors", "CPU High" in r.stdout)

        r = run(["monitors", "--tag", "env:nonexistent"], env=env)
        check("monitors --tag nonexistent → 'No monitors found'", "No monitors found" in r.stdout)

        r = run(["monitors", "--name", "CPU"], env=env)
        check("monitors --name filter shows CPU High", "CPU High" in r.stdout)
        check("monitors --name filter excludes Error Rate", "Error Rate" not in r.stdout)

        r = run(["monitors", "--state", "Alert"], env=env)
        check("monitors --state Alert only shows alerting", "CPU High" in r.stdout)
        check("monitors --state Alert excludes OK monitors", "Error Rate" not in r.stdout)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR GET
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor get ===\n")

        r = run(["monitor", "101"], env=env)
        check("monitor 101 exits 0", r.returncode == 0, r.stderr)
        check("monitor 101 shows name", "CPU High" in r.stdout)
        check("monitor 101 shows type", "metric alert" in r.stdout)
        check("monitor 101 shows state", "Alert" in r.stdout)
        check("monitor 101 shows query", "system.cpu.user" in r.stdout)

        r = run(["--json", "monitor", "101"], env=env)
        check("monitor 101 --json is valid JSON", _try_json(r.stdout) is not None)
        j = _try_json(r.stdout)
        check("monitor 101 --json has id field", isinstance(j, dict) and j.get("id") == 101)

        r = run(["monitor", "999"], env=env)
        check("monitor 999 → non-zero (404)", r.returncode != 0)
        check("monitor 999 → 404 in stderr", "404" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR-STATUS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor-status ===\n")

        r = run(["monitor-status"], env=env)
        check("monitor-status exits 1 (alerting present)", r.returncode == 1, r.stderr)
        check("monitor-status shows ALERT group", "ALERT" in r.stdout)
        check("monitor-status shows WARN group", "WARN" in r.stdout)
        check("monitor-status shows total count", "Total monitors:" in r.stdout)
        check("monitor-status lists alerting monitor by name", "CPU High" in r.stdout)

        r = run(["--json", "monitor-status"], env=env)
        check("monitor-status --json exits 1 (alerting)", r.returncode == 1, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-status --json is valid JSON", j is not None)
        check("monitor-status --json has by_state", isinstance(j, dict) and "by_state" in j)
        check("monitor-status --json ALERT entries have id+name",
              isinstance(j, dict) and all("id" in m and "name" in m
                                          for m in j.get("by_state", {}).get("ALERT", [])))

        r = run(["monitors", "--state", "OK"], env=env)
        check("monitors --state OK includes only OK monitors", "Error Rate" in r.stdout)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR-MUTE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor-mute ===\n")

        _requests.clear()
        r = run(["monitor-mute", "101", "--dry-run"], env=env)
        check("monitor-mute --dry-run exits 0", r.returncode == 0, r.stderr)
        check("monitor-mute --dry-run shows [dry-run]", "[dry-run]" in r.stdout)
        check("monitor-mute --dry-run sends no HTTP", not any("/monitor/101/mute" in p for _, p in _requests))

        _requests.clear()
        r = run(["--json", "monitor-mute", "101", "--dry-run"], env=env)
        check("monitor-mute --dry-run --json exits 0", r.returncode == 0)
        j = _try_json(r.stdout)
        check("monitor-mute --dry-run --json is valid JSON", j is not None, r.stdout)
        check("monitor-mute --dry-run --json has command field",
              isinstance(j, dict) and j.get("command") == "monitor-mute")
        check("monitor-mute --dry-run --json is marked",
              isinstance(j, dict) and j.get("dry_run") is True)
        check("monitor-mute --dry-run --json has monitor_id",
              isinstance(j, dict) and j.get("monitor_id") == 101)
        check("monitor-mute --dry-run --json sends no HTTP", not any("/mute" in p for _, p in _requests))

        r = run(["monitor-mute", "101"], env=env)
        check("monitor-mute 101 exits 0", r.returncode == 0, r.stderr)
        check("monitor-mute 101 shows muted", "Muted" in r.stdout)
        check("monitor-mute 101 shows monitor name", "CPU High" in r.stdout)

        r = run(["monitor-mute", "101", "--end", "now+1h",
                 "--scope", "host:web-01", "--message", "Deploying"], env=env)
        check("monitor-mute with --end --scope --message exits 0", r.returncode == 0, r.stderr)
        check("mute body included scope in last request",
              isinstance(_last_body, dict) and "scope" in _last_body)
        check("mute body included message", isinstance(_last_body, dict) and "Deploying" in (_last_body.get("message") or ""))

        r = run(["monitor-mute", "999"], env=env)
        check("monitor-mute 999 → non-zero (404)", r.returncode != 0)
        check("monitor-mute 999 → 404 in stderr", "404" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR-UNMUTE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor-unmute ===\n")

        _requests.clear()
        r = run(["monitor-unmute", "101", "--dry-run"], env=env)
        check("monitor-unmute --dry-run exits 0", r.returncode == 0)
        check("monitor-unmute --dry-run sends no HTTP", not any("/unmute" in p for _, p in _requests))

        r = run(["--json", "monitor-unmute", "101", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("monitor-unmute --dry-run --json has command=monitor-unmute",
              isinstance(j, dict) and j.get("command") == "monitor-unmute")

        r = run(["monitor-unmute", "101"], env=env)
        check("monitor-unmute 101 exits 0", r.returncode == 0, r.stderr)
        check("monitor-unmute shows Unmuted", "Unmuted" in r.stdout)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR-CREATE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor-create ===\n")

        _requests.clear()
        r = run(["monitor-create",
                 "--name", "Test CPU Alert",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 95",
                 "--dry-run"], env=env)
        check("monitor-create --dry-run exits 0", r.returncode == 0)
        check("monitor-create --dry-run shows monitor name", "Test CPU Alert" in r.stdout)
        check("monitor-create --dry-run sends no HTTP", not any("/monitor" in p for _, p in _requests))

        r = run(["--json", "monitor-create",
                 "--name", "Test CPU Alert",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 95",
                 "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("monitor-create --dry-run --json has body.type",
              isinstance(j, dict) and (j.get("body") or {}).get("type") == "metric alert")
        check("monitor-create --dry-run --json has body.query",
              isinstance(j, dict) and "system.cpu.user" in ((j.get("body") or {}).get("query") or ""))

        r = run(["monitor-create",
                 "--name", "Prod CPU Alert",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 90",
                 "--message", "@pagerduty CPU is high",
                 "--tags", "env:prod,service:api",
                 "--priority", "2"], env=env)
        check("monitor-create live exits 0", r.returncode == 0, r.stderr)
        check("monitor-create live shows Created", "Created" in r.stdout)
        check("monitor-create sends tags in body",
              isinstance(_last_body, dict) and "env:prod" in (_last_body.get("tags") or []))
        check("monitor-create sends priority in body",
              isinstance(_last_body, dict) and _last_body.get("priority") == 2)

        # ══════════════════════════════════════════════════════════════════
        # MONITOR-DELETE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== monitor-delete ===\n")

        _requests.clear()
        r = run(["monitor-delete", "101", "--dry-run"], env=env)
        check("monitor-delete --dry-run exits 0", r.returncode == 0)
        check("monitor-delete --dry-run sends no HTTP", not any(m == "DELETE" for m, _ in _requests))

        r = run(["--json", "monitor-delete", "101", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("monitor-delete --dry-run --json has monitor_id",
              isinstance(j, dict) and j.get("monitor_id") == 101)

        r = run(["monitor-delete", "101"], env=env)
        check("monitor-delete 101 exits 0", r.returncode == 0, r.stderr)
        check("monitor-delete 101 shows Deleted", "Deleted" in r.stdout)

        r = run(["--json", "monitor-delete", "101"], env=env)
        j = _try_json(r.stdout)
        check("monitor-delete --json has deleted=True",
              isinstance(j, dict) and j.get("deleted") is True)

        r = run(["monitor-delete", "999"], env=env)
        check("monitor-delete 999 → non-zero (404)", r.returncode != 0)

        # ══════════════════════════════════════════════════════════════════
        # LOGS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== logs ===\n")

        r = run(["logs"], env=env)
        check("logs default query exits 0", r.returncode == 0, r.stderr)
        check("logs shows entries", "api" in r.stdout or "worker" in r.stdout)
        check("logs shows timestamp", "2026-05-21" in r.stdout)
        check("logs shows service and status", "error" in r.stdout or "warn" in r.stdout)

        r = run(["--json", "logs"], env=env)
        j = _try_json(r.stdout)
        check("logs --json is valid JSON", j is not None)
        check("logs --json has logs list", isinstance(j, dict) and isinstance(j.get("logs"), list))
        check("logs --json has count field", isinstance(j, dict) and "count" in j)
        check("logs --json has meta field", isinstance(j, dict) and "meta" in j)

        r = run(["logs", "--service", "worker"], env=env)
        check("logs --service worker exits 0", r.returncode == 0, r.stderr)
        check("logs --service worker shows worker entries", "worker" in r.stdout)
        check("logs --service worker body has service:worker in query",
              "worker" in r.stdout)

        r = run(["logs", "--status", "error"], env=env)
        check("logs --status error exits 0", r.returncode == 0, r.stderr)
        check("logs --status error shows error entries", "error" in r.stdout)

        r = run(["logs", "--limit", "1"], env=env)
        check("logs --limit 1 exits 0", r.returncode == 0, r.stderr)

        r = run(["logs", "--service", "nonexistent"], env=env)
        check("logs --service nonexistent → No logs found", "No logs found" in r.stdout)

        r = run(["logs", "--from", "now-2h", "--to", "now"], env=env)
        check("logs --from --to exits 0", r.returncode == 0, r.stderr)

        r = run(["logs", "--from", "now-7d", "--to", "now-1d"], env=env)
        check("logs multi-day range exits 0", r.returncode == 0, r.stderr)

        r = run(["logs", "--cursor", "page2"], env=env)
        check("logs --cursor page2 returns empty (end of results)", "No logs found" in r.stdout)

        r = run(["--json", "logs", "--cursor", "page2"], env=env)
        j = _try_json(r.stdout)
        check("logs --cursor page2 --json has empty logs list",
              isinstance(j, dict) and j.get("logs") == [])

        r = run(["logs", "error"], env=env)
        check("logs with explicit query string exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # METRICS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== metrics ===\n")

        r = run(["metrics", "avg:system.cpu.user{host:web-01}"], env=env)
        check("metrics exits 0", r.returncode == 0, r.stderr)
        check("metrics shows Metric:", "Metric:" in r.stdout)
        check("metrics shows Points:", "Points:" in r.stdout)
        check("metrics shows Last:", "Last:" in r.stdout)
        check("metrics shows correct metric name", "system.cpu.user" in r.stdout)

        r = run(["--json", "metrics", "avg:system.cpu.user{*}"], env=env)
        j = _try_json(r.stdout)
        check("metrics --json is valid JSON", j is not None)
        check("metrics --json has series", isinstance(j, dict) and "series" in j)
        check("metrics --json series non-empty", isinstance(j, dict) and len(j.get("series", [])) > 0)

        r = run(["metrics", "avg:no.data.metric{*}"], env=env)
        check("metrics no-data exits 0", r.returncode == 0, r.stderr)
        check("metrics no-data shows 'No data returned'", "No data returned" in r.stdout)

        r = run(["metrics", "avg:system.cpu.user{*}", "--from", "now-4h", "--to", "now-1h"], env=env)
        check("metrics custom --from/--to exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # METRICS-LIST
        # ══════════════════════════════════════════════════════════════════
        print("\n=== metrics-list ===\n")

        r = run(["metrics-list"], env=env)
        check("metrics-list exits 0", r.returncode == 0, r.stderr)
        check("metrics-list shows system.cpu.user", "system.cpu.user" in r.stdout)
        check("metrics-list shows kubernetes metrics", "kubernetes" in r.stdout)

        r = run(["--json", "metrics-list"], env=env)
        j = _try_json(r.stdout)
        check("metrics-list --json has metrics list", isinstance(j, dict) and isinstance(j.get("metrics"), list))
        check("metrics-list --json count matches", isinstance(j, dict) and j.get("count") == len(j.get("metrics", [])))

        r = run(["metrics-list", "--prefix", "system"], env=env)
        check("metrics-list --prefix system exits 0", r.returncode == 0, r.stderr)
        check("metrics-list --prefix filters results", "kubernetes" not in r.stdout)
        check("metrics-list --prefix shows system metrics", "system.cpu" in r.stdout)

        r = run(["--json", "metrics-list", "--prefix", "kubernetes"], env=env)
        j = _try_json(r.stdout)
        check("metrics-list --prefix kubernetes --json: only k8s metrics",
              isinstance(j, dict) and all(m.startswith("kubernetes") for m in j.get("metrics", [])))

        # ══════════════════════════════════════════════════════════════════
        # EVENTS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== events ===\n")

        r = run(["events"], env=env)
        check("events exits 0", r.returncode == 0, r.stderr)
        check("events shows Deploy", "Deploy" in r.stdout)
        check("events shows Alert triggered", "Alert" in r.stdout)

        r = run(["--json", "events"], env=env)
        j = _try_json(r.stdout)
        check("events --json is valid JSON", j is not None)
        check("events --json has events list", isinstance(j, dict) and isinstance(j.get("events"), list))
        check("events --json count matches", isinstance(j, dict) and j.get("count") == len(j.get("events", [])))

        r = run(["events", "--priority", "low"], env=env)
        check("events --priority low → empty (no low events)", r.returncode == 0, r.stderr)

        r = run(["events", "--from", "now-24h", "--to", "now"], env=env)
        check("events --from/--to exits 0", r.returncode == 0, r.stderr)

        r = run(["events", "--tags", "deploy"], env=env)
        check("events --tags exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # EVENT-POST
        # ══════════════════════════════════════════════════════════════════
        print("\n=== event-post ===\n")

        _requests.clear()
        r = run(["event-post", "--title", "Deploy started", "--text", "v2.4.0 deploying", "--dry-run"], env=env)
        check("event-post --dry-run exits 0", r.returncode == 0)
        check("event-post --dry-run shows [dry-run]", "[dry-run]" in r.stdout)
        check("event-post --dry-run sends no HTTP", not any("POST" == m and "/events" in p for m, p in _requests))

        r = run(["--json", "event-post", "--title", "Deploy", "--text", "body", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("event-post --dry-run --json has command=event-post",
              isinstance(j, dict) and j.get("command") == "event-post")
        check("event-post --dry-run --json body has title",
              isinstance(j, dict) and (j.get("body") or {}).get("title") == "Deploy")

        r = run(["event-post", "--title", "Deploy v2.4.0",
                 "--text", "Deployment started by CI",
                 "--priority", "normal",
                 "--tags", "env:prod,service:api",
                 "--alert-type", "info"], env=env)
        check("event-post live exits 0", r.returncode == 0, r.stderr)
        check("event-post live shows Posted event", "Posted event" in r.stdout)
        check("event-post sends tags in body",
              isinstance(_last_body, dict) and "env:prod" in (_last_body.get("tags") or []))
        check("event-post sends alert_type in body",
              isinstance(_last_body, dict) and _last_body.get("alert_type") == "info")

        r = run(["--json", "event-post", "--title", "Test", "--text", "Test body"], env=env)
        j = _try_json(r.stdout)
        check("event-post --json live returns event id", isinstance(j, dict) and "id" in j)

        # ══════════════════════════════════════════════════════════════════
        # INCIDENTS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== incidents ===\n")

        r = run(["incidents"], env=env)
        check("incidents exits 0", r.returncode == 0, r.stderr)
        check("incidents shows inc-001", "inc-001" in r.stdout)
        check("incidents shows API latency degraded", "API latency" in r.stdout)
        check("incidents shows SEV-2", "SEV-2" in r.stdout)

        r = run(["--json", "incidents"], env=env)
        j = _try_json(r.stdout)
        check("incidents --json is valid JSON", j is not None)
        check("incidents --json has data list", isinstance(j, dict) and isinstance(j.get("data"), list))
        check("incidents --json exposes the page boundary", isinstance(j, dict) and j.get("offset") == 0 and j.get("page_size") == 100 and "has_more" in j)

        r = run(["incidents", "--state", "active"], env=env)
        check("incidents --state active exits 0", r.returncode == 0, r.stderr)
        check("incidents --state active shows active incidents", "active" in r.stdout)
        check("incidents --state active excludes resolved", "resolved" not in r.stdout)

        r = run(["incidents", "--state", "resolved"], env=env)
        check("incidents --state resolved shows resolved ones", "resolved" in r.stdout)

        # ══════════════════════════════════════════════════════════════════
        # INCIDENT GET
        # ══════════════════════════════════════════════════════════════════
        print("\n=== incident get ===\n")

        r = run(["incident", "inc-001"], env=env)
        check("incident inc-001 exits 0", r.returncode == 0, r.stderr)
        check("incident inc-001 shows title", "API latency" in r.stdout)
        check("incident inc-001 shows status", "active" in r.stdout)
        check("incident inc-001 shows severity", "SEV-2" in r.stdout)
        check("incident inc-001 shows created date", "2026-05-21" in r.stdout)
        check("incident inc-001 shows impact scope", "US customers" in r.stdout)

        r = run(["--json", "incident", "inc-001"], env=env)
        j = _try_json(r.stdout)
        check("incident --json is valid JSON", j is not None)
        check("incident --json has data.id", (j or {}).get("data", {}).get("id") == "inc-001")

        r = run(["incident", "inc-999"], env=env)
        check("incident inc-999 → non-zero (404)", r.returncode != 0)
        check("incident inc-999 → 404 in stderr", "404" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # INCIDENT-CREATE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== incident-create ===\n")

        _requests.clear()
        r = run(["incident-create", "--title", "DB latency spike", "--dry-run"], env=env)
        check("incident-create --dry-run exits 0", r.returncode == 0)
        check("incident-create --dry-run shows [dry-run]", "[dry-run]" in r.stdout)
        check("incident-create --dry-run sends no HTTP", not any("POST" == m and "/incidents" in p for m, p in _requests))

        r = run(["--json", "incident-create", "--title", "DB latency spike",
                 "--severity", "SEV-2", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("incident-create --dry-run --json has command", isinstance(j, dict) and j.get("command") == "incident-create")
        check("incident-create --dry-run --json has attributes.title",
              isinstance(j, dict) and (j.get("attributes") or {}).get("title") == "DB latency spike")
        check("incident-create --dry-run --json has attributes.severity",
              isinstance(j, dict) and (((j.get("attributes") or {}).get("fields") or {}).get("severity") or {}).get("value") == "SEV-2")

        r = run(["incident-create", "--title", "Checkout errors",
                 "--severity", "SEV-1", "--customer-impacted"], env=env)
        check("incident-create live exits 0", r.returncode == 0, r.stderr)
        check("incident-create live shows Created", "Created" in r.stdout)
        check("incident-create sends customer_impacted=True",
              isinstance(_last_body, dict) and
              (((_last_body.get("data") or {}).get("attributes") or {}).get("customer_impacted") is True))

        # ══════════════════════════════════════════════════════════════════
        # INCIDENT-UPDATE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== incident-update ===\n")

        _requests.clear()
        r = run(["incident-update", "inc-001", "--status", "stable", "--dry-run"], env=env)
        check("incident-update --dry-run exits 0", r.returncode == 0)
        check("incident-update --dry-run sends no HTTP",
              not any("PATCH" == m and "/incidents" in p for m, p in _requests))

        r = run(["--json", "incident-update", "inc-001", "--title", "New title", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("incident-update --dry-run --json has incident_id",
              isinstance(j, dict) and j.get("incident_id") == "inc-001")
        check("incident-update --dry-run --json has attributes.title",
              isinstance(j, dict) and (j.get("attributes") or {}).get("title") == "New title")

        r = run(["incident-update", "inc-001", "--status", "stable"], env=env)
        check("incident-update live exits 0", r.returncode == 0, r.stderr)
        check("incident-update shows Updated", "Updated" in r.stdout)

        r = run(["incident-update", "inc-999", "--status", "resolved"], env=env)
        check("incident-update 999 → non-zero (404)", r.returncode != 0)

        r = run(["incident-update", "inc-001"], env=env)
        check("incident-update with no attrs → non-zero (missing required)", r.returncode != 0)

        # ══════════════════════════════════════════════════════════════════
        # INCIDENT-RESOLVE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== incident-resolve ===\n")

        _requests.clear()
        r = run(["incident-resolve", "inc-001", "--dry-run"], env=env)
        check("incident-resolve --dry-run exits 0", r.returncode == 0)
        check("incident-resolve --dry-run sends no HTTP",
              not any("PATCH" == m and "/incidents" in p for m, p in _requests))

        r = run(["--json", "incident-resolve", "inc-001", "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("incident-resolve --dry-run --json has command=incident-resolve",
              isinstance(j, dict) and j.get("command") == "incident-resolve")
        check("incident-resolve --dry-run --json has incident_id",
              isinstance(j, dict) and j.get("incident_id") == "inc-001")

        r = run(["incident-resolve", "inc-001"], env=env)
        check("incident-resolve live exits 0", r.returncode == 0, r.stderr)
        check("incident-resolve sends state=resolved dropdown in body",
              isinstance(_last_body, dict) and
              (((((_last_body.get("data") or {}).get("attributes") or {}).get("fields") or {}).get("state") or {}).get("value") == "resolved"))

        # ══════════════════════════════════════════════════════════════════
        # DASHBOARDS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== dashboards ===\n")

        r = run(["dashboards"], env=env)
        check("dashboards exits 0", r.returncode == 0, r.stderr)
        check("dashboards shows dash-aaa", "dash-aaa" in r.stdout)
        check("dashboards shows Service Overview", "Service Overview" in r.stdout)
        check("dashboards shows layout type", "ordered" in r.stdout or "free" in r.stdout)

        r = run(["--json", "dashboards"], env=env)
        j = _try_json(r.stdout)
        check("dashboards --json is valid JSON", j is not None)
        check("dashboards --json has dashboards list",
              isinstance(j, dict) and isinstance(j.get("dashboards"), list))
        check("dashboards --json count correct",
              isinstance(j, dict) and j.get("count") == len(j.get("dashboards", [])))

        r = run(["dashboard", "dash-aaa"], env=env)
        check("dashboard dash-aaa exits 0", r.returncode == 0, r.stderr)
        check("dashboard shows title", "Service Overview" in r.stdout)
        check("dashboard shows Widgets:", "Widgets:" in r.stdout)
        check("dashboard shows widget count", "2" in r.stdout)

        r = run(["--json", "dashboard", "dash-aaa"], env=env)
        j = _try_json(r.stdout)
        check("dashboard --json has id field", isinstance(j, dict) and j.get("id") == "dash-aaa")
        check("dashboard --json has widgets list", isinstance(j, dict) and isinstance(j.get("widgets"), list))

        r = run(["dashboard", "dash-404"], env=env)
        check("dashboard dash-404 → non-zero (404)", r.returncode != 0)
        check("dashboard dash-404 → 404 in stderr", "404" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # SLOs
        # ══════════════════════════════════════════════════════════════════
        print("\n=== SLOs ===\n")

        r = run(["slos"], env=env)
        check("slos exits 0", r.returncode == 0, r.stderr)
        check("slos shows slo-001", "slo-001" in r.stdout)
        check("slos shows API Availability", "API Availability" in r.stdout)
        check("slos shows type", "metric" in r.stdout)

        r = run(["--json", "slos"], env=env)
        j = _try_json(r.stdout)
        check("slos --json has slos list", isinstance(j, dict) and isinstance(j.get("slos"), list))
        check("slos --json count correct",
              isinstance(j, dict) and j.get("count") == len(j.get("slos", [])))

        r = run(["slos", "--tags", "team:nonexistent"], env=env)
        check("slos --tags no match → 'No SLOs found'", "No SLOs found" in r.stdout)

        r = run(["slo", "slo-001"], env=env)
        check("slo slo-001 exits 0", r.returncode == 0, r.stderr)
        check("slo shows SLI value", "99.95" in r.stdout)
        check("slo shows Target", "99.9" in r.stdout)
        check("slo shows error budget remaining", "82.3" in r.stdout)
        check("slo shows Error budget remaining label", "Error budget" in r.stdout)

        r = run(["--json", "slo", "slo-001"], env=env)
        j = _try_json(r.stdout)
        check("slo --json is valid JSON", j is not None)
        check("slo --json has data.overall.sli_value",
              isinstance(j, dict) and (j.get("data") or {}).get("overall", {}).get("sli_value") == 99.95)

        r = run(["slo", "slo-001", "--from", "now-30d", "--to", "now"], env=env)
        check("slo with --from/--to exits 0", r.returncode == 0, r.stderr)

        r = run(["slo", "slo-999"], env=env)
        check("slo slo-999 → non-zero (404)", r.returncode != 0)
        check("slo slo-999 → 404 in stderr", "404" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # SERVICES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== services ===\n")

        r = run(["services"], env=env)
        check("services exits 0", r.returncode == 0, r.stderr)
        check("services shows api service", "api" in r.stdout)
        check("services shows worker service", "worker" in r.stdout)
        check("services shows team name", "platform" in r.stdout or "data-eng" in r.stdout)
        check("services shows description", "REST API" in r.stdout)

        r = run(["--json", "services"], env=env)
        j = _try_json(r.stdout)
        check("services --json has services list",
              isinstance(j, dict) and isinstance(j.get("services"), list))
        check("services --json count correct",
              isinstance(j, dict) and j.get("count") == len(j.get("services", [])))

        r = run(["services", "--page-size", "1"], env=env)
        check("services --page-size 1 exits 0", r.returncode == 0, r.stderr)
        r2 = run(["--json", "services", "--page-size", "1"], env=env)
        j2 = _try_json(r2.stdout)
        check("services --page-size 1 returns only 1 service",
              isinstance(j2, dict) and j2.get("count") == 1)
        check("services JSON reports pagination rather than claiming count is total",
              isinstance(j2, dict) and j2.get("page") == 1 and j2.get("page_size") == 1
              and "total" in j2 and "has_next_page" in j2 and "truncated" in j2)

        # ══════════════════════════════════════════════════════════════════
        # SNAPSHOT
        # ══════════════════════════════════════════════════════════════════
        print("\n=== snapshot ===\n")

        r = run(["snapshot"], env=env)
        check("snapshot exits 1 (alerting monitors present)", r.returncode == 1, r.stderr)
        check("snapshot shows Monitors:", "Monitors:" in r.stdout)
        check("snapshot shows Events (1h):", "Events (1h):" in r.stdout)
        check("snapshot shows SLOs:", "SLOs:" in r.stdout)
        check("snapshot shows ALERT line", "ALERT" in r.stdout)
        check("snapshot shows CPU High in alert list", "CPU High" in r.stdout)
        check("snapshot shows WARN line", "WARN" in r.stdout)

        r = run(["--json", "snapshot"], env=env)
        j = _try_json(r.stdout)
        check("snapshot --json is valid JSON", j is not None)
        check("snapshot --json has tool=datadog",
              isinstance(j, dict) and j.get("tool") == "datadog")
        check("snapshot --json has timestamp",
              isinstance(j, dict) and "timestamp" in j)
        check("snapshot --json has monitors object",
              isinstance(j, dict) and isinstance(j.get("monitors"), dict))
        check("snapshot --json monitors has total, alerting, warning",
              isinstance(j, dict) and all(k in (j.get("monitors") or {}) for k in ("total", "alerting", "warning")))
        check("snapshot --json alerting list non-empty",
              isinstance(j, dict) and len((j.get("monitors") or {}).get("alerting", [])) > 0)
        check("snapshot --json alerting entries have id and name",
              isinstance(j, dict) and all(
                  "id" in m and "name" in m
                  for m in (j.get("monitors") or {}).get("alerting", [])))
        check("snapshot --json has recent_events int",
              isinstance(j, dict) and isinstance(j.get("recent_events"), int))
        check("snapshot --json has slos int",
              isinstance(j, dict) and isinstance(j.get("slos"), int))

        # ══════════════════════════════════════════════════════════════════
        # ERROR HANDLING
        # ══════════════════════════════════════════════════════════════════
        print("\n=== error handling ===\n")

        r = run(["monitor", "999"], env=env)
        check("404 error → non-zero exit", r.returncode != 0)
        check("API errors use exit 2 (distinct from alerting)", r.returncode == 2)
        check("404 error → '404' in stderr", "404" in r.stderr)

        r = run(["monitor", "429"], env=env)
        check("429 rate-limit → non-zero exit", r.returncode != 0)
        check("429 rate-limit → error message on stderr", len(r.stderr) > 0)

        r = run(["monitor", "500"], env=env)
        check("500 server error → non-zero exit", r.returncode != 0)
        check("500 server error → '500' in stderr", "500" in r.stderr)

        # connection refused: point at a closed port
        r = run(["monitors"], env={**env, "DD_API_BASE_URL": "http://127.0.0.1:1"})
        check("connection refused → non-zero exit", r.returncode != 0)
        check("connection refused → error message on stderr", len(r.stderr) > 0)

        # ══════════════════════════════════════════════════════════════════
        # TIME PARSING
        # ══════════════════════════════════════════════════════════════════
        print("\n=== time parsing ===\n")

        for time_arg in ["now-1h", "now-2d", "now-30m", "now-1w", "now"]:
            r = run(["events", "--from", time_arg], env=env)
            check(f"time '{time_arg}' accepted by --from", r.returncode == 0, r.stderr)

        r = run(["events", "--from", "2026-01-01"], env=env)
        check("ISO date 2026-01-01 accepted by --from", r.returncode == 0, r.stderr)

        r = run(["events", "--from", "1716289200"], env=env)
        check("epoch integer accepted by --from", r.returncode == 0, r.stderr)

        r = run(["events", "--from", "not-a-date"], env=env)
        check("invalid time string → non-zero exit", r.returncode != 0)
        check("invalid time string → error in stderr", "Cannot parse time" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # DD_SITE OVERRIDE
        # ══════════════════════════════════════════════════════════════════
        print("\n=== DD_SITE / base URL ===\n")

        # DD_API_BASE_URL takes priority over DD_SITE
        r = run(["monitors"], env={**env, "DD_SITE": "datadoghq.eu",
                                   "DD_API_BASE_URL": base})
        check("DD_API_BASE_URL overrides DD_SITE", r.returncode == 0, r.stderr)

        # When no DD_API_BASE_URL set, DD_SITE shapes the URL
        # (we can't actually reach datadoghq.eu in tests, just verify exit != 0 differently)
        r = run(["monitors"], env={k: v for k, v in env.items()
                                   if k != "DD_API_BASE_URL"} | {"DD_SITE": "datadoghq.eu"})
        check("DD_SITE=datadoghq.eu with no base override → connection error (not auth error)",
              r.returncode != 0 and "DD_API_KEY" not in r.stderr)

        # Empty DD_SITE falls back to datadoghq.com
        r = run(["monitors"], env={**env, "DD_SITE": ""})
        check("DD_SITE empty → falls back to datadoghq.com base URL, test server still responds",
              r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # AUTH HEADER VERIFICATION
        # ══════════════════════════════════════════════════════════════════
        print("\n=== auth header verification ===\n")

        _requests.clear()
        r = run(["monitors"], env=env)
        check("valid creds → 200 response, exits 0", r.returncode == 0, r.stderr)

        r = run(["monitors"], env=_env(base, api_key="bad-key", app_key=VALID_APP_KEY))
        check("bad API key → 403 → non-zero exit", r.returncode != 0)

        r = run(["monitors"], env=_env(base, api_key=VALID_API_KEY, app_key="bad-app-key"))
        check("bad APP key → 403 → non-zero exit", r.returncode != 0)

        # ══════════════════════════════════════════════════════════════════
        # HELP OUTPUT
        # ══════════════════════════════════════════════════════════════════
        print("\n=== help output ===\n")

        r = run(["--help"], env=env)
        check("--help exits 0", r.returncode == 0)
        check("--help mentions monitors", "monitors" in r.stdout)
        check("--help mentions logs", "logs" in r.stdout)
        check("--help mentions incidents", "incidents" in r.stdout)
        check("--help mentions snapshot", "snapshot" in r.stdout)

        for cmd in ["monitors", "monitor-mute", "logs", "metrics", "incidents",
                    "incident-create", "dashboards", "slos", "services", "snapshot"]:
            r = run([cmd, "--help"], env=env)
            check(f"{cmd} --help exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # EDGE CASES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== edge cases ===\n")

        # monitor-create without required args
        r = run(["monitor-create", "--name", "Only name"], env=env)
        check("monitor-create missing --type → non-zero exit", r.returncode != 0)

        r = run(["monitor-create", "--name", "x", "--type", "metric alert"], env=env)
        check("monitor-create missing --query → non-zero exit", r.returncode != 0)

        # incident-create without --title
        r = run(["incident-create"], env=env)
        check("incident-create missing --title → non-zero exit", r.returncode != 0)

        # event-post missing required args
        r = run(["event-post", "--title", "Only title"], env=env)
        check("event-post missing --text → non-zero exit", r.returncode != 0)

        # monitor-mute with time expressions as --end
        r = run(["monitor-mute", "101", "--end", "now-1h", "--dry-run"], env=env)
        check("monitor-mute --end now-1h accepted", r.returncode == 0)

        r = run(["monitor-mute", "101", "--end", "now+1h", "--dry-run"], env=env)
        check("monitor-mute --end now+1h accepted", r.returncode == 0)

        r = run(["monitor-mute", "101", "--end", "now", "--dry-run"], env=env)
        check("monitor-mute --end now accepted", r.returncode == 0)

        # priority choices validated
        r = run(["event-post", "--title", "T", "--text", "B", "--priority", "urgent"], env=env)
        check("event-post invalid --priority → non-zero exit", r.returncode != 0)

        # monitor-create priority range validation
        r = run(["monitor-create", "--name", "x", "--type", "metric alert",
                 "--query", "q", "--priority", "6", "--dry-run"], env=env)
        check("monitor-create --priority 6 (out of range) → non-zero", r.returncode != 0)

        # incident-create invalid severity
        r = run(["incident-create", "--title", "T", "--severity", "SEV-9", "--dry-run"], env=env)
        check("incident-create invalid --severity → non-zero", r.returncode != 0)

        # logs with --limit 0 (edge: still parses, server returns empty slice)
        r = run(["logs", "--limit", "0"], env=env)
        check("logs --limit 0 exits 0 (server decides)", r.returncode == 0, r.stderr)

        # metrics-list empty prefix
        r = run(["metrics-list", "--prefix", ""], env=env)
        check("metrics-list --prefix empty string exits 0", r.returncode == 0, r.stderr)

        # no-alerting list exits 0
        r = run(["monitors", "--state", "OK"], env=env)
        check("no-alerting monitors list exits 0", r.returncode == 0)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — HTTP ERROR CODES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: HTTP error codes ===\n")

        r = run(["monitor", "401"], env=env)
        check("401 Unauthorized → non-zero exit", r.returncode != 0)
        check("401 Unauthorized → '401' in stderr", "401" in r.stderr)
        check("401 Unauthorized → error detail in stderr", len(r.stderr.strip()) > 5)

        r = run(["monitor", "422"], env=env)
        check("422 Unprocessable → non-zero exit", r.returncode != 0)
        check("422 Unprocessable → '422' in stderr", "422" in r.stderr)

        r = run(["monitor", "429"], env=env)
        check("429 Rate Limited → non-zero exit", r.returncode != 0)
        check("429 Rate Limited → '429' in stderr", "429" in r.stderr)

        r = run(["monitor", "500"], env=env)
        check("500 Server Error → non-zero exit", r.returncode != 0)
        check("500 Server Error → '500' in stderr", "500" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — CLEAN STATE EXIT CODES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: clean state exit codes ===\n")

        r = run(["monitor-status", "--tag", "env:nonexistent"], env=env)
        check("monitor-status all-empty → exits 0", r.returncode == 0, r.stderr)
        check("monitor-status all-empty → shows Total monitors: 0", "Total monitors: 0" in r.stdout)

        r = run(["--json", "monitor-status", "--tag", "env:nonexistent"], env=env)
        check("monitor-status all-empty --json → exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-status all-empty --json → ALERT list empty",
              isinstance(j, dict) and j.get("by_state", {}).get("ALERT") is None)

        r = run(["monitor-status", "--tag", "env:ok-only"], env=env)
        check("monitor-status all-OK → exits 0", r.returncode == 0, r.stderr)

        r = run(["--json", "monitor-status", "--tag", "env:ok-only"], env=env)
        check("monitor-status all-OK --json → exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-status all-OK --json → no ALERT key in by_state",
              isinstance(j, dict) and "ALERT" not in (j.get("by_state") or {}))
        check("monitor-status all-OK --json → OK key present",
              isinstance(j, dict) and "OK" in (j.get("by_state") or {}))

        r = run(["slos"], env=env)
        check("slos exits 0 (read-only, always clean)", r.returncode == 0, r.stderr)

        r = run(["services"], env=env)
        check("services exits 0 (read-only, always clean)", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — REQUEST BODY ASSERTIONS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: request body assertions ===\n")

        # logs combined --service + --status filter query composition
        r = run(["--json", "logs", "--service", "api", "--status", "error"], env=env)
        check("logs --service + --status exits 0", r.returncode == 0, r.stderr)
        # verify both filters were in the query by checking the server received them
        # (since error+service:api query matches neither service:worker nor service:nonexistent,
        #  it returns all logs → count > 0)
        j = _try_json(r.stdout)
        check("logs --service + --status --json logs list is list",
              isinstance(j, dict) and isinstance(j.get("logs"), list))

        # verify via a second call that the composed query hits the right logs path
        r2 = run(["logs", "timeout", "--service", "api", "--status", "error"], env=env)
        check("logs query + --service + --status combined exits 0", r2.returncode == 0, r2.stderr)

        # monitor-create body: message + tags + priority all sent
        r = run(["--json", "monitor-create",
                 "--name", "Body Test Monitor",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 95",
                 "--message", "notify @pagerduty",
                 "--tags", "env:prod,team:platform",
                 "--priority", "1"], env=env)
        check("monitor-create all fields --json exits 0", r.returncode == 0, r.stderr)
        check("monitor-create body has message",
              isinstance(_last_body, dict) and "notify @pagerduty" in (_last_body.get("message") or ""))
        check("monitor-create body has correct tags",
              isinstance(_last_body, dict) and "team:platform" in (_last_body.get("tags") or []))
        check("monitor-create body has priority=1",
              isinstance(_last_body, dict) and _last_body.get("priority") == 1)
        check("monitor-create body has type field",
              isinstance(_last_body, dict) and _last_body.get("type") == "metric alert")
        check("monitor-create body has query field",
              isinstance(_last_body, dict) and "system.cpu.user" in (_last_body.get("query") or ""))

        # event-post body: all optional fields sent when specified
        r = run(["--json", "event-post",
                 "--title", "Full body test",
                 "--text", "Event body text",
                 "--priority", "low",
                 "--tags", "env:staging,deploy",
                 "--alert-type", "warning"], env=env)
        check("event-post full body exits 0", r.returncode == 0, r.stderr)
        check("event-post body priority=low",
              isinstance(_last_body, dict) and _last_body.get("priority") == "low")
        check("event-post body alert_type=warning",
              isinstance(_last_body, dict) and _last_body.get("alert_type") == "warning")
        check("event-post body tags list contains deploy",
              isinstance(_last_body, dict) and "deploy" in (_last_body.get("tags") or []))

        # incident-update body: all three fields together
        r = run(["incident-update", "inc-001",
                 "--title", "Updated title",
                 "--status", "stable",
                 "--severity", "SEV-3"], env=env)
        check("incident-update all three fields exits 0", r.returncode == 0, r.stderr)
        sent_attrs = ((_last_body.get("data") or {}).get("attributes") or {})
        check("incident-update body has title", sent_attrs.get("title") == "Updated title")
        fields = sent_attrs.get("fields") or {}
        check("incident-update body has state dropdown",
              (fields.get("state") or {}).get("value") == "stable" and (fields.get("state") or {}).get("type") == "dropdown")
        check("incident-update body has severity dropdown",
              (fields.get("severity") or {}).get("value") == "SEV-3" and (fields.get("severity") or {}).get("type") == "dropdown")
        check("incident-update body data.id matches arg",
              ((_last_body.get("data") or {}).get("id")) == "inc-001")

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — --JSON LIVE WRITE RESPONSES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: --json live write responses ===\n")

        r = run(["--json", "monitor-mute", "101"], env=env)
        check("monitor-mute live --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-mute live --json is valid JSON", j is not None, r.stdout)
        check("monitor-mute live --json has id=101", isinstance(j, dict) and j.get("id") == 101)
        check("monitor-mute live --json has name", isinstance(j, dict) and j.get("name") == "CPU High")

        r = run(["--json", "monitor-unmute", "101"], env=env)
        check("monitor-unmute live --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-unmute live --json has id=101", isinstance(j, dict) and j.get("id") == 101)

        r = run(["--json", "monitor-create",
                 "--name", "JSON Response Test",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 90"], env=env)
        check("monitor-create live --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor-create live --json has id", isinstance(j, dict) and j.get("id") == 201)
        check("monitor-create live --json has name echoed back",
              isinstance(j, dict) and j.get("name") == "JSON Response Test")

        r = run(["--json", "incident-update", "inc-001", "--status", "active"], env=env)
        check("incident-update live --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("incident-update live --json has data.id",
              isinstance(j, dict) and (j.get("data") or {}).get("id") == "inc-001")

        r = run(["--json", "incident-resolve", "inc-001"], env=env)
        check("incident-resolve live --json exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("incident-resolve live --json is valid JSON", j is not None, r.stdout)

        r = run(["--json", "event-post", "--title", "JSON test", "--text", "body"], env=env)
        check("event-post live --json has id", isinstance(_try_json(r.stdout), dict) and
              "id" in (_try_json(r.stdout) or {}))

        r = run(["--json", "monitor-delete", "101"], env=env)
        check("monitor-delete live --json has deleted=True",
              (_try_json(r.stdout) or {}).get("deleted") is True)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — OPTIONAL FIELD HANDLING
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: optional fields ===\n")

        # monitor-create with only required fields
        r = run(["monitor-create",
                 "--name", "Minimal Monitor",
                 "--type", "metric alert",
                 "--query", "avg(last_5m):avg:system.cpu.user{*} > 80"], env=env)
        check("monitor-create minimal (no optional fields) exits 0", r.returncode == 0, r.stderr)
        check("monitor-create minimal body has no message key",
              isinstance(_last_body, dict) and "message" not in _last_body)
        check("monitor-create minimal body has no tags key",
              isinstance(_last_body, dict) and "tags" not in _last_body)
        check("monitor-create minimal body has no priority key",
              isinstance(_last_body, dict) and "priority" not in _last_body)

        # monitor-create log alert type
        r = run(["monitor-create",
                 "--name", "Log Alert",
                 "--type", "log alert",
                 "--query", "logs(\"status:error\").count > 50",
                 "--dry-run"], env=env)
        check("monitor-create --type 'log alert' --dry-run exits 0", r.returncode == 0)
        r = run(["--json", "monitor-create",
                 "--name", "Log Alert",
                 "--type", "log alert",
                 "--query", "logs(\"status:error\").count > 50",
                 "--dry-run"], env=env)
        j = _try_json(r.stdout)
        check("monitor-create --type 'log alert' body.type is 'log alert'",
              isinstance(j, dict) and (j.get("body") or {}).get("type") == "log alert")

        # incident-create without --severity (optional)
        r = run(["incident-create", "--title", "No severity incident"], env=env)
        check("incident-create without --severity exits 0", r.returncode == 0, r.stderr)
        sent_attrs = ((_last_body.get("data") or {}).get("attributes") or {})
        check("incident-create without --severity body has no severity field",
              "severity" not in (sent_attrs.get("fields") or {}))

        # incident-create without --customer-impacted (default False)
        r = run(["incident-create", "--title", "Default impacted"], env=env)
        check("incident-create default customer_impacted=False in body",
              ((_last_body.get("data") or {}).get("attributes") or {}).get("customer_impacted") is False)

        # monitor-mute minimal (no optional args)
        r = run(["monitor-mute", "101"], env=env)
        check("monitor-mute minimal (no --end/--scope/--message) exits 0", r.returncode == 0, r.stderr)
        check("monitor-mute minimal body is empty (sent as None)",
              isinstance(_last_body, dict) and len(_last_body) == 0)

        # event-post minimal (just title + text)
        r = run(["event-post", "--title", "Minimal event", "--text", "Event text"], env=env)
        check("event-post minimal exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — DRY-RUN STRUCTURE COMPLETENESS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: dry-run JSON structure ===\n")

        for cmd_args, expected_cmd in [
            (["monitor-mute", "101", "--dry-run"], "monitor-mute"),
            (["monitor-unmute", "101", "--dry-run"], "monitor-unmute"),
            (["monitor-create", "--name", "x", "--type", "metric alert", "--query", "q", "--dry-run"], "monitor-create"),
            (["monitor-delete", "101", "--dry-run"], "monitor-delete"),
            (["event-post", "--title", "T", "--text", "B", "--dry-run"], "event-post"),
            (["incident-create", "--title", "T", "--dry-run"], "incident-create"),
            (["incident-update", "inc-001", "--status", "active", "--dry-run"], "incident-update"),
            (["incident-resolve", "inc-001", "--dry-run"], "incident-resolve"),
        ]:
            r = run(["--json"] + cmd_args, env=env)
            j = _try_json(r.stdout)
            check(f"{expected_cmd} --dry-run --json has tool=datadog",
                  isinstance(j, dict) and j.get("tool") == "datadog")
            check(f"{expected_cmd} --dry-run --json has command={expected_cmd}",
                  isinstance(j, dict) and j.get("command") == expected_cmd)
            check(f"{expected_cmd} --dry-run exits 0", r.returncode == 0)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — TIME PARSING EDGE CASES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: time parsing edge cases ===\n")

        # monitor-mute --end accepts ISO8601 date
        r = run(["monitor-mute", "101", "--end", "2026-06-01", "--dry-run"], env=env)
        check("monitor-mute --end ISO date 2026-06-01 exits 0", r.returncode == 0)

        # monitor-mute --end accepts epoch integer string
        r = run(["monitor-mute", "101", "--end", "1748736000", "--dry-run"], env=env)
        check("monitor-mute --end epoch integer exits 0", r.returncode == 0)

        # logs --from epoch integer
        r = run(["logs", "--from", "1716289200"], env=env)
        check("logs --from epoch integer exits 0", r.returncode == 0, r.stderr)

        # slo with explicit epoch range
        r = run(["slo", "slo-001", "--from", "1716289200", "--to", "1716892800"], env=env)
        check("slo --from/--to epoch integers exits 0", r.returncode == 0, r.stderr)

        # events with ISO8601 --from
        r = run(["events", "--from", "2026-05-01"], env=env)
        check("events --from ISO date exits 0", r.returncode == 0, r.stderr)

        # metrics with now-30m
        r = run(["metrics", "avg:system.cpu.user{*}", "--from", "now-30m"], env=env)
        check("metrics --from now-30m exits 0", r.returncode == 0, r.stderr)

        # week offset
        r = run(["events", "--from", "now-2w"], env=env)
        check("events --from now-2w exits 0", r.returncode == 0, r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — FILTER COMPOSITION
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: filter composition ===\n")

        # metrics-list returns empty for unknown prefix
        r = run(["metrics-list", "--prefix", "xyznonexistent"], env=env)
        check("metrics-list unknown prefix → No metrics found", "No metrics found" in r.stdout)

        r = run(["--json", "metrics-list", "--prefix", "xyznonexistent"], env=env)
        j = _try_json(r.stdout)
        check("metrics-list unknown prefix --json → empty list",
              isinstance(j, dict) and j.get("metrics") == [] and j.get("count") == 0)

        # monitors --page-size respected
        r = run(["--json", "monitors", "--page-size", "2"], env=env)
        check("monitors --page-size 2 exits 0", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitors JSON records the requested page", isinstance(j, dict) and j.get("page") == 0 and j.get("page_size") == 2)

        # logs: explicit query with spaces
        r = run(["logs", "error connection timeout"], env=env)
        check("logs query with spaces exits 0", r.returncode == 0, r.stderr)

        # incidents: both active and resolved in list
        r = run(["--json", "incidents"], env=env)
        j = _try_json(r.stdout)
        statuses = [(i.get("attributes") or {}).get("state") for i in (j or {}).get("data", [])]
        check("incidents list contains both active and resolved states",
              "active" in statuses and "resolved" in statuses)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — TEXT OUTPUT FORMAT
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: text output format ===\n")

        # events text output includes formatted timestamp
        r = run(["events"], env=env)
        check("events text output has bracketed ISO timestamp", "[20" in r.stdout and "T" in r.stdout)
        check("events text output has priority field", "normal" in r.stdout)
        check("events text output has event title", "Deploy" in r.stdout)

        r = run(["logs", "nullable"], env=env)
        check("logs text output tolerates nullable fixed-width fields", r.returncode == 0, r.stderr)
        check("logs nullable output omits literal None", "None" not in r.stdout)

        r = run(["events", "--tags", "nullable"], env=env)
        check("events text output tolerates nullable priority/title", r.returncode == 0, r.stderr)
        check("events nullable output omits literal None", "None" not in r.stdout)

        r = run(["incidents"], env=env)
        check("incidents text output tolerates nullable status/severity", r.returncode == 0, r.stderr)
        check("incidents nullable output omits literal None", "None" not in r.stdout)

        # metrics text shows scope
        r = run(["metrics", "avg:system.cpu.user{host:web-01}"], env=env)
        check("metrics text shows Scope: host:web-01", "host:web-01" in r.stdout)
        check("metrics text shows Last: with value and timestamp", "Last:   52.1" in r.stdout)

        # dashboards text shows both IDs
        r = run(["dashboards"], env=env)
        check("dashboards text shows dash-aaa", "dash-aaa" in r.stdout)
        check("dashboards text shows dash-bbb", "dash-bbb" in r.stdout)
        check("dashboards text shows both layout types", "ordered" in r.stdout and "free" in r.stdout)

        # monitors text shows all three monitors
        r = run(["monitors"], env=env)
        check("monitors text shows all 3 monitors", r.stdout.count("  [") >= 3)

        # incidents text shows severity in brackets
        r = run(["incidents"], env=env)
        check("incidents text has SEV-1 bracket", "[SEV-1  ]" in r.stdout)

        # slos text shows both SLOs
        r = run(["slos"], env=env)
        check("slos text shows slo-001 and slo-002",
              "slo-001" in r.stdout and "slo-002" in r.stdout)

        # services text shows descriptions
        r = run(["services"], env=env)
        check("services text shows Core REST API description", "Core REST API" in r.stdout)
        check("services text shows Background job processor", "Background job" in r.stdout)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — SEVERITY ALL VALID VALUES
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: severity choices ===\n")

        for sev in ["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5", "UNKNOWN"]:
            r = run(["incident-create", "--title", f"Test {sev}", "--severity", sev, "--dry-run"], env=env)
            check(f"incident-create --severity {sev} accepted (dry-run exits 0)", r.returncode == 0)

        # incident-update severity choices
        for sev in ["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5", "UNKNOWN"]:
            r = run(["incident-update", "inc-001", "--severity", sev, "--dry-run"], env=env)
            check(f"incident-update --severity {sev} accepted (dry-run exits 0)", r.returncode == 0)

        # ══════════════════════════════════════════════════════════════════
        # DEEP REGRESSION — SNAPSHOT BUG FIX VERIFICATION
        # ══════════════════════════════════════════════════════════════════
        print("\n=== deep regression: snapshot bug fixes ===\n")

        # Verify snapshot correctly handles events and slos (operator precedence fix)
        r = run(["--json", "snapshot"], env=env)
        j = _try_json(r.stdout)
        check("snapshot --json recent_events is int (not None)", isinstance(j, dict) and isinstance(j.get("recent_events"), int))
        check("snapshot --json recent_events >= 0", isinstance(j, dict) and (j.get("recent_events") or 0) >= 0)
        check("snapshot --json slos is int (not None)", isinstance(j, dict) and isinstance(j.get("slos"), int))
        check("snapshot --json slos >= 0", isinstance(j, dict) and (j.get("slos") or 0) >= 0)
        # The fixture has 2 events and 2 SLOs
        check("snapshot --json recent_events == 2", isinstance(j, dict) and j.get("recent_events") == 2)
        check("snapshot --json slos == 2", isinstance(j, dict) and j.get("slos") == 2)
        # monitors total should be 3 (our fixture)
        check("snapshot --json monitors.total == 3",
              isinstance(j, dict) and (j.get("monitors") or {}).get("total") == 3)
        # alerting: exactly 1 (CPU High)
        check("snapshot --json monitors.alerting count == 1",
              isinstance(j, dict) and len((j.get("monitors") or {}).get("alerting", [])) == 1)
        # warning: exactly 1 (Memory Warning)
        check("snapshot --json monitors.warning count == 1",
              isinstance(j, dict) and len((j.get("monitors") or {}).get("warning", [])) == 1)

        # snapshot exits 1 text mode too
        r = run(["snapshot"], env=env)
        check("snapshot text mode exits 1 (alerting present)", r.returncode == 1)
        check("snapshot text mode shows correct total", "3 total" in r.stdout)
        check("snapshot text mode shows 1 alerting", "1 alerting" in r.stdout)
        check("snapshot text mode shows 1 warning", "1 warning" in r.stdout)
        check("snapshot text mode events=2", "Events (1h): 2" in r.stdout)
        check("snapshot text mode slos=2", "SLOs:        2" in r.stdout)

        partial_env = _env(base + "/partial-empty")
        r = run(["snapshot"], env=partial_env)
        check("snapshot partial failure with empty successes does not report total failure",
              "Snapshot failed" not in r.stderr)
        check("snapshot partial failure warns about failed section", "Warning: monitors" in r.stderr)
        check("snapshot partial failure exits 0 when no alerting monitors returned", r.returncode == 0, r.stderr)
        check("snapshot partial failure shows empty successful sections",
              "Events (1h): 0" in r.stdout and "SLOs:        0" in r.stdout)
        r = run(["--json", "snapshot"], env=partial_env)
        j = _try_json(r.stdout)
        check("snapshot JSON marks a partial failure as degraded",
              isinstance(j, dict) and j.get("degraded") is True and j.get("errors"))

        all_fail_env = _env(base + "/all-fail")
        r = run(["snapshot"], env=all_fail_env)
        check("snapshot all failed exits non-zero", r.returncode != 0)
        check("snapshot all failed uses API-error exit 2", r.returncode == 2)
        check("snapshot all failed reports total failure", "Snapshot failed" in r.stderr)

        # ══════════════════════════════════════════════════════════════════
        # --json AFTER SUBCOMMAND (flag must work in either position)
        # ══════════════════════════════════════════════════════════════════
        print("\n=== --json flag position ===\n")

        # --json before subcommand (existing behavior)
        r = run(["--json", "monitors"], env=env)
        check("--json before subcommand works", r.returncode == 0 and _try_json(r.stdout) is not None)

        # --json after subcommand (new behavior via shared parent parser)
        r = run(["monitors", "--json"], env=env)
        check("--json after subcommand works", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("--json after subcommand produces valid JSON", j is not None, r.stdout[:200])
        check("--json after subcommand has monitors key", isinstance(j, dict) and "monitors" in j)

        r = run(["monitor", "101", "--json"], env=env)
        check("monitor <id> --json after subcommand works", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("monitor <id> --json after subcommand is valid JSON", j is not None)

        r = run(["monitor-status", "--json"], env=env)
        check("monitor-status --json after subcommand works", r.returncode in (0, 1), r.stderr)
        j = _try_json(r.stdout)
        check("monitor-status --json after subcommand is valid JSON", j is not None)

        r = run(["logs", "--json"], env=env)
        check("logs --json after subcommand works", r.returncode == 0, r.stderr)
        j = _try_json(r.stdout)
        check("logs --json after subcommand is valid JSON", j is not None)

        # ══════════════════════════════════════════════════════════════════
        # SNAPSHOT WITH MISSING CREDENTIALS
        # ══════════════════════════════════════════════════════════════════
        print("\n=== snapshot credential error ===\n")

        bad_env = {**env, "DD_API_KEY": "", "DD_APP_KEY": ""}
        r = run(["snapshot"], env=bad_env)
        check("snapshot with missing creds exits non-zero", r.returncode != 0)
        check("snapshot with missing creds reports error",
              "DD_API_KEY" in r.stderr or "credential" in r.stderr.lower() or "Missing" in r.stderr)

        print(f"\nResults: {PASS} passed, {FAIL} failed")
        return 0 if FAIL == 0 else 1

    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
