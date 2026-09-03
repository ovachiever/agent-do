#!/usr/bin/env python3
"""agent-jira backend: connection profiles, issue management, search, sprints."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DRY_RUN_EXIT_CODE = 0


# ── helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _home() -> Path:
    return Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))


def _err(msg: str, code: int = 1) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(code)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, default=str))


def _validate_profile_name(name: str) -> None:
    """Reject names that would cause path traversal or filesystem issues."""
    if not name or not name.strip():
        _err("Profile name cannot be empty")
    if name != name.strip():
        _err(f"Profile name cannot have leading or trailing whitespace: {name!r}")
    if "/" in name or "\\" in name or "\x00" in name:
        _err(f"Profile name contains invalid characters ('/', '\\\\', or null): {name!r}")
    if name.startswith("."):
        _err(f"Profile name cannot start with '.': {name!r}")
    if len(name) > 64:
        _err(f"Profile name too long (max 64 chars): {name!r}")


def _parse_limit(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        _err(f"--limit must be an integer, got: {value!r}")
        return 0  # unreachable
    if n < 0:
        _err(f"--limit must be non-negative, got: {n}")
    return n


def _validate_base_url(url: str) -> str:
    """Return a normalized Jira base URL or fail fast on unsafe schemes."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        _err(f"Jira base URL must start with http:// or https://, got: {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def _reject_unknown_flags(
    argv: list[str],
    *,
    bool_flags: set[str] | None = None,
    value_flags: set[str] | None = None,
) -> None:
    """Reject unknown or valueless flags before a typo can turn into a write."""
    bool_flags = bool_flags or set()
    value_flags = value_flags or set()
    i = 0
    while i < len(argv):
        token = argv[i]
        if not token.startswith("--"):
            i += 1
            continue
        if token in value_flags:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                _err(f"{token} requires a value")
            i += 2
        elif token in bool_flags:
            i += 1
        else:
            _err(f"Unknown flag: {token}")


def _jql_quote(value: str) -> str:
    """Quote a JQL string literal, preserving backslashes and quotes."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ── credential storage ─────────────────────────────────────────────────────────

def _creds_dir() -> Path:
    return _home() / "jira" / ".creds"


def _profiles_path() -> Path:
    return _home() / "jira" / "connections.json"


def _creds_store(profile: str, url: str, email: str, token: str) -> None:
    d = _creds_dir()
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    payload = json.dumps({"url": url, "email": email, "token": token}).encode()
    target = d / profile
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.close(fd)
        os.replace(tmp, target)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _creds_get(profile: str) -> dict[str, str] | None:
    """Return {url, email, token} for a profile, checking env vars first."""
    p = profile.upper().replace("-", "_")
    env_url   = os.environ.get(f"JIRA_URL_{p}")
    env_email = os.environ.get(f"JIRA_EMAIL_{p}")
    env_token = os.environ.get(f"JIRA_API_TOKEN_{p}")
    if env_url and env_email and env_token:
        return {"url": env_url, "email": env_email, "token": env_token}
    f = _creds_dir() / profile
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _err(f"Credentials file for profile '{profile}' is corrupted. "
                 f"Re-add with: agent-do jira connections add {profile} --url ... --email ... --token ...")
    return None


def _creds_delete(profile: str) -> None:
    try:
        (_creds_dir() / profile).unlink()
    except FileNotFoundError:
        pass


def _load_profiles() -> dict[str, Any]:
    p = _profiles_path()
    if not p.exists():
        return {"profiles": {}, "default": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"profiles": {}, "default": None}


def _save_profiles(data: dict[str, Any]) -> None:
    p = _profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, json.dumps(data, indent=2).encode())
        os.close(fd)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── HTTP client ────────────────────────────────────────────────────────────────

class JiraClient:
    def __init__(self, url: str, email: str, token: str, *, server: bool = False):
        self.base = _validate_base_url(url)
        self.email = email
        self.token = token
        self.server = server
        self.api_version = "2" if server else "3"
        raw = f"{email}:{token}".encode()
        self._basic_auth = "Basic " + base64.b64encode(raw).decode()
        self._auth = "Bearer " + token if server else self._basic_auth

    def _api(self, path: str) -> str:
        return f"{self.base}/rest/api/{self.api_version}/{path.lstrip('/')}"

    def _agile(self, path: str) -> str:
        return f"{self.base}/rest/agile/1.0/{path.lstrip('/')}"

    def _search(self) -> str:
        # Jira Cloud removed GET /rest/api/3/search; use the enhanced search endpoint.
        return "search" if self.server else "search/jql"

    def request(self, method: str, url: str, *, body: Any = None, suppress_errors: bool = False) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": self._auth,
            "Accept": "application/json",
        }
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and self.server and self._auth != self._basic_auth:
                self._auth = self._basic_auth
                return self.request(method, url, body=body, suppress_errors=suppress_errors)
            body_bytes = exc.read()
            try:
                detail = json.loads(body_bytes)
                messages = detail.get("errorMessages") or []
                errors = detail.get("errors") or {}
                msg = "; ".join(messages + [f"{k}: {v}" for k, v in errors.items()])
                if not msg:
                    msg = detail.get("message") or str(detail)
            except (json.JSONDecodeError, AttributeError):
                msg = body_bytes.decode(errors="replace")[:200]
            if suppress_errors:
                return {"_error": msg, "status": exc.code}
            if exc.code == 401:
                _err(f"Jira API 401 Unauthorized — check your API token and email. {msg}".rstrip(". "))
            elif exc.code == 403:
                _err(f"Jira API 403 Forbidden — your account lacks permission for this action. {msg}".rstrip(". "))
            elif exc.code == 429:
                _err(f"Jira API 429 Too Many Requests — slow down or check rate limits. {msg}".rstrip(". "))
            else:
                _err(f"Jira API {exc.code} {exc.reason}: {msg}")
        except urllib.error.URLError as exc:
            _err(f"Could not connect to Jira: {exc.reason}")

    def search(self, jql: str, *, max_results: int, fields: str | None = None,
               suppress_errors: bool = False) -> Any:
        params: dict[str, Any] = {"jql": jql, "maxResults": max_results}
        if fields is not None:
            params["fields"] = fields if self.server else [f.strip() for f in fields.split(",") if f.strip()]
        if self.server:
            return self.get(self._search(), params=params, suppress_errors=suppress_errors)
        return self.post(self._search(), params, suppress_errors=suppress_errors)

    def get(self, path: str, *, params: dict[str, Any] | None = None, agile: bool = False,
            suppress_errors: bool = False) -> Any:
        base_url = self._agile(path) if agile else self._api(path)
        if params:
            base_url += "?" + urllib.parse.urlencode(
                {k: v for k, v in params.items() if v is not None}
            )
        return self.request("GET", base_url, suppress_errors=suppress_errors)

    def post(self, path: str, body: Any, *, agile: bool = False, suppress_errors: bool = False) -> Any:
        url = self._agile(path) if agile else self._api(path)
        return self.request("POST", url, body=body, suppress_errors=suppress_errors)

    def put(self, path: str, body: Any, *, agile: bool = False) -> Any:
        url = self._agile(path) if agile else self._api(path)
        return self.request("PUT", url, body=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", self._api(path))

    def _text_body(self, text: str) -> Any:
        """Return description/comment body in the correct format for this API version."""
        if self.server:
            return text
        # Cloud uses Atlassian Document Format (ADF)
        return {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": text}]}
            ],
        }

    def _extract_text(self, body: Any) -> str:
        """Extract plain text from ADF or plain string."""
        if isinstance(body, str):
            return body
        if isinstance(body, dict):
            parts: list[str] = []

            def visit(node: Any) -> None:
                if not isinstance(node, dict):
                    return
                if node.get("type") == "text":
                    parts.append(str(node.get("text", "")))
                for child in node.get("content") or []:
                    visit(child)

            visit(body)
            return " ".join(parts)
        return ""


def _get_client(connection: str | None) -> JiraClient:
    """Resolve a connection profile and return a JiraClient."""
    data = _load_profiles()

    # Env-var fallback (no profile configured)
    env_url   = os.environ.get("JIRA_URL", "")
    env_email = os.environ.get("JIRA_EMAIL", "")
    env_token = os.environ.get("JIRA_API_TOKEN", "")

    if connection:
        creds = _creds_get(connection)
        if not creds:
            _err(f"Profile '{connection}' not found. Run: agent-do jira connections add {connection} ...")
        meta = data["profiles"].get(connection, {})
        try:
            return JiraClient(creds["url"], creds["email"], creds["token"],
                              server=meta.get("server", False))
        except ValueError as exc:
            _err(str(exc))

    default = data.get("default")
    if default:
        creds = _creds_get(default)
        if creds:
            meta = data["profiles"].get(default, {})
            try:
                return JiraClient(creds["url"], creds["email"], creds["token"],
                                  server=meta.get("server", False))
            except ValueError as exc:
                _err(str(exc))

    if env_url and env_email and env_token:
        try:
            return JiraClient(env_url, env_email, env_token)
        except ValueError as exc:
            _err(str(exc))

    _err(
        "No Jira connection configured.\n"
        "  agent-do jira connections add <name> --url <url> --email <email> --token-stdin\n"
        "Or set JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN environment variables."
    )


def _resolve_assignee(client: JiraClient, assignee: str) -> str:
    """Resolve Cloud email addresses to account IDs when possible."""
    if client.server or "@" not in assignee:
        return assignee

    users = client.get("user/search", params={"query": assignee, "maxResults": 10})
    if not isinstance(users, list):
        users = []

    def _email(u: dict[str, Any]) -> str:
        return (u.get("emailAddress") or "").strip().lower()

    matches = [u for u in users if isinstance(u, dict) and _email(u) == assignee.lower()]
    if not matches and len(users) == 1 and isinstance(users[0], dict):
        matches = [users[0]]

    if not matches:
        found = ", ".join(
            f"{u.get('displayName') or u.get('accountId') or u.get('name') or 'unknown'} <{u.get('emailAddress') or ''}>"
            for u in users
            if isinstance(u, dict)
        )
        suffix = f" (found: {found})" if found else ""
        _err(f"Could not resolve Jira user from email {assignee!r}{suffix}")

    user = matches[0]
    return user.get("accountId") or user.get("name") or assignee


# ── formatting helpers ─────────────────────────────────────────────────────────

def _fmt_date(iso: str | None) -> str:
    if not iso:
        return ""
    return iso[:10]


def _fmt_issue(issue: dict[str, Any], client: JiraClient) -> dict[str, Any]:
    f = issue.get("fields") or {}
    return {
        "key": issue.get("key"),
        "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "type": (f.get("issuetype") or {}).get("name", ""),
        "priority": (f.get("priority") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName") or (f.get("assignee") or {}).get("emailAddress", ""),
        "reporter": (f.get("reporter") or {}).get("displayName", ""),
        "labels": f.get("labels") or [],
        "created": _fmt_date(f.get("created")),
        "updated": _fmt_date(f.get("updated")),
        "url": f"{client.base}/browse/{issue.get('key')}",
        "description": client._extract_text(f.get("description")),
    }


def _normalize_issue_link_type(raw: str) -> tuple[str, str]:
    """Return (canonical_link_type, relation_label) for common Jira link phrases."""
    value = " ".join(raw.strip().lower().replace("_", " ").replace("-", " ").split())
    mapping = {
        "blocks": ("Blocks", "blocks"),
        "block": ("Blocks", "blocks"),
        "is blocked by": ("Blocks", "is blocked by"),
        "blocked by": ("Blocks", "is blocked by"),
        "clones": ("Cloners", "clones"),
        "clone": ("Cloners", "clones"),
        "is cloned by": ("Cloners", "is cloned by"),
        "cloned by": ("Cloners", "is cloned by"),
        "duplicates": ("Duplicates", "duplicates"),
        "duplicate": ("Duplicates", "duplicates"),
        "is duplicated by": ("Duplicates", "is duplicated by"),
        "duplicated by": ("Duplicates", "is duplicated by"),
        "relates to": ("Relates", "relates to"),
        "relates": ("Relates", "relates to"),
    }
    if value not in mapping:
        _err(
            f"Unknown issue link type: {raw!r}. Use one of: blocks, is blocked by, clones, is cloned by, duplicates, is duplicated by, relates to"
        )
    return mapping[value]


# ── connections ────────────────────────────────────────────────────────────────

def cmd_connections(argv: list[str]) -> None:
    sub = argv[0] if argv else "list"
    rest = argv[1:]

    if sub in ("list", "ls"):
        _reject_unknown_flags(rest, bool_flags={"--json"})
        json_mode = "--json" in rest
        data = _load_profiles()
        profiles = data.get("profiles", {})
        default = data.get("default")
        if json_mode:
            _print_json({
                "profiles": [
                    {"name": name, "default": name == default, **profile}
                    for name, profile in profiles.items()
                ],
                "default": default,
            })
            return
        if not profiles:
            print("No Jira connection profiles saved.")
            print("  agent-do jira connections add <name> --url <url> --email <email> --token-stdin")
            return
        for name, p in profiles.items():
            marker = " *" if name == default else ""
            kind = "Server" if p.get("server") else "Cloud"
            url = p.get("url", "")
            added = p.get("added_at", "")[:10]
            print(f"  {name}{marker}  [{kind}]  {url}  {added}  (credentials stored securely)")

    elif sub == "add":
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections add <name> --url <url> --email <email> --token-stdin")
        _validate_profile_name(name)
        url = email = token = ""
        is_server = is_default = False
        token_from_stdin = False
        _reject_unknown_flags(
            rest[1:],
            bool_flags={"--server", "--default", "--token-stdin", "--json"},
            value_flags={"--url", "--email", "--token"},
        )
        i = 1
        while i < len(rest):
            if rest[i] == "--url" and i + 1 < len(rest):
                url = rest[i + 1].strip()
                i += 2
            elif rest[i] == "--email" and i + 1 < len(rest):
                email = rest[i + 1].strip()
                i += 2
            elif rest[i] == "--token" and i + 1 < len(rest):
                token = rest[i + 1].strip()
                i += 2
            elif rest[i] == "--token-stdin":
                token_from_stdin = True
                i += 1
            elif rest[i] == "--server":
                is_server = True
                i += 1
            elif rest[i] == "--default":
                is_default = True
                i += 1
            else:
                i += 1
        if not url:
            _err("--url is required")
        if not email:
            _err("--email is required")
        if token and token_from_stdin:
            _err("Use only one of --token or --token-stdin")
        if token_from_stdin:
            token = sys.stdin.read().strip()
        if not token:
            _err("--token-stdin is required (or --token for legacy interactive use)")
        url = _validate_base_url(url)

        data = _load_profiles()
        overwriting = name in data["profiles"]
        data["profiles"][name] = {
            "url": url,
            "server": is_server,
            "added_at": _now(),
        }
        if is_default or not data.get("default"):
            data["default"] = name
        _creds_store(name, url, email, token)
        _save_profiles(data)
        kind = "Server/DC" if is_server else "Cloud"
        verb = "Updated" if overwriting else "Saved"
        if "--json" in rest:
            _print_json({"name": name, "url": url, "server": is_server,
                         "default": data["default"] == name, "updated": overwriting})
        else:
            print(f"{verb} profile '{name}' [{kind}]  {url}"
                  + (" (default)" if data["default"] == name else ""))

    elif sub == "remove":
        _reject_unknown_flags(rest[1:], bool_flags={"--json"})
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections remove <name>")
        data = _load_profiles()
        if name not in data["profiles"]:
            _err(f"Profile '{name}' not found. Use 'connections list' to see saved profiles.")
        del data["profiles"][name]
        _creds_delete(name)
        if data.get("default") == name:
            data["default"] = next(iter(data["profiles"]), None)
        _save_profiles(data)
        if "--json" in rest:
            _print_json({"name": name, "removed": True, "default": data.get("default")})
        else:
            print(f"Removed profile '{name}'")

    elif sub == "set-default":
        _reject_unknown_flags(rest[1:], bool_flags={"--json"})
        name = rest[0] if rest else None
        if not name:
            _err("Usage: connections set-default <name>")
        data = _load_profiles()
        if name not in data["profiles"]:
            _err(f"Profile '{name}' not found. Use 'connections list' to see saved profiles.")
        data["default"] = name
        _save_profiles(data)
        if "--json" in rest:
            _print_json({"default": name})
        else:
            print(f"Default connection set to '{name}'")

    else:
        _err(f"Unknown connections subcommand: {sub!r}. Use: list, add, remove, set-default")


# ── whoami ─────────────────────────────────────────────────────────────────────

def cmd_whoami(argv: list[str]) -> None:
    connection = None
    json_mode = False
    _reject_unknown_flags(argv, bool_flags={"--json"}, value_flags={"--connection"})
    i = 0
    while i < len(argv):
        if argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1
    client = _get_client(connection)
    data = client.get("myself")
    if json_mode:
        _print_json(data)
    else:
        print(f"Account: {data.get('displayName')} <{data.get('emailAddress')}>")
        print(f"ID:      {data.get('accountId') or data.get('name')}")
        print(f"Jira:    {client.base}")


# ── snapshot ───────────────────────────────────────────────────────────────────

def cmd_snapshot(argv: list[str]) -> None:
    connection = None
    json_mode = False
    _reject_unknown_flags(argv, bool_flags={"--json"}, value_flags={"--connection"})
    i = 0
    while i < len(argv):
        if argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            i += 1
    client = _get_client(connection)
    projects_data = client.get("project", params={"expand": "description"})
    projects = []
    for p in (projects_data or []):
        try:
            jql = f"project = {_jql_quote(str(p['key']))} AND statusCategory != Done"
            if client.server:
                result = client.search(jql, max_results=0, suppress_errors=True)
                open_count = -1 if result.get("_error") else result.get("total", 0)
            else:
                result = client.post("search/approximate-count", {"jql": jql}, suppress_errors=True)
                open_count = -1 if result.get("_error") else result.get("count", -1)
        except Exception:
            open_count = -1
        projects.append({
            "key": p.get("key"),
            "name": p.get("name"),
            "type": p.get("projectTypeKey"),
            "open_issues": open_count,
        })
    payload = {
        "tool": "snapshot",
        "timestamp": _now(),
        "data": {"project_count": len(projects), "projects": projects},
    }
    if json_mode:
        _print_json(payload)
    else:
        print(f"Jira: {client.base}  Projects: {len(projects)}")
        for p in projects:
            open_str = str(p["open_issues"]) if p["open_issues"] >= 0 else "?"
            print(f"  {p['key']:<12} {p['name']:<40} {open_str} open")


# ── users ──────────────────────────────────────────────────────────────────────

def cmd_user(argv: list[str]) -> None:
    """Find Jira users by display name, email, or username."""
    if not argv:
        _err("Usage: user find <query>  (name, email, or account ID fragment)")

    # Support: user find <query>  OR  user <query>  (shorthand)
    if argv[0] == "find":
        rest = argv[1:]
    else:
        rest = argv

    if not rest:
        _err("Usage: user find <query>  (name, email, or account ID fragment)")

    _reject_unknown_flags(rest, bool_flags={"--json"}, value_flags={"--email", "--query", "--connection"})
    query = None
    i = 0
    while i < len(rest):
        if rest[i] in ("--email", "--query") and i + 1 < len(rest):
            query = rest[i + 1]
            i += 2
        elif rest[i] == "--connection" and i + 1 < len(rest):
            i += 2  # skip; _parse_common handles it
        elif rest[i].startswith("-"):
            i += 1  # skip boolean flags (e.g. --json)
        elif query is None:
            query = rest[i]
            i += 1
        else:
            i += 1

    if not query:
        _err("Usage: user find <query>  (name, email, or account ID fragment)")

    connection, json_mode, _ = _parse_common(rest)
    client = _get_client(connection)

    if client.server:
        users = client.get("user/search", params={"username": query, "maxResults": 10})
    else:
        users = client.get("user/search", params={"query": query, "maxResults": 10})

    if not isinstance(users, list):
        users = []

    if json_mode:
        _print_json({"users": users})
    else:
        if not users:
            print(f"No users found matching: {query!r}")
            return
        for u in users:
            account_id = u.get("accountId") or u.get("name", "")
            display = u.get("displayName", "")
            email_addr = u.get("emailAddress", "")
            print(f"  {account_id:<36}  {display:<30}  <{email_addr}>")


# ── issues ─────────────────────────────────────────────────────────────────────

def cmd_issue(argv: list[str]) -> None:
    sub = argv[0] if argv else ""
    rest = argv[1:]
    dispatch = {
        "view": _issue_view,
        "list": _issue_list,
        "create": _issue_create,
        "link": _issue_link,
        "delete": _issue_delete,
        "comment": _issue_comment,
        "assign": _issue_assign,
        "transition": _issue_transition,
        "label": _issue_label,
        "edit": _issue_edit,
    }
    fn = dispatch.get(sub)
    if not fn:
        _err(f"Unknown issue subcommand: {sub!r}. Use: view, list, create, link, delete, comment, assign, transition, label, edit")
    fn(rest)


def _parse_common(argv: list[str], *, start: int = 0) -> tuple[str | None, bool, list[str]]:
    """Parse --connection and --json flags, return (connection, json_mode, remaining)."""
    connection = None
    json_mode = False
    remaining = []
    i = start
    while i < len(argv):
        if argv[i] == "--connection" and i + 1 < len(argv):
            connection = argv[i + 1]
            i += 2
        elif argv[i] == "--json":
            json_mode = True
            i += 1
        else:
            remaining.append(argv[i])
            i += 1
    return connection, json_mode, remaining


def _issue_view(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue view <ISSUE-KEY> [--comments] [--json] [--connection <name>]")
    _reject_unknown_flags(argv[1:], bool_flags={"--comments", "--json"}, value_flags={"--connection"})
    key = argv[0]
    show_comments = "--comments" in argv
    connection, json_mode, _ = _parse_common(argv, start=1)
    client = _get_client(connection)
    expand = "renderedFields,names,changelog"
    if show_comments:
        expand += ",comment"
    issue = client.get(f"issue/{key}", params={"expand": expand})
    fmt = _fmt_issue(issue, client)
    if show_comments:
        comments = []
        for c in (((issue.get("fields") or {}).get("comment") or {}).get("comments") or []):
            comments.append({
                "author": (c.get("author") or {}).get("displayName", ""),
                "created": _fmt_date(c.get("created")),
                "body": client._extract_text(c.get("body")),
            })
        fmt["comments"] = comments
    if json_mode:
        _print_json(fmt)
    else:
        print(f"{fmt['key']}: {fmt['summary']}")
        print(f"  Status:   {fmt['status']}  |  Type: {fmt['type']}  |  Priority: {fmt['priority']}")
        print(f"  Assignee: {fmt['assignee'] or '(unassigned)'}  |  Reporter: {fmt['reporter']}")
        print(f"  Labels:   {', '.join(fmt['labels']) or '(none)'}")
        print(f"  Created:  {fmt['created']}  |  Updated: {fmt['updated']}")
        print(f"  URL:      {fmt['url']}")
        if fmt.get("description"):
            print(f"\n  {fmt['description'][:400]}")
        if show_comments and fmt.get("comments"):
            print(f"\n  Comments ({len(fmt['comments'])}):")
            for c in fmt["comments"]:
                print(f"    [{c['created']}] {c['author']}: {c['body'][:200]}")


def _issue_list(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue list <PROJECT-KEY> [--status <name>] [--assignee <user>] [--mine] [--limit N] [--json]")
    _reject_unknown_flags(
        argv[1:],
        bool_flags={"--mine", "--json"},
        value_flags={"--status", "--assignee", "--type", "--priority", "--label", "--limit", "--connection"},
    )
    project = argv[0]
    status = assignee = issue_type = priority = label = None
    limit = 50
    i = 1
    while i < len(argv):
        if argv[i] == "--status" and i + 1 < len(argv):
            status = argv[i + 1]
            i += 2
        elif argv[i] == "--assignee" and i + 1 < len(argv):
            assignee = argv[i + 1]
            i += 2
        elif argv[i] == "--mine":
            assignee = "currentUser()"
            i += 1
        elif argv[i] == "--type" and i + 1 < len(argv):
            issue_type = argv[i + 1]
            i += 2
        elif argv[i] == "--priority" and i + 1 < len(argv):
            priority = argv[i + 1]
            i += 2
        elif argv[i] == "--label" and i + 1 < len(argv):
            label = argv[i + 1]
            i += 2
        elif argv[i] == "--limit" and i + 1 < len(argv):
            limit = _parse_limit(argv[i + 1])
            i += 2
        else:
            i += 1
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    jql_parts = [f"project = {_jql_quote(project)}"]
    if status:
        jql_parts.append(f"status = {_jql_quote(status)}")
    if assignee:
        # Don't quote JQL functions (e.g. currentUser(), membersOf())
        if "(" in assignee:
            jql_parts.append(f"assignee = {assignee}")
        else:
            jql_parts.append(f"assignee = {_jql_quote(assignee)}")
    if issue_type:
        jql_parts.append(f"issuetype = {_jql_quote(issue_type)}")
    if priority:
        jql_parts.append(f"priority = {_jql_quote(priority)}")
    if label:
        jql_parts.append(f"labels = {_jql_quote(label)}")
    jql_parts.append("ORDER BY updated DESC")
    jql = " AND ".join(jql_parts[:-1]) + " " + jql_parts[-1]

    result = client.search(jql, max_results=limit,
                           fields="summary,status,issuetype,priority,assignee,labels,created,updated")
    issues = [_fmt_issue(i, client) for i in (result.get("issues") or [])]
    total = result.get("total")
    is_complete = total is not None or result.get("isLast", True)
    display_total = total if total is not None else (len(issues) if is_complete else f"≥{len(issues)}")

    if json_mode:
        _print_json({"tool": "issue_list", "timestamp": _now(),
                     "data": {"project": project, "total": total, "count": len(issues), "is_complete": is_complete, "issues": issues}})
    else:
        print(f"{project}  ({len(issues)} of {display_total})")
        for iss in issues:
            assignee_str = iss["assignee"] or "unassigned"
            print(f"  {iss['key']:<12} [{iss['status']:<16}] {iss['summary'][:60]}  ({assignee_str})")


def _issue_create(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue create <PROJECT-KEY> --summary <text> [options]")
    _reject_unknown_flags(
        argv[1:],
        bool_flags={"--dry-run", "--json"},
        value_flags={
            "--summary", "--description", "--type", "--assignee", "--priority",
            "--label", "--parent", "--sprint", "--sprint-field", "--connection",
        },
    )
    project = argv[0]
    summary = description = assignee = parent = sprint_id = None
    sprint_field = os.environ.get("JIRA_SPRINT_FIELD", "customfield_10020")
    issue_type = "Task"
    priority = None
    labels: list[str] = []
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--summary" and i + 1 < len(argv):
            summary = argv[i + 1]
            i += 2
        elif argv[i] == "--description" and i + 1 < len(argv):
            description = argv[i + 1]
            i += 2
        elif argv[i] == "--type" and i + 1 < len(argv):
            issue_type = argv[i + 1]
            i += 2
        elif argv[i] == "--assignee" and i + 1 < len(argv):
            assignee = argv[i + 1]
            i += 2
        elif argv[i] == "--priority" and i + 1 < len(argv):
            priority = argv[i + 1]
            i += 2
        elif argv[i] == "--label" and i + 1 < len(argv):
            labels.append(argv[i + 1])
            i += 2
        elif argv[i] == "--parent" and i + 1 < len(argv):
            parent = argv[i + 1]
            i += 2
        elif argv[i] == "--sprint" and i + 1 < len(argv):
            sprint_id = argv[i + 1]
            i += 2
        elif argv[i] == "--sprint-field" and i + 1 < len(argv):
            sprint_field = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not summary:
        _err("--summary is required")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    fields: dict[str, Any] = {
        "project": {"key": project},
        "summary": summary,
        "issuetype": {"name": issue_type},
    }
    if description:
        fields["description"] = client._text_body(description)
    resolved_assignee = _resolve_assignee(client, assignee) if assignee else None

    if resolved_assignee:
        if client.server:
            fields["assignee"] = {"name": resolved_assignee}
        else:
            fields["assignee"] = {"accountId": resolved_assignee}
    if priority:
        fields["priority"] = {"name": priority}
    if labels:
        fields["labels"] = labels
    if parent:
        fields["parent"] = {"key": parent}
    if sprint_id is not None:
        if not sprint_field.startswith("customfield_"):
            _err(f"--sprint-field must be a Jira custom field id like customfield_10020, got: {sprint_field!r}")
        try:
            fields[sprint_field] = {"id": int(sprint_id)}
        except ValueError:
            _err(f"--sprint must be a numeric sprint ID, got: {sprint_id!r}")

    body = {"fields": fields}

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_create", "project": project,
                         "fields": {k: v for k, v in fields.items() if k != "project"}})
        else:
            print(f"[dry-run] would create {issue_type} in {project}:")
            print(f"  Summary: {summary}")
            if description:
                print(f"  Description: {description[:100]}")
            if resolved_assignee:
                print(f"  Assignee: {resolved_assignee}")
            if priority:
                print(f"  Priority: {priority}")
            if labels:
                print(f"  Labels: {', '.join(labels)}")
            if parent:
                print(f"  Parent: {parent}")
            if sprint_id:
                print(f"  Sprint: {sprint_id}")
        sys.exit(DRY_RUN_EXIT_CODE)

    result = client.post("issue", body, suppress_errors=True)
    if isinstance(result, dict) and result.get("_error"):
        message = str(result.get("_error", "")).lower()
        if issue_type.lower() != "task" and ("issuetype" in message or "issue type" in message):
            _err(f"Jira rejected issue type {issue_type!r}; no issue was created. Verify the project's available issue types and retry.")
        else:
            _err(str(result["_error"]))
    key = result.get("key", "?")
    url = f"{client.base}/browse/{key}"
    if json_mode:
        payload = {"key": key, "url": url}
        _print_json(payload)
    else:
        print(f"Created {key}: {summary}")
        print(f"  {url}")


def _issue_link(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue link <ISSUE-KEY> --to <ISSUE-KEY> --type <blocks|is blocked by|clones|is cloned by|duplicates|is duplicated by|relates to>")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--to", "--type", "--connection"})
    key = argv[0]
    target = None
    link_type = "relates to"
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--to" and i + 1 < len(argv):
            target = argv[i + 1]
            i += 2
        elif argv[i] == "--type" and i + 1 < len(argv):
            link_type = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not target:
        _err("--to is required")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    canonical_type, relation = _normalize_issue_link_type(link_type)
    relation_value = relation
    subject_outward = relation_value in ("blocks", "clones", "duplicates", "relates to")
    if relation_value == "is blocked by":
        subject_outward = False
    elif relation_value == "blocks":
        subject_outward = True
    elif relation_value == "is cloned by":
        subject_outward = False
    elif relation_value == "clones":
        subject_outward = True
    elif relation_value == "is duplicated by":
        subject_outward = False
    elif relation_value == "duplicates":
        subject_outward = True

    if subject_outward:
        outward_key, inward_key = key, target
    else:
        outward_key, inward_key = target, key

    body = {
        "type": {"name": canonical_type},
        "outwardIssue": {"key": outward_key},
        "inwardIssue": {"key": inward_key},
    }

    if dry_run:
        if json_mode:
            _print_json({
                "dry_run": True,
                "action": "issue_link",
                "from": key,
                "to": target,
                "link_type": relation_value,
                "jira_type": canonical_type,
                "outward_issue": outward_key,
                "inward_issue": inward_key,
            })
        else:
            print(f"[dry-run] would link {key} {relation_value} {target}")
            print(f"  Jira type: {canonical_type}")
            print(f"  Outward issue: {outward_key}")
            print(f"  Inward issue:  {inward_key}")
        sys.exit(DRY_RUN_EXIT_CODE)

    client.post("issueLink", body)
    if json_mode:
        _print_json({
            "from": key,
            "to": target,
            "link_type": relation_value,
            "jira_type": canonical_type,
            "outward_issue": outward_key,
            "inward_issue": inward_key,
        })
    else:
        print(f"Linked {key} {relation_value} {target}")


def _issue_delete(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue delete <ISSUE-KEY> [--dry-run] [--confirm]")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--confirm", "--json"}, value_flags={"--connection"})
    key = argv[0]
    dry_run = False
    confirm = False
    i = 1
    while i < len(argv):
        if argv[i] == "--dry-run":
            dry_run = True
            i += 1
        elif argv[i] == "--confirm":
            confirm = True
            i += 1
        else:
            i += 1
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_delete", "key": key})
        else:
            print(f"[dry-run] would delete {key}")
        sys.exit(DRY_RUN_EXIT_CODE)

    if not confirm:
        _err("Delete requires --confirm (or use --dry-run to preview)")

    client.delete(f"issue/{key}")
    if json_mode:
        _print_json({"key": key, "deleted": True})
    else:
        print(f"Deleted {key}")


def _issue_comment(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue comment <ISSUE-KEY> --body <text> [--dry-run]")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--body", "--connection"})
    key = argv[0]
    body_text = None
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--body" and i + 1 < len(argv):
            body_text = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not body_text:
        _err("--body is required")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_comment", "key": key, "body": body_text})
        else:
            print(f"[dry-run] would comment on {key}:")
            print(f"  {body_text[:200]}")
        sys.exit(DRY_RUN_EXIT_CODE)

    result = client.post(f"issue/{key}/comment", {"body": client._text_body(body_text)})
    comment_id = result.get("id")
    if json_mode:
        _print_json({"key": key, "comment_id": comment_id})
    else:
        print(f"Comment added to {key} (id: {comment_id})")


def _issue_assign(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue assign <ISSUE-KEY> --to <account-id-or-email>")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--to", "--connection"})
    key = argv[0]
    to = None
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--to" and i + 1 < len(argv):
            to = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not to:
        _err("--to is required (use 'none' to unassign)")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    if dry_run:
        action = "unassign" if to.lower() == "none" else f"assign to {to}"
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_assign", "key": key, "to": to})
        else:
            print(f"[dry-run] would {action} {key}")
        sys.exit(DRY_RUN_EXIT_CODE)

    if to.lower() == "none":
        body: dict[str, Any] = {"accountId": None} if not client.server else {"name": None}
    elif client.server:
        body = {"name": to}
    else:
        body = {"accountId": _resolve_assignee(client, to)}

    client.put(f"issue/{key}/assignee", body)
    if json_mode:
        _print_json({"key": key, "assignee": to})
    else:
        print(f"Assigned {key} to {to}")


def _issue_transition(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue transition <ISSUE-KEY> --to <status-name>")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--to", "--connection"})
    key = argv[0]
    to_status = None
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--to" and i + 1 < len(argv):
            to_status = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not to_status:
        _err("--to is required (run `agent-do jira transitions <key>` to see options)")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    # Look up the transition ID by name
    t_data = client.get(f"issue/{key}/transitions")
    transitions = t_data.get("transitions") or []
    match = next(
        (t for t in transitions if t.get("name", "").lower() == to_status.lower()),
        None,
    )
    if not match:
        available = [t.get("name", "") for t in transitions]
        _err(f"Transition '{to_status}' not found for {key}. Available: {', '.join(available)}")

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_transition", "key": key,
                         "transition": match["name"], "id": match["id"]})
        else:
            print(f"[dry-run] would transition {key} → '{match['name']}' (id: {match['id']})")
        sys.exit(DRY_RUN_EXIT_CODE)

    client.post(f"issue/{key}/transitions", {"transition": {"id": match["id"]}})
    if json_mode:
        _print_json({"key": key, "transition": match["name"]})
    else:
        print(f"Transitioned {key} → {match['name']}")


def _issue_label(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue label <ISSUE-KEY> [--add <label>] [--remove <label>]")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--add", "--remove", "--connection"})
    key = argv[0]
    add_labels: list[str] = []
    remove_labels: list[str] = []
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--add" and i + 1 < len(argv):
            add_labels.append(argv[i + 1])
            i += 2
        elif argv[i] == "--remove" and i + 1 < len(argv):
            remove_labels.append(argv[i + 1])
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not add_labels and not remove_labels:
        _err("Specify at least one --add or --remove label")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    # Get current labels
    issue = client.get(f"issue/{key}", params={"fields": "labels"})
    current = [(l.get("value") if isinstance(l, dict) else l)
               for l in ((issue.get("fields") or {}).get("labels") or [])]
    updated = [l for l in current if l not in remove_labels]
    for l in add_labels:
        if l not in updated:
            updated.append(l)

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_label", "key": key,
                         "before": current, "after": updated})
        else:
            print(f"[dry-run] would update labels on {key}:")
            print(f"  Before: {', '.join(current) or '(none)'}")
            print(f"  After:  {', '.join(updated) or '(none)'}")
        sys.exit(DRY_RUN_EXIT_CODE)

    client.put(f"issue/{key}", {"fields": {"labels": updated}})
    if json_mode:
        _print_json({"key": key, "labels": updated})
    else:
        print(f"Labels updated on {key}: {', '.join(updated) or '(none)'}")


def _issue_edit(argv: list[str]) -> None:
    if not argv:
        _err("Usage: issue edit <ISSUE-KEY> [--summary <text>] [--description <text>] [--priority <p>]")
    _reject_unknown_flags(argv[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--summary", "--description", "--priority", "--connection"})
    key = argv[0]
    summary = description = priority = None
    dry_run = False
    i = 1
    while i < len(argv):
        if argv[i] == "--summary" and i + 1 < len(argv):
            summary = argv[i + 1]
            i += 2
        elif argv[i] == "--description" and i + 1 < len(argv):
            description = argv[i + 1]
            i += 2
        elif argv[i] == "--priority" and i + 1 < len(argv):
            priority = argv[i + 1]
            i += 2
        elif argv[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    if not any([summary, description, priority]):
        _err("Specify at least one field to edit: --summary, --description, --priority")
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    fields: dict[str, Any] = {}
    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = client._text_body(description)
    if priority:
        fields["priority"] = {"name": priority}

    if dry_run:
        if json_mode:
            _print_json({"dry_run": True, "action": "issue_edit", "key": key, "fields": fields})
        else:
            print(f"[dry-run] would edit {key}:")
            for k, v in fields.items():
                print(f"  {k}: {v}")
        sys.exit(DRY_RUN_EXIT_CODE)

    client.put(f"issue/{key}", {"fields": fields})
    if json_mode:
        _print_json({"key": key, "updated": list(fields.keys())})
    else:
        print(f"Updated {key}: {', '.join(fields.keys())}")


# ── transitions ────────────────────────────────────────────────────────────────

def cmd_transitions(argv: list[str]) -> None:
    if not argv:
        _err("Usage: transitions <ISSUE-KEY> [--connection <name>] [--json]")
    _reject_unknown_flags(argv[1:], bool_flags={"--json"}, value_flags={"--connection"})
    key = argv[0]
    connection, json_mode, _ = _parse_common(argv, start=1)
    client = _get_client(connection)
    data = client.get(f"issue/{key}/transitions")
    transitions = [{"id": t["id"], "name": t["name"],
                    "to": (t.get("to") or {}).get("name", "")}
                   for t in (data.get("transitions") or [])]
    if json_mode:
        _print_json({"key": key, "transitions": transitions})
    else:
        print(f"Available transitions for {key}:")
        for t in transitions:
            print(f"  {t['id']:>4}  {t['name']:<30}  → {t['to']}")


# ── search ─────────────────────────────────────────────────────────────────────

def cmd_search(argv: list[str]) -> None:
    if not argv or argv[0].startswith("-"):
        _err("Usage: search '<JQL>' [--limit N] [--fields <fields>] [--json]")
    _reject_unknown_flags(argv[1:], bool_flags={"--json"}, value_flags={"--limit", "--fields", "--connection"})
    jql = argv[0]
    limit = 50
    fields = "summary,status,issuetype,priority,assignee,labels,created,updated"
    i = 1
    while i < len(argv):
        if argv[i] == "--limit" and i + 1 < len(argv):
            limit = _parse_limit(argv[i + 1])
            i += 2
        elif argv[i] == "--fields" and i + 1 < len(argv):
            fields = argv[i + 1]
            i += 2
        else:
            i += 1
    connection, json_mode, _ = _parse_common(argv[1:])
    client = _get_client(connection)

    result = client.search(jql, max_results=limit, fields=fields)
    issues = [_fmt_issue(iss, client) for iss in (result.get("issues") or [])]
    total = result.get("total")
    is_complete = total is not None or result.get("isLast", True)
    display_total = total if total is not None else (len(issues) if is_complete else f"≥{len(issues)}")

    if json_mode:
        _print_json({"tool": "search", "timestamp": _now(),
                     "data": {"jql": jql, "total": total, "count": len(issues), "is_complete": is_complete, "issues": issues}})
    else:
        print(f"JQL: {jql}  ({len(issues)} of {display_total})")
        for iss in issues:
            print(f"  {iss['key']:<12} [{iss['status']:<16}] {iss['summary'][:60]}")


# ── boards & sprints ───────────────────────────────────────────────────────────

def cmd_board(argv: list[str]) -> None:
    sub = argv[0] if argv else "list"
    rest = argv[1:]
    if sub == "list":
        _reject_unknown_flags(rest, bool_flags={"--json"}, value_flags={"--project", "--connection"})
        project = None
        i = 0
        while i < len(rest):
            if rest[i] == "--project" and i + 1 < len(rest):
                project = rest[i + 1]
                i += 2
            else:
                i += 1
        connection, json_mode, _ = _parse_common(rest)
        client = _get_client(connection)
        params: dict[str, Any] = {}
        if project:
            params["projectKeyOrId"] = project
        data = client.get("board", params=params, agile=True)
        boards = data.get("values") or []
        if json_mode:
            _print_json({"boards": boards})
        else:
            for b in boards:
                print(f"  {b.get('id'):>5}  {b.get('name'):<40}  [{b.get('type')}]")
    else:
        _err(f"Unknown board subcommand: {sub!r}. Use: list")


def cmd_sprint(argv: list[str]) -> None:
    if not argv:
        _err("Usage: sprint <list|active|add> ...")
    sub = argv[0]
    rest = argv[1:]

    if sub == "list":
        if not rest or rest[0].startswith("-"):
            _err("Usage: sprint list <BOARD-ID>")
        _reject_unknown_flags(rest[1:], bool_flags={"--json"}, value_flags={"--state", "--connection"})
        board_id = rest[0]
        state = "active"
        i = 1
        while i < len(rest):
            if rest[i] == "--state" and i + 1 < len(rest):
                state = rest[i + 1]
                i += 2
            else:
                i += 1
        connection, json_mode, _ = _parse_common(rest[1:])
        client = _get_client(connection)
        data = client.get(f"board/{board_id}/sprint", params={"state": state}, agile=True)
        sprints = data.get("values") or []
        if json_mode:
            _print_json({"board_id": board_id, "sprints": sprints})
        else:
            for s in sprints:
                start = _fmt_date(s.get("startDate"))
                end = _fmt_date(s.get("endDate"))
                print(f"  {s.get('id'):>5}  {s.get('name'):<40}  {start} → {end}  [{s.get('state')}]")

    elif sub == "active":
        if not rest or rest[0].startswith("-"):
            _err("Usage: sprint active <BOARD-ID>")
        _reject_unknown_flags(rest[1:], bool_flags={"--json"}, value_flags={"--connection"})
        board_id = rest[0]
        connection, json_mode, _ = _parse_common(rest[1:])
        client = _get_client(connection)
        data = client.get(f"board/{board_id}/sprint", params={"state": "active"}, agile=True)
        sprints = data.get("values") or []
        if not sprints:
            if json_mode:
                _print_json({"sprint": None, "issues": []})
            else:
                print("No active sprint found.")
            return
        sprint = sprints[0]
        sprint_id = sprint.get("id")
        issues_data = client.get(f"sprint/{sprint_id}/issue",
                                  params={"maxResults": 100,
                                          "fields": "summary,status,issuetype,priority,assignee"},
                                  agile=True)
        issues = [_fmt_issue(i, client) for i in (issues_data.get("issues") or [])]
        if json_mode:
            _print_json({"sprint": sprint, "issues": issues})
        else:
            print(f"Sprint: {sprint.get('name')}  [{sprint.get('state')}]")
            print(f"  {_fmt_date(sprint.get('startDate'))} → {_fmt_date(sprint.get('endDate'))}")
            print(f"  {len(issues)} issues:")
            for iss in issues:
                assignee_str = iss["assignee"] or "unassigned"
                print(f"    {iss['key']:<12} [{iss['status']:<16}] {iss['summary'][:50]}  ({assignee_str})")

    elif sub == "add":
        if not rest or rest[0].startswith("-"):
            _err("Usage: sprint add <ISSUE-KEY> --sprint <id>")
        _reject_unknown_flags(rest[1:], bool_flags={"--dry-run", "--json"}, value_flags={"--sprint", "--connection"})
        key = rest[0]
        sprint_id = None
        dry_run = False
        i = 1
        while i < len(rest):
            if rest[i] == "--sprint" and i + 1 < len(rest):
                sprint_id = rest[i + 1]
                i += 2
            elif rest[i] == "--dry-run":
                dry_run = True
                i += 1
            else:
                i += 1
        if not sprint_id:
            _err("--sprint <id> is required")
        connection, json_mode, _ = _parse_common(rest[1:])
        client = _get_client(connection)

        if dry_run:
            if json_mode:
                _print_json({"dry_run": True, "action": "sprint_add",
                             "key": key, "sprint_id": sprint_id})
            else:
                print(f"[dry-run] would add {key} to sprint {sprint_id}")
            sys.exit(DRY_RUN_EXIT_CODE)

        client.post(f"sprint/{sprint_id}/issue", {"issues": [key]}, agile=True)
        if json_mode:
            _print_json({"key": key, "sprint_id": sprint_id})
        else:
            print(f"Added {key} to sprint {sprint_id}")

    else:
        _err(f"Unknown sprint subcommand: {sub!r}. Use: list, active, add")


# ── dispatch ───────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> None:
    if not argv:
        _err("Usage: agent-do jira <command> [args]. Try: agent-do jira --help")
    cmd = argv[0]
    rest = argv[1:]
    dispatch = {
        "connections": cmd_connections,
        "whoami":      cmd_whoami,
        "snapshot":    cmd_snapshot,
        "user":        cmd_user,
        "issue":       cmd_issue,
        "transitions": cmd_transitions,
        "search":      cmd_search,
        "board":       cmd_board,
        "sprint":      cmd_sprint,
    }
    fn = dispatch.get(cmd)
    if not fn:
        _err(f"Unknown command: {cmd!r}. Try: agent-do jira --help")
    fn(rest)


if __name__ == "__main__":
    main(sys.argv[1:])
