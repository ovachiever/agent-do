#!/usr/bin/env python3
"""Offline tests for agent-appstore: fixture server, no network, no Apple.

Drives tools/agent-appstore/appstore_ops.py as a subprocess against a local
JSON:API fixture and asserts the behavior the tool claims: JWT shape and
lifetime, 401 re-mint, pagination and truncation markers, the device platform
enum split, signing-material redaction, the existing-tester linkage path, the
recoverable submit flow, report download handling, and JSON-mode errors.
Also locks PAGE_LIMIT to the quantity authority record it cites.
"""

from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "agent-appstore" / "appstore_ops.py"
sys.path.insert(0, str(REPO / "lib"))

PASS = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global PASS
    if not condition:
        print(f"  FAIL {label}: {detail}")
        raise SystemExit(1)
    PASS += 1
    print(f"  ok {label}")


# ── fixture server ─────────────────────────────────────────────────────────

REQUESTS: list[dict] = []
STATE = {"builds_401_once": True, "last_submission_app": ""}

PENDING_APP = "1234567890"
HAPPY_SUBMIT_APP = "555"
FAILING_ITEM_APP = "999"


def jsonapi(data, total=None, next_url=None):
    payload = {"data": data, "links": {}}
    if total is not None:
        payload["meta"] = {"paging": {"total": total, "limit": 200}}
    if next_url:
        payload["links"]["next"] = next_url
    return payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _record(self, body=None):
        REQUESTS.append({
            "method": self.command,
            "path": self.path,
            "accept": self.headers.get("Accept", ""),
            "authorization": self.headers.get("Authorization", ""),
            "body": body,
        })

    def _send(self, payload, status=200, content_type="application/json", raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else None

    def do_GET(self):
        self._record()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path

        if path == "/v1/apps":
            page1 = [
                {"type": "apps", "id": PENDING_APP,
                 "attributes": {"name": "Demo", "bundleId": "com.example.demo",
                                "sku": "D1", "primaryLocale": "en-US"}},
                {"type": "apps", "id": "1234567891",
                 "attributes": {"name": "Other", "bundleId": "com.example.other",
                                "sku": "O1", "primaryLocale": "en-US"}},
            ]
            if query.get("filter[bundleId]"):
                wanted = query["filter[bundleId]"][0]
                hits = [a for a in page1 if a["attributes"]["bundleId"] == wanted]
                return self._send(jsonapi(hits, total=len(hits)))
            if query.get("page") == ["2"]:
                third = [{"type": "apps", "id": "1234567892",
                          "attributes": {"name": "Third", "bundleId": "com.example.third",
                                         "sku": "T1", "primaryLocale": "en-US"}}]
                return self._send(jsonapi(third, total=3))
            port = self.server.server_address[1]
            return self._send(jsonapi(
                page1, total=3,
                next_url=f"http://127.0.0.1:{port}/v1/apps?page=2&limit=2"))

        if path == "/v1/builds":
            if STATE["builds_401_once"]:
                STATE["builds_401_once"] = False
                return self._send({"errors": [{"status": "401", "code": "NOT_AUTHORIZED",
                                               "title": "auth", "detail": "forced"}]},
                                  status=401)
            build = [{"type": "builds", "id": "b-1",
                      "attributes": {"version": "42", "uploadedDate": "2026-10-01T00:00:00Z",
                                     "processingState": "VALID", "expired": False}}]
            return self._send(jsonapi(build, total=7))

        if path == "/v1/reviewSubmissions":
            app = (query.get("filter[app]") or [""])[0]
            if app == PENDING_APP:
                subs = [{"type": "reviewSubmissions", "id": "rs-1",
                         "attributes": {"platform": "IOS", "state": "WAITING_FOR_REVIEW",
                                        "submittedDate": None}}]
                return self._send(jsonapi(subs, total=1))
            return self._send(jsonapi([], total=0))

        if path == "/v1/betaTesters":
            email = (query.get("filter[email]") or [""])[0]
            if email == "existing@example.com":
                tester = [{"type": "betaTesters", "id": "bt-1",
                           "attributes": {"email": email, "firstName": "Already",
                                          "lastName": "Here", "inviteType": "EMAIL",
                                          "state": "INVITED"}}]
                return self._send(jsonapi(tester, total=1))
            return self._send(jsonapi([], total=0))

        if path == "/v1/certificates":
            certs = [{"type": "certificates", "id": "c-1",
                      "attributes": {"displayName": "Dist", "certificateType": "DISTRIBUTION",
                                     "expirationDate": "2027-01-01T00:00:00Z",
                                     "certificateContent": "BASE64CERTMATERIAL"}}]
            return self._send(jsonapi(certs, total=1))

        if path.startswith("/v1/apps/") and path.endswith("/customerReviews"):
            reviews = [{"type": "customerReviews", "id": "r-1",
                        "attributes": {"rating": 2, "title": "Hmm",
                                       "body": "The widget crashes on launch.",
                                       "reviewerNickname": "nick", "territory": "USA",
                                       "createdDate": "2026-10-01T00:00:00Z"}}]
            return self._send(jsonapi(reviews, total=1))

        if path.startswith("/v1/apps/"):
            app_id = path.rsplit("/", 1)[-1]
            return self._send({"data": {"type": "apps", "id": app_id,
                                        "attributes": {"name": "Demo",
                                                       "bundleId": "com.example.demo",
                                                       "sku": "D1",
                                                       "primaryLocale": "en-US"}}})

        if path == "/v1/salesReports":
            raw = gzip.compress(b"Provider\tSKU\tUnits\nAPPLE\tD1\t3\n")
            return self._send(None, content_type="application/a-gzip", raw=raw)

        return self._send(jsonapi([], total=0))

    def do_POST(self):
        body = self._read_body()
        self._record(body)
        path = urlparse(self.path).path

        if path == "/v1/betaTesters":
            attrs = body["data"]["attributes"]
            tester = {"type": "betaTesters", "id": "bt-new",
                      "attributes": {"email": attrs["email"],
                                     "firstName": attrs.get("firstName"),
                                     "lastName": attrs.get("lastName"),
                                     "inviteType": "EMAIL", "state": "INVITED"}}
            return self._send({"data": tester}, status=201)

        if path.startswith("/v1/betaGroups/") and path.endswith("/relationships/betaTesters"):
            return self._send(None, status=204, raw=b"")

        if path == "/v1/reviewSubmissions":
            STATE["last_submission_app"] = body["data"]["relationships"]["app"]["data"]["id"]
            sub = {"type": "reviewSubmissions", "id": "sub-1",
                   "attributes": {"platform": "IOS", "state": "READY_FOR_REVIEW",
                                  "submittedDate": None}}
            return self._send({"data": sub}, status=201)

        if path == "/v1/reviewSubmissionItems":
            if STATE["last_submission_app"] == FAILING_ITEM_APP:
                return self._send({"errors": [{"status": "422", "code": "ENTITY_ERROR",
                                               "title": "invalid",
                                               "detail": "forced item failure"}]},
                                  status=422)
            return self._send({"data": {"type": "reviewSubmissionItems", "id": "it-1"}},
                              status=201)

        return self._send(jsonapi([]))

    def do_PATCH(self):
        body = self._read_body()
        self._record(body)
        path = urlparse(self.path).path
        if path.startswith("/v1/reviewSubmissions/"):
            attrs = body["data"].get("attributes") or {}
            state = "CANCELING" if attrs.get("canceled") else "WAITING_FOR_REVIEW"
            sub = {"type": "reviewSubmissions", "id": body["data"]["id"],
                   "attributes": {"platform": "IOS", "state": state,
                                  "submittedDate": "2026-10-16T00:00:00Z"}}
            return self._send({"data": sub})
        return self._send(jsonapi([]))


def make_key(tmp: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path = tmp / "test-key.p8"
    path.write_bytes(pem)
    return path


def run_tool(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def main() -> int:
    from quantities import lookup
    sys.path.insert(0, str(TOOL.parent))
    import appstore_ops

    print("appstore offline tests")

    # The shipped page cap IS the authority record; a stale copy fails here.
    record = lookup("apple.appstoreconnect.page_limit")
    check(appstore_ops.PAGE_LIMIT == int(record["value"]),
          "PAGE_LIMIT equals apple.appstoreconnect.page_limit",
          f"{appstore_ops.PAGE_LIMIT} != {record['value']}")
    cap = lookup("apple.appstoreconnect.token_lifetime")
    check(appstore_ops.token_lifetime_seconds() <= int(cap["value"]),
          "token lifetime stays under the authority cap")
    check(appstore_ops.DEVICE_PLATFORMS == ("IOS", "MAC_OS", "UNIVERSAL"),
          "device platform enum is BundleIdPlatform")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        key_path = make_key(tmp)
        env = dict(os.environ)
        env.update({
            "ASC_API_URL": f"http://127.0.0.1:{port}/v1",
            "ASC_KEY_ID": "TESTKEY123",
            "ASC_ISSUER_ID": "57246542-96fe-1a63-e053-0824d011072a",
            "ASC_PRIVATE_KEY_PATH": str(key_path),
        })

        # pagination + truncation marker
        result = run_tool(env, "apps", "--limit", "2")
        check(result.returncode == 0, "apps exits 0", result.stderr)
        check("[truncated: 2 of 3 shown]" in result.stdout,
              "truncation marker carries magnitude", result.stdout)
        result = run_tool(env, "apps", "--limit", "2", "--all")
        check("3 apps (total 3)" in result.stdout, "--all follows pagination",
              result.stdout)

        # 401 re-mint: first builds call is refused, retry must succeed
        result = run_tool(env, "builds", "--app", PENDING_APP, "--limit", "1")
        check(result.returncode == 0, "builds survives a forced 401", result.stderr)
        build_tokens = [r["authorization"] for r in REQUESTS
                        if r["path"].startswith("/v1/builds")]
        check(len(build_tokens) >= 2 and build_tokens[-1] != build_tokens[-2],
              "retry after 401 carries a freshly minted token")

        # JWT shape, signature, lifetime (verified against the test key)
        import jwt as pyjwt
        from cryptography.hazmat.primitives import serialization as ser
        token = REQUESTS[0]["authorization"].removeprefix("Bearer ")
        public = ser.load_pem_private_key(key_path.read_bytes(), None).public_key()
        header = pyjwt.get_unverified_header(token)
        claims = pyjwt.decode(token, public, algorithms=["ES256"],
                              audience="appstoreconnect-v1")
        check(header == {"alg": "ES256", "kid": "TESTKEY123", "typ": "JWT"},
              "JWT header exact", str(header))
        check(claims["iss"] == env["ASC_ISSUER_ID"], "JWT iss claim")
        check(claims["exp"] - claims["iat"] <= int(cap["value"]),
              "JWT lifetime under the 20-minute cap")

        # device platform enum split
        result = run_tool(env, "devices", "--platform", "TV_OS")
        check(result.returncode == 2, "devices refuses TV_OS", result.stderr)
        result = run_tool(env, "devices", "--platform", "UNIVERSAL")
        check(result.returncode == 0, "devices accepts UNIVERSAL", result.stderr)

        # signing material redaction
        result = run_tool(env, "--json", "certs")
        check("BASE64CERTMATERIAL" not in result.stdout,
              "certs --json redacts certificateContent", result.stdout)
        check("[redacted:" in result.stdout, "redaction is announced")
        result = run_tool(env, "--json", "certs", "--with-content")
        check("BASE64CERTMATERIAL" in result.stdout,
              "--with-content includes certificateContent")

        # review body reaches the text output
        result = run_tool(env, "reviews", PENDING_APP)
        check("The widget crashes on launch." in result.stdout,
              "reviews text output carries the body", result.stdout)

        # add-tester: existing email links, never re-creates
        REQUESTS.clear()
        result = run_tool(env, "testflight", "add-tester", "existing@example.com",
                          "--group", "g1")
        check(result.returncode == 0, "add-tester existing exits 0", result.stderr)
        posts = [r["path"] for r in REQUESTS if r["method"] == "POST"]
        check("/v1/betaGroups/g1/relationships/betaTesters" in posts,
              "existing tester is linked via the relationships endpoint")
        check("/v1/betaTesters" not in posts, "existing tester is not re-created")
        result = run_tool(env, "testflight", "add-tester", "new@example.com",
                          "--group", "g1")
        check(result.returncode == 0, "add-tester new exits 0", result.stderr)
        check(any(r["path"] == "/v1/betaTesters" and r["method"] == "POST"
                  for r in REQUESTS), "new tester is created")

        # submit: refuses while a submission is open
        result = run_tool(env, "submit", PENDING_APP, "--version-id", "v-1", "--yes")
        check(result.returncode == 1 and "already has an open review submission"
              in result.stderr, "submit refuses on an open submission", result.stderr)

        # submit: happy path reaches WAITING_FOR_REVIEW
        result = run_tool(env, "submit", HAPPY_SUBMIT_APP, "--version-id", "v-1", "--yes")
        check(result.returncode == 0, "submit happy path exits 0", result.stderr)
        check("WAITING_FOR_REVIEW" in result.stdout, "submit reports the new state")

        # submit: item failure cancels the submission it created
        REQUESTS.clear()
        result = run_tool(env, "submit", FAILING_ITEM_APP, "--version-id", "v-1", "--yes")
        check(result.returncode == 1, "submit fails when the item attach fails")
        cancels = [r for r in REQUESTS if r["method"] == "PATCH"
                   and (r["body"] or {}).get("data", {}).get("attributes", {}).get("canceled")]
        check(len(cancels) == 1, "failed submit cancels its own submission")
        check("canceled the partially built submission" in result.stderr,
              "cancel is reported to the caller", result.stderr)

        # reports: a-gzip only Accept, decompressed file, --output required
        REQUESTS.clear()
        out = tmp / "sales.tsv"
        result = run_tool(env, "reports", "sales", "--vendor", "1", "--frequency",
                          "MONTHLY", "--output", str(out))
        check(result.returncode == 0, "sales report exits 0", result.stderr)
        check(out.read_text().startswith("Provider\tSKU"),
              "report is decompressed tab-separated text")
        report_req = [r for r in REQUESTS if r["path"].startswith("/v1/salesReports")]
        check(report_req and report_req[0]["accept"] == "application/a-gzip",
              "report request accepts application/a-gzip only",
              str(report_req))
        result = run_tool(env, "reports", "sales", "--vendor", "1", "--frequency",
                          "MONTHLY")
        check(result.returncode == 2, "--output is required")

        # JSON-mode failure is one JSON document
        bare = {k: v for k, v in env.items() if not k.startswith("ASC_")}
        bare["ASC_API_URL"] = env["ASC_API_URL"]
        result = run_tool(bare, "--json", "apps")
        check(result.returncode == 1, "missing creds exits 1")
        payload = json.loads(result.stdout)
        check(payload.get("ok") is False and "missing credentials"
              in payload.get("message", ""), "json error is a JSON document",
              result.stdout)

    server.shutdown()
    print(f"appstore tests passed ({PASS} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
