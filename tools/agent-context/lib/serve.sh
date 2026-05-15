#!/usr/bin/env bash
# lib/serve.sh — Local read-only HTML dashboard for agent-context.

cmd_serve() {
    local host="127.0.0.1" port="8765" once=false
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --host) host="${2:-127.0.0.1}"; shift 2 ;;
            --port) port="${2:-8765}"; shift 2 ;;
            --once|--print-url) once=true; shift ;;
            --help|-h)
                cat <<'EOF'
Usage: agent-context serve [--host 127.0.0.1] [--port 8765]

Serve a read-only local HTML dashboard for context freshness, version currency,
source provenance, and package details.
EOF
                return 0
                ;;
            *) shift ;;
        esac
    done

    ensure_init
    if [[ "$once" == "true" ]]; then
        echo "http://${host}:${port}/"
        return 0
    fi

    python3 - "$CONTEXT_INDEX_DB" "$CONTEXT_HOME/config.yaml" "$CONTEXT_CACHE_DIR" "$host" "$port" <<'PY'
import html
import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


db_path, config_path, cache_dir, host, port_raw = sys.argv[1:6]
port = int(port_raw)


def q(value):
    return html.escape(str(value or ""), quote=True)


def rows():
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    result = conn.execute(
        """
        SELECT id, name, type, trust, source, cache_path, token_count,
               fetched_at, checked_at, expires_at, refresh_status, refresh_error,
               source_kind, content_format, version_package, doc_version,
               latest_version, version_status, version_checked_at, version_error
        FROM package_meta
        ORDER BY
          CASE COALESCE(version_status, 'unknown')
            WHEN 'behind_major' THEN 0
            WHEN 'behind_minor' THEN 1
            WHEN 'behind_patch' THEN 2
            WHEN 'registry_failed' THEN 3
            WHEN 'current' THEN 5
            ELSE 4
          END,
          name
        """
    ).fetchall()
    conn.close()
    return result


STYLE = """
body{margin:0;font:14px/1.45 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;color:#1f2933;background:#f7f8fa}
header{background:#172033;color:#fff;padding:22px 28px}
h1{margin:0 0 4px;font-size:24px}
main{padding:24px 28px;max-width:1280px;margin:0 auto}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}
.metric{background:#fff;border:1px solid #d8dee8;border-radius:6px;padding:12px}
.metric b{display:block;font-size:22px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #d8dee8;border-radius:6px;overflow:hidden}
th,td{padding:9px 10px;border-bottom:1px solid #e7ebf0;text-align:left;vertical-align:top}
th{background:#edf1f5;font-size:12px;text-transform:uppercase;color:#52606d}
tr:hover{background:#f9fbfd}
.pill{display:inline-block;border-radius:999px;padding:2px 8px;font-size:12px;background:#edf1f5}
.current,.floating_fresh,.fresh,.local{background:#dff6e6;color:#14532d}
.behind_major,.failed,.registry_failed{background:#ffe3e3;color:#8a1f1f}
.behind_minor,.behind_patch,.stale{background:#fff3bf;color:#6b4e00}
.unknown,.no_version{background:#e7ebf0;color:#52606d}
a{color:#1261a6;text-decoration:none}a:hover{text-decoration:underline}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
"""


def is_local_no_version(row):
    source_kind = row["source_kind"] or ""
    row_type = row["type"] or ""
    return source_kind.startswith("local") or row_type in {"skill", "local"}


def version_display(row):
    status = row["version_status"] or "unknown"
    if status == "unknown" and is_local_no_version(row):
        if (row["source_kind"] or "") == "local-skill" or (row["type"] or "") == "skill":
            return "no_version", "local skill - no versioning", "local content; no external package version"
        return "no_version", "local project - no versioning", "local content; no external package version"
    return (
        status,
        status,
        f"docs {row['doc_version'] or 'unknown'} / latest {row['latest_version'] or 'unknown'}",
    )


def dashboard():
    items = rows()
    counts = {}
    for row in items:
        version_class, _, _ = version_display(row)
        counts[version_class] = counts.get(version_class, 0) + 1
        counts[row["refresh_status"] or "unknown"] = counts.get(row["refresh_status"] or "unknown", 0) + 1
    metric_html = "".join(
        f"<div class='metric'><span>{q(label)}</span><b>{count}</b></div>"
        for label, count in [
            ("packages", len(items)),
            ("fresh", counts.get("fresh", 0)),
            ("stale/failed", counts.get("stale", 0) + counts.get("failed", 0)),
            ("current docs", counts.get("current", 0) + counts.get("floating_fresh", 0)),
            ("behind docs", counts.get("behind_major", 0) + counts.get("behind_minor", 0) + counts.get("behind_patch", 0)),
            ("not versioned", counts.get("no_version", 0)),
        ]
    )
    table = []
    for row in items:
        version_class, version_label, version_detail = version_display(row)
        refresh_status = row["refresh_status"] or "unknown"
        table.append(
            "<tr>"
            f"<td><a href='/package?id={q(row['id'])}'>{q(row['name'])}</a><br><code>{q(row['id'])}</code></td>"
            f"<td>{q(row['type'])}<br><span class='pill'>{q(row['source_kind'])}</span></td>"
            f"<td><span class='pill {q(refresh_status)}'>{q(refresh_status)}</span><br><small>{q(row['checked_at'])}</small></td>"
            f"<td><span class='pill {q(version_class)}'>{q(version_label)}</span><br><small>{q(version_detail)}</small></td>"
            f"<td>{q(row['version_package'] or '')}</td>"
            f"<td><a href='{q(row['source'])}'>{q(row['source'])}</a></td>"
            "</tr>"
        )
    return page(
        "agent-context",
        f"<div class='metrics'>{metric_html}</div>"
        "<table><thead><tr><th>Package</th><th>Type</th><th>Freshness</th><th>Currency</th><th>Version Package</th><th>Source</th></tr></thead>"
        f"<tbody>{''.join(table)}</tbody></table>",
    )


def package_detail(package_id):
    match = None
    for row in rows():
        if row["id"] == package_id:
            match = row
            break
    if not match:
        return page("Not found", "<p>Package not found.</p>"), 404
    cache_path = match["cache_path"] or ""
    files = []
    if cache_path and os.path.isdir(cache_path):
        for dirpath, _, filenames in os.walk(cache_path):
            for filename in sorted(filenames):
                rel = os.path.relpath(os.path.join(dirpath, filename), cache_path)
                files.append(rel)
    body = (
        f"<p><a href='/'>Back</a></p><h2>{q(match['name'])}</h2>"
        "<table>"
        + "".join(
            f"<tr><th>{q(key)}</th><td>{q(match[key])}</td></tr>"
            for key in match.keys()
            if key != "cache_path"
        )
        + "</table>"
        "<h3>Cached Files</h3><ul>"
        + "".join(f"<li><code>{q(file)}</code></li>" for file in files)
        + "</ul>"
    )
    return page(match["name"], body), 200


def page(title, body):
    return f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{q(title)}</title><style>{STYLE}</style></head><body><header><h1>agent-context</h1><div>Local documentation freshness, provenance, and version currency</div></header><main>{body}</main></body></html>"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        status = 200
        if parsed.path == "/":
            body = dashboard()
        elif parsed.path == "/package":
            body, status = package_detail(parse_qs(parsed.query).get("id", [""])[0])
        elif parsed.path == "/data.json":
            data = [dict(row) for row in rows()]
            body = json.dumps({"packages": data}, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body.encode())
            return
        else:
            body, status = page("Not found", "<p>Not found.</p>"), 404
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, fmt, *args):
        print(fmt % args, file=sys.stderr)


server = ThreadingHTTPServer((host, port), Handler)
print(f"Serving agent-context at http://{host}:{port}/")
server.serve_forever()
PY
}
