#!/usr/bin/env python3
"""Regression tests for agent-jira: connections, issues, search, sprints."""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
JIRA_PY = ROOT / "tools" / "agent-jira" / "jira_ops.py"
AGENT_DO = ROOT / "agent-do"
sys.path.insert(0, str(ROOT / "lib"))
import registry  # noqa: E402

PASS = 0
FAIL = 0

# Track requests to assert on dry-run (no HTTP calls made)
_requests: list[tuple[str, str]] = []
_auth_headers: list[str] = []
_post_bodies: dict[str, dict] = {}
_put_bodies: dict[str, dict] = {}
FAIL_SNAPSHOT_FOR_OPS = False


def check(desc: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        print(f"  ✓ {desc}")
        PASS += 1
    else:
        print(f"  ✗ {desc}")
        if detail:
            print(f"    {detail[:300]}")
        FAIL += 1


def run(argv: list[str], *, env: dict[str, str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(JIRA_PY), *argv],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def run_wrapper(argv: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(AGENT_DO), *argv],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


class JiraHandler(http.server.BaseHTTPRequestHandler):
    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _send(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_err(self, msg: str, status: int = 400) -> None:
        self._send({"errorMessages": [msg], "errors": {}}, status=status)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def _route_get(self, path: str, qs: dict) -> None:
        # both api v2 (server) and v3 (cloud) share the same fake responses
        path = path.replace("/rest/api/2/", "/rest/api/3/")

        if path == "/rest/api/3/myself":
            self._send({
                "accountId": "uid-abc",
                "displayName": "Test User",
                "emailAddress": "test@example.com",
                "name": "test",
            })

        elif path == "/rest/api/3/project":
            self._send([
                {"key": "PROJ", "name": "Test Project", "projectTypeKey": "software"},
                {"key": "OPS", "name": "Ops Project", "projectTypeKey": "business"},
            ])

        elif path in ("/rest/api/3/search", "/rest/api/3/search/jql"):
            jql = qs.get("jql", [""])[0]
            if "statusCategory != Done" in jql:
                if FAIL_SNAPSHOT_FOR_OPS and "project = OPS" in jql:
                    self._send_err("OPS search failed", status=500)
                    return
                count = 5 if "project = PROJ" in jql else 2
                self._send({"total": count, "issues": [], "maxResults": 0})
            elif "assignee = currentUser()" in jql:
                # --mine: return one issue assigned to current user
                self._send({
                    "total": 1,
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix login bug",
                                "status": {"name": "In Progress"},
                                "issuetype": {"name": "Bug"},
                                "priority": {"name": "High"},
                                "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                                "reporter": {"displayName": "Reporter"},
                                "labels": ["backend"],
                                "created": "2026-01-01T00:00:00.000Z",
                                "updated": "2026-01-15T00:00:00.000Z",
                                "description": None,
                            },
                        }
                    ],
                })
            elif '"EMPTY"' in jql:
                self._send({"total": 0, "issues": [], "maxResults": 50})
            else:
                self._send({
                    "total": 2,
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix login bug",
                                "status": {"name": "In Progress"},
                                "issuetype": {"name": "Bug"},
                                "priority": {"name": "High"},
                                "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                                "reporter": {"displayName": "Reporter"},
                                "labels": ["backend"],
                                "created": "2026-01-01T00:00:00.000Z",
                                "updated": "2026-01-15T00:00:00.000Z",
                                "description": None,
                            },
                        },
                        {
                            "key": "PROJ-2",
                            "fields": {
                                "summary": "Add dark mode",
                                "status": {"name": "Todo"},
                                "issuetype": {"name": "Story"},
                                "priority": {"name": "Medium"},
                                "assignee": None,
                                "reporter": {"displayName": "Reporter"},
                                "labels": [],
                                "created": "2026-01-02T00:00:00.000Z",
                                "updated": "2026-01-16T00:00:00.000Z",
                                "description": None,
                            },
                        },
                    ],
                })

        elif path == "/rest/api/3/issue/PROJ-1/transitions":
            self._send({
                "transitions": [
                    {"id": "11", "name": "To Do", "to": {"name": "Todo"}},
                    {"id": "21", "name": "In Progress", "to": {"name": "In Progress"}},
                    {"id": "31", "name": "Done", "to": {"name": "Done"}},
                ]
            })

        elif path == "/rest/api/3/issueLink":
            self._send({}, status=201)

        elif path.startswith("/rest/api/3/issue/PROJ-1"):
            self._send({
                "key": "PROJ-1",
                "fields": {
                    "summary": "Fix login bug",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Bug"},
                    "priority": {"name": "High"},
                    "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                    "reporter": {"displayName": "Reporter"},
                    "labels": ["backend", "auth"],
                    "created": "2026-01-01T00:00:00.000Z",
                    "updated": "2026-01-15T00:00:00.000Z",
                    "description": {
                        "type": "doc",
                        "version": 1,
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Login is broken"}]}],
                    },
                    "comment": {
                        "comments": [
                            {
                                "author": {"displayName": "Reviewer"},
                                "created": "2026-01-10T00:00:00.000Z",
                                "body": {
                                    "type": "doc",
                                    "version": 1,
                                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Please fix ASAP"}]}],
                                },
                            }
                        ]
                    },
                },
            })

        elif path.startswith("/rest/api/3/issue/PROJ-NOASSIGN"):
            self._send({
                "key": "PROJ-NOASSIGN",
                "fields": {
                    "summary": "Unassigned issue",
                    "status": {"name": "Todo"},
                    "issuetype": {"name": "Task"},
                    "priority": {"name": "Low"},
                    "assignee": None,
                    "reporter": {"displayName": "Reporter"},
                    "labels": [],
                    "created": "2026-01-01T00:00:00.000Z",
                    "updated": "2026-01-01T00:00:00.000Z",
                    "description": None,
                    "comment": {"comments": []},
                },
            })

        elif path == "/rest/api/3/issue/PROJ-NOTRANS/transitions":
            self._send({"transitions": []})

        elif path.startswith("/rest/api/3/issue/PROJ-NOTRANS"):
            self._send({"key": "PROJ-NOTRANS", "fields": {"summary": "No transitions", "status": {"name": "Todo"},
                "issuetype": {"name": "Task"}, "priority": {"name": "Low"}, "assignee": None,
                "reporter": {"displayName": "Reporter"}, "labels": [], "created": "2026-01-01T00:00:00.000Z",
                "updated": "2026-01-01T00:00:00.000Z", "description": None, "comment": {"comments": []}}})

        elif path.startswith("/rest/api/3/issue/PROJ-401"):
            self._send_err("Not authenticated", status=401)

        elif path.startswith("/rest/api/3/issue/PROJ-403"):
            self._send_err("Forbidden", status=403)

        elif path.startswith("/rest/api/3/issue/PROJ-500"):
            self._send_err("Internal server error", status=500)

        elif path == "/rest/api/3/issue/PROJ-999":
            self._send_err("Issue does not exist or you do not have permission.", status=404)

        elif path == "/rest/api/3/user/search":
            query = qs.get("query", [""])[0] or qs.get("username", [""])[0]
            if "nobody" in query:
                self._send([])
            else:
                self._send([
                    {
                        "accountId": "acc-abc123",
                        "displayName": "Alice Smith",
                        "emailAddress": "alice@example.com",
                        "name": "alice",
                    },
                    {
                        "accountId": "acc-def456",
                        "displayName": "Alice Jones",
                        "emailAddress": "alicej@example.com",
                        "name": "alicej",
                    },
                ])

        elif path == "/rest/agile/1.0/board":
            project_filter = qs.get("projectKeyOrId", [""])[0]
            boards = [
                {"id": 42, "name": "PROJ Board", "type": "scrum"},
                {"id": 43, "name": "OPS Board", "type": "kanban"},
            ]
            if project_filter == "PROJ":
                boards = [b for b in boards if b["name"].startswith("PROJ")]
            self._send({"values": boards})

        elif path.startswith("/rest/agile/1.0/board/42/sprint"):
            state = qs.get("state", ["active"])[0]
            if state in ("active", "all"):
                self._send({
                    "values": [
                        {
                            "id": 1,
                            "name": "Sprint 1",
                            "state": "active",
                            "startDate": "2026-01-01T00:00:00.000Z",
                            "endDate": "2026-01-14T00:00:00.000Z",
                        }
                    ]
                })
            else:
                self._send({"values": []})

        elif path.startswith("/rest/agile/1.0/board/99/sprint"):
            # board with no active sprint
            self._send({"values": []})

        elif path == "/rest/agile/1.0/sprint/1/issue":
            self._send({
                "issues": [
                    {
                        "key": "PROJ-1",
                        "fields": {
                            "summary": "Fix login bug",
                            "status": {"name": "In Progress"},
                            "issuetype": {"name": "Bug"},
                            "priority": {"name": "High"},
                            "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                            "reporter": {"displayName": "Reporter"},
                            "labels": [],
                            "created": "2026-01-01T00:00:00.000Z",
                            "updated": "2026-01-15T00:00:00.000Z",
                            "description": None,
                        },
                    }
                ]
            })

        else:
            self._send_err(f"Not found: {path}", status=404)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        _requests.append(("GET", self.path))
        _auth_headers.append(self.headers.get("Authorization", ""))
        self._route_get(parsed.path, qs)

    def do_POST(self) -> None:  # noqa: N802
        body_bytes = self._read_body()
        _requests.append(("POST", self.path))
        _auth_headers.append(self.headers.get("Authorization", ""))
        path = urlparse(self.path).path
        path = path.replace("/rest/api/2/", "/rest/api/3/")
        body = json.loads(body_bytes) if body_bytes else {}
        _post_bodies[path] = body

        if path == "/rest/api/3/search/jql":
            jql = body.get("jql", "")
            if "statusCategory != Done" in jql:
                if FAIL_SNAPSHOT_FOR_OPS and "project = OPS" in jql:
                    self._send_err("OPS search failed", status=500)
                    return
                count = 5 if "project = PROJ" in jql else 2
                self._send({"issues": [{"key": f"{'PROJ' if count == 5 else 'OPS'}-{i}"} for i in range(count)]})
            elif "assignee = currentUser()" in jql:
                self._send({
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix login bug",
                                "status": {"name": "In Progress"},
                                "issuetype": {"name": "Bug"},
                                "priority": {"name": "High"},
                                "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                                "reporter": {"displayName": "Reporter"},
                                "labels": ["backend"],
                                "created": "2026-01-01T00:00:00.000Z",
                                "updated": "2026-01-15T00:00:00.000Z",
                                "description": None,
                            },
                        }
                    ],
                })
            elif '"EMPTY"' in jql:
                self._send({"issues": [], "maxResults": body.get("maxResults", 50)})
            else:
                self._send({
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "fields": {
                                "summary": "Fix login bug",
                                "status": {"name": "In Progress"},
                                "issuetype": {"name": "Bug"},
                                "priority": {"name": "High"},
                                "assignee": {"displayName": "Test User", "emailAddress": "test@example.com"},
                                "reporter": {"displayName": "Reporter"},
                                "labels": ["backend"],
                                "created": "2026-01-01T00:00:00.000Z",
                                "updated": "2026-01-15T00:00:00.000Z",
                                "description": None,
                            },
                        },
                        {
                            "key": "PROJ-2",
                            "fields": {
                                "summary": "Add dark mode",
                                "status": {"name": "Todo"},
                                "issuetype": {"name": "Story"},
                                "priority": {"name": "Medium"},
                                "assignee": None,
                                "reporter": {"displayName": "Reporter"},
                                "labels": [],
                                "created": "2026-01-02T00:00:00.000Z",
                                "updated": "2026-01-16T00:00:00.000Z",
                                "description": None,
                            },
                        },
                    ],
                })
        elif path == "/rest/api/3/search/approximate-count":
            jql = body.get("jql", "")
            if FAIL_SNAPSHOT_FOR_OPS and "OPS" in jql:
                self._send_err("OPS search failed", status=500)
            else:
                self._send({"count": 5 if "PROJ" in jql else 2})
        elif path == "/rest/api/3/issue":
            project = ((body.get("fields") or {}).get("project") or {}).get("key")
            issue_type = ((body.get("fields") or {}).get("issuetype") or {}).get("name")
            if project == "KAN" and issue_type == "Bug":
                self._send_err("Project KAN does not accept issue type Bug", status=400)
            elif project == "KAN":
                self._send({"key": "KAN-8", "id": "10008"}, status=201)
            else:
                self._send({"key": "PROJ-3", "id": "10003"}, status=201)
        elif path == "/rest/api/3/issueLink":
            self._send({}, status=201)
        elif path == "/rest/api/3/issue/PROJ-1/comment":
            self._send({"id": "cmt-1"})
        elif path == "/rest/api/3/issue/PROJ-1/transitions":
            self._send(None, status=204)
        elif path == "/rest/api/3/issue/PROJ-3":
            self._send(None, status=204)
        elif path == "/rest/agile/1.0/sprint/1/issue":
            self._send(None, status=204)
        else:
            self._send_err(f"Not found: {path}", status=404)

    def do_PUT(self) -> None:  # noqa: N802
        body_bytes = self._read_body()
        _requests.append(("PUT", self.path))
        _auth_headers.append(self.headers.get("Authorization", ""))
        path = urlparse(self.path).path
        path = path.replace("/rest/api/2/", "/rest/api/3/")
        body = json.loads(body_bytes) if body_bytes else {}
        _put_bodies[path] = body

        if path in ("/rest/api/3/issue/PROJ-1/assignee", "/rest/api/3/issue/PROJ-1"):
            self._send(None, status=204)
        else:
            self._send_err(f"Not found: {path}", status=404)

    def do_DELETE(self) -> None:  # noqa: N802
        _requests.append(("DELETE", self.path))
        _auth_headers.append(self.headers.get("Authorization", ""))
        path = urlparse(self.path).path
        path = path.replace("/rest/api/2/", "/rest/api/3/")

        if path == "/rest/api/3/issue/PROJ-3":
            self._send(None, status=204)
        else:
            self._send_err(f"Not found: {path}", status=404)


def _make_env(tmp: Path, port: int, *, extra: dict | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_DO_HOME"] = str(tmp / "home")
    env.pop("JIRA_URL", None)
    env.pop("JIRA_EMAIL", None)
    env.pop("JIRA_API_TOKEN", None)
    env["SERVER_PORT"] = str(port)
    if extra:
        env.update(extra)
    return env


def main() -> int:
    global PASS, FAIL

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        server = socketserver.TCPServer(("127.0.0.1", 0), JiraHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        base_url = f"http://127.0.0.1:{port}"

        try:
            env = _make_env(tmp, port)
            home = Path(env["AGENT_DO_HOME"])

            # ── connections ─────────────────────────────────────────────────────

            print("\nconnections add")
            r = run(["connections", "add", "work",
                     "--url", base_url,
                     "--email", "test@example.com",
                     "--token-stdin",
                     "--default"], env=env, stdin="tok-secret\n")
            check("connections add exits 0", r.returncode == 0, r.stderr)
            check("connections add prints profile name", "work" in r.stdout, r.stdout)
            check("connections add marks default", "default" in r.stdout, r.stdout)

            creds_file = home / "jira" / ".creds" / "work"
            check("connections add: creds file exists", creds_file.exists(), str(creds_file))
            check(
                "connections add: creds file mode is 0o600",
                stat.S_IMODE(creds_file.stat().st_mode) == 0o600,
                oct(stat.S_IMODE(creds_file.stat().st_mode)),
            )
            meta_file = home / "jira" / "connections.json"
            creds = json.loads(creds_file.read_text())
            check("connections add: url stored in creds", creds.get("url") == base_url, str(creds))
            check("connections add: token stored in creds", creds.get("token") == "tok-secret", str(creds))
            check("connections add --token-stdin keeps token out of stdout", "tok-secret" not in r.stdout, r.stdout)

            print("\nconnections add: URL normalization")
            r = run(["connections", "add", "normalized",
                     "--url", base_url + "/",
                     "--email", "norm@example.com",
                     "--token", "tok-normal"], env=env)
            check("connections add normalized exits 0", r.returncode == 0, r.stderr)
            normalized_creds = json.loads((home / "jira" / ".creds" / "normalized").read_text())
            check("connections add normalized stores trimmed url", normalized_creds.get("url") == base_url, str(normalized_creds))
            normalized_meta = json.loads(meta_file.read_text())
            check("connections add normalized stores trimmed url in metadata",
                  normalized_meta["profiles"]["normalized"].get("url") == base_url, str(normalized_meta["profiles"]["normalized"]))

            check("connections add: connections.json created", meta_file.exists())
            meta = json.loads(meta_file.read_text())
            check("connections add: token NOT in connections.json", "tok-secret" not in meta_file.read_text())
            check("connections add: default set in metadata", meta.get("default") == "work")

            print("\nconnections add: overwrite existing profile")
            r = run(["connections", "add", "work",
                     "--url", base_url,
                     "--email", "updated@example.com",
                     "--token", "tok-updated",
                     "--default"], env=env)
            check("connections add overwrite exits 0", r.returncode == 0, r.stderr)
            check("connections add overwrite prints 'Updated'", "Updated" in r.stdout, r.stdout)
            updated_creds = json.loads(creds_file.read_text())
            check("connections add overwrite: new email stored", updated_creds.get("email") == "updated@example.com")
            check("connections add overwrite: new token stored", updated_creds.get("token") == "tok-updated")
            # Restore original creds for remaining tests
            run(["connections", "add", "work",
                 "--url", base_url,
                 "--email", "test@example.com",
                 "--token", "tok-secret",
                 "--default"], env=env)

            print("\nconnections add second profile")
            r2 = run(["connections", "add", "personal",
                      "--url", base_url,
                      "--email", "me@personal.com",
                      "--token", "tok-personal"], env=env)
            check("connections add second exits 0", r2.returncode == 0, r2.stderr)
            check("connections add second: creds file at 0o600",
                  stat.S_IMODE((home / "jira" / ".creds" / "personal").stat().st_mode) == 0o600)
            check("connections add second does not change default", meta_file.read_text().count('"default"') >= 1)
            r = run(["connections", "add", "jsonprofile", "--url", base_url,
                     "--email", "json@example.com", "--token", "tok-json", "--json"], env=env)
            check("connections add --json exits 0", r.returncode == 0, r.stderr)
            check("connections add --json hides token", "tok-json" not in r.stdout, r.stdout)

            print("\nconnections list")
            r = run(["connections", "list"], env=env)
            check("connections list exits 0", r.returncode == 0, r.stderr)
            check("connections list shows work", "work" in r.stdout, r.stdout)
            check("connections list shows default marker", "*" in r.stdout, r.stdout)
            check("connections list shows personal", "personal" in r.stdout, r.stdout)
            check("connections list shows Cloud type", "Cloud" in r.stdout, r.stdout)
            check("connections list hides token", "tok-secret" not in r.stdout, r.stdout)
            r = run(["connections", "list", "--json"], env=env)
            check("connections list --json exits 0", r.returncode == 0, r.stderr)
            check("connections list --json hides token", "tok-secret" not in r.stdout, r.stdout)
            check("connections list --json has profiles", len(json.loads(r.stdout)["profiles"]) >= 2, r.stdout)

            print("\nconnections set-default")
            r = run(["connections", "set-default", "personal"], env=env)
            check("set-default exits 0", r.returncode == 0, r.stderr)
            meta_after = json.loads(meta_file.read_text())
            check("set-default changes metadata", meta_after.get("default") == "personal")
            r = run(["connections", "set-default", "work", "--json"], env=env)
            check("set-default --json exits 0", r.returncode == 0, r.stderr)
            check("set-default --json reports default", json.loads(r.stdout)["default"] == "work", r.stdout)

            r = run(["connections", "set-default", "nonexistent-profile"], env=env)
            check("set-default nonexistent exits 1", r.returncode == 1)
            check("set-default nonexistent mentions listing", "list" in r.stderr.lower() or "connections" in r.stderr.lower(), r.stderr)

            # restore default to work for remaining tests
            run(["connections", "set-default", "work"], env=env)

            print("\nconnections add --server flag")
            r = run(["connections", "add", "dc",
                     "--url", base_url,
                     "--email", "admin",
                     "--token", "pat-123",
                     "--server"], env=env)
            check("connections add --server exits 0", r.returncode == 0, r.stderr)
            check("connections add --server shows Server/DC", "Server" in r.stdout, r.stdout)
            meta_dc = json.loads(meta_file.read_text())
            check("connections add --server: server=true in metadata", meta_dc["profiles"]["dc"].get("server") is True)

            print("\nconnections remove")
            r = run(["connections", "remove", "dc"], env=env)
            check("connections remove exits 0", r.returncode == 0, r.stderr)
            check("connections remove: creds file gone", not (home / "jira" / ".creds" / "dc").exists())
            meta_after = json.loads(meta_file.read_text())
            check("connections remove: metadata updated", "dc" not in meta_after.get("profiles", {}))
            r = run(["connections", "remove", "jsonprofile", "--json"], env=env)
            check("connections remove --json exits 0", r.returncode == 0, r.stderr)
            check("connections remove --json confirms removal", json.loads(r.stdout)["removed"] is True, r.stdout)

            r = run(["connections", "remove", "nonexistent-profile"], env=env)
            check("connections remove nonexistent exits 1", r.returncode == 1)
            check("connections remove nonexistent mentions listing", "list" in r.stderr.lower() or "connections" in r.stderr.lower(), r.stderr)

            print("\nconnections add: missing required args")
            r = run(["connections", "add", "bad", "--url", base_url, "--email", "x@x.com"], env=env)
            check("connections add missing --token exits 1", r.returncode == 1)
            check("connections add missing --token prints error", "Error:" in r.stderr, r.stderr)

            r = run(["connections", "add", "bad2", "--email", "x@x.com", "--token", "t"], env=env)
            check("connections add missing --url exits 1", r.returncode == 1)

            print("\nconnections add: profile name validation")
            r = run(["connections", "add", "../evil",
                     "--url", base_url, "--email", "x@x.com", "--token", "t"], env=env)
            check("profile name with slash exits 1", r.returncode == 1)
            check("profile name with slash prints error", "Error:" in r.stderr, r.stderr)

            r = run(["connections", "add", "bad-url",
                     "--url", "not-a-url", "--email", "x@x.com", "--token", "t"], env=env)
            check("connections add invalid url exits 1", r.returncode == 1)
            check("connections add invalid url prints error", "http:// or https://" in r.stderr, r.stderr)

            r = run(["connections", "add", "bad-scheme",
                     "--url", "ftp://example.com", "--email", "x@x.com", "--token", "t"], env=env)
            check("connections add unsupported scheme exits 1", r.returncode == 1)
            check("connections add unsupported scheme prints error", "http:// or https://" in r.stderr, r.stderr)

            r = run(["connections", "add", "bad-empty-host",
                     "--url", "https://", "--email", "x@x.com", "--token", "t"], env=env)
            check("connections add empty-host url exits 1", r.returncode == 1)
            check("connections add empty-host url prints error", "http:// or https://" in r.stderr, r.stderr)

            r = run(["connections", "add", ".hidden",
                     "--url", base_url, "--email", "x@x.com", "--token", "t"], env=env)
            check("profile name starting with dot exits 1", r.returncode == 1)

            r = run(["connections", "add", "a" * 65,
                     "--url", base_url, "--email", "x@x.com", "--token", "t"], env=env)
            check("profile name >64 chars exits 1", r.returncode == 1)

            # ── whoami ──────────────────────────────────────────────────────────

            print("\nwhoami")
            r = run(["whoami"], env=env)
            check("whoami exits 0", r.returncode == 0, r.stderr)
            check("whoami shows account", "Test User" in r.stdout, r.stdout)
            check("whoami shows email", "test@example.com" in r.stdout, r.stdout)
            check("whoami shows jira base url", base_url in r.stdout, r.stdout)

            r = run(["whoami", "--json"], env=env)
            check("whoami --json exits 0", r.returncode == 0, r.stderr)
            payload = json.loads(r.stdout)
            check("whoami --json has displayName", payload.get("displayName") == "Test User")
            check("whoami --json has emailAddress", payload.get("emailAddress") == "test@example.com")

            print("\nwhoami --connection")
            r = run(["whoami", "--connection", "personal"], env=env)
            check("whoami --connection exits 0", r.returncode == 0, r.stderr)

            r = run(["whoami", "--connection", "nonexistent"], env=env)
            check("whoami bad connection exits 1", r.returncode == 1)
            check("whoami bad connection prints error", "not found" in r.stderr.lower() or "Error:" in r.stderr, r.stderr)

            # ── snapshot ────────────────────────────────────────────────────────

            print("\nsnapshot")
            r = run(["snapshot"], env=env)
            check("snapshot exits 0", r.returncode == 0, r.stderr)
            check("snapshot shows project count", "2" in r.stdout, r.stdout)
            check("snapshot shows PROJ key", "PROJ" in r.stdout, r.stdout)
            check("snapshot shows open issue count", "5" in r.stdout, r.stdout)

            r = run(["snapshot", "--json"], env=env)
            check("snapshot --json exits 0", r.returncode == 0, r.stderr)
            snap = json.loads(r.stdout)
            check("snapshot --json tool field", snap.get("tool") == "snapshot")
            check("snapshot --json project_count", snap["data"]["project_count"] == 2)
            projects = snap["data"]["projects"]
            proj_keys = [p["key"] for p in projects]
            check("snapshot --json has PROJ", "PROJ" in proj_keys)
            check("snapshot --json has open_issues", all("open_issues" in p for p in projects))

            print("\nsnapshot: tolerate a project search failure")
            global FAIL_SNAPSHOT_FOR_OPS
            FAIL_SNAPSHOT_FOR_OPS = True
            try:
                r = run(["snapshot", "--json"], env=env)
            finally:
                FAIL_SNAPSHOT_FOR_OPS = False
            check("snapshot failure case exits 0", r.returncode == 0, r.stderr)
            snap_fail = json.loads(r.stdout)
            fail_projects = {p["key"]: p["open_issues"] for p in snap_fail["data"]["projects"]}
            check("snapshot failure case keeps project list", set(fail_projects) == {"PROJ", "OPS"}, str(fail_projects))
            check("snapshot failure case marks broken project unknown", fail_projects["OPS"] == -1, str(fail_projects))

            # ── user find ───────────────────────────────────────────────────────

            print("\nuser find")
            _requests.clear()
            r = run(["user", "find", "alice"], env=env)
            check("user find exits 0", r.returncode == 0, r.stderr)
            check("user find shows account ID", "acc-abc123" in r.stdout, r.stdout)
            check("user find shows display name", "Alice Smith" in r.stdout, r.stdout)
            check("user find shows email", "alice@example.com" in r.stdout, r.stdout)
            # Cloud should use ?query= param
            user_reqs = [path for m, path in _requests if m == "GET" and "user/search" in path]
            check("user find Cloud uses ?query= param", any("query=" in p for p in user_reqs), str(user_reqs))

            r = run(["user", "find", "--email", "alice@example.com"], env=env)
            check("user find --email exits 0", r.returncode == 0, r.stderr)
            check("user find --email shows results", "Alice" in r.stdout, r.stdout)

            r = run(["user", "find", "nobody@example.com"], env=env)
            check("user find no results exits 0", r.returncode == 0, r.stderr)
            check("user find no results shows helpful message", "No users" in r.stdout or "no users" in r.stdout.lower(), r.stdout)

            r = run(["user", "find", "--json", "alice"], env=env)
            check("user find --json exits 0", r.returncode == 0, r.stderr)
            uj = json.loads(r.stdout)
            check("user find --json has users key", "users" in uj)
            check("user find --json has 2 users", len(uj["users"]) == 2)
            check("user find --json user has accountId", uj["users"][0].get("accountId") == "acc-abc123")

            r = run(["user", "find"], env=env)
            check("user find no query exits 1", r.returncode == 1)
            check("user find no query prints error", "Error:" in r.stderr, r.stderr)

            print("\nuser find: Server/DC uses ?username= param")
            run(["connections", "add", "dc3",
                 "--url", base_url,
                 "--email", "admin",
                 "--token", "pat",
                 "--server"], env=env)
            _requests.clear()
            r = run(["user", "find", "alice", "--connection", "dc3"], env=env)
            check("user find Server/DC exits 0", r.returncode == 0, r.stderr)
            server_user_reqs = [path for m, path in _requests if m == "GET" and "user/search" in path]
            check("user find Server/DC uses ?username= param", any("username=" in p for p in server_user_reqs), str(server_user_reqs))
            run(["connections", "remove", "dc3"], env=env)

            # ── issue view ──────────────────────────────────────────────────────

            print("\nissue view")
            r = run(["issue", "view", "PROJ-1"], env=env)
            check("issue view exits 0", r.returncode == 0, r.stderr)
            check("issue view shows key", "PROJ-1" in r.stdout, r.stdout)
            check("issue view shows summary", "Fix login bug" in r.stdout, r.stdout)
            check("issue view shows status", "In Progress" in r.stdout, r.stdout)
            check("issue view shows assignee", "Test User" in r.stdout, r.stdout)
            check("issue view shows labels", "backend" in r.stdout, r.stdout)
            check("issue view shows description", "Login is broken" in r.stdout, r.stdout)

            r = run(["issue", "view", "PROJ-1", "--comments"], env=env)
            check("issue view --comments exits 0", r.returncode == 0, r.stderr)
            check("issue view --comments shows comment author", "Reviewer" in r.stdout, r.stdout)
            check("issue view --comments shows comment body", "Please fix ASAP" in r.stdout, r.stdout)

            r = run(["issue", "view", "PROJ-1", "--json"], env=env)
            check("issue view --json exits 0", r.returncode == 0, r.stderr)
            iv = json.loads(r.stdout)
            check("issue view --json key", iv.get("key") == "PROJ-1")
            check("issue view --json summary", iv.get("summary") == "Fix login bug")
            check("issue view --json status", iv.get("status") == "In Progress")
            check("issue view --json labels", "backend" in (iv.get("labels") or []))

            r = run(["issue", "view", "PROJ-1", "--comments", "--json"], env=env)
            check("issue view --comments --json exits 0", r.returncode == 0, r.stderr)
            ivj = json.loads(r.stdout)
            check("issue view --comments --json has comments key", "comments" in ivj)
            check("issue view --comments --json has comment body", len(ivj.get("comments", [])) > 0)

            print("\nissue view: unassigned issue")
            r = run(["issue", "view", "PROJ-NOASSIGN"], env=env)
            check("issue view unassigned exits 0", r.returncode == 0, r.stderr)
            check("issue view unassigned shows (unassigned)", "unassigned" in r.stdout.lower(), r.stdout)

            r = run(["issue", "view", "PROJ-999"], env=env)
            check("issue view 404 exits 1", r.returncode == 1)
            check("issue view 404 prints error", "Error:" in r.stderr, r.stderr)

            print("\nissue view: HTTP error messages")
            r = run(["issue", "view", "PROJ-401"], env=env)
            check("issue view 401 exits 1", r.returncode == 1)
            check("issue view 401 mentions API token", "api token" in r.stderr.lower() or "token" in r.stderr.lower(), r.stderr)

            r = run(["issue", "view", "PROJ-403"], env=env)
            check("issue view 403 exits 1", r.returncode == 1)
            check("issue view 403 mentions permission", "permission" in r.stderr.lower(), r.stderr)

            r = run(["issue", "view", "PROJ-500"], env=env)
            check("issue view 500 exits 1", r.returncode == 1)

            # ── issue list ──────────────────────────────────────────────────────

            print("\nissue list")
            r = run(["issue", "list", "PROJ"], env=env)
            check("issue list exits 0", r.returncode == 0, r.stderr)
            check("issue list shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)
            check("issue list shows PROJ-2", "PROJ-2" in r.stdout, r.stdout)
            check("issue list shows total", "2 of 2" in r.stdout or "(2 of 2)" in r.stdout or "2" in r.stdout)

            r = run(["issue", "list", "PROJ", "--json"], env=env)
            check("issue list --json exits 0", r.returncode == 0, r.stderr)
            il = json.loads(r.stdout)
            check("issue list --json has issues", len(il["data"]["issues"]) == 2)
            check("issue list --json project field", il["data"]["project"] == "PROJ")

            print("\nissue list --mine")
            _requests.clear()
            r = run(["issue", "list", "PROJ", "--mine"], env=env)
            check("issue list --mine exits 0", r.returncode == 0, r.stderr)
            check("issue list --mine shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)
            # Cloud search uses POST /search/jql; verify currentUser() stays unquoted in the JSON body.
            mine_jql = (_post_bodies.get("/rest/api/3/search/jql") or {}).get("jql", "")
            check("issue list --mine sends unquoted currentUser()", "currentUser()" in mine_jql, mine_jql)
            check("issue list --mine does NOT quote currentUser()", '"currentUser()"' not in mine_jql, mine_jql)
            mine_fields = (_post_bodies.get("/rest/api/3/search/jql") or {}).get("fields")
            check("Cloud enhanced search sends fields as an array", isinstance(mine_fields, list), str(mine_fields))

            print("\nissue list: all filters combined")
            r = run(["issue", "list", "PROJ",
                     "--status", "In Progress",
                     "--type", "Bug",
                     "--priority", "High",
                     "--label", "backend",
                     "--assignee", "test@example.com",
                     "--limit", "25"], env=env)
            check("issue list all filters exits 0", r.returncode == 0, r.stderr)

            print("\nissue list: empty project")
            r = run(["issue", "list", "EMPTY"], env=env)
            check("issue list empty project exits 0", r.returncode == 0, r.stderr)
            check("issue list empty project shows 0 results", "0" in r.stdout, r.stdout)

            print("\nissue list --limit validation")
            r = run(["issue", "list", "PROJ", "--limit", "notanumber"], env=env)
            check("issue list --limit non-integer exits 1", r.returncode == 1)
            check("issue list --limit non-integer prints error", "Error:" in r.stderr, r.stderr)

            r = run(["issue", "list", "PROJ", "--limit", "-1"], env=env)
            check("issue list --limit -1 exits 1", r.returncode == 1)
            check("issue list --limit -1 prints error", "Error:" in r.stderr, r.stderr)

            # ── issue create ────────────────────────────────────────────────────

            print("\nissue create")
            _requests.clear()
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "New feature request",
                     "--type", "Story",
                     "--priority", "Medium",
                     "--label", "frontend",
                     "--label", "ux"], env=env)
            check("issue create exits 0", r.returncode == 0, r.stderr)
            check("issue create prints key", "PROJ-3" in r.stdout, r.stdout)

            create_body = _post_bodies.get("/rest/api/3/issue", {})
            fields = create_body.get("fields", {})
            check("issue create sends summary", fields.get("summary") == "New feature request")
            check("issue create sends type", (fields.get("issuetype") or {}).get("name") == "Story")
            check("issue create sends priority", (fields.get("priority") or {}).get("name") == "Medium")
            check("issue create sends labels", set(fields.get("labels", [])) == {"frontend", "ux"})

            r = run(["issue", "create", "PROJ",
                     "--summary", "With description",
                     "--description", "Detailed description here"], env=env)
            check("issue create with description exits 0", r.returncode == 0, r.stderr)
            create_body2 = _post_bodies.get("/rest/api/3/issue", {})
            desc = create_body2.get("fields", {}).get("description", {})
            check("issue create sends ADF description", isinstance(desc, dict) and desc.get("type") == "doc")

            print("\nissue create: rejected issue type")
            _requests.clear()
            _post_bodies.clear()
            r = run(["issue", "create", "KAN",
                     "--summary", "Green Lantern alter ego is Hal Jordan instead of Kyle Rayner",
                     "--type", "Bug"], env=env)
            check("issue create KAN bug fails", r.returncode == 1, r.stderr)
            check("issue create KAN bug gives a retry hint", "no issue was created" in r.stderr.lower(), r.stderr)
            kan_posts = [path for m, path in _requests if m == "POST" and path == "/rest/api/3/issue"]
            check("issue create KAN bug never substitutes Task", len(kan_posts) == 1, str(_requests))

            print("\nissue create: assignee email resolves to accountId")
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "Email-assigned issue",
                     "--assignee", "alice@example.com"], env=env)
            check("issue create assignee email exits 0", r.returncode == 0, r.stderr)
            email_body = _post_bodies.get("/rest/api/3/issue", {})
            email_assignee = (email_body.get("fields") or {}).get("assignee") or {}
            check("issue create assignee email sends accountId", email_assignee.get("accountId") == "acc-abc123", str(email_body))

            print("\nissue create --parent")
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "Child issue",
                     "--parent", "PROJ-1"], env=env)
            check("issue create --parent exits 0", r.returncode == 0, r.stderr)
            parent_body = _post_bodies.get("/rest/api/3/issue", {})
            parent_field = (parent_body.get("fields") or {}).get("parent", {})
            check("issue create --parent sends parent key", parent_field.get("key") == "PROJ-1")

            print("\nissue create --sprint")
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "Sprint issue",
                     "--sprint", "42"], env=env)
            check("issue create --sprint exits 0", r.returncode == 0, r.stderr)
            sprint_body = _post_bodies.get("/rest/api/3/issue", {})
            sprint_field = (sprint_body.get("fields") or {}).get("customfield_10020", {})
            check("issue create --sprint sends customfield_10020", sprint_field.get("id") == 42)

            print("\nissue create --sprint-field override")
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "Sprint issue with custom field",
                     "--sprint", "42",
                     "--sprint-field", "customfield_12345"], env=env)
            check("issue create --sprint-field exits 0", r.returncode == 0, r.stderr)
            custom_sprint_body = _post_bodies.get("/rest/api/3/issue", {})
            custom_sprint_field = (custom_sprint_body.get("fields") or {}).get("customfield_12345", {})
            check("issue create --sprint-field sends requested field", custom_sprint_field.get("id") == 42, str(custom_sprint_body))

            r = run(["issue", "create", "PROJ",
                     "--summary", "Bad sprint",
                     "--sprint", "notanumber"], env=env)
            check("issue create --sprint non-integer exits 1", r.returncode == 1)
            check("issue create --sprint non-integer prints error", "Error:" in r.stderr, r.stderr)

            print("\nissue create --dry-run")
            _requests_before = len(_requests)
            r = run(["issue", "create", "PROJ",
                     "--summary", "Dry run test",
                     "--dry-run"], env=env)
            check("issue create --dry-run exits 0", r.returncode == 0)
            check("issue create --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            check("issue create --dry-run shows summary", "Dry run test" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("issue create --dry-run makes no HTTP request", len(new_posts) == 0)

            print("\nissue create --dry-run --json")
            r = run(["issue", "create", "PROJ",
                     "--summary", "Json dry run",
                     "--dry-run", "--json"], env=env)
            check("issue create --dry-run --json exits 0", r.returncode == 0)
            drj = json.loads(r.stdout)
            check("issue create --dry-run --json has dry_run=true", drj.get("dry_run") is True)
            check("issue create --dry-run --json has action", drj.get("action") == "issue_create")
            check("issue create --dry-run --json has project", drj.get("project") == "PROJ")
            check("issue create --dry-run --json has fields", "fields" in drj)

            r = run(["issue", "create", "PROJ"], env=env)
            check("issue create missing --summary exits 1", r.returncode == 1)
            check("issue create missing --summary prints error", "Error:" in r.stderr, r.stderr)

            r = run(["issue", "create", "PROJ", "--summary", "x", "--json"], env=env)
            check("issue create --json exits 0", r.returncode == 0, r.stderr)
            cj = json.loads(r.stdout)
            check("issue create --json has key", "key" in cj)
            check("issue create --json has url", "url" in cj)

            # ── issue comment ───────────────────────────────────────────────────

            print("\nissue comment")
            r = run(["issue", "comment", "PROJ-1", "--body", "This is a comment"], env=env)
            check("issue comment exits 0", r.returncode == 0, r.stderr)
            check("issue comment prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            comment_body = _post_bodies.get("/rest/api/3/issue/PROJ-1/comment", {})
            body_field = comment_body.get("body", {})
            check("issue comment sends ADF body", isinstance(body_field, dict) and body_field.get("type") == "doc")

            _requests_before = len(_requests)
            r = run(["issue", "comment", "PROJ-1", "--body", "Preview", "--dry-run"], env=env)
            check("issue comment --dry-run exits 0", r.returncode == 0)
            check("issue comment --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("issue comment --dry-run makes no HTTP request", len(new_posts) == 0)

            print("\nissue comment --dry-run --json")
            r = run(["issue", "comment", "PROJ-1", "--body", "Preview", "--dry-run", "--json"], env=env)
            check("issue comment --dry-run --json exits 0", r.returncode == 0)
            cdj = json.loads(r.stdout)
            check("issue comment --dry-run --json has dry_run=true", cdj.get("dry_run") is True)
            check("issue comment --dry-run --json has action", "comment" in cdj.get("action", ""))

            r = run(["issue", "comment", "PROJ-1"], env=env)
            check("issue comment missing --body exits 1", r.returncode == 1)

            r = run(["issue", "comment", "PROJ-1", "--body", "ok", "--json"], env=env)
            check("issue comment --json exits 0", r.returncode == 0, r.stderr)
            cmt_j = json.loads(r.stdout)
            check("issue comment --json has key", cmt_j.get("key") == "PROJ-1")

            # ── issue assign ────────────────────────────────────────────────────

            print("\nissue assign")
            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "user-account-id-123"], env=env)
            check("issue assign exits 0", r.returncode == 0, r.stderr)
            check("issue assign prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            assign_body = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign sends accountId", assign_body.get("accountId") == "user-account-id-123")

            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "alice@example.com"], env=env)
            check("issue assign email exits 0", r.returncode == 0, r.stderr)
            email_assign_body = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign email sends accountId", email_assign_body.get("accountId") == "acc-abc123", str(email_assign_body))

            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "none"], env=env)
            check("issue assign --to none exits 0", r.returncode == 0, r.stderr)
            unassign_body = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign --to none sends null accountId", unassign_body.get("accountId") is None)

            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "NONE"], env=env)
            check("issue assign --to NONE (uppercase) exits 0", r.returncode == 0, r.stderr)
            unassign_body2 = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign --to NONE sends null accountId", unassign_body2.get("accountId") is None)

            print("\nissue assign: Server/DC uses 'name' field")
            run(["connections", "add", "dc4",
                 "--url", base_url,
                 "--email", "admin",
                 "--token", "pat",
                 "--server"], env=env)
            _put_bodies.clear()
            r = run(["issue", "assign", "PROJ-1", "--to", "jira-user", "--connection", "dc4"], env=env)
            check("issue assign Server/DC exits 0", r.returncode == 0, r.stderr)
            dc_assign = _put_bodies.get("/rest/api/3/issue/PROJ-1/assignee", {})
            check("issue assign Server/DC sends 'name' not accountId", "name" in dc_assign, str(dc_assign))
            check("issue assign Server/DC 'name' value correct", dc_assign.get("name") == "jira-user")
            run(["connections", "remove", "dc4"], env=env)

            _requests_before = len(_requests)
            r = run(["issue", "assign", "PROJ-1", "--to", "x@x.com", "--dry-run"], env=env)
            check("issue assign --dry-run exits 0", r.returncode == 0)
            check("issue assign --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_puts = [m for m in _requests[_requests_before:] if m[0] == "PUT"]
            check("issue assign --dry-run makes no HTTP request", len(new_puts) == 0)

            print("\nissue assign --dry-run --json")
            r = run(["issue", "assign", "PROJ-1", "--to", "x@x.com", "--dry-run", "--json"], env=env)
            check("issue assign --dry-run --json exits 0", r.returncode == 0)
            adj = json.loads(r.stdout)
            check("issue assign --dry-run --json has dry_run=true", adj.get("dry_run") is True)
            check("issue assign --dry-run --json has assignee", "assignee" in adj or "to" in adj)

            r = run(["issue", "assign", "PROJ-1"], env=env)
            check("issue assign missing --to exits 1", r.returncode == 1)

            # ── issue transition ─────────────────────────────────────────────────

            print("\nissue transition")
            r = run(["issue", "transition", "PROJ-1", "--to", "Done"], env=env)
            check("issue transition exits 0", r.returncode == 0, r.stderr)
            check("issue transition prints status", "Done" in r.stdout, r.stdout)

            transition_body = _post_bodies.get("/rest/api/3/issue/PROJ-1/transitions", {})
            check("issue transition sends transition id", (transition_body.get("transition") or {}).get("id") == "31")

            r = run(["issue", "transition", "PROJ-1", "--to", "done"], env=env)
            check("issue transition case-insensitive exits 0", r.returncode == 0, r.stderr)

            r = run(["issue", "transition", "PROJ-1", "--to", "Nonexistent Status"], env=env)
            check("issue transition bad status exits 1", r.returncode == 1)
            check("issue transition bad status lists available", "To Do" in r.stderr or "Done" in r.stderr, r.stderr)

            print("\nissue transition: no transitions available")
            r = run(["issue", "transition", "PROJ-NOTRANS", "--to", "Done"], env=env)
            check("issue transition no transitions exits 1", r.returncode == 1)
            check("issue transition no transitions prints error", "Error:" in r.stderr or "no" in r.stderr.lower(), r.stderr)

            _requests_before = len(_requests)
            r = run(["issue", "transition", "PROJ-1", "--to", "Done", "--dry-run"], env=env)
            check("issue transition --dry-run exits 0", r.returncode == 0)
            check("issue transition --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"
                         and "transitions" in m[1]]
            check("issue transition --dry-run makes no transition POST", len(new_posts) == 0)

            print("\nissue transition --dry-run --json")
            r = run(["issue", "transition", "PROJ-1", "--to", "Done", "--dry-run", "--json"], env=env)
            check("issue transition --dry-run --json exits 0", r.returncode == 0, r.stderr)
            if r.returncode == 0 and r.stdout.strip():
                tdj = json.loads(r.stdout)
                check("issue transition --dry-run --json has dry_run=true", tdj.get("dry_run") is True)
                check("issue transition --dry-run --json has transition name", "transition" in tdj or "to" in tdj)
            else:
                check("issue transition --dry-run --json has dry_run=true", False, r.stdout or r.stderr)
                check("issue transition --dry-run --json has transition name", False, r.stdout or r.stderr)

            # ── issue label ──────────────────────────────────────────────────────

            print("\nissue label")
            _put_bodies.clear()
            r = run(["issue", "label", "PROJ-1", "--add", "newlabel", "--remove", "auth"], env=env)
            check("issue label exits 0", r.returncode == 0, r.stderr)
            check("issue label prints updated labels", "PROJ-1" in r.stdout, r.stdout)

            label_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            updated_labels = (label_body.get("fields") or {}).get("labels", [])
            check("issue label adds new label", "newlabel" in updated_labels)
            check("issue label removes auth", "auth" not in updated_labels)
            check("issue label keeps backend", "backend" in updated_labels)

            print("\nissue label: add existing label (no duplicate)")
            _put_bodies.clear()
            r = run(["issue", "label", "PROJ-1", "--add", "backend"], env=env)
            check("issue label add existing exits 0", r.returncode == 0, r.stderr)
            dedup_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            dedup_labels = (dedup_body.get("fields") or {}).get("labels", [])
            check("issue label add existing: no duplicate", dedup_labels.count("backend") <= 1)

            print("\nissue label: remove non-existent label (graceful)")
            _put_bodies.clear()
            r = run(["issue", "label", "PROJ-1", "--remove", "doesnotexist"], env=env)
            check("issue label remove nonexistent exits 0", r.returncode == 0, r.stderr)

            _requests_before = len(_requests)
            r = run(["issue", "label", "PROJ-1", "--add", "x", "--dry-run"], env=env)
            check("issue label --dry-run exits 0", r.returncode == 0)
            check("issue label --dry-run shows before/after", "Before:" in r.stdout and "After:" in r.stdout, r.stdout)
            new_puts = [m for m in _requests[_requests_before:] if m[0] == "PUT"]
            check("issue label --dry-run makes no HTTP PUT", len(new_puts) == 0)

            print("\nissue label --dry-run --json")
            r = run(["issue", "label", "PROJ-1", "--add", "x", "--dry-run", "--json"], env=env)
            check("issue label --dry-run --json exits 0", r.returncode == 0)
            ldj = json.loads(r.stdout)
            check("issue label --dry-run --json has dry_run=true", ldj.get("dry_run") is True)

            r = run(["issue", "label", "PROJ-1"], env=env)
            check("issue label no --add/--remove exits 1", r.returncode == 1)

            # ── issue edit ───────────────────────────────────────────────────────

            print("\nissue edit")
            _put_bodies.clear()
            r = run(["issue", "edit", "PROJ-1",
                     "--summary", "Updated summary",
                     "--priority", "Low"], env=env)
            check("issue edit exits 0", r.returncode == 0, r.stderr)
            check("issue edit prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            edit_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            edit_fields = edit_body.get("fields", {})
            check("issue edit sends summary", edit_fields.get("summary") == "Updated summary")
            check("issue edit sends priority", (edit_fields.get("priority") or {}).get("name") == "Low")

            _put_bodies.clear()
            r = run(["issue", "edit", "PROJ-1", "--description", "New desc", "--dry-run"], env=env)
            check("issue edit --dry-run exits 0", r.returncode == 0)
            check("issue edit --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            check("issue edit --dry-run makes no PUT", "/rest/api/3/issue/PROJ-1" not in _put_bodies)

            print("\nissue edit --dry-run --json")
            r = run(["issue", "edit", "PROJ-1", "--summary", "x", "--dry-run", "--json"], env=env)
            check("issue edit --dry-run --json exits 0", r.returncode == 0)
            edj = json.loads(r.stdout)
            check("issue edit --dry-run --json has dry_run=true", edj.get("dry_run") is True)

            r = run(["issue", "edit", "PROJ-1"], env=env)
            check("issue edit no fields exits 1", r.returncode == 1)

            r = run(["issue", "edit", "PROJ-1", "--summary", "x", "--json"], env=env)
            check("issue edit --json exits 0", r.returncode == 0, r.stderr)
            ej = json.loads(r.stdout)
            check("issue edit --json has key", ej.get("key") == "PROJ-1")
            check("issue edit --json has updated fields", "summary" in (ej.get("updated") or []))

            # ── transitions ──────────────────────────────────────────────────────

            print("\ntransitions")
            r = run(["transitions", "PROJ-1"], env=env)
            check("transitions exits 0", r.returncode == 0, r.stderr)
            check("transitions shows To Do", "To Do" in r.stdout, r.stdout)
            check("transitions shows In Progress", "In Progress" in r.stdout, r.stdout)
            check("transitions shows Done", "Done" in r.stdout, r.stdout)

            r = run(["transitions", "PROJ-1", "--json"], env=env)
            check("transitions --json exits 0", r.returncode == 0, r.stderr)
            tj = json.loads(r.stdout)
            check("transitions --json key field", tj.get("key") == "PROJ-1")
            check("transitions --json has 3 transitions", len(tj.get("transitions", [])) == 3)
            names = [t["name"] for t in tj["transitions"]]
            check("transitions --json contains Done", "Done" in names)

            print("\ntransitions: no transitions available")
            r = run(["transitions", "PROJ-NOTRANS", "--json"], env=env)
            check("transitions no available exits 0", r.returncode == 0, r.stderr)
            notrans_j = json.loads(r.stdout)
            check("transitions no available --json empty list", notrans_j.get("transitions") == [])

            # ── search ───────────────────────────────────────────────────────────

            print("\nsearch")
            r = run(["search", "project = PROJ AND status = 'In Progress'"], env=env)
            check("search exits 0", r.returncode == 0, r.stderr)
            check("search shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)
            check("search shows JQL in output", "PROJ" in r.stdout, r.stdout)

            r = run(["search", "project = PROJ", "--json"], env=env)
            check("search --json exits 0", r.returncode == 0, r.stderr)
            sj = json.loads(r.stdout)
            check("search --json tool field", sj.get("tool") == "search")
            check("search --json has issues", len(sj["data"]["issues"]) > 0)
            check("search --json has total", "total" in sj["data"])
            check("search --json omits unavailable Cloud total",
                  sj["data"]["total"] is None and sj["data"]["is_complete"] is True, str(sj["data"]))
            check("search --json has jql", "jql" in sj["data"])

            r = run(["search", "project = PROJ", "--limit", "10", "--json"], env=env)
            check("search --limit exits 0", r.returncode == 0, r.stderr)

            print("\nsearch: validation")
            r = run(["search", "project = PROJ", "--limit", "badval"], env=env)
            check("search --limit non-integer exits 1", r.returncode == 1)
            check("search --limit non-integer prints error", "Error:" in r.stderr, r.stderr)

            r = run(["search"], env=env)
            check("search no JQL exits 1", r.returncode == 1)
            check("search no JQL prints error", "Error:" in r.stderr, r.stderr)

            # ── board ────────────────────────────────────────────────────────────

            print("\nboard list")
            r = run(["board", "list"], env=env)
            check("board list exits 0", r.returncode == 0, r.stderr)
            check("board list shows PROJ Board", "PROJ Board" in r.stdout, r.stdout)
            check("board list shows OPS Board", "OPS Board" in r.stdout, r.stdout)
            check("board list shows board type", "scrum" in r.stdout, r.stdout)

            r = run(["board", "list", "--json"], env=env)
            check("board list --json exits 0", r.returncode == 0, r.stderr)
            bj = json.loads(r.stdout)
            check("board list --json has boards", len(bj.get("boards", [])) == 2)

            print("\nboard list --project filter")
            r = run(["board", "list", "--project", "PROJ"], env=env)
            check("board list --project exits 0", r.returncode == 0, r.stderr)
            check("board list --project shows PROJ Board", "PROJ Board" in r.stdout, r.stdout)
            check("board list --project shows only 1 board", "OPS Board" not in r.stdout, r.stdout)

            # ── sprint ───────────────────────────────────────────────────────────

            print("\nsprint list")
            r = run(["sprint", "list", "42"], env=env)
            check("sprint list exits 0", r.returncode == 0, r.stderr)
            check("sprint list shows Sprint 1", "Sprint 1" in r.stdout, r.stdout)
            check("sprint list shows active state", "active" in r.stdout, r.stdout)

            r = run(["sprint", "list", "42", "--json"], env=env)
            check("sprint list --json exits 0", r.returncode == 0, r.stderr)
            slj = json.loads(r.stdout)
            check("sprint list --json has sprints", len(slj.get("sprints", [])) == 1)
            check("sprint list --json board_id", slj.get("board_id") == "42")

            print("\nsprint list --state closed")
            r = run(["sprint", "list", "42", "--state", "closed"], env=env)
            check("sprint list --state closed exits 0", r.returncode == 0, r.stderr)
            check("sprint list --state closed shows 0 sprints", "0" in r.stdout or "No sprints" in r.stdout or r.stdout.strip() == "" or "sprints" in r.stdout.lower(), r.stdout)

            print("\nsprint active")
            r = run(["sprint", "active", "42"], env=env)
            check("sprint active exits 0", r.returncode == 0, r.stderr)
            check("sprint active shows sprint name", "Sprint 1" in r.stdout, r.stdout)
            check("sprint active shows issue count", "1 issues" in r.stdout or "issues" in r.stdout, r.stdout)
            check("sprint active shows PROJ-1", "PROJ-1" in r.stdout, r.stdout)

            r = run(["sprint", "active", "42", "--json"], env=env)
            check("sprint active --json exits 0", r.returncode == 0, r.stderr)
            saj = json.loads(r.stdout)
            check("sprint active --json has sprint", "sprint" in saj)
            check("sprint active --json has issues", len(saj.get("issues", [])) > 0)

            print("\nsprint active: no active sprint")
            r = run(["sprint", "active", "99"], env=env)
            check("sprint active no sprint exits 0 or 1", r.returncode in (0, 1))
            check("sprint active no sprint shows helpful message", "no active" in r.stdout.lower() or "no active" in r.stderr.lower() or "not found" in r.stdout.lower() or "not found" in r.stderr.lower(), r.stdout + r.stderr)

            print("\nsprint add")
            _requests_before = len(_requests)
            r = run(["sprint", "add", "PROJ-1", "--sprint", "1"], env=env)
            check("sprint add exits 0", r.returncode == 0, r.stderr)
            check("sprint add prints confirmation", "PROJ-1" in r.stdout, r.stdout)

            print("\nsprint add --json")
            r = run(["sprint", "add", "PROJ-1", "--sprint", "1", "--json"], env=env)
            check("sprint add --json exits 0", r.returncode == 0, r.stderr)
            saj2 = json.loads(r.stdout)
            check("sprint add --json has key", "key" in saj2 or "issue" in saj2)
            check("sprint add --json has sprint_id", "sprint_id" in saj2 or "sprint" in str(saj2))

            _requests_before = len(_requests)
            r = run(["sprint", "add", "PROJ-2", "--sprint", "1", "--dry-run"], env=env)
            check("sprint add --dry-run exits 0", r.returncode == 0)
            check("sprint add --dry-run shows preview", "[dry-run]" in r.stdout, r.stdout)
            new_posts = [m for m in _requests[_requests_before:] if m[0] == "POST"]
            check("sprint add --dry-run makes no HTTP request", len(new_posts) == 0)

            print("\nsprint add --dry-run --json")
            r = run(["sprint", "add", "PROJ-1", "--sprint", "1", "--dry-run", "--json"], env=env)
            check("sprint add --dry-run --json exits 0", r.returncode == 0)
            sadj = json.loads(r.stdout)
            check("sprint add --dry-run --json has dry_run=true", sadj.get("dry_run") is True)

            r = run(["sprint", "add", "PROJ-1"], env=env)
            check("sprint add missing --sprint exits 1", r.returncode == 1)

            # ── env var credentials ──────────────────────────────────────────────

            print("\nenv var credentials")
            env_no_profile = _make_env(tmp / "envtest", port, extra={
                "JIRA_URL": base_url,
                "JIRA_EMAIL": "env@example.com",
                "JIRA_API_TOKEN": "env-token",
            })
            (tmp / "envtest" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_no_profile)
            check("env var credentials: whoami exits 0", r.returncode == 0, r.stderr)
            check("env var credentials: resolves without profile", "Test User" in r.stdout, r.stdout)

            print("\nenv var credentials (bad URL)")
            env_bad_url = _make_env(tmp / "envbadurl", port, extra={
                "JIRA_URL": "ftp://example.com",
                "JIRA_EMAIL": "env@example.com",
                "JIRA_API_TOKEN": "env-token",
            })
            (tmp / "envbadurl" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_bad_url)
            check("env var credentials bad url exits 1", r.returncode == 1)
            check("env var credentials bad url prints error", "http:// or https://" in r.stderr, r.stderr)

            print("\npartial env var credentials (missing token)")
            env_partial = _make_env(tmp / "partial", port, extra={
                "JIRA_URL": base_url,
                "JIRA_EMAIL": "env@example.com",
                # JIRA_API_TOKEN intentionally omitted
            })
            (tmp / "partial" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_partial)
            check("partial env creds exits 1", r.returncode == 1)
            check("partial env creds shows helpful error", "JIRA_API_TOKEN" in r.stderr or "token" in r.stderr.lower() or "connections add" in r.stderr, r.stderr)

            print("\nper-profile env var credentials")
            env_per_profile = _make_env(tmp / "envprofile", port, extra={
                "JIRA_URL_MYCONN": base_url,
                "JIRA_EMAIL_MYCONN": "profile@example.com",
                "JIRA_API_TOKEN_MYCONN": "profile-token",
            })
            (tmp / "envprofile" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami", "--connection", "myconn"], env=env_per_profile)
            check("per-profile env var: whoami exits 0", r.returncode == 0, r.stderr)

            print("\nno credentials error")
            env_no_creds = _make_env(tmp / "nocreds", port)
            (tmp / "nocreds" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["whoami"], env=env_no_creds)
            check("no credentials exits 1", r.returncode == 1)
            check("no credentials shows helpful error", "connections add" in r.stderr or "JIRA_URL" in r.stderr, r.stderr)

            # ── server/DC mode ───────────────────────────────────────────────────

            print("\nServer/DC mode")
            run(["connections", "add", "dc2",
                 "--url", base_url,
                 "--email", "admin",
                 "--token", "pat",
                 "--server"], env=env)
            _auth_headers.clear()
            r = run(["whoami", "--connection", "dc2"], env=env)
            check("Server/DC whoami exits 0", r.returncode == 0, r.stderr)
            check("Server/DC uses Bearer PAT auth", any(h == "Bearer pat" for h in _auth_headers), str(_auth_headers))

            # Server mode uses api/2/ paths - verify via issue create ADF vs plain text
            _post_bodies.clear()
            run(["issue", "create", "PROJ",
                 "--summary", "Server issue",
                 "--description", "Plain text desc",
                 "--connection", "dc2"], env=env)
            server_create = _post_bodies.get("/rest/api/3/issue", {})
            desc_val = (server_create.get("fields") or {}).get("description", "")
            check("Server/DC sends plain-text description", isinstance(desc_val, str), str(desc_val))

            # ── connections: empty state ─────────────────────────────────────────

            print("\nconnections list: empty state")
            env_empty = _make_env(tmp / "emptyconn", port)
            (tmp / "emptyconn" / "home").mkdir(parents=True, exist_ok=True)
            r = run(["connections", "list"], env=env_empty)
            check("connections list empty exits 0", r.returncode == 0, r.stderr)
            check("connections list empty shows helpful message", "No" in r.stdout and "profile" in r.stdout.lower(), r.stdout)
            check("connections list empty shows add command", "connections add" in r.stdout, r.stdout)

            print("\nconnections add: URL without http")
            r = run(["connections", "add", "badurl",
                     "--url", "ftp://bad.example.com",
                     "--email", "x@x.com",
                     "--token", "t"], env=env)
            check("connections add non-http URL exits 1", r.returncode == 1)
            check("connections add non-http URL prints error", "http" in r.stderr.lower(), r.stderr)

            print("\nconnections remove: removing default clears default")
            # Work is currently the default; remove it and check default becomes next profile
            data_before = json.loads(meta_file.read_text())
            default_before = data_before.get("default")
            check("default before remove is 'work'", default_before == "work")
            run(["connections", "remove", "work"], env=env)
            data_after = json.loads(meta_file.read_text())
            check("after removing default, default changes", data_after.get("default") != "work")
            # Restore 'work' for remaining tests
            run(["connections", "add", "work",
                 "--url", base_url, "--email", "test@example.com",
                 "--token", "tok-secret", "--default"], env=env)

            # ── user find: --connection flag ordering ────────────────────────────

            print("\nuser find: --connection before positional query")
            run(["connections", "add", "dc5",
                 "--url", base_url, "--email", "admin", "--token", "pat", "--server"], env=env)
            _requests.clear()
            r = run(["user", "find", "--connection", "dc5", "alice"], env=env)
            check("user find --connection before query exits 0", r.returncode == 0, r.stderr)
            check("user find --connection before query shows results", "Alice" in r.stdout, r.stdout)
            # Verify it used ?username= (Server/DC), proving --connection was parsed correctly
            ureqs = [path for m, path in _requests if m == "GET" and "user/search" in path]
            check("user find --connection before query used correct connection", any("username=" in p for p in ureqs), str(ureqs))
            run(["connections", "remove", "dc5"], env=env)

            # ── issue list: --mine + --assignee interaction ──────────────────────

            print("\nissue list: --mine then --assignee (last wins)")
            _requests.clear()
            r = run(["issue", "list", "PROJ", "--mine", "--assignee", "alice@example.com"], env=env)
            check("--mine then --assignee exits 0", r.returncode == 0, r.stderr)
            mine_then_ass = (_post_bodies.get("/rest/api/3/search/jql") or {}).get("jql", "")
            # last flag (--assignee alice) wins → should NOT have currentUser() in JQL
            check("--mine then --assignee: explicit assignee wins", "currentUser" not in mine_then_ass, mine_then_ass)

            _requests.clear()
            r = run(["issue", "list", "PROJ", "--assignee", "alice@example.com", "--mine"], env=env)
            check("--assignee then --mine exits 0", r.returncode == 0, r.stderr)
            ass_then_mine = (_post_bodies.get("/rest/api/3/search/jql") or {}).get("jql", "")
            # last flag (--mine) wins → should have currentUser() in JQL
            check("--assignee then --mine: --mine wins", "currentUser" in ass_then_mine, ass_then_mine)

            # ── issue create: duplicate labels ───────────────────────────────────

            print("\nissue create: duplicate labels")
            _post_bodies.clear()
            r = run(["issue", "create", "PROJ",
                     "--summary", "Dedup test",
                     "--label", "frontend",
                     "--label", "frontend",
                     "--label", "backend"], env=env)
            check("issue create duplicate labels exits 0", r.returncode == 0, r.stderr)
            dup_body = _post_bodies.get("/rest/api/3/issue", {})
            dup_labels = (dup_body.get("fields") or {}).get("labels", [])
            # The code sends what was passed; Jira deduplicates server-side, but test what we send
            check("issue create duplicate labels sends labels list", len(dup_labels) >= 2, str(dup_labels))

            # ── issue link ───────────────────────────────────────────────────────

            print("\nissue link")
            _requests.clear()
            _post_bodies.clear()
            r = run(["issue", "link", "PROJ-3", "--to", "PROJ-1", "--type", "blocks", "--json"], env=env)
            check("issue link exits 0", r.returncode == 0, r.stderr)
            link_payload = json.loads(r.stdout)
            check("issue link json from field", link_payload["from"] == "PROJ-3", r.stdout)
            check("issue link json to field", link_payload["to"] == "PROJ-1", r.stdout)
            check("issue link json type field", link_payload["link_type"] == "blocks", r.stdout)
            link_body = _post_bodies.get("/rest/api/3/issueLink", {})
            check("issue link sends canonical Jira type", (link_body.get("type") or {}).get("name") == "Blocks", str(link_body))
            check("issue link sends outward issue", (link_body.get("outwardIssue") or {}).get("key") == "PROJ-3", str(link_body))
            check("issue link sends inward issue", (link_body.get("inwardIssue") or {}).get("key") == "PROJ-1", str(link_body))

            _requests.clear()
            r = run(["issue", "link", "PROJ-3", "--to", "PROJ-1", "--type", "is blocked by", "--dry-run", "--json"], env=env)
            check("issue link dry-run exits 0", r.returncode == 0, r.stderr)
            dry_link = json.loads(r.stdout)
            check("issue link dry-run reports relation", dry_link["link_type"] == "is blocked by", r.stdout)
            check("issue link dry-run reverses outward issue", dry_link["outward_issue"] == "PROJ-1", r.stdout)
            check("issue link dry-run reverses inward issue", dry_link["inward_issue"] == "PROJ-3", r.stdout)
            check("issue link dry-run makes no HTTP request", not any(path == "/rest/api/3/issueLink" for _, path in _requests), str(_requests))

            # ── issue delete ────────────────────────────────────────────────────

            print("\nissue delete")
            _requests.clear()
            r = run(["issue", "delete", "PROJ-3", "--dry-run", "--json"], env=env)
            check("issue delete dry-run exits 0", r.returncode == 0, r.stderr)
            delete_preview = json.loads(r.stdout)
            check("issue delete dry-run action", delete_preview["action"] == "issue_delete", r.stdout)
            check("issue delete dry-run key", delete_preview["key"] == "PROJ-3", r.stdout)
            check("issue delete dry-run makes no HTTP request", not any(path.endswith("/PROJ-3") for _, path in _requests), str(_requests))

            _requests.clear()
            r = run(["issue", "delete", "PROJ-3", "--confirm", "--json"], env=env)
            check("issue delete exits 0", r.returncode == 0, r.stderr)
            delete_payload = json.loads(r.stdout)
            check("issue delete json key", delete_payload["key"] == "PROJ-3", r.stdout)
            check("issue delete json deleted", delete_payload["deleted"] is True, r.stdout)
            check("issue delete sent DELETE", any(m == "DELETE" and path == "/rest/api/3/issue/PROJ-3" for m, path in _requests), str(_requests))

            # ── issue edit: all three fields ─────────────────────────────────────

            print("\nissue edit: all three fields simultaneously")
            _put_bodies.clear()
            r = run(["issue", "edit", "PROJ-1",
                     "--summary", "New summary",
                     "--description", "New description",
                     "--priority", "Highest"], env=env)
            check("issue edit all fields exits 0", r.returncode == 0, r.stderr)
            all_edit_body = _put_bodies.get("/rest/api/3/issue/PROJ-1", {})
            all_fields = all_edit_body.get("fields", {})
            check("issue edit all fields: summary sent", all_fields.get("summary") == "New summary")
            check("issue edit all fields: description sent", all_fields.get("description") is not None)
            check("issue edit all fields: priority sent", (all_fields.get("priority") or {}).get("name") == "Highest")

            # ── issue label: add and remove same label simultaneously ────────────

            print("\nissue label: add and remove same label")
            _put_bodies.clear()
            r = run(["issue", "label", "PROJ-1", "--add", "backend", "--remove", "backend"], env=env)
            # remove runs first (filters current), then add re-adds it → net neutral or add wins
            check("issue label add+remove same label exits 0", r.returncode == 0, r.stderr)

            # ── issue transition: missing --to flag ──────────────────────────────

            print("\nissue transition: missing --to")
            r = run(["issue", "transition", "PROJ-1"], env=env)
            check("issue transition no --to exits 1", r.returncode == 1)
            check("issue transition no --to shows error", "Error:" in r.stderr, r.stderr)
            check("issue transition no --to mentions transitions command", "transitions" in r.stderr.lower(), r.stderr)

            # ── unknown flag rejection ───────────────────────────────────────────

            print("\nunknown flag rejection")
            _requests.clear()
            r = run(["issue", "delete", "PROJ-3", "--confirm", "--dry-rnu"], env=env)
            check("issue delete typo flag exits 1", r.returncode == 1)
            check("issue delete typo flag reports unknown flag", "Unknown flag" in r.stderr, r.stderr)
            check("issue delete typo flag sends no DELETE", not any(m == "DELETE" for m, _ in _requests), str(_requests))

            r = run(["issue", "create", "PROJ", "--summary", "x", "--dry-rnu"], env=env)
            check("issue create typo flag exits 1", r.returncode == 1)
            check("issue create typo flag reports unknown flag", "Unknown flag" in r.stderr, r.stderr)

            # ── unknown subcommand errors ────────────────────────────────────────

            print("\nunknown subcommand errors")
            r = run(["issue", "bogus"], env=env)
            check("issue bogus subcommand exits 1", r.returncode == 1)
            check("issue bogus subcommand lists valid commands", "view" in r.stderr or "create" in r.stderr, r.stderr)

            r = run(["board", "bogus"], env=env)
            check("board bogus subcommand exits 1", r.returncode == 1)

            r = run(["sprint", "bogus"], env=env)
            check("sprint bogus subcommand exits 1", r.returncode == 1)
            check("sprint bogus subcommand lists valid commands", "list" in r.stderr or "active" in r.stderr, r.stderr)

            r = run(["connections", "bogus"], env=env)
            check("connections bogus subcommand exits 1", r.returncode == 1)
            check("connections bogus subcommand lists valid subcommands", "add" in r.stderr or "list" in r.stderr, r.stderr)

            r = run_wrapper(["jira", "completely-unknown-cmd"], env=env)
            check("top-level unknown command exits 1", r.returncode == 1)
            check("top-level unknown command mentions --help", "help" in r.stderr.lower(), r.stderr)

            r = run_wrapper(["jira", "completely-unknown-cmd", "--json"], env=env)
            check("top-level unknown command --json exits 1", r.returncode == 1)
            unknown_json = json.loads(r.stdout)
            check("top-level unknown command --json has error", unknown_json.get("success") is False and "Unknown command" in unknown_json.get("error", ""), r.stdout)

            # ── search --fields ──────────────────────────────────────────────────

            print("\nsearch --fields")
            r = run(["search", "project = PROJ", "--fields", "summary,status", "--json"], env=env)
            check("search --fields exits 0", r.returncode == 0, r.stderr)
            sfj = json.loads(r.stdout)
            check("search --fields returns data", "data" in sfj)

            # ── sprint list: no-arg errors ───────────────────────────────────────

            print("\nsprint list/active: missing board ID")
            r = run(["sprint", "list"], env=env)
            check("sprint list no board ID exits 1", r.returncode == 1)

            r = run(["sprint", "active"], env=env)
            check("sprint active no board ID exits 1", r.returncode == 1)

            # ── issue subcommand: no key errors ──────────────────────────────────

            print("\nissue commands: missing issue key")
            r = run(["issue", "view"], env=env)
            check("issue view no key exits 1", r.returncode == 1)

            r = run(["issue", "comment", "PROJ-1", "--body", ""], env=env)
            check("issue comment empty --body exits 1", r.returncode == 1)

            r = run(["issue", "assign", "PROJ-1", "--to", ""], env=env)
            check("issue assign empty --to exits 1", r.returncode == 1)

            r = run(["issue", "list"], env=env)
            check("issue list no project key exits 1", r.returncode == 1)

            r = run(["issue", "create"], env=env)
            check("issue create no project key exits 1", r.returncode == 1)

            # ── whoami: corrupted connections.json ───────────────────────────────

            print("\nwhoami: corrupted connections.json (graceful fallback)")
            env_corrupt = _make_env(tmp / "corrupt", port)
            corrupt_home = tmp / "corrupt" / "home"
            corrupt_home.mkdir(parents=True, exist_ok=True)
            (corrupt_home / "jira").mkdir(parents=True, exist_ok=True)
            (corrupt_home / "jira" / "connections.json").write_text("{ not valid json !! }")
            # Should fall back to env vars gracefully when connections.json is unreadable
            env_corrupt["JIRA_URL"] = base_url
            env_corrupt["JIRA_EMAIL"] = "fallback@example.com"
            env_corrupt["JIRA_API_TOKEN"] = "fallback-token"
            r = run(["whoami"], env=env_corrupt)
            check("whoami with corrupted connections.json exits 0 (falls back to env)", r.returncode == 0, r.stderr)

            # ── connections add: empty values ────────────────────────────────────

            print("\nconnections add: empty or invalid values")
            r = run(["connections", "add", "emptyval",
                     "--url", "",
                     "--email", "x@x.com",
                     "--token", "t"], env=env)
            check("connections add empty URL exits 1", r.returncode == 1)

            r = run(["connections", "add", "emptyval",
                     "--url", base_url,
                     "--email", "",
                     "--token", "t"], env=env)
            check("connections add empty email exits 1", r.returncode == 1)

            r = run(["connections", "add", "emptyval",
                     "--url", base_url,
                     "--email", "x@x.com",
                     "--token", ""], env=env)
            check("connections add empty token exits 1", r.returncode == 1)

            # ── issue view: issue with no description ────────────────────────────

            print("\nissue view: issue with no description (plain text)")
            r = run(["issue", "view", "PROJ-NOASSIGN"], env=env)
            check("issue view no description exits 0", r.returncode == 0, r.stderr)
            check("issue view no description no crash on None", "PROJ-NOASSIGN" in r.stdout, r.stdout)

            # ── whoami: no args to top-level dispatch ────────────────────────────

            print("\ntop-level dispatch: no args")
            r = run_wrapper(["jira"], env=env)
            check("no args exits 0", r.returncode == 0)
            check("no args shows usage", "agent-do jira" in r.stdout or "Usage" in r.stdout, r.stdout)

        finally:
            server.shutdown()
            server.server_close()

    # ── dispatch test (agent-do jira --help) ─────────────────────────────────────
    print("\nagent-do dispatch")
    r = subprocess.run(
        [str(AGENT_DO), "jira", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    check("agent-do jira --help exits 0", r.returncode == 0, r.stderr)
    check("agent-do jira --help shows CONNECTION MANAGEMENT", "CONNECTION MANAGEMENT" in r.stdout, r.stdout)
    check("agent-do jira --help shows issue commands", "issue view" in r.stdout, r.stdout)
    check("agent-do jira --help shows delete", "issue delete" in r.stdout, r.stdout)
    check("agent-do jira --help shows sprint", "sprint" in r.stdout, r.stdout)
    check("agent-do jira --help shows user find", "user find" in r.stdout, r.stdout)
    check("agent-do jira --help shows --mine", "--mine" in r.stdout, r.stdout)
    check("agent-do jira --help shows --sprint", "--sprint" in r.stdout, r.stdout)

    print("\nregistry metadata")
    reg = registry.load_registry()
    jira_info = reg["tools"]["jira"]
    jira_commands = jira_info["commands"]
    check("registry documents issue link", "issue link" in jira_commands)
    check("registry documents issue delete", "issue delete" in jira_commands)
    check("registry documents user find", "user find" in jira_commands)
    check("registry no longer has routing.command_concurrency",
          "command_concurrency" not in (jira_info.get("routing") or {}))
    jira_contracts = registry.get_tool_contracts(jira_info)
    check("registry contracts put issue link in write beats",
          "issue link" in jira_contracts.get("interact", []) and "issue link" in jira_contracts.get("save", []))
    jira_attrs = registry.get_tool_contract_attributes(jira_info)
    check("registry contracts mark issue delete destructive",
          "destructive" in jira_attrs.get("issue delete", []))
    check("registry contracts mark connections add sensitive",
          "sensitive" in jira_attrs.get("connections add", []))

    print(f"\nResults: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
