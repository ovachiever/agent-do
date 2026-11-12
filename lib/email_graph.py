"""Read-only Graph mailbox provider, adapted from travel-bank's graph_auth/mailsearch.

Use the same O365 client-credentials flow and search-plus-local-verification
contract. Credentials arrive through agent-do's registry/creds resolver. Tokens
stay in memory; this module never loads another project's .env or token cache.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import logging
import os
from urllib.parse import quote, unquote, urlparse


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
GRAPH_KEYS = ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID", "GRAPH_TARGET_MAILBOX")
# Microsoft, https://learn.microsoft.com/en-us/graph/search-query-parameter
# This is a provider ceiling, never a page size or a client-side truncation.
GRAPH_SEARCH_CEILING = 1000
GRAPH_SEARCH_AUTHORITY = "https://learn.microsoft.com/en-us/graph/search-query-parameter"
MESSAGE_FIELDS = "id,parentFolderId,subject,from,receivedDateTime,isRead,body,internetMessageId,hasAttachments"


class GraphError(Exception):
    def __init__(self, code: str, *, status: int | None = None):
        self.code = code
        self.status = status
        super().__init__(code)

    def receipt(self) -> dict:
        return {"error": self.code, **({"http_status": self.status} if self.status else {})}


class GraphMailbox:
    def __init__(self):
        self.target = os.environ.get("GRAPH_TARGET_MAILBOX", "").strip()
        self.local_account = os.environ.get("AGENT_EMAIL_GRAPH_ACCOUNT", "").strip()
        self.missing = [key for key in GRAPH_KEYS if not os.environ.get(key)]
        self.sdk_available = importlib.util.find_spec("O365") is not None
        self.account = None
        self.roles: list[str] | None = None
        self._folders: list[dict] | None = None
        self.last_search: dict = {}

    @property
    def configured(self) -> bool:
        return not self.missing and self.sdk_available

    @property
    def root(self) -> str:
        return f"{GRAPH_ROOT}/users/{quote(self.target, safe='')}"

    def status(self, *, probe: bool = False) -> dict:
        result = {
            "provider": "graph", "target_mailbox": self.target,
            "configured": not self.missing, "missing": self.missing,
            "sdk_available": self.sdk_available, "live_search_ready": False,
            "dependency": "O365>=2.1,<3",
            "readiness": "not_checked" if self.configured else "not_configured",
            "roles": self.roles,
            "permission_scope": "Application roles do not prove Exchange mailbox access-policy restrictions.",
        }
        if probe and self.configured:
            try:
                # A real body read distinguishes Mail.Read from Mail.ReadBasic.
                payload = self._get(self.root + "/mailFolders/inbox/messages", params={
                    "$select": "id,body,receivedDateTime", "$orderby": "receivedDateTime desc",
                })
                if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                    raise GraphError("graph_invalid_response")
                result.update(live_search_ready=True, readiness="verified", roles=self.roles,
                              live_newest_received=next((r.get("receivedDateTime") for r in payload["value"]), None))
            except GraphError as exc:
                result.update(readiness="failed", **exc.receipt())
        return result

    def _authenticate(self) -> None:
        if self.account is not None:
            return
        if self.missing:
            raise GraphError("graph_credentials_missing")
        if not self.sdk_available:
            raise GraphError("graph_dependency_missing")
        # SDK diagnostics can include HTTP response bodies. Only typed, sanitized
        # errors cross this provider boundary, never tokens or OAuth responses.
        for name in ("O365", "msal"):
            logger = logging.getLogger(name)
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
        try:
            from O365 import Account
            from O365.utils.token import MemoryTokenBackend

            backend = MemoryTokenBackend()
            account = Account(
                (os.environ["AZURE_CLIENT_ID"], os.environ["AZURE_CLIENT_SECRET"]),
                auth_flow_type="credentials", tenant_id=os.environ["AZURE_TENANT_ID"],
                token_backend=backend,
                default_headers={"Prefer": 'IdType="ImmutableId", outlook.body-content-type="text"'},
            )
            if not account.authenticate():
                raise GraphError("graph_authentication_failed")
            token = backend.get_access_token() or {}
            # Observation only, never an authorization decision or JWT verifier.
            try:
                encoded = token["secret"].split(".")[1]
                claims = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
                self.roles = sorted(str(role) for role in claims["roles"])
            except (KeyError, ValueError, IndexError, TypeError):
                self.roles = None
            self.account = account
        except GraphError:
            raise
        except Exception:
            raise GraphError("graph_authentication_failed") from None

    def _get(self, url: str, *, params: dict | None = None, raw: bool = False):
        # Follow provider pagination verbatim, but never send auth to a different
        # host, mailbox or API resource supplied by a response.
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "graph.microsoft.com" or not unquote(parsed.path).startswith(
            f"/v1.0/users/{self.target}/"
        ):
            raise GraphError("graph_invalid_next_link")
        self._authenticate()
        try:
            response = self.account.con.get(url, params=params)
            response.raise_for_status()
            return response.text if raw else response.json()
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise GraphError("graph_request_failed", status=status) from None

    def _pages(self, url: str, *, params: dict | None = None):
        visited = set()
        while url:
            if url in visited:
                raise GraphError("graph_pagination_loop")
            visited.add(url)
            payload = self._get(url, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                raise GraphError("graph_invalid_response")
            if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in payload["value"]):
                raise GraphError("graph_invalid_response")
            yield from payload["value"]
            url = payload.get("@odata.nextLink")
            params = None
            if url is not None and not isinstance(url, str):
                raise GraphError("graph_invalid_next_link")

    def folders(self) -> list[dict]:
        if self._folders is None:
            folders = []
            pending = [self.root + "/mailFolders"]
            seen = set()
            while pending:
                for folder in self._pages(pending.pop(), params={"$select": "id,displayName,childFolderCount"}):
                    if folder["id"] in seen:
                        continue
                    seen.add(folder["id"])
                    folders.append(folder)
                    if folder.get("childFolderCount"):
                        pending.append(self.root + "/mailFolders/" + quote(folder["id"], safe="") + "/childFolders")
            self._folders = folders
        return self._folders

    def folder(self, name: str) -> dict:
        if name.lower() in {"inbox", "in box", "inbox/"}:
            return self._get(self.root + "/mailFolders/inbox", params={"$select": "id,displayName"})
        matches = [f for f in self.folders() if f["displayName"].lower() == name.lower() or f["id"] == name]
        if len(matches) != 1:
            raise GraphError("graph_mailbox_ambiguous" if matches else "graph_mailbox_not_found")
        return matches[0]

    def message_id(self, remote_id: str) -> str:
        return f"graph:{quote(self.target, safe='')}:{remote_id}"

    def query(self, args, *, matches=None) -> tuple[list[dict], tuple[int, int]]:
        folder_name = args.mailbox or ("" if args.all_mailboxes else "Inbox")
        folder = self.folder(folder_name) if folder_name else None
        collection = self.root + ("/mailFolders/" + quote(folder["id"], safe="") if folder else "") + "/messages"
        params = {"$select": MESSAGE_FIELDS}
        # Match the existing literal subject/body search contract locally, after
        # Graph's indexed search (which can also match attachments).
        term = args.query_text or args.contains or args.subject_filter or args.from_filter
        if term:
            params["$search"] = json.dumps(term)
        else:
            params["$orderby"] = "receivedDateTime desc"
        rows = []
        matched = 0
        for row in self._pages(collection, params=params):
            rows.append(row)
            # Unsearched Graph collections are ordered by receivedDateTime.
            # A caller-requested limit can stop that walk after matching, never
            # before it. Search results use sent-date ordering, so read every
            # page before selecting the newest received messages.
            if matches is None or matches(row):
                matched += 1
            if not term and args.limit is not None and matched >= args.limit:
                break
        self.last_search = {
            "returned_by_provider": len(rows), "provider_search_ceiling": GRAPH_SEARCH_CEILING if term else None,
            "authority": GRAPH_SEARCH_AUTHORITY if term else None,
            "possibly_truncated": bool(term and len(rows) >= GRAPH_SEARCH_CEILING),
        }
        for row in rows:
            row["_mailbox"] = folder["displayName"] if folder else row.get("parentFolderId", "")
        counts = []
        for unread in (False, True):
            count_params = {"$count": "true", "$select": "id"}
            if unread:
                count_params["$filter"] = "isRead eq false"
            payload = self._get(collection, params=count_params)
            count = payload.get("@odata.count")
            if not isinstance(count, int):
                raise GraphError("graph_count_unavailable")
            counts.append(count)
        return rows, tuple(counts)

    def get(self, message_id: str, *, mailbox: str = "", all_mailboxes: bool = False) -> dict:
        prefix = self.message_id("")
        if not message_id.startswith(prefix):
            raise GraphError("graph_message_account_mismatch")
        remote_id = message_id[len(prefix):]
        url = self.root + "/messages/" + quote(remote_id, safe="")
        row = self._get(url, params={"$select": MESSAGE_FIELDS})
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise GraphError("graph_invalid_response")
        folder = self.folder(mailbox or "Inbox") if mailbox or not all_mailboxes else None
        if folder and row.get("parentFolderId") != folder["id"]:
            raise GraphError("graph_message_outside_scope")
        row["_mailbox"] = folder["displayName"] if folder else row.get("parentFolderId", "")
        row["_raw_source"] = self._get(url + "/$value", raw=True)
        return row

    def resolve_message_id(self, internet_message_id: str) -> str:
        if not internet_message_id:
            raise GraphError("graph_message_id_unavailable")
        escaped = internet_message_id.replace("'", "''")
        rows = list(self._pages(self.root + "/messages", params={
            "$filter": f"internetMessageId eq '{escaped}'", "$select": "id",
        }))
        if len(rows) != 1:
            raise GraphError("graph_message_ambiguous" if rows else "graph_message_not_found")
        return self.message_id(rows[0]["id"])
