#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import contextlib
import fcntl
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


HOME = Path.home()


class ImportRefused(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class TypedArrayValue:
    def __init__(self, kind: str, data: bytes):
        self.kind = kind
        self.data = data


class EncodedValueRequired(ValueError):
    pass


def session_path(name: str) -> Path:
    if not name or name in {".", ".."} or any(char in name for char in ("/", "\\", "\0")):
        raise ImportRefused("INVALID_SESSION_NAME", "Session name must be a single directory name.")
    return HOME / ".agent-browse" / "sessions" / name


def write_json_atomic(file: Path, value: dict) -> str:
    """Publish a complete private file; return the digest of the published bytes."""
    content = json.dumps(value, indent=2).encode()
    with tempfile.NamedTemporaryFile(dir=file.parent, prefix=".import-", delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
            os.replace(temporary, file)
        finally:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(content).hexdigest()


BROWSERS = {
    "comet": {
        "extractor": "chromium",
        "profile_candidates": [
            HOME / "Library/Application Support/Comet/Default",
        ],
        "keychain_candidates": [
            ("Comet Safe Storage", "Comet"),
            ("ai.perplexity.comet Safe Storage", "ai.perplexity.comet"),
        ],
    },
    "atlas": {
        "extractor": "chromium",
        "profile_candidates": [
            *sorted(
                (HOME / "Library/Application Support/com.openai.atlas/browser-data/host").glob("user-*"),
                key=lambda candidate: candidate.stat().st_mtime,
                reverse=True,
            ),
            HOME / "Library/Application Support/com.openai.atlas/browser-data/host/Default",
        ],
        "keychain_candidates": [
            ("Chromium Safe Storage", "Chromium"),
            ("ChatGPT Atlas Safe Storage", "ChatGPT Atlas"),
            ("Atlas Safe Storage", "Atlas"),
            ("OpenAI Atlas Safe Storage", "OpenAI Atlas"),
            ("com.openai.atlas Safe Storage", "com.openai.atlas"),
        ],
    },
    "chrome": {
        "extractor": "chrome",
        "profile_candidates": [
            HOME / "Library/Application Support/Google/Chrome/Default",
        ],
        "keychain_candidates": [("Chrome Safe Storage", "Chrome")],
    },
    "arc": {
        "extractor": "arc",
        "profile_candidates": [
            HOME / "Library/Application Support/Arc/User Data/Default",
        ],
        "keychain_candidates": [("Arc Safe Storage", "Arc")],
    },
    "edge": {
        "extractor": "edge",
        "profile_candidates": [
            HOME / "Library/Application Support/Microsoft Edge/Default",
        ],
        "keychain_candidates": [("Microsoft Edge Safe Storage", "Microsoft Edge")],
    },
    "brave": {
        "extractor": "brave",
        "profile_candidates": [
            HOME / "Library/Application Support/BraveSoftware/Brave-Browser/Default",
        ],
        "keychain_candidates": [("Brave Safe Storage", "Brave")],
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{host}"


def origin_matches_domain(origin: str | None, domain_filter: str | None) -> bool:
    if not origin:
        return False
    if not domain_filter:
        return True
    hostname = urlparse(origin).hostname or ""
    needle = domain_filter.lstrip(".")
    return hostname == needle or hostname.endswith(f".{needle}")


def resolve_profile_root(config: dict) -> Path | None:
    profiles: list[Path] = config.get("profile_candidates", [])
    for candidate in profiles:
        cookie_file = resolve_cookie_file(candidate)
        if cookie_file and cookie_file.stat().st_size > 0:
            return candidate
    for candidate in profiles:
        if candidate.exists():
            return candidate
    return None


def resolve_cookie_file(profile_root: Path | None) -> Path | None:
    if not profile_root:
        return None
    for cookie_file in (profile_root / "Network" / "Cookies", profile_root / "Cookies"):
        if cookie_file.is_file():
            return cookie_file
    return None


def _patch_cookie3_keychain(config: dict, extractor_name: str):
    import browser_cookie3

    original_fn = browser_cookie3._get_osx_keychain_password
    default_password = getattr(browser_cookie3, "CHROMIUM_DEFAULT_PASSWORD", b"peanuts")

    def patched_fn(service, user):
        for candidate_service, candidate_user in config["keychain_candidates"]:
            if service == candidate_service and user == candidate_user:
                return original_fn(candidate_service, candidate_user)
        if extractor_name == "chromium" and service == "Chromium Safe Storage" and user == "Chromium":
            for candidate_service, candidate_user in config["keychain_candidates"]:
                result = original_fn(candidate_service, candidate_user)
                if result and result != default_password:
                    return result
        return original_fn(service, user)

    browser_cookie3._get_osx_keychain_password = patched_fn
    return browser_cookie3, original_fn


def extract_cookies(config: dict, cookie_file: Path, domain_filter: str | None):
    try:
        import browser_cookie3
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "browser_cookie3 is not installed. Install the Python package 'browser-cookie3' to use session import-browser."
        ) from exc

    extractor_name = config.get("extractor", "chromium")
    extractor = getattr(browser_cookie3, {
        "chromium": "Chromium", "chrome": "Chrome", "arc": "Arc", "edge": "Edge", "brave": "Brave",
    }.get(extractor_name, ""), None)
    if extractor is None:
        raise RuntimeError(f"browser_cookie3 does not support extractor '{extractor_name}'")

    original_fn = browser_cookie3._get_osx_keychain_password
    try:
        browser_cookie3, original_fn = _patch_cookie3_keychain(config, extractor_name)
        reader = extractor(domain_name=domain_filter or "", cookie_file=str(cookie_file))
        # CookieJar keys omit Chromium's partition identity, so load() can
        # overwrite a live first-party login with an expired third-party row.
        # Keep the dependency's database access, keychain and decryption, but
        # serialize every live row directly into Playwright's cookie format.
        with browser_cookie3._DatabaseConnetion(reader.cookie_file) as connection:
            connection.text_factory = browser_cookie3._text_factory
            cursor = connection.cursor()
            integrity = reader._has_integrity_check_for_cookie_domain(cursor)
            columns = {row[1] for row in cursor.execute("PRAGMA table_info(cookies)")}
            secure_column = "is_secure" if "is_secure" in columns else "secure"
            optional = [
                "top_frame_site_key" if "top_frame_site_key" in columns else "''",
                "has_cross_site_ancestor" if "has_cross_site_ancestor" in columns else "1",
                "samesite" if "samesite" in columns else "-1",
            ]
            query = f"SELECT host_key, path, {secure_column}, expires_utc, name, value, encrypted_value, is_httponly, {', '.join(optional)} FROM cookies"
            current_time = datetime.now(timezone.utc).timestamp()
            cookies = []
            for host, path, secure, expires_nt, name, value, encrypted, http_only, partition, cross_site, same_site in cursor.execute(query):
                if not origin_matches_domain(f"https://{host.lstrip('.')}", domain_filter):
                    continue
                expires = expires_nt / 1_000_000 - reader.UNIX_TO_NT_EPOCH_OFFSET if expires_nt else None
                if expires is not None and expires <= current_time:
                    continue
                cookie = {
                    "name": name, "value": reader._decrypt(value, encrypted, integrity),
                    "domain": host, "path": path, "secure": bool(secure), "httpOnly": bool(http_only),
                }
                if expires is not None:
                    cookie["expires"] = expires
                if same_site in {0, 1, 2}:
                    cookie["sameSite"] = {0: "None", 1: "Lax", 2: "Strict"}[same_site]
                elif same_site != -1:
                    raise ImportRefused("BROWSER_COOKIES_UNREADABLE", "Unsupported cookie SameSite value.")
                if partition:
                    cookie["partitionKey"] = partition
                    cookie["_crHasCrossSiteAncestor"] = bool(cross_site)
                cookies.append(cookie)
            return cookies
    finally:
        browser_cookie3._get_osx_keychain_password = original_fn


def choose_live_values(records: Iterable, key_attr: str, value_attr: str, seq_attr: str, live_predicate) -> dict[str, str]:
    latest: dict[str, tuple[int, bool, str]] = {}
    for record in records:
        key = getattr(record, key_attr, None)
        if not key:
            continue
        seq = int(getattr(record, seq_attr, 0) or 0)
        is_live = bool(live_predicate(record))
        value = getattr(record, value_attr, "") or ""
        prev = latest.get(key)
        if prev is None or seq >= prev[0]:
            latest[key] = (seq, is_live, value)
    return {
        key: value
        for key, (_, is_live, value) in latest.items()
        if is_live
    }


def parse_indexeddb_origin_dirname(dirname: str) -> str | None:
    base = dirname.removesuffix(".indexeddb.leveldb")
    match = re.match(r"^(https?)_(.+)_(\d+)$", base)
    if not match:
        return None
    scheme, host, port = match.groups()
    if port == "0":
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def to_playwright_json(value):
    if isinstance(value, TypedArrayValue):
        raise EncodedValueRequired("typed arrays require Playwright valueEncoded")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("unsupported non-finite float")
        return value
    if isinstance(value, tuple):
        return [to_playwright_json(item) for item in value]
    if isinstance(value, list):
        return [to_playwright_json(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("unsupported non-string object key")
            result[key] = to_playwright_json(item)
        return result
    raise ValueError(f"unsupported IndexedDB value type: {type(value).__name__}")


def to_playwright_encoded(value, seen=None):
    """Playwright's storageScript serialized-value format, including typed arrays.

    Keep byte views as bytes instead of expanding them into millions of JSON
    integers and changing their JavaScript type during restoration.
    """
    seen = {} if seen is None else seen
    if isinstance(value, TypedArrayValue):
        return {"ta": {"k": value.kind, "b": base64.b64encode(value.data).decode("ascii")}}
    if value is None:
        return {"v": "null"}
    if isinstance(value, (str, bool, int, float)):
        return to_playwright_json(value)
    if isinstance(value, (list, tuple, dict)):
        if id(value) in seen:
            return {"ref": seen[id(value)]}
        ref = seen[id(value)] = len(seen) + 1
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("unsupported non-string object key")
            return {"o": [{"k": key, "v": to_playwright_encoded(item, seen)} for key, item in value.items()], "id": ref}
        return {"a": [to_playwright_encoded(item, seen) for item in value], "id": ref}
    raise ValueError(f"unsupported IndexedDB value type: {type(value).__name__}")


def decode_object_store_key_path(raw_value: bytes | None):
    if not raw_value or raw_value in {b"\x00", b"\x00\x00", b"\x00\x00\x00"}:
        return None
    raise ValueError(f"unsupported IndexedDB keyPath encoding: {raw_value!r}")


def decode_object_store_auto_increment(raw_value: bytes | None) -> bool:
    return bool(raw_value and raw_value not in {b"\x00", b"\x00\x00"})


def latest_leveldb_records(records: Iterable) -> list:
    latest = {}
    for record in records:
        key = record.user_key
        if key not in latest or record.seq > latest[key].seq:
            latest[key] = record
    return sorted(latest.values(), key=lambda record: record.seq)


def collect_indexeddb(profile_root: Path | None, domain_filter: str | None):
    warnings: list[str] = []
    indexeddb_by_origin: dict[str, list[dict]] = {}

    if not profile_root:
        return indexeddb_by_origin, warnings

    try:
        import ccl_simplesnappy
        from ccl_chromium_reader.ccl_chromium_indexeddb import (
            IndexedDb,
            IndexedDbRecord,
            IdbKey,
            _le_varint_from_bytes,
            WrappedDatabase,
            DatabaseMetadataType,
            ObjectStoreMetadataType,
            decode_truncated_int,
        )
        from ccl_chromium_reader.serialization_formats import ccl_v8_value_deserializer, ccl_blink_value_deserializer
        from ccl_chromium_reader.storage_formats.ccl_leveldb import KeyState
    except ModuleNotFoundError as exc:
        raise ImportRefused("BROWSER_STORAGE_READER_UNAVAILABLE", "The required Chromium storage reader is unavailable; no fresh session was published.") from exc

    class BrowserValueReader(ccl_v8_value_deserializer.Deserializer):
        def _wrap_js_array_buffer_view(self, raw):
            if not isinstance(raw, bytes):
                raise ValueError("ArrayBufferView requires a byte buffer")
            tag = chr(self._read_le_varint()[0])
            offset = self._read_le_varint()[0]
            length = self._read_le_varint()[0]
            if self.version >= 14:
                self._read_le_varint()  # flags
            kinds = {"b": ("i8", 1), "B": ("ui8", 1), "C": ("ui8c", 1),
                     "w": ("i16", 2), "W": ("ui16", 2), "d": ("i32", 4), "D": ("ui32", 4),
                     "f": ("f32", 4), "F": ("f64", 8), "q": ("bi64", 8), "Q": ("bui64", 8)}
            if tag not in kinds:
                raise ValueError("unsupported ArrayBufferView tag")
            kind, width = kinds[tag]
            if offset + length > len(raw) or length % width or offset % width:
                raise ValueError("invalid ArrayBufferView bounds")
            return TypedArrayValue(kind, raw[offset:offset + length])

    class ChromiumIndexedDb(IndexedDb):
        def _cache_records(self):
            self._fetched_records = latest_leveldb_records(self._db.iterate_records_raw())

        def read_record_precursor(self, key, db_id, store_id, buffer, bad_deserializer_data_handler, external_data_path=None):
            # Chromium's IDBValueUnwrapper: ff 11 02 means one unframed Snappy
            # chunk containing the original Blink/V8 envelope. It can itself
            # be stored in a blob. The pinned reader handles blob indirection
            # but not this envelope; reuse its existing Snappy decoder.
            # chromium: third_party/blink/renderer/modules/indexeddb/idb_value_wrapping.cc
            if buffer.startswith(b"\xff\x11\x02"):
                buffer = ccl_simplesnappy.decompress(io.BytesIO(buffer[3:]))
            return super().read_record_precursor(
                key, db_id, store_id, buffer, bad_deserializer_data_handler, external_data_path
            )

        def iterate_records(self, db_id, store_id, *, live_only=False, bad_deserializer_data_handler=None):
            # The pinned reader's default V8 adapter discards typed-array kind
            # and expands the bytes into a Python tuple. Use its envelope/key
            # readers with our type-preserving value decoder instead.
            prefix = self.make_prefix(db_id, store_id, 1)
            blink = ccl_blink_value_deserializer.BlinkV8Deserializer()
            for record in self._fetched_records:
                if not record.key.startswith(prefix) or (live_only and record.state != KeyState.Live):
                    continue
                key = IdbKey(record.key[len(prefix):])
                value, external_path = None, None
                if record.value:
                    _, version = _le_varint_from_bytes(record.value)
                    precursor = self.read_record_precursor(key, db_id, store_id, record.value[len(version):], None)
                    if precursor is None:
                        raise ValueError("IndexedDB record could not be resolved")
                    _, serialized, _, external_path = precursor
                    value = BrowserValueReader(serialized, host_object_delegate=blink.read).read()
                yield IndexedDbRecord(self, db_id, store_id, key, value,
                                      record.state == KeyState.Live, record.seq, record.origin_file, external_path)

    indexeddb_root = profile_root / "IndexedDB"
    if not indexeddb_root.exists():
        return indexeddb_by_origin, warnings

    for db_dir in sorted(indexeddb_root.glob("*.indexeddb.leveldb")):
        origin = parse_indexeddb_origin_dirname(db_dir.name)
        if not origin or not origin_matches_domain(origin, domain_filter):
            continue

        raw_db = None
        try:
            # Out-of-line IndexedDB values live beside the LevelDB, not in
            # Cookies or Local State. The reader resolves them during iteration.
            raw_db = ChromiumIndexedDb(db_dir, leveldb_blob_dir=db_dir.with_suffix(".blob"))
            databases: list[dict] = []
            for dbid in raw_db.global_metadata.db_ids:
                version_record = raw_db.database_metadata._metas.get((dbid.dbid_no, DatabaseMetadataType.IdbVersion))
                version = decode_truncated_int(version_record.value) if version_record else 1
                stores: list[dict] = []
                for object_store in WrappedDatabase(raw_db, dbid):
                    key_path_record = raw_db.object_store_meta._metas.get(
                        (dbid.dbid_no, object_store.object_store_id, ObjectStoreMetadataType.KeyPath)
                    )
                    auto_increment_record = raw_db.object_store_meta._metas.get(
                        (dbid.dbid_no, object_store.object_store_id, ObjectStoreMetadataType.AutoIncrementFlag)
                    )
                    try:
                        key_path = decode_object_store_key_path(key_path_record.value if key_path_record else None)
                    except ValueError as exc:
                        warnings.append(f"Skipping IndexedDB store {dbid.name}/{object_store.name}: {exc}")
                        continue

                    auto_increment = decode_object_store_auto_increment(
                        auto_increment_record.value if auto_increment_record else None
                    )
                    records: list[dict] = []
                    skipped_records = 0
                    for record in object_store.iterate_records(live_only=True):
                        if not record.is_live:
                            continue
                        try:
                            try:
                                entry = {"value": to_playwright_json(record.value)}
                            except EncodedValueRequired:
                                entry = {"valueEncoded": to_playwright_encoded(record.value)}
                            if key_path is None:
                                entry["key"] = to_playwright_json(record.key.value)
                        except ValueError:
                            skipped_records += 1
                            continue
                        records.append(entry)
                    if skipped_records:
                        warnings.append(
                            f"Skipped {skipped_records} non-serializable IndexedDB records in {dbid.name}/{object_store.name}"
                        )
                    if not records:
                        continue
                    store_payload = {
                        "name": object_store.name,
                        "records": records,
                        "indexes": [],
                        "autoIncrement": auto_increment,
                    }
                    if key_path is not None:
                        if isinstance(key_path, list):
                            store_payload["keyPathArray"] = key_path
                        else:
                            store_payload["keyPath"] = key_path
                    stores.append(store_payload)
                if stores:
                    databases.append(
                        {
                            "name": dbid.name,
                            "version": version,
                            "stores": stores,
                        }
                    )
            if databases:
                indexeddb_by_origin[origin] = databases
        except Exception as exc:
            raise ImportRefused(
                "BROWSER_STORAGE_UNREADABLE",
                f"Unable to decode IndexedDB for {origin} ({type(exc).__name__}). "
                "Check the profile and its sibling .indexeddb.blob directory.",
            ) from exc
        finally:
            if raw_db is not None:
                raw_db.close()

    return indexeddb_by_origin, warnings


def merge_origin_state(local_storage_origins: list[dict], indexeddb_by_origin: dict[str, list[dict]]) -> list[dict]:
    by_origin: dict[str, dict] = {}
    for origin in local_storage_origins:
        by_origin[origin["origin"]] = {
            "origin": origin["origin"],
            "localStorage": origin.get("localStorage", []),
        }
    for origin, databases in indexeddb_by_origin.items():
        entry = by_origin.setdefault(origin, {"origin": origin, "localStorage": []})
        entry["indexedDB"] = databases
    return [by_origin[key] for key in sorted(by_origin)]


def collect_session_storage(directory: Path, domain_filter: str | None) -> dict[str, dict[str, str]]:
    from ccl_chromium_reader.storage_formats.ccl_leveldb import RawLevelDb, KeyState

    # RawLevelDb is a forensic history reader. Imports need the current key
    # snapshot, including tombstones, before joining namespaces to map values.
    # Otherwise an obsolete namespace can falsely assign a reused map ID to
    # two origins, or resurrect deleted sessionStorage values.
    with RawLevelDb(directory) as db:
        records = latest_leveldb_records(db.iterate_records_raw())

    maps = {}
    for record in records:
        key = record.user_key
        if not key.startswith(b"namespace-") or record.state != KeyState.Live:
            continue
        parts = key.decode("utf-8").split("-", 2)
        if len(parts) != 3 or not parts[2] or not record.value:
            continue  # Namespace metadata without a storage map.
        storage_key = parts[2]
        map_id = record.value.decode("utf-8")
        if map_id in maps and maps[map_id] != storage_key:
            raise ImportRefused("BROWSER_STORAGE_UNREADABLE", "Live Session Storage map IDs disagree about their origin.")
        maps[map_id] = storage_key

    selected = {}
    for map_id, storage_key in maps.items():
        origin = normalize_origin(storage_key)
        if not origin or not origin_matches_domain(origin, domain_filter):
            continue
        if "^" in storage_key:
            raise ImportRefused("BROWSER_STORAGE_UNSUPPORTED", "Selected Session Storage has a partitioned origin that cannot be restored as an unpartitioned session.")
        selected[map_id] = origin

    values = {}
    for record in records:
        key = record.user_key
        if not key.startswith(b"map-"):
            continue
        parts = key.decode("utf-8").split("-", 2)
        if len(parts) != 3 or not parts[2] or parts[1] not in selected:
            continue
        pair = (selected[parts[1]], parts[2])
        if pair not in values or record.seq > values[pair].seq:
            values[pair] = record
    result = {}
    for (origin, key), record in values.items():
        if record.state == KeyState.Live:
            result.setdefault(origin, {})[key] = record.value.decode("utf-16-le")
    return result


def import_storage(profile_root: Path | None, domain_filter: str | None):
    warnings: list[str] = []
    local_storage_origins: list[dict] = []
    session_by_origin: dict[str, dict[str, str]] = {}

    if not profile_root:
        return [], session_by_origin, warnings

    try:
        from ccl_chromium_reader import ccl_chromium_localstorage
    except ModuleNotFoundError as exc:
        raise ImportRefused("BROWSER_STORAGE_READER_UNAVAILABLE", "The required Chromium storage reader is unavailable; no fresh session was published.") from exc

    local_storage_dir = profile_root / "Local Storage" / "leveldb"
    if local_storage_dir.exists():
        with ccl_chromium_localstorage.LocalStoreDb(local_storage_dir) as db:
            for storage_key in db.iter_storage_keys():
                origin = normalize_origin(str(storage_key))
                if not origin or not origin_matches_domain(origin, domain_filter):
                    continue
                values = choose_live_values(
                    db.iter_records_for_storage_key(storage_key),
                    key_attr="script_key",
                    value_attr="value",
                    seq_attr="leveldb_seq_number",
                    live_predicate=lambda rec: getattr(rec, "is_live", False),
                )
                if values:
                    local_storage_origins.append(
                        {
                            "origin": origin,
                            "localStorage": [
                                {"name": key, "value": value}
                                for key, value in sorted(values.items())
                            ],
                        }
                    )

    session_storage_dir = profile_root / "Session Storage"
    if session_storage_dir.exists():
        session_by_origin = collect_session_storage(session_storage_dir, domain_filter)

    indexeddb_by_origin, indexeddb_warnings = collect_indexeddb(profile_root, domain_filter)
    warnings.extend(indexeddb_warnings)
    return merge_origin_state(local_storage_origins, indexeddb_by_origin), session_by_origin, warnings


def choose_primary_url(domain_filter: str | None, cookies: list[dict], origins: list[dict], session_by_origin: dict[str, dict[str, str]]) -> str:
    primary_domain = domain_filter.lstrip(".") if domain_filter else ""
    if not primary_domain and cookies:
        primary_domain = cookies[0]["domain"].lstrip(".")
    if primary_domain:
        return f"https://{primary_domain}"

    candidates = [origin["origin"] for origin in origins] + list(session_by_origin)
    return sorted(candidates)[0] if candidates else "about:blank"


def read_browser_session(session_name: str, browser_type: str, domain_filter: str | None):
    if browser_type not in BROWSERS:
        raise ImportRefused("UNSUPPORTED_BROWSER", f"Use a supported browser: {', '.join(sorted(BROWSERS))}")

    config = BROWSERS[browser_type]
    profile_root = resolve_profile_root(config)
    cookie_file = resolve_cookie_file(profile_root)
    if not cookie_file:
        tried = ", ".join(str(candidate / 'Cookies') for candidate in config.get("profile_candidates", []))
        raise ImportRefused("BROWSER_PROFILE_UNAVAILABLE", f"{browser_type} cookie file not found. Tried: {tried}")

    try:
        cookies = extract_cookies(config, cookie_file, domain_filter)
    except Exception as exc:
        raise ImportRefused(
            "BROWSER_COOKIES_UNREADABLE",
            f"Unable to read {browser_type} cookies ({type(exc).__name__}). Check the profile, cookie reader and keychain access.",
        ) from exc
    if not cookies:
        filter_msg = f" matching '{domain_filter}'" if domain_filter else ""
        raise ImportRefused("BROWSER_COOKIES_EMPTY", f"No cookies found in {browser_type}{filter_msg}")

    try:
        origins, session_by_origin, warnings = import_storage(profile_root, domain_filter)
    except ImportRefused:
        raise
    except Exception as exc:
        raise ImportRefused(
            "BROWSER_STORAGE_UNREADABLE",
            f"Unable to read {browser_type} browser storage ({type(exc).__name__}).",
        ) from exc
    url = choose_primary_url(domain_filter, cookies, origins, session_by_origin)

    storage_state = {"cookies": cookies, "origins": origins}
    files = {
        "storage.json": storage_state,
        "state.json": {
            "url": url,
            "viewport": {"width": 1920, "height": 1080},
            "scroll": {"x": 0, "y": 0},
        },
        "meta.json": {
            "name": session_name,
            "description": f"Imported from {browser_type}" + (f" ({domain_filter})" if domain_filter else ""),
            "created": now_iso(),
            "lastUsed": now_iso(),
            "url": url,
            "cookieCount": len(cookies),
            "originsCount": len(origins),
            "sessionOriginsCount": len(session_by_origin),
            "indexedDbCount": sum(len(origin.get("indexedDB", [])) for origin in origins),
            "authentication": "unverified",
        },
        "session-storage.json": {"origins": session_by_origin} if session_by_origin else {},
    }

    return files, {
        "imported": True,
        "session": session_name,
        "browser": browser_type,
        "domain": domain_filter or "(all)",
        "cookieCount": len(cookies),
        "originsCount": len(origins),
        "sessionOriginsCount": len(session_by_origin),
        "indexedDbCount": sum(len(origin.get("indexedDB", [])) for origin in origins),
        "storageImported": bool(origins or session_by_origin),
        "profileRoot": str(profile_root),
        "url": url,
        "warnings": warnings,
        "authentication": "unverified",
    }


def import_browser_session(session_name: str, browser_type: str, domain_filter: str | None):
    session_dir = session_path(session_name)
    session_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    status_file = session_dir / "import-status.json"
    # One importer may publish this name at a time. A failed/interrupted attempt
    # leaves the old data intact but unusable for load/export until refreshed.
    with (session_dir / ".import.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ImportRefused("BROWSER_IMPORT_BUSY", "Another import owns this session; retry after it completes.") from exc
        status = {"attempt": uuid.uuid4().hex, "browser": browser_type, "at": now_iso(), "status": "importing"}
        write_json_atomic(status_file, status)
        try:
            # Some forensic readers print raw records on malformed input.
            # Keep the CLI machine-readable and never emit stored values.
            diagnostics = io.StringIO()
            with contextlib.redirect_stdout(diagnostics), contextlib.redirect_stderr(diagnostics):
                files, result = read_browser_session(session_name, browser_type, domain_filter)
            if diagnostics.getvalue():
                raise ImportRefused("BROWSER_READER_DIAGNOSTIC", "Browser reader reported malformed records; import refused without logging stored values.")
            digests = {name: write_json_atomic(session_dir / name, content) for name, content in files.items()}
            # lastUsed in meta.json is intentionally mutable.
            digests.pop("meta.json")
            write_json_atomic(status_file, {**status, "status": "ready", "files": digests})
            return result
        except Exception as exc:
            refusal = exc if isinstance(exc, ImportRefused) else ImportRefused(
                "BROWSER_IMPORT_FAILED", f"Browser import failed ({type(exc).__name__}); no fresh session was published."
            )
            write_json_atomic(status_file, {**status, "status": "failed", "code": refusal.code})
            if refusal is exc:
                raise
            raise refusal from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import browser cookies and storage into agent-browse")
    parser.add_argument("--session", required=True)
    parser.add_argument("--browser", default="comet")
    parser.add_argument("--domain", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = import_browser_session(
            session_name=args.session,
            browser_type=args.browser,
            domain_filter=args.domain or None,
        )
    except Exception as exc:
        refusal = exc if isinstance(exc, ImportRefused) else ImportRefused(
            "BROWSER_IMPORT_FAILED", f"Browser import failed ({type(exc).__name__})."
        )
        print(json.dumps({"imported": False, "session": args.session, "code": refusal.code, "error": str(refusal)}), file=sys.stderr)
        return 2

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
