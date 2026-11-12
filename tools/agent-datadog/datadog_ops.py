#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

_DEFAULT_SITE = "datadoghq.com"


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_time(value: str) -> int:
    v = value.strip().lower()
    if v == "now":
        return _now_epoch()
    if v.startswith("now-") or v.startswith("now+"):
        sign = -1 if v[3] == "-" else 1
        tail = v[4:]
        try:
            if tail.endswith("h"):
                return _now_epoch() + sign * int(tail[:-1]) * 3600
            if tail.endswith("d"):
                return _now_epoch() + sign * int(tail[:-1]) * 86400
            if tail.endswith("m"):
                return _now_epoch() + sign * int(tail[:-1]) * 60
            if tail.endswith("w"):
                return _now_epoch() + sign * int(tail[:-1]) * 604800
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dt%H:%M:%Sz", "%Y-%m-%dt%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(v, fmt).replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            pass
    try:
        return int(v)
    except ValueError:
        _err(f"Cannot parse time: {value!r}. Use 'now', 'now+1h', 'now-1h', ISO8601, or epoch integer.")
    return _now_epoch()  # unreachable — _err exits


def _epoch_to_iso(epoch: int | float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dd_base() -> str:
    override = os.environ.get("DD_API_BASE_URL", "").strip()
    if override:
        return override.rstrip("/")
    site = os.environ.get("DD_SITE", _DEFAULT_SITE).strip() or _DEFAULT_SITE
    return f"https://api.{site}"


def _require_keys() -> tuple[str, str]:
    api_key = os.environ.get("DD_API_KEY", "").strip()
    app_key = os.environ.get("DD_APP_KEY", "").strip()
    missing = []
    if not api_key:
        missing.append("DD_API_KEY")
    if not app_key:
        missing.append("DD_APP_KEY")
    if missing:
        _err(f"Missing credentials: {', '.join(missing)}. Set these environment variables.")
    return api_key, app_key


def _err(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def _request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    api_version: str = "v1",
    timeout: int = 30,
) -> Any:
    api_key, app_key = _require_keys()
    base = _dd_base()
    url = f"{base}/api/{api_version}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v is not None}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered)

    data: bytes | None = None
    headers: dict[str, str] = {
        "DD-API-KEY": api_key,
        "DD-APPLICATION-KEY": app_key,
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
            detail = err_data.get("errors") or err_data.get("error") or err_data.get("message") or raw
            if isinstance(detail, list):
                detail = "; ".join(str(x) for x in detail)
        except (json.JSONDecodeError, AttributeError):
            detail = raw or str(exc)
        _err(f"Datadog API {exc.code}: {detail}", code=2)
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower():
            _err(f"Datadog API request timed out after {timeout}s", code=2)
        _err(f"Datadog API request failed: {reason}", code=2)


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _text(value: Any, default: str = "") -> str:
    return default if value is None else str(value)


def _incident_dropdown(value: str) -> dict[str, str]:
    """Build the OpenAPI IncidentFieldAttributesSingleValue representation."""
    return {"type": "dropdown", "value": value}


def _incident_field_value(attrs: dict[str, Any], name: str) -> str:
    field = (attrs.get("fields") or {}).get(name) or {}
    if isinstance(field, dict) and field.get("value") is not None:
        return _text(field["value"])
    # Older response payloads exposed severity directly.  This fallback keeps
    # existing incidents readable while writes always use the current schema.
    return _text(attrs.get(name))


def _dry_run(args: argparse.Namespace, command: str, human_msg: str, **extra: Any) -> int:
    preview: dict[str, Any] = {"tool": "datadog", "command": command, "dry_run": True, **extra}
    if args.json:
        _print_json(preview)
    else:
        print(f"[dry-run] {human_msg}")
    return 0


# ── monitors ──────────────────────────────────────────────────────────────────

def cmd_monitors(args: argparse.Namespace) -> int:
    # Datadog's v1 monitor pagination needs both page and page_size.  Sending
    # only page_size has no useful paging semantics on this endpoint.
    params: dict[str, Any] = {"page": args.page, "page_size": args.page_size}
    if args.tag:
        params["monitor_tags"] = args.tag
    if args.name:
        params["name"] = args.name
    data = _request("GET", "/monitor", params=params)
    monitors = data if isinstance(data, list) else []
    # The v1 endpoint does not accept a monitor state query parameter.  Filter
    # the complete response locally instead of claiming that the server did it.
    if args.state:
        monitors = [m for m in monitors if (m.get("overall_state") or "").lower() == args.state.lower()]

    if args.json:
        _print_json({"monitors": monitors, "count": len(monitors), "page": args.page, "page_size": args.page_size})
        return 0

    if not monitors:
        print("No monitors found")
        return 0

    for m in monitors:
        state = (m.get("overall_state") or "unknown").upper()
        print(f"{m.get('id', '')}  [{state:<8}]  {m.get('name', '')}")
        if m.get("tags"):
            print(f"  tags: {', '.join(m['tags'])}")
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    data = _request("GET", f"/monitor/{urllib.parse.quote(str(args.id))}")
    if args.json:
        _print_json(data)
        return 0
    print(f"ID:     {data.get('id')}")
    print(f"Name:   {data.get('name')}")
    print(f"Type:   {data.get('type')}")
    print(f"State:  {data.get('overall_state')}")
    print(f"Query:  {data.get('query')}")
    if data.get("message"):
        print(f"Msg:    {str(data.get('message'))[:200]}")
    if data.get("tags"):
        print(f"Tags:   {', '.join(data['tags'])}")
    return 0


def cmd_monitor_status(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.tag:
        params["monitor_tags"] = args.tag

    data = _request("GET", "/monitor", params=params or None)
    monitors = data if isinstance(data, list) else []

    by_state: dict[str, list[dict[str, Any]]] = {}
    for m in monitors:
        state = (m.get("overall_state") or "unknown").upper()
        by_state.setdefault(state, []).append(m)

    if args.json:
        _print_json({
            "total": len(monitors),
            "by_state": {
                k: [{"id": m.get("id"), "name": m.get("name")} for m in v]
                for k, v in by_state.items()
            },
        })
        return 0 if "ALERT" not in by_state else 1

    print(f"Total monitors: {len(monitors)}")
    for state in ("ALERT", "WARN", "NO DATA", "OK", "UNKNOWN"):
        if state in by_state:
            print(f"\n{state} ({len(by_state[state])}):")
            for m in by_state[state][:10]:
                print(f"  {m.get('id')}  {m.get('name')}")

    return 1 if "ALERT" in by_state else 0


def cmd_monitor_mute(args: argparse.Namespace) -> int:
    if args.dry_run:
        extra: dict[str, Any] = {"monitor_id": args.id}
        if args.end:
            extra["end"] = args.end
        if args.scope:
            extra["scope"] = args.scope
        if args.message:
            extra["message"] = args.message
        return _dry_run(args, "monitor-mute", f"Would mute monitor {args.id}", **extra)

    body: dict[str, Any] = {}
    if args.end:
        body["end"] = _parse_time(args.end)
    if args.scope:
        body["scope"] = [args.scope]
    if args.message:
        body["message"] = args.message

    data = _request("POST", f"/monitor/{urllib.parse.quote(str(args.id))}/mute", body=body or None)
    if args.json:
        _print_json(data)
        return 0
    print(f"Muted monitor {data.get('id')} [{data.get('name')}]")
    return 0


def cmd_monitor_unmute(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _dry_run(args, "monitor-unmute", f"Would unmute monitor {args.id}", monitor_id=args.id)

    data = _request("POST", f"/monitor/{urllib.parse.quote(str(args.id))}/unmute")
    if args.json:
        _print_json(data)
        return 0
    print(f"Unmuted monitor {data.get('id')} [{data.get('name')}]")
    return 0


def cmd_monitor_create(args: argparse.Namespace) -> int:
    body: dict[str, Any] = {
        "type": args.monitor_type,
        "name": args.name,
        "query": args.query,
    }
    if args.message:
        body["message"] = args.message
    if args.tags:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.priority is not None:
        body["priority"] = args.priority

    if args.dry_run:
        return _dry_run(
            args,
            "monitor-create",
            f"Would create monitor: {args.name}\n  type:  {args.monitor_type}\n  query: {args.query}",
            body=body,
        )

    data = _request("POST", "/monitor", body=body)
    if args.json:
        _print_json(data)
        return 0
    print(f"Created monitor {data.get('id')}: {data.get('name')}")
    return 0


def cmd_monitor_delete(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _dry_run(args, "monitor-delete", f"Would delete monitor {args.id}", monitor_id=args.id)

    _request("DELETE", f"/monitor/{urllib.parse.quote(str(args.id))}")
    if args.json:
        _print_json({"deleted": True, "monitor_id": args.id})
        return 0
    print(f"Deleted monitor {args.id}")
    return 0


# ── logs ──────────────────────────────────────────────────────────────────────

def cmd_logs(args: argparse.Namespace) -> int:
    query = args.query or "*"
    if args.service:
        query = f"service:{args.service} {query}".strip()
    if args.status:
        query = f"status:{args.status} {query}".strip()

    from_epoch = _parse_time(args.from_time)
    to_epoch = _parse_time(args.to_time)

    body: dict[str, Any] = {
        "filter": {
            "query": query,
            "from": _epoch_to_iso(from_epoch),
            "to": _epoch_to_iso(to_epoch),
        },
        "page": {"limit": args.limit},
        "sort": "-timestamp",
    }
    if args.cursor:
        body["page"]["cursor"] = args.cursor

    data = _request("POST", "/logs/events/search", body=body, api_version="v2")
    logs = (data.get("data") or []) if isinstance(data, dict) else []

    if args.json:
        _print_json({"logs": logs, "count": len(logs), "meta": data.get("meta") if isinstance(data, dict) else None})
        return 0

    if not logs:
        print("No logs found")
        return 0

    for entry in logs:
        attrs = entry.get("attributes") or {}
        ts = _text(attrs.get("timestamp"))
        svc = _text(attrs.get("service"))
        status = _text(attrs.get("status"))
        msg = _text(attrs.get("message"))
        print(f"[{ts}] [{status:<5}] {svc}: {msg[:200]}")
    return 0


# ── metrics ───────────────────────────────────────────────────────────────────

def cmd_metrics(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {
        "query": args.metric,
        "from": _parse_time(args.from_time),
        "to": _parse_time(args.to_time),
    }
    data = _request("GET", "/query", params=params)
    series = data.get("series") or []

    if args.json:
        _print_json(data)
        return 0

    if not series:
        print("No data returned for metric")
        return 0

    for s in series:
        print(f"Metric: {s.get('metric')}")
        print(f"Scope:  {s.get('scope')}")
        points = s.get("pointlist") or []
        print(f"Points: {len(points)}")
        if points:
            last = points[-1]
            ts_iso = _epoch_to_iso(last[0] / 1000) if last[0] > 1e12 else _epoch_to_iso(last[0])
            print(f"Last:   {last[1]} at {ts_iso}")
    return 0


def cmd_metrics_list(args: argparse.Namespace) -> int:
    data = _request("GET", "/metrics", api_version="v2")
    metrics_data = data.get("data") or []
    names = [m.get("id") for m in metrics_data if m.get("id")]
    # /api/v2/metrics has no prefix filter.  Keep the user-facing option, but
    # make it an explicit local filter rather than sending an ignored parameter.
    if args.prefix:
        names = [name for name in names if name.startswith(args.prefix)]

    if args.json:
        _print_json({"metrics": names, "count": len(names)})
        return 0

    if not names:
        print("No metrics found")
        return 0

    for name in names:
        print(name)
    return 0


# ── events ────────────────────────────────────────────────────────────────────

def cmd_events(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {
        "start": _parse_time(args.from_time),
        "end": _parse_time(args.to_time) if args.to_time else _now_epoch(),
    }
    if args.priority:
        params["priority"] = args.priority
    if args.tags:
        params["tags"] = args.tags

    data = _request("GET", "/events", params=params)
    events = data.get("events") or []

    if args.json:
        _print_json({"events": events, "count": len(events)})
        return 0

    if not events:
        print("No events found")
        return 0

    for ev in events:
        ts = _epoch_to_iso(ev.get("date_happened", 0))
        priority = _text(ev.get("priority"))
        title = _text(ev.get("title"))
        print(f"[{ts}] [{priority:<6}] {title}")
        if ev.get("text"):
            print(f"  {str(ev['text'])[:200]}")
    return 0


def cmd_event_post(args: argparse.Namespace) -> int:
    body: dict[str, Any] = {"title": args.title, "text": args.text}
    if args.priority:
        body["priority"] = args.priority
    if args.tags:
        body["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
    if args.alert_type:
        body["alert_type"] = args.alert_type

    if args.dry_run:
        return _dry_run(args, "event-post", f"Would post event: {args.title}", body=body)

    data = _request("POST", "/events", body=body)
    event = data.get("event") or data
    if args.json:
        _print_json(event)
        return 0
    print(f"Posted event {event.get('id')}: {event.get('title')}")
    return 0


# ── incidents ─────────────────────────────────────────────────────────────────

def cmd_incidents(args: argparse.Namespace) -> int:
    # The endpoint defaults to ten records.  Request the documented maximum,
    # but expose the offset so a page never masquerades as a complete list.
    data = _request("GET", "/incidents", params={
        "page[size]": args.page_size,
        "page[offset]": args.offset,
    }, api_version="v2")
    incidents = data.get("data") or []
    # Listing incidents does not accept filter[state].  Apply this supported
    # CLI filter to the returned page, rather than sending a silent no-op.
    if args.state:
        incidents = [inc for inc in incidents if ((inc.get("attributes") or {}).get("state") or "").lower() == args.state]

    if args.json:
        _print_json({
            **data,
            "data": incidents,
            "page_size": args.page_size,
            "offset": args.offset,
            "has_more": len(incidents) >= args.page_size,
        })
        return 0

    if not incidents:
        print("No incidents found")
        return 0

    for inc in incidents:
        attrs = inc.get("attributes") or {}
        status = _text(attrs.get("state"))
        severity = _incident_field_value(attrs, "severity")
        title = _text(attrs.get("title"))
        print(f"{inc.get('id', '')}  [{status:<8}] [{severity:<7}]  {title}")
    if len(incidents) >= args.page_size:
        print(f"Showing up to {args.page_size} incidents from offset {args.offset}; more may be available.")
    return 0


def cmd_incident_get(args: argparse.Namespace) -> int:
    data = _request("GET", f"/incidents/{urllib.parse.quote(str(args.id))}", api_version="v2")
    if args.json:
        _print_json(data)
        return 0
    inc = data.get("data") or {}
    attrs = inc.get("attributes") or {}
    print(f"ID:       {inc.get('id')}")
    print(f"Title:    {attrs.get('title')}")
    print(f"Status:   {attrs.get('state')}")
    print(f"Severity: {_incident_field_value(attrs, 'severity')}")
    print(f"Created:  {attrs.get('created')}")
    if attrs.get("customer_impact_scope"):
        print(f"Impact:   {attrs['customer_impact_scope']}")
    return 0


def cmd_incident_create(args: argparse.Namespace) -> int:
    attrs: dict[str, Any] = {
        "title": args.title,
        "customer_impacted": args.customer_impacted,
    }
    if args.severity:
        attrs["fields"] = {"severity": _incident_dropdown(args.severity)}

    body: dict[str, Any] = {"data": {"type": "incidents", "attributes": attrs}}

    if args.dry_run:
        return _dry_run(args, "incident-create", f"Would create incident: {args.title}", attributes=attrs)

    data = _request("POST", "/incidents", body=body, api_version="v2")
    inc = data.get("data") or {}
    iattrs = inc.get("attributes") or {}
    if args.json:
        _print_json(data)
        return 0
    print(f"Created incident {inc.get('id')}: {iattrs.get('title')}")
    print(f"Status: {iattrs.get('state')}")
    return 0


def cmd_incident_update(args: argparse.Namespace) -> int:
    attrs: dict[str, Any] = {}
    if args.title:
        attrs["title"] = args.title
    fields: dict[str, Any] = {}
    if args.status:
        fields["state"] = _incident_dropdown(args.status)
    if args.severity:
        fields["severity"] = _incident_dropdown(args.severity)
    if fields:
        attrs["fields"] = fields

    if not attrs:
        _err("At least one of --title, --status, --severity is required")

    body: dict[str, Any] = {"data": {"type": "incidents", "id": args.id, "attributes": attrs}}

    if args.dry_run:
        return _dry_run(
            args,
            "incident-update",
            f"Would update incident {args.id}",
            incident_id=args.id,
            attributes=attrs,
        )

    data = _request("PATCH", f"/incidents/{urllib.parse.quote(str(args.id))}", body=body, api_version="v2")
    if args.json:
        _print_json(data)
        return 0
    inc = data.get("data") or {}
    iattrs = inc.get("attributes") or {}
    print(f"Updated incident {inc.get('id')}: {iattrs.get('title')}")
    return 0


def cmd_incident_resolve(args: argparse.Namespace) -> int:
    body: dict[str, Any] = {
        "data": {"type": "incidents", "id": args.id, "attributes": {
            "fields": {"state": _incident_dropdown("resolved")},
        }}
    }

    if args.dry_run:
        return _dry_run(args, "incident-resolve", f"Would resolve incident {args.id}", incident_id=args.id)

    data = _request("PATCH", f"/incidents/{urllib.parse.quote(str(args.id))}", body=body, api_version="v2")
    if args.json:
        _print_json(data)
        return 0
    inc = data.get("data") or {}
    state = ((inc.get("attributes") or {}).get("state") or "").lower()
    if state != "resolved":
        _err(f"Datadog returned incident {args.id} without a resolved state")
    print(f"Resolved incident {inc.get('id', args.id)}")
    return 0


# ── dashboards ────────────────────────────────────────────────────────────────

def cmd_dashboards(args: argparse.Namespace) -> int:
    data = _request("GET", "/dashboard")
    dashboards = data.get("dashboards") or []

    if args.json:
        _print_json({"dashboards": dashboards, "count": len(dashboards)})
        return 0

    if not dashboards:
        print("No dashboards found")
        return 0

    for d in dashboards:
        print(f"{d.get('id', '')}  {d.get('title', '')}  [{d.get('layout_type', '')}]")
    return 0


def cmd_dashboard_get(args: argparse.Namespace) -> int:
    data = _request("GET", f"/dashboard/{urllib.parse.quote(str(args.id))}")
    if args.json:
        _print_json(data)
        return 0
    print(f"ID:      {data.get('id')}")
    print(f"Title:   {data.get('title')}")
    print(f"Layout:  {data.get('layout_type')}")
    if data.get("url"):
        print(f"URL:     {data.get('url')}")
    widgets = data.get("widgets") or []
    print(f"Widgets: {len(widgets)}")
    return 0


# ── SLOs ──────────────────────────────────────────────────────────────────────

def cmd_slos(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.tags:
        params["tags"] = args.tags

    data = _request("GET", "/slo", params=params or None)
    slos = data.get("data") or []

    if args.json:
        _print_json({"slos": slos, "count": len(slos)})
        return 0

    if not slos:
        print("No SLOs found")
        return 0

    for s in slos:
        print(f"{s.get('id', '')}  {s.get('name', '')}  [{s.get('type', '')}]")
    return 0


def cmd_slo_status(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {
        "from_ts": _parse_time(args.from_time) if args.from_time else _now_epoch() - 86400 * 30,
        "to_ts": _parse_time(args.to_time) if args.to_time else _now_epoch(),
    }

    data = _request("GET", f"/slo/{urllib.parse.quote(str(args.id))}/history", params=params)
    history = data.get("data") or {}

    if args.json:
        _print_json(data)
        return 0

    print(f"SLO: {history.get('name', args.id)}")
    overall = history.get("overall") or {}
    print(f"SLI:        {overall.get('sli_value', 'N/A')}")
    print(f"Target:     {overall.get('target', 'N/A')}")
    print(f"Timeframe:  {overall.get('timeframe', 'N/A')}")
    budget = overall.get("error_budget_remaining")
    if budget is not None:
        print(f"Error budget remaining: {budget}%")
    return 0


# ── services ──────────────────────────────────────────────────────────────────

def cmd_services(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {"page[size]": args.page_size, "page[number]": args.page}

    data = _request("GET", "/services/definitions", params=params, api_version="v2")
    services = data.get("data") or []
    pagination = (data.get("meta") or {}).get("pagination") or {}
    total = pagination.get("total")
    has_next = bool(pagination.get("next"))
    truncated = has_next or (total is None and len(services) >= args.page_size)
    if total is not None:
        truncated = truncated or args.page * args.page_size < total

    if args.json:
        _print_json({
            "services": services,
            "count": len(services),
            "page": args.page,
            "page_size": args.page_size,
            "total": total,
            "has_next_page": has_next,
            "truncated": truncated,
        })
        return 0

    if not services:
        print("No services found")
        return 0

    for s in services:
        attrs = s.get("attributes") or {}
        schema = attrs.get("schema") or {}
        name = schema.get("dd-service") or s.get("id") or ""
        team = schema.get("team") or ""
        desc = str(schema.get("description") or "")[:80]
        print(f"{name}  [{team}]  {desc}")
    if truncated:
        print(f"Showing page {args.page} ({len(services)} returned); more results are available.")
    return 0


# ── snapshot ──────────────────────────────────────────────────────────────────

def cmd_snapshot(args: argparse.Namespace) -> int:
    monitors: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    slos: list[dict[str, Any]] = []
    errors: list[str] = []
    fetch_count = 0

    def _fetch(label: str, fn: Any) -> Any:
        nonlocal fetch_count
        fetch_count += 1
        try:
            return fn()
        except SystemExit as exc:
            errors.append(f"{label}: exit({exc.code})")
            return None

    result = _fetch("monitors", lambda: _request("GET", "/monitor", params={"page_size": 100}))
    if result is not None:
        monitors = result if isinstance(result, list) else []

    result = _fetch("events", lambda: _request("GET", "/events",
                    params={"start": _now_epoch() - 3600, "end": _now_epoch()}))
    if result is not None:
        events = (result.get("events") or []) if isinstance(result, dict) else []

    result = _fetch("slos", lambda: _request("GET", "/slo"))
    if result is not None:
        slos = (result.get("data") or []) if isinstance(result, dict) else []

    if len(errors) == fetch_count:
        # All sections failed — surface the error rather than showing empty data
        _err(f"Snapshot failed — all API requests errored. Check DD_API_KEY / DD_APP_KEY. "
             f"Sections: {'; '.join(errors)}", code=2)

    if errors:
        for e in errors:
            print(f"Warning: {e}", file=sys.stderr)

    alerting = [m for m in monitors if (m.get("overall_state") or "").upper() == "ALERT"]
    warning = [m for m in monitors if (m.get("overall_state") or "").upper() == "WARN"]

    payload: dict[str, Any] = {
        "tool": "datadog",
        "timestamp": _now_iso(),
        "monitors": {
            "total": len(monitors),
            "alerting": [{"id": m.get("id"), "name": m.get("name")} for m in alerting],
            "warning": [{"id": m.get("id"), "name": m.get("name")} for m in warning],
        },
        "recent_events": len(events),
        "slos": len(slos),
        "degraded": bool(errors),
        "errors": errors,
    }

    if args.json:
        _print_json(payload)
        return 0 if not alerting else 1

    print(f"Monitors:    {len(monitors)} total, {len(alerting)} alerting, {len(warning)} warning")
    for m in alerting:
        print(f"  ALERT  {m.get('id')}  {m.get('name')}")
    for m in warning:
        print(f"  WARN   {m.get('id')}  {m.get('name')}")
    print(f"Events (1h): {len(events)}")
    print(f"SLOs:        {len(slos)}")

    return 1 if alerting else 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    # Shared parent so --json can appear before OR after the subcommand.
    # SUPPRESS default prevents subparser from resetting root parser's args.json=True.
    _common = argparse.ArgumentParser(add_help=False)
    _common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                         help="Output JSON")

    parser = argparse.ArgumentParser(
        prog="agent-datadog",
        description="Datadog observability: monitors, logs, metrics, incidents, dashboards, SLOs",
        epilog=(
            "Exit codes: write-command --dry-run previews exit 0 without sending HTTP; "
            "monitor-status and snapshot exit 1 when monitors are alerting; API errors exit 2."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    def _sub(name: str, **kw: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[_common], **kw)

    # monitors
    p = _sub("monitors", help="List monitors")
    p.add_argument("--tag", help="Filter by tag (e.g. env:prod)")
    p.add_argument("--name", help="Filter by name substring")
    p.add_argument("--state", help="Filter by state: Alert, Warn, OK, No Data")
    p.add_argument("--page", type=int, default=0, help="Page number (default: 0)")
    p.add_argument("--page-size", dest="page_size", type=int, default=100)

    # monitor
    p = _sub("monitor", help="Get one monitor by ID")
    p.add_argument("id", type=int)

    # monitor-status
    p = _sub("monitor-status", help="Alert state summary across all monitors")
    p.add_argument("--tag", help="Filter by tag")

    # monitor-mute
    p = _sub("monitor-mute", help="Mute a monitor")
    p.add_argument("id", type=int)
    p.add_argument("--end", help="Mute until (now+1h, ISO8601, or epoch integer)")
    p.add_argument("--scope", help="Scope to mute (e.g. host:web-01)")
    p.add_argument("--message", help="Mute reason")
    p.add_argument("--dry-run", action="store_true")

    # monitor-unmute
    p = _sub("monitor-unmute", help="Unmute a monitor")
    p.add_argument("id", type=int)
    p.add_argument("--dry-run", action="store_true")

    # monitor-create
    p = _sub("monitor-create", help="Create a monitor")
    p.add_argument("--name", required=True)
    p.add_argument("--type", dest="monitor_type", required=True,
                   help="Monitor type (e.g. 'metric alert', 'log alert')")
    p.add_argument("--query", required=True, help="Monitor query")
    p.add_argument("--message", help="Alert notification message")
    p.add_argument("--tags", help="Comma-separated tags to attach")
    p.add_argument("--priority", type=int, choices=[1, 2, 3, 4, 5], help="Priority 1 (highest) to 5")
    p.add_argument("--dry-run", action="store_true")

    # monitor-delete
    p = _sub("monitor-delete", help="Delete a monitor")
    p.add_argument("id", type=int)
    p.add_argument("--dry-run", action="store_true")

    # logs
    p = _sub("logs", help="Search logs")
    p.add_argument("query", nargs="?", default="*", help="Log query (default: *)")
    p.add_argument("--from", dest="from_time", default="now-1h", help="From time (default: now-1h)")
    p.add_argument("--to", dest="to_time", default="now", help="To time (default: now)")
    p.add_argument("--service", help="Filter by service name")
    p.add_argument("--status", choices=["error", "warn", "info", "debug"], help="Filter by log status")
    p.add_argument("--limit", type=int, default=25, help="Max log entries returned (default: 25)")
    p.add_argument("--cursor", help="Pagination cursor from previous result")

    # metrics
    p = _sub("metrics", help="Query metric timeseries")
    p.add_argument("metric", help="Metric query (e.g. avg:system.cpu.user{*})")
    p.add_argument("--from", dest="from_time", default="now-1h", help="From time (default: now-1h)")
    p.add_argument("--to", dest="to_time", default="now", help="To time (default: now)")

    # metrics-list
    p = _sub("metrics-list", help="List available metrics")
    p.add_argument("--prefix", help="Filter metrics by name prefix")

    # events
    p = _sub("events", help="List events")
    p.add_argument("--from", dest="from_time", default="now-1h", help="From time (default: now-1h)")
    p.add_argument("--to", dest="to_time", default=None, help="To time (default: now)")
    p.add_argument("--priority", choices=["normal", "low"], help="Filter by priority")
    p.add_argument("--tags", help="Filter by comma-separated tags")

    # event-post
    p = _sub("event-post", help="Post a Datadog event")
    p.add_argument("--title", required=True, help="Event title")
    p.add_argument("--text", required=True, help="Event body text")
    p.add_argument("--priority", choices=["normal", "low"], default="normal")
    p.add_argument("--tags", help="Comma-separated tags")
    p.add_argument("--alert-type", dest="alert_type",
                   choices=["error", "warning", "info", "success"], help="Alert type")
    p.add_argument("--dry-run", action="store_true")

    # incidents
    p = _sub("incidents", help="List incidents")
    p.add_argument("--state", choices=["active", "stable", "resolved"], help="Filter this page by state")
    p.add_argument("--offset", type=int, default=0, help="Result offset (default: 0)")
    p.add_argument("--page-size", dest="page_size", type=int, default=100, help="Results per page (default: 100)")

    # incident
    p = _sub("incident", help="Get one incident by ID")
    p.add_argument("id", help="Incident ID")

    # incident-create
    p = _sub("incident-create", help="Create an incident")
    p.add_argument("--title", required=True)
    p.add_argument("--severity", choices=["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5", "UNKNOWN"])
    p.add_argument("--customer-impacted", dest="customer_impacted", action="store_true", default=False)
    p.add_argument("--dry-run", action="store_true")

    # incident-update
    p = _sub("incident-update", help="Update an incident")
    p.add_argument("id", help="Incident ID")
    p.add_argument("--title", help="New title")
    p.add_argument("--status", choices=["active", "stable", "resolved"])
    p.add_argument("--severity", choices=["SEV-1", "SEV-2", "SEV-3", "SEV-4", "SEV-5", "UNKNOWN"])
    p.add_argument("--dry-run", action="store_true")

    # incident-resolve
    p = _sub("incident-resolve", help="Resolve an incident")
    p.add_argument("id", help="Incident ID")
    p.add_argument("--dry-run", action="store_true")

    # dashboards
    _sub("dashboards", help="List all dashboards")

    # dashboard
    p = _sub("dashboard", help="Get one dashboard")
    p.add_argument("id", help="Dashboard ID")

    # slos
    p = _sub("slos", help="List SLOs")
    p.add_argument("--tags", help="Filter by tags")

    # slo
    p = _sub("slo", help="Get SLO history and error budget")
    p.add_argument("id", help="SLO ID")
    p.add_argument("--from", dest="from_time", default=None, help="From time (default: 30 days ago)")
    p.add_argument("--to", dest="to_time", default=None, help="To time (default: now)")

    # services
    p = _sub("services", help="List service catalog definitions")
    p.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    p.add_argument("--page-size", dest="page_size", type=int, default=100)

    # snapshot
    _sub("snapshot", help="Observability snapshot: monitors + events + SLOs")

    return parser


_DISPATCH = {
    "monitors": cmd_monitors,
    "monitor": cmd_monitor,
    "monitor-status": cmd_monitor_status,
    "monitor-mute": cmd_monitor_mute,
    "monitor-unmute": cmd_monitor_unmute,
    "monitor-create": cmd_monitor_create,
    "monitor-delete": cmd_monitor_delete,
    "logs": cmd_logs,
    "metrics": cmd_metrics,
    "metrics-list": cmd_metrics_list,
    "events": cmd_events,
    "event-post": cmd_event_post,
    "incidents": cmd_incidents,
    "incident": cmd_incident_get,
    "incident-create": cmd_incident_create,
    "incident-update": cmd_incident_update,
    "incident-resolve": cmd_incident_resolve,
    "dashboards": cmd_dashboards,
    "dashboard": cmd_dashboard_get,
    "slos": cmd_slos,
    "slo": cmd_slo_status,
    "services": cmd_services,
    "snapshot": cmd_snapshot,
}


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    handler = _DISPATCH.get(args.command)
    if not handler:
        _err(f"Unknown command: {args.command}")
    return handler(args)  # type: ignore[misc]


if __name__ == "__main__":
    raise SystemExit(main())
