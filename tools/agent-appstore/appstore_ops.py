#!/usr/bin/env python3
"""agent-appstore backend - App Store Connect REST API (api.appstoreconnect.apple.com).

Endpoints, parameters, and request schemas verified against Apple's official
App Store Connect OpenAPI specification 4.5.1 (2026-10-15). JWT requirements
verified against "Generating Tokens for API Requests" on developer.apple.com.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "lib"))

from quantities import QuantityError, lookup  # noqa: E402

ASC_API = os.environ.get("ASC_API_URL", "https://api.appstoreconnect.apple.com/v1")

# Apple's published per-page ceiling for collection endpoints. Must equal the
# authority record apple.appstoreconnect.page_limit; tests/test_appstore.py
# asserts the equality, so a stale copy fails the suite.
PAGE_LIMIT = 200

# Apple rejects a token whose iat->exp span exceeds the published lifetime cap
# (apple.appstoreconnect.token_lifetime); the margin keeps a locally fast clock
# from presenting Apple a span over the cap.
CLOCK_SKEW_SECONDS = 60

# "Latest build" is one row by definition; this is the size of the answer
# being requested, not a fraction of any ceiling.
NEWEST_BUILD_ROWS = 1

# Wall-clock budget for one HTTP exchange. urllib's own default is no timeout
# at all, which hangs a session on a stalled connection; report downloads are
# the largest payloads this tool moves and finish well inside a minute.
REQUEST_TIMEOUT_SECONDS = 60

# Review submission states that count as pending (non-terminal); terminal
# states are CANCELING, COMPLETING, COMPLETE.
PENDING_SUBMISSION_STATES = "READY_FOR_REVIEW,WAITING_FOR_REVIEW,IN_REVIEW,UNRESOLVED_ISSUES"

# Platform (appStoreVersions, reviewSubmissions) and BundleIdPlatform
# (device filter) are different enums in the spec; devices reject TV_OS and
# VISION_OS and accept UNIVERSAL.
PLATFORMS = ("IOS", "MAC_OS", "TV_OS", "VISION_OS")
DEVICE_PLATFORMS = ("IOS", "MAC_OS", "UNIVERSAL")

# Resource attributes that carry signing material; stripped from JSON output
# unless --with-content is passed, so a casual listing never dumps them.
CONTENT_ATTRIBUTES = ("certificateContent", "profileContent")
REVIEW_SORTS = ("rating", "-rating", "createdDate", "-createdDate")
SALES_FREQUENCIES = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
SALES_REPORT_TYPES = (
    "SALES", "PRE_ORDER", "NEWSSTAND", "SUBSCRIPTION", "SUBSCRIPTION_EVENT",
    "SUBSCRIBER", "SUBSCRIPTION_OFFER_CODE_REDEMPTION", "INSTALLS",
    "FIRST_ANNUAL", "WIN_BACK_ELIGIBILITY",
)
SALES_REPORT_SUBTYPES = (
    "SUMMARY", "DETAILED", "SUMMARY_INSTALL_TYPE", "SUMMARY_TERRITORY",
    "SUMMARY_CHANNEL",
)
FINANCE_REPORT_TYPES = ("FINANCIAL", "FINANCE_DETAIL")

_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0}


JSON_MODE = False


def fail(message: str, *, code: int = 1, error: str = "error") -> SystemExit:
    if JSON_MODE:
        print(json.dumps({"ok": False, "error": error, "message": message}, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return SystemExit(code)


def require_credentials() -> tuple[str, str, str]:
    key_id = os.environ.get("ASC_KEY_ID", "").strip()
    issuer_id = os.environ.get("ASC_ISSUER_ID", "").strip()
    key_path = os.environ.get("ASC_PRIVATE_KEY_PATH", "").strip()
    missing = [
        name for name, value in (
            ("ASC_KEY_ID", key_id),
            ("ASC_ISSUER_ID", issuer_id),
            ("ASC_PRIVATE_KEY_PATH", key_path),
        ) if not value
    ]
    if missing:
        raise fail(
            f"missing credentials: {', '.join(missing)} "
            f"(store each with: agent-do creds store <NAME> --stdin)"
        )
    if not Path(key_path).is_file():
        raise fail(f"ASC_PRIVATE_KEY_PATH does not point to a readable file: {key_path}")
    return key_id, issuer_id, key_path


def token_lifetime_seconds() -> int:
    try:
        record = lookup("apple.appstoreconnect.token_lifetime")
    except QuantityError as exc:
        raise fail(f"cannot resolve token lifetime from the quantity authority:\n{exc}")
    return int(record["value"]) - CLOCK_SKEW_SECONDS


def mint_token(*, force: bool = False) -> str:
    now = time.time()
    if not force and _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"] - CLOCK_SKEW_SECONDS:
        return _TOKEN_CACHE["token"]

    key_id, issuer_id, key_path = require_credentials()
    try:
        import jwt
    except ImportError:
        raise fail("PyJWT is not installed (pip install pyjwt cryptography)")
    if not hasattr(jwt, "encode"):
        raise fail("the installed 'jwt' module is not PyJWT (pip install pyjwt)")

    private_key = Path(key_path).read_text()
    issued_at = int(now)
    expires_at = issued_at + token_lifetime_seconds()
    try:
        token = jwt.encode(
            {
                "iss": issuer_id,
                "iat": issued_at,
                "exp": expires_at,
                "aud": "appstoreconnect-v1",
            },
            private_key,
            algorithm="ES256",
            headers={"kid": key_id, "typ": "JWT"},
        )
    except (ValueError, TypeError, jwt.exceptions.PyJWTError):
        raise fail(
            f"could not sign with the key at {key_path}; it must be the PEM "
            f"EC private key (.p8) downloaded from App Store Connect",
            error="invalid_private_key",
        )
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires_at"] = float(expires_at)
    return token


def format_api_error(status: int, payload: str, rate_header: str | None) -> str:
    detail = payload
    try:
        data = json.loads(payload)
        errors = data.get("errors") or []
        parts = []
        for item in errors:
            title = item.get("title") or ""
            det = item.get("detail") or ""
            code = item.get("code") or ""
            parts.append(": ".join(p for p in (code, title, det) if p))
        if parts:
            detail = "; ".join(parts)
    except (json.JSONDecodeError, AttributeError):
        pass
    message = f"App Store Connect API {status}: {detail}"
    if status == 429 and rate_header:
        message += f" (X-Rate-Limit: {rate_header})"
    return message


def api_request(
    method: str,
    path_or_url: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    raw: bool = False,
    retry_auth: bool = True,
) -> Any:
    if path_or_url.startswith("http"):
        url = path_or_url
    else:
        url = f"{ASC_API.rstrip('/')}{path_or_url}"
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)

    headers = {
        "Authorization": f"Bearer {mint_token()}",
        # Report downloads are served as application/a-gzip only; everything
        # else is JSON. Asking for exactly what each call consumes.
        "Accept": "application/a-gzip" if raw else "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if raw:
                return response.read()
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and retry_auth:
            mint_token(force=True)
            return api_request(
                method, path_or_url, params=params, body=body, raw=raw, retry_auth=False
            )
        payload = exc.read().decode("utf-8", errors="replace")
        raise fail(format_api_error(exc.code, payload, exc.headers.get("X-Rate-Limit")))
    except urllib.error.URLError as exc:
        raise fail(f"App Store Connect API request failed: {exc.reason}")


def paginate(
    path: str,
    params: dict[str, Any],
    *,
    limit: int,
    follow_all: bool,
) -> tuple[list[dict[str, Any]], int | None, bool]:
    """One page by default; every page with follow_all. Returns (items, total, truncated)."""
    if limit < 1:
        raise fail("--limit must be at least 1")
    if limit > PAGE_LIMIT and not follow_all:
        raise fail(
            f"--limit {limit} is above the API page cap of {PAGE_LIMIT}; "
            f"pass --all to follow pagination instead"
        )

    items: list[dict[str, Any]] = []
    total: int | None = None
    page_params = dict(params)
    page_params["limit"] = min(limit, PAGE_LIMIT)
    url: str | None = path
    first = True
    while url:
        payload = api_request("GET", url, params=page_params if first else None)
        first = False
        items.extend(payload.get("data") or [])
        paging = (payload.get("meta") or {}).get("paging") or {}
        if paging.get("total") is not None:
            total = paging["total"]
        next_url = (payload.get("links") or {}).get("next")
        if not follow_all or not next_url:
            truncated = bool(next_url) or (total is not None and len(items) < total)
            return items, total, truncated
        url = next_url
    return items, total, False


def attr(item: dict[str, Any], name: str) -> Any:
    return (item.get("attributes") or {}).get(name)


def redact_content(items: list[dict[str, Any]], with_content: bool) -> list[dict[str, Any]]:
    """Strip signing material from listings unless the caller asked for it."""
    if with_content:
        return items
    for item in items:
        attributes = item.get("attributes") or {}
        for name in CONTENT_ATTRIBUTES:
            if attributes.get(name):
                attributes[name] = f"[redacted: pass --with-content to include {name}]"
    return items


def emit_list(
    args: argparse.Namespace,
    kind: str,
    items: list[dict[str, Any]],
    total: int | None,
    truncated: bool,
    line_for: Any,
) -> None:
    shown = len(items)
    if args.json:
        print(json.dumps({
            "ok": True,
            "kind": kind,
            "shown": shown,
            "total": total,
            "truncated": truncated,
            "items": items,
        }, indent=2))
        return
    for item in items:
        print(line_for(item))
    if truncated and total is not None:
        print(f"[truncated: {shown} of {total} shown]")
    elif truncated:
        print(f"[truncated: {shown} shown, more pages exist; pass --all]")
    else:
        print(f"{shown} {kind}" + (f" (total {total})" if total is not None else ""))


def resolve_app(ref: str) -> dict[str, Any]:
    if re.fullmatch(r"\d+", ref):
        payload = api_request("GET", f"/apps/{urllib.parse.quote(ref, safe='')}")
        return payload.get("data") or {}
    items, _, _ = paginate(
        "/apps", {"filter[bundleId]": ref}, limit=PAGE_LIMIT, follow_all=False
    )
    if len(items) == 1:
        return items[0]
    if not items:
        raise fail(f"no app found with id or bundle id '{ref}'")
    matches = ", ".join(f"{attr(i, 'bundleId')} (id {i.get('id')})" for i in items)
    raise fail(f"bundle id '{ref}' matched {len(items)} apps: {matches}")


# ── line formatters (attribute names verified against spec 4.5.1) ─────────


def app_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'bundleId') or ''}  "
        f"{attr(item, 'name') or ''}  sku:{attr(item, 'sku') or ''}"
    )


def build_line(item: dict[str, Any]) -> str:
    expired = " expired" if attr(item, "expired") else ""
    return (
        f"{item.get('id', '')}  build {attr(item, 'version') or ''}  "
        f"[{attr(item, 'processingState') or ''}]{expired}  "
        f"uploaded:{attr(item, 'uploadedDate') or ''}"
    )


def version_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'versionString') or ''}  "
        f"{attr(item, 'platform') or ''}  [{attr(item, 'appVersionState') or attr(item, 'appStoreState') or ''}]  "
        f"created:{attr(item, 'createdDate') or ''}"
    )


def group_line(item: dict[str, Any]) -> str:
    internal = "internal" if attr(item, "isInternalGroup") else "external"
    link = " public-link" if attr(item, "publicLinkEnabled") else ""
    return f"{item.get('id', '')}  {attr(item, 'name') or ''}  [{internal}]{link}"


def tester_line(item: dict[str, Any]) -> str:
    name = " ".join(p for p in (attr(item, "firstName"), attr(item, "lastName")) if p)
    return (
        f"{item.get('id', '')}  {attr(item, 'email') or ''}  {name}  "
        f"invite:{attr(item, 'inviteType') or ''}  state:{attr(item, 'state') or ''}"
    )


def review_line(item: dict[str, Any]) -> str:
    stars = attr(item, "rating")
    line = (
        f"{item.get('id', '')}  {stars}/5  {attr(item, 'territory') or ''}  "
        f"{attr(item, 'createdDate') or ''}  "
        f"{attr(item, 'reviewerNickname') or ''}: {attr(item, 'title') or ''}"
    )
    body = attr(item, "body")
    if body:
        line += "\n  " + str(body).replace("\n", "\n  ")
    return line


def cert_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'displayName') or attr(item, 'name') or ''}  "
        f"[{attr(item, 'certificateType') or ''}]  expires:{attr(item, 'expirationDate') or ''}"
    )


def profile_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'name') or ''}  "
        f"[{attr(item, 'profileType') or ''}]  state:{attr(item, 'profileState') or ''}  "
        f"expires:{attr(item, 'expirationDate') or ''}"
    )


def device_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'name') or ''}  "
        f"{attr(item, 'platform') or ''}  [{attr(item, 'status') or ''}]  "
        f"udid:{attr(item, 'udid') or ''}"
    )


def submission_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('id', '')}  {attr(item, 'platform') or ''}  "
        f"[{attr(item, 'state') or ''}]  submitted:{attr(item, 'submittedDate') or ''}"
    )


# ── commands ───────────────────────────────────────────────────────────────


def cmd_snapshot(args: argparse.Namespace) -> int:
    apps, total, truncated = paginate(
        "/apps", {"sort": "name"}, limit=args.limit, follow_all=False
    )
    entries = []
    for app in apps:
        app_id = str(app.get("id"))
        builds = api_request("GET", "/builds", params={
            "filter[app]": app_id,
            "sort": "-uploadedDate",
            "limit": NEWEST_BUILD_ROWS,
        })
        latest = (builds.get("data") or [None])[0] if builds.get("data") else None
        submissions = api_request("GET", "/reviewSubmissions", params={
            "filter[app]": app_id,
            "filter[state]": PENDING_SUBMISSION_STATES,
            "limit": PAGE_LIMIT,
        })
        pending = submissions.get("data") or []
        entries.append({"app": app, "latest_build": latest, "pending_submissions": pending})

    if args.json:
        print(json.dumps({
            "ok": True,
            "kind": "snapshot",
            "shown": len(entries),
            "total": total,
            "truncated": truncated,
            "apps": entries,
        }, indent=2))
        return 0

    for entry in entries:
        print(app_line(entry["app"]))
        if entry["latest_build"]:
            print(f"  latest {build_line(entry['latest_build'])}")
        else:
            print("  latest build: none")
        if entry["pending_submissions"]:
            for sub in entry["pending_submissions"]:
                print(f"  pending submission {submission_line(sub)}")
        else:
            print("  pending submissions: none")
    if truncated and total is not None:
        print(f"[truncated: {len(entries)} of {total} apps shown; raise --limit]")
    else:
        print(f"{len(entries)} apps" + (f" (total {total})" if total is not None else ""))
    return 0


def cmd_apps(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {"sort": "name"}
    if args.bundle_id:
        params["filter[bundleId]"] = args.bundle_id
    if args.name:
        params["filter[name]"] = args.name
    items, total, truncated = paginate("/apps", params, limit=args.limit, follow_all=args.all)
    emit_list(args, "apps", items, total, truncated, app_line)
    return 0


def cmd_app(args: argparse.Namespace) -> int:
    app = resolve_app(args.ref)
    if args.json:
        print(json.dumps({"ok": True, "app": app}, indent=2))
        return 0
    print(f"ID:        {app.get('id')}")
    print(f"Name:      {attr(app, 'name')}")
    print(f"Bundle ID: {attr(app, 'bundleId')}")
    print(f"SKU:       {attr(app, 'sku')}")
    print(f"Locale:    {attr(app, 'primaryLocale')}")
    return 0


def cmd_builds(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {"sort": "-uploadedDate"}
    if args.app:
        params["filter[app]"] = str(resolve_app(args.app).get("id"))
    items, total, truncated = paginate("/builds", params, limit=args.limit, follow_all=args.all)
    emit_list(args, "builds", items, total, truncated, build_line)
    return 0


def cmd_versions(args: argparse.Namespace) -> int:
    app = resolve_app(args.ref)
    params: dict[str, Any] = {}
    if args.platform:
        params["filter[platform]"] = args.platform
    items, total, truncated = paginate(
        f"/apps/{urllib.parse.quote(str(app.get('id')), safe='')}/appStoreVersions",
        params, limit=args.limit, follow_all=args.all,
    )
    emit_list(args, "versions", items, total, truncated, version_line)
    return 0


def cmd_testflight(args: argparse.Namespace) -> int:
    if args.tf_command == "groups":
        params: dict[str, Any] = {}
        if args.app:
            params["filter[app]"] = str(resolve_app(args.app).get("id"))
        items, total, truncated = paginate(
            "/betaGroups", params, limit=args.limit, follow_all=args.all
        )
        emit_list(args, "beta groups", items, total, truncated, group_line)
        return 0

    if args.tf_command == "testers":
        params = {}
        if args.group:
            params["filter[betaGroups]"] = args.group
        if args.email:
            params["filter[email]"] = args.email
        if args.app:
            params["filter[apps]"] = str(resolve_app(args.app).get("id"))
        items, total, truncated = paginate(
            "/betaTesters", params, limit=args.limit, follow_all=args.all
        )
        emit_list(args, "beta testers", items, total, truncated, tester_line)
        return 0

    if args.tf_command == "add-tester":
        existing, _, _ = paginate(
            "/betaTesters", {"filter[email]": args.email},
            limit=PAGE_LIMIT, follow_all=False,
        )
        if existing:
            # Already a tester: link to the groups instead of re-creating,
            # which the API refuses with 409.
            tester = existing[0]
            linkage = {"data": [{"type": "betaTesters", "id": str(tester.get("id"))}]}
            for group_id in args.group:
                api_request(
                    "POST",
                    f"/betaGroups/{urllib.parse.quote(group_id, safe='')}/relationships/betaTesters",
                    body=linkage,
                )
            if args.json:
                print(json.dumps({"ok": True, "tester": tester, "created": False,
                                  "groups": args.group}, indent=2))
            else:
                print(f"{args.email} is already a tester; added to {len(args.group)} group(s)")
                print(tester_line(tester))
            return 0

        attributes: dict[str, Any] = {"email": args.email}
        if args.first:
            attributes["firstName"] = args.first
        if args.last:
            attributes["lastName"] = args.last
        body = {
            "data": {
                "type": "betaTesters",
                "attributes": attributes,
                "relationships": {
                    "betaGroups": {
                        "data": [{"type": "betaGroups", "id": gid} for gid in args.group]
                    }
                },
            }
        }
        created = api_request("POST", "/betaTesters", body=body)
        tester = created.get("data") or {}
        if args.json:
            print(json.dumps({"ok": True, "tester": tester, "created": True,
                              "groups": args.group}, indent=2))
        else:
            print(f"Invited {args.email} to {len(args.group)} group(s)")
            print(tester_line(tester))
        return 0

    raise fail(f"unknown testflight command: {args.tf_command}")


def cmd_reviews(args: argparse.Namespace) -> int:
    app = resolve_app(args.ref)
    params: dict[str, Any] = {"sort": args.sort}
    if args.rating:
        params["filter[rating]"] = args.rating
    if args.territory:
        params["filter[territory]"] = args.territory
    items, total, truncated = paginate(
        f"/apps/{urllib.parse.quote(str(app.get('id')), safe='')}/customerReviews",
        params, limit=args.limit, follow_all=args.all,
    )
    emit_list(args, "reviews", items, total, truncated, review_line)
    return 0


def cmd_certs(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.type:
        params["filter[certificateType]"] = args.type
    items, total, truncated = paginate(
        "/certificates", params, limit=args.limit, follow_all=args.all
    )
    emit_list(args, "certificates", redact_content(items, args.with_content),
              total, truncated, cert_line)
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.type:
        params["filter[profileType]"] = args.type
    items, total, truncated = paginate(
        "/profiles", params, limit=args.limit, follow_all=args.all
    )
    emit_list(args, "profiles", redact_content(items, args.with_content),
              total, truncated, profile_line)
    return 0


def cmd_devices(args: argparse.Namespace) -> int:
    params: dict[str, Any] = {}
    if args.platform:
        params["filter[platform]"] = args.platform
    if args.status:
        params["filter[status]"] = args.status
    items, total, truncated = paginate(
        "/devices", params, limit=args.limit, follow_all=args.all
    )
    emit_list(args, "devices", items, total, truncated, device_line)
    return 0


def write_report(raw: bytes, output: str, *, force: bool, json_mode: bool) -> int:
    path = Path(output)
    if path.exists() and not force:
        raise fail(f"refusing to overwrite existing file {path} (pass --force)")
    try:
        text = gzip.decompress(raw).decode("utf-8", errors="replace")
    except OSError:
        raise fail("report payload was not gzip data; nothing written")
    path.write_text(text)
    lines = text.count("\n")
    if json_mode:
        print(json.dumps({
            "ok": True, "output": str(path), "lines": lines, "bytes": len(text)
        }, indent=2))
    else:
        print(f"Wrote {path} ({lines} lines, {len(text)} bytes, tab-separated)")
    return 0


def cmd_reports(args: argparse.Namespace) -> int:
    if args.report_command == "sales":
        params = {
            "filter[vendorNumber]": args.vendor,
            "filter[reportType]": args.type,
            "filter[reportSubType]": args.subtype,
            "filter[frequency]": args.frequency,
        }
        if args.date:
            params["filter[reportDate]"] = args.date
        raw = api_request("GET", "/salesReports", params=params, raw=True)
        return write_report(raw, args.output, force=args.force, json_mode=args.json)

    if args.report_command == "finance":
        params = {
            "filter[vendorNumber]": args.vendor,
            "filter[reportType]": args.type,
            "filter[regionCode]": args.region,
            "filter[reportDate]": args.date,
        }
        raw = api_request("GET", "/financeReports", params=params, raw=True)
        return write_report(raw, args.output, force=args.force, json_mode=args.json)

    raise fail(f"unknown reports command: {args.report_command}")


def cmd_respond(args: argparse.Namespace) -> int:
    body = {
        "data": {
            "type": "customerReviewResponses",
            "attributes": {"responseBody": args.body},
            "relationships": {
                "review": {"data": {"type": "customerReviews", "id": args.review_id}}
            },
        }
    }
    created = api_request("POST", "/customerReviewResponses", body=body)
    data = created.get("data") or {}
    if args.json:
        print(json.dumps({"ok": True, "response": data}, indent=2))
    else:
        print(f"Published response {data.get('id')} to review {args.review_id}")
        print(f"State: {attr(data, 'state')}")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    if not args.yes:
        raise fail(
            "submit sends the version to App Review; pass --yes to confirm", code=2
        )
    app = resolve_app(args.ref)
    app_id = str(app.get("id"))

    # An app can have one open submission; surface it instead of creating a
    # duplicate the API would reject or orphan.
    open_subs = api_request("GET", "/reviewSubmissions", params={
        "filter[app]": app_id,
        "filter[state]": PENDING_SUBMISSION_STATES,
        "limit": PAGE_LIMIT,
    })
    pending = open_subs.get("data") or []
    if pending:
        lines = "; ".join(submission_line(sub) for sub in pending)
        raise fail(
            f"app {attr(app, 'bundleId')} already has an open review submission: "
            f"{lines}. Cancel or complete it in App Store Connect first.",
            error="submission_exists",
        )

    submission = api_request("POST", "/reviewSubmissions", body={
        "data": {
            "type": "reviewSubmissions",
            "attributes": {"platform": args.platform},
            "relationships": {
                "app": {"data": {"type": "apps", "id": app_id}}
            },
        }
    })
    submission_id = str((submission.get("data") or {}).get("id"))

    def cancel_submission(reason: str) -> None:
        # Best effort: a failed step must not strand a half-built submission.
        try:
            api_request("PATCH", f"/reviewSubmissions/{submission_id}", body={
                "data": {
                    "type": "reviewSubmissions",
                    "id": submission_id,
                    "attributes": {"canceled": True},
                }
            })
            note = f"canceled the partially built submission {submission_id}"
        except SystemExit:
            note = (
                f"could not cancel submission {submission_id}; cancel it in "
                f"App Store Connect before retrying"
            )
        raise fail(f"{reason}; {note}", error="submit_incomplete")

    try:
        api_request("POST", "/reviewSubmissionItems", body={
            "data": {
                "type": "reviewSubmissionItems",
                "relationships": {
                    "reviewSubmission": {
                        "data": {"type": "reviewSubmissions", "id": submission_id}
                    },
                    "appStoreVersion": {
                        "data": {"type": "appStoreVersions", "id": args.version_id}
                    },
                },
            }
        })
    except SystemExit:
        cancel_submission(f"attaching version {args.version_id} failed")

    try:
        updated = api_request("PATCH", f"/reviewSubmissions/{submission_id}", body={
            "data": {
                "type": "reviewSubmissions",
                "id": submission_id,
                "attributes": {"submitted": True},
            }
        })
    except SystemExit:
        cancel_submission("marking the submission submitted failed")

    data = updated.get("data") or {}
    state = attr(data, "state")
    if state == "READY_FOR_REVIEW":
        cancel_submission(
            f"submission {submission_id} is still READY_FOR_REVIEW after the "
            f"submit call, so nothing went to App Review"
        )
    if args.json:
        print(json.dumps({"ok": True, "submission": data}, indent=2))
    else:
        print(f"Submitted for review: {submission_line(data)}")
        print(f"App: {attr(app, 'bundleId')}  version id: {args.version_id}")
    return 0


# ── parser ─────────────────────────────────────────────────────────────────


def add_list_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=PAGE_LIMIT,
                        help=f"Rows to fetch (page cap {PAGE_LIMIT})")
    parser.add_argument("--all", action="store_true",
                        help="Follow pagination to the end")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-appstore",
        description="App Store Connect management via Apple's official REST API",
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snap = subparsers.add_parser("snapshot", help="Apps + latest builds + pending submissions")
    snap.add_argument("--limit", type=int, default=10,
                      help="Apps to include in the snapshot fan-out (default 10)")

    apps = subparsers.add_parser("apps", help="List apps")
    apps.add_argument("--bundle-id", help="Filter by exact bundle id")
    apps.add_argument("--name", help="Filter by app name")
    add_list_flags(apps)

    app = subparsers.add_parser("app", help="One app's details")
    app.add_argument("ref", help="App Store Connect app id or bundle id")

    builds = subparsers.add_parser("builds", help="List builds, newest first")
    builds.add_argument("--app", help="App id or bundle id")
    add_list_flags(builds)

    versions = subparsers.add_parser("versions", help="App Store versions for an app")
    versions.add_argument("ref", help="App id or bundle id")
    versions.add_argument("--platform", choices=PLATFORMS)
    add_list_flags(versions)

    tf = subparsers.add_parser("testflight", help="TestFlight groups and testers")
    tf_sub = tf.add_subparsers(dest="tf_command", required=True)
    groups = tf_sub.add_parser("groups", help="List beta groups")
    groups.add_argument("--app", help="App id or bundle id")
    add_list_flags(groups)
    testers = tf_sub.add_parser("testers", help="List beta testers")
    testers.add_argument("--group", help="Beta group id")
    testers.add_argument("--email", help="Filter by tester email")
    testers.add_argument("--app", help="App id or bundle id")
    add_list_flags(testers)
    add_tester = tf_sub.add_parser("add-tester", help="Invite a beta tester")
    add_tester.add_argument("email", help="Tester email address")
    add_tester.add_argument("--group", action="append", required=True,
                            help="Beta group id (repeatable)")
    add_tester.add_argument("--first", help="First name")
    add_tester.add_argument("--last", help="Last name")

    reviews = subparsers.add_parser("reviews", help="Customer reviews for an app")
    reviews.add_argument("ref", help="App id or bundle id")
    reviews.add_argument("--sort", choices=REVIEW_SORTS, default="-createdDate")
    reviews.add_argument("--rating", type=int, choices=range(1, 6))
    reviews.add_argument("--territory", help="Territory code, like USA")
    add_list_flags(reviews)

    certs = subparsers.add_parser("certs", help="Signing certificates")
    certs.add_argument("--type", help="Certificate type filter")
    certs.add_argument("--with-content", action="store_true",
                       help="Include certificateContent in JSON output")
    add_list_flags(certs)

    profiles = subparsers.add_parser("profiles", help="Provisioning profiles")
    profiles.add_argument("--type", help="Profile type filter")
    profiles.add_argument("--with-content", action="store_true",
                          help="Include profileContent in JSON output")
    add_list_flags(profiles)

    devices = subparsers.add_parser("devices", help="Registered devices")
    devices.add_argument("--platform", choices=DEVICE_PLATFORMS)
    devices.add_argument("--status", choices=("ENABLED", "DISABLED"))
    add_list_flags(devices)

    reports = subparsers.add_parser("reports", help="Sales and finance report downloads")
    rep_sub = reports.add_subparsers(dest="report_command", required=True)
    sales = rep_sub.add_parser("sales", help="Download a sales report")
    sales.add_argument("--vendor", required=True, help="Vendor number")
    sales.add_argument("--frequency", required=True, choices=SALES_FREQUENCIES)
    sales.add_argument("--date", help="Report date (YYYY-MM-DD, YYYY-MM, or YYYY per frequency)")
    sales.add_argument("--type", default="SALES", choices=SALES_REPORT_TYPES)
    sales.add_argument("--subtype", default="SUMMARY", choices=SALES_REPORT_SUBTYPES)
    sales.add_argument("--output", required=True, help="Output file path for the decompressed report")
    sales.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    finance = rep_sub.add_parser("finance", help="Download a finance report")
    finance.add_argument("--vendor", required=True, help="Vendor number")
    finance.add_argument("--region", required=True, help="Region code, like US or ZZ")
    finance.add_argument("--date", required=True, help="Report date (YYYY-MM)")
    finance.add_argument("--type", default="FINANCIAL", choices=FINANCE_REPORT_TYPES)
    finance.add_argument("--output", required=True, help="Output file path for the decompressed report")
    finance.add_argument("--force", action="store_true", help="Overwrite an existing output file")

    respond = subparsers.add_parser("respond", help="Publish a response to a customer review")
    respond.add_argument("review_id", help="Customer review id")
    respond.add_argument("--body", required=True, help="Response text")

    submit = subparsers.add_parser("submit", help="Submit an App Store version for review")
    submit.add_argument("ref", help="App id or bundle id")
    submit.add_argument("--version-id", required=True, help="appStoreVersion id (see versions)")
    submit.add_argument("--platform", choices=PLATFORMS, default="IOS")
    submit.add_argument("--yes", action="store_true", help="Confirm the submission")

    return parser


HANDLERS = {
    "snapshot": cmd_snapshot,
    "apps": cmd_apps,
    "app": cmd_app,
    "builds": cmd_builds,
    "versions": cmd_versions,
    "testflight": cmd_testflight,
    "reviews": cmd_reviews,
    "certs": cmd_certs,
    "profiles": cmd_profiles,
    "devices": cmd_devices,
    "reports": cmd_reports,
    "respond": cmd_respond,
    "submit": cmd_submit,
}


def main() -> int:
    global JSON_MODE
    args = build_parser().parse_args()
    JSON_MODE = bool(getattr(args, "json", False))
    handler = HANDLERS.get(args.command)
    if handler is None:
        raise fail(f"unknown command: {args.command}", code=2)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
