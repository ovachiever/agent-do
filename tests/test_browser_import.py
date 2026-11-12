#!/usr/bin/env python3
"""Unit coverage for browser-profile import helpers."""

from __future__ import annotations

import importlib.util
import base64
import builtins
import contextlib
import fcntl
import io
import json
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "agent-browse" / "import_browser.py"
SPEC = importlib.util.spec_from_file_location("import_browser", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_normalize_origin() -> None:
    require(MODULE.normalize_origin("https://platform.openai.com/") == "https://platform.openai.com", "expected trailing slash to be removed")
    require(MODULE.normalize_origin("https://vercel.com:8443/login") == "https://vercel.com:8443", "expected port to be preserved")
    require(MODULE.normalize_origin("chrome://settings") is None, "expected non-http origin to be skipped")


def test_domain_matching() -> None:
    require(MODULE.origin_matches_domain("https://platform.openai.com", ".openai.com"), "expected subdomain match")
    require(MODULE.origin_matches_domain("https://openai.com", ".openai.com"), "expected apex match")
    require(not MODULE.origin_matches_domain("https://vercel.com", ".openai.com"), "expected non-match")


def test_parse_indexeddb_origin_dirname() -> None:
    require(
        MODULE.parse_indexeddb_origin_dirname("https_vercel.com_0.indexeddb.leveldb") == "https://vercel.com",
        "expected default port suffix to be removed",
    )
    require(
        MODULE.parse_indexeddb_origin_dirname("https_app.example.com_8443.indexeddb.leveldb") == "https://app.example.com:8443",
        "expected explicit port suffix to be preserved",
    )
    require(MODULE.parse_indexeddb_origin_dirname("nonsense") is None, "expected invalid IndexedDB dirname to be ignored")


def test_to_playwright_json_handles_plain_values() -> None:
    value = MODULE.to_playwright_json(
        {
            "token": "abc",
            "count": 2,
            "flags": [True, False],
            "nested": {"org": "o_123"},
            "tupled": ("a", "b"),
        }
    )
    require(
        value == {
            "token": "abc",
            "count": 2,
            "flags": [True, False],
            "nested": {"org": "o_123"},
            "tupled": ["a", "b"],
        },
        f"unexpected json conversion: {value}",
    )


def test_merge_origin_state_attaches_indexeddb() -> None:
    origins = MODULE.merge_origin_state(
        [{"origin": "https://vercel.com", "localStorage": [{"name": "x", "value": "1"}]}],
        {"https://vercel.com": [{"name": "vcf-frecency", "version": 1, "stores": []}]},
    )
    require(len(origins) == 1, f"unexpected merged origin count: {origins}")
    require(origins[0]["origin"] == "https://vercel.com", f"unexpected origin payload: {origins[0]}")
    require(origins[0]["localStorage"] == [{"name": "x", "value": "1"}], f"unexpected localStorage: {origins[0]}")
    require(
        origins[0]["indexedDB"] == [{"name": "vcf-frecency", "version": 1, "stores": []}],
        f"unexpected indexedDB payload: {origins[0]}",
    )


def test_choose_live_values_prefers_latest_non_deleted() -> None:
    records = [
        SimpleNamespace(script_key="token", value="old", leveldb_seq_number=1, is_live=True),
        SimpleNamespace(script_key="token", value="new", leveldb_seq_number=3, is_live=True),
        SimpleNamespace(script_key="theme", value="dark", leveldb_seq_number=2, is_live=False),
        SimpleNamespace(script_key="theme", value="light", leveldb_seq_number=1, is_live=True),
    ]
    values = MODULE.choose_live_values(
        records,
        key_attr="script_key",
        value_attr="value",
        seq_attr="leveldb_seq_number",
        live_predicate=lambda rec: rec.is_live,
    )
    require(values == {"token": "new"}, f"unexpected live values: {values}")


def test_choose_live_values_for_session_records() -> None:
    records = [
        SimpleNamespace(key="sid", value="abc", leveldb_sequence_number=5, is_deleted=False),
        SimpleNamespace(key="sid", value="def", leveldb_sequence_number=6, is_deleted=True),
        SimpleNamespace(key="returnTo", value="/billing", leveldb_sequence_number=7, is_deleted=False),
    ]
    values = MODULE.choose_live_values(
        records,
        key_attr="key",
        value_attr="value",
        seq_attr="leveldb_sequence_number",
        live_predicate=lambda rec: not rec.is_deleted,
    )
    require(values == {"returnTo": "/billing"}, f"unexpected session values: {values}")


def test_choose_primary_url_prefers_domain_root_when_available() -> None:
    url = MODULE.choose_primary_url(
        ".openai.com",
        cookies=[{"domain": ".openai.com"}],
        origins=[
            {"origin": "https://openai.com", "localStorage": [{"name": "a", "value": "1"}]},
            {"origin": "https://platform.openai.com", "localStorage": [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}]},
        ],
        session_by_origin={"https://auth.openai.com": {"sid": "1"}},
    )
    require(url == "https://openai.com", f"unexpected primary URL: {url}")


def test_cookie_partitions_expiry_and_attributes_survive_import() -> None:
    import browser_cookie3
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        cookie_file = profile / "Cookies"
        with sqlite3.connect(cookie_file) as connection:
            connection.execute("CREATE TABLE cookies (host_key, path, is_secure, expires_utc, name, value, encrypted_value, is_httponly, top_frame_site_key, has_cross_site_ancestor, samesite)")
            future = (MODULE.datetime.now(MODULE.timezone.utc).timestamp() + 3600 + browser_cookie3.Arc.UNIX_TO_NT_EPOCH_OFFSET) * 1_000_000
            expired = (browser_cookie3.Arc.UNIX_TO_NT_EPOCH_OFFSET + 1) * 1_000_000
            connection.executemany("INSERT INTO cookies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                (".youtube.com", "/", 1, future, "SID", "first-party", b"", 1, "", 0, 1),
                (".youtube.com", "/", 1, future, "SID", "third-party", b"", 1, "https://example.com", 1, 0),
                (".youtube.com", "/", 1, future, "SID", "same-site-partition", b"", 1, "https://youtube.com", 0, 0),
                (".youtube.com", "/", 1, expired, "SID", "expired", b"", 1, "https://expired.example", 1, 0),
                ("www.youtube.com", "/", 1, 0, "session", "ephemeral", b"", 0, "", 0, -1),
                ("notyoutube.com", "/", 1, future, "SID", "wrong-domain", b"", 1, "", 0, 2),
            ])
        # Use the dependency's real plaintext decode and database reader without
        # asking a test runner to access the operating system's keychain.
        reader = object.__new__(browser_cookie3.Arc)
        reader.cookie_file = str(cookie_file)
        config = {**MODULE.BROWSERS["arc"], "profile_candidates": [profile]}
        with patch.object(browser_cookie3, "Arc", return_value=reader), patch.object(MODULE, "BROWSERS", {"arc": config}):
            files, result = MODULE.read_browser_session("fixture", "arc", ".youtube.com")
        cookies = files["storage.json"]["cookies"]
        require(result["cookieCount"] == 4, "partition identity must preserve all live matching cookies")
        by_value = {cookie["value"]: cookie for cookie in cookies}
        require(set(by_value) == {"first-party", "third-party", "same-site-partition", "ephemeral"}, "expired and lookalike-domain cookies must be excluded")
        require("partitionKey" not in by_value["first-party"], "first-party cookie must stay unpartitioned")
        require(by_value["first-party"]["httpOnly"] and by_value["first-party"]["sameSite"] == "Lax", "security attributes must survive")
        require(by_value["third-party"]["partitionKey"] == "https://example.com" and by_value["third-party"]["_crHasCrossSiteAncestor"], "third-party partition must survive")
        require(by_value["same-site-partition"]["_crHasCrossSiteAncestor"] is False, "same-site partition must stay distinct")
        require("expires" not in by_value["ephemeral"] and "sameSite" not in by_value["ephemeral"], "unspecified session-cookie attributes must remain unspecified")


def test_legacy_cookie_schema_still_works() -> None:
    import browser_cookie3
    with tempfile.TemporaryDirectory() as directory:
        cookie_file = Path(directory) / "Cookies"
        with sqlite3.connect(cookie_file) as connection:
            connection.execute("CREATE TABLE cookies (host_key, path, secure, expires_utc, name, value, encrypted_value, is_httponly)")
            connection.execute("INSERT INTO cookies VALUES ('.example.com', '/', 0, 0, 'sample', 'fixture', X'', 0)")
        reader = object.__new__(browser_cookie3.Arc)
        reader.cookie_file = str(cookie_file)
        with patch.object(browser_cookie3, "Arc", return_value=reader):
            cookies = MODULE.extract_cookies(MODULE.BROWSERS["arc"], cookie_file, None)
        require(cookies == [{"name": "sample", "value": "fixture", "domain": ".example.com", "path": "/", "secure": False, "httpOnly": False}], "legacy nonpartitioned cookies must remain supported")


def varint(value: int) -> bytes:
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result) + bytes([value])


def write_leveldb_log(db: Path, records: list[tuple[bytes, bytes | None]]) -> None:
    db.mkdir(parents=True, exist_ok=True)
    batch = struct.pack("<QI", 1, len(records))
    for rec_key, rec_value in records:
        batch += bytes([0 if rec_value is None else 1]) + varint(len(rec_key)) + rec_key
        if rec_value is not None:
            batch += varint(len(rec_value)) + rec_value
    # Masked CRC32C of the FULL record type followed by the batch.
    crc = 0xffffffff
    for byte in b"\x01" + batch:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82f63b78 if crc & 1 else 0)
    crc ^= 0xffffffff
    masked = (((crc >> 15) | (crc << 17)) + 0xa282ead8) & 0xffffffff
    (db / "000001.log").write_bytes(struct.pack("<IHB", masked, len(batch), 1) + batch)


def chromium_blob_profile(profile: Path, *, missing_blob=False, compressed=False, external=True, history=False, deleted=False, typed_array=False) -> Path:
    """Synthetic LevelDB WAL plus a real external Blink/V8 string value.

    No personal browser data, no browser or keychain, and no mocked blob reader.
    Encoding: Chromium IndexedDB leveldb_coding_scheme and LevelDB log_format.
    """
    db = profile / "IndexedDB/https_www.youtube.com_0.indexeddb.leveldb"
    db.mkdir(parents=True)
    (profile / "Cookies").write_bytes(b"fixture")
    def string(value):
        return varint(len(value)) + value.encode("utf-16-be")
    key = b"\x01" + string("key")
    value = b"blob fixture value"
    blob = b'\xff\x14\xff\x0f"' + varint(len(value)) + value
    if typed_array:
        # V8 ArrayBuffer followed by a Uint8Array view (offset 1, length 2).
        blob = b"\xff\x14\xff\x0fB\x04\x00\x01\xfe\xffVB\x01\x02\x00"
    if compressed:
        # A valid single Snappy literal, inside Chromium's compression envelope.
        blob = b"\xff\x11\x02" + varint(len(blob)) + bytes([(len(blob) - 1) << 2]) + blob
    records = [
        (b"\x00\x00\x00\x00\xc9" + string("https://www.youtube.com") + string("fixture"), b"\x01"),
        (b"\x00\x01\x00\x00\x03", b"\x01"),
        (b"\x00\x01\x00\x00\x04", b"\x01"),
        (b"\x00\x01\x00\x00\x32\x01\x00", "store".encode("utf-16-be")),
        (b"\x00\x01\x00\x00\x32\x01\x01", b"\x00"),
        (b"\x00\x01\x00\x00\x32\x01\x02", b"\x00"),
        (b"\x00\x01\x01\x01" + key, b"\x01" + (b"\xff\x11\x01" + varint(len(blob)) + b"\x00" if external else blob)),
        (b"\x00\x01\x01\x03" + key, b"\x00\x01\x00" + varint(len(blob))),
    ]
    if history:
        records.insert(0, (b"\x00\x01\x01\x01" + key, b"\x01obsolete-invalid-envelope"))
    if deleted:
        records.append((b"\x00\x01\x01\x01" + key, None))
    write_leveldb_log(db, records)
    if not missing_blob:
        blob_file = db.with_suffix(".blob") / "1/00/1"
        blob_file.parent.mkdir(parents=True)
        blob_file.write_bytes(blob)
    return db


def test_real_blob_reader_regression() -> None:
    from ccl_chromium_reader.ccl_chromium_indexeddb import WrappedIndexDB
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        db = chromium_blob_profile(profile)
        reader = WrappedIndexDB(db)
        try:
            try:
                list(reader[1][1].iterate_records(live_only=True))
                raise AssertionError("fixture must reproduce the original missing-blob-dir failure")
            except ValueError as exc:
                require(str(exc) == "Can't resolve blob if blob dir is not set", str(exc))
        finally:
            reader.close()
        origins, warnings = MODULE.collect_indexeddb(profile, ".youtube.com")
        require(not warnings, f"unexpected warnings: {warnings}")
        records = origins["https://www.youtube.com"][0]["stores"][0]["records"]
        require(records == [{"value": "blob fixture value", "key": "key"}], "external value must round-trip")


def test_missing_blob_refuses_instead_of_skipping_store() -> None:
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        chromium_blob_profile(profile, missing_blob=True)
        try:
            MODULE.collect_indexeddb(profile, ".youtube.com")
            raise AssertionError("unreadable blobs must refuse")
        except MODULE.ImportRefused as exc:
            require(exc.code == "BROWSER_STORAGE_UNREADABLE", str(exc))


def test_missing_storage_dependencies_refuse_instead_of_dropping_state() -> None:
    original_import = builtins.__import__
    for missing, operation in (("ccl_chromium_reader", MODULE.import_storage), ("ccl_simplesnappy", MODULE.collect_indexeddb)):
        def unavailable(name, *args, **kwargs):
            if name == missing:
                raise ModuleNotFoundError(missing)
            return original_import(name, *args, **kwargs)
        with patch.object(builtins, "__import__", side_effect=unavailable):
            try:
                operation(Path("synthetic-profile"), None)
                raise AssertionError("a missing storage reader must not yield a successful partial import")
            except MODULE.ImportRefused as exc:
                require(exc.code == "BROWSER_STORAGE_READER_UNAVAILABLE", str(exc))


def test_snappy_envelopes_inline_and_inside_blobs() -> None:
    for external in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            chromium_blob_profile(profile, compressed=True, external=external)
            origins, warnings = MODULE.collect_indexeddb(profile, ".youtube.com")
            require(not warnings, "compressed records must not be skipped")
            records = origins["https://www.youtube.com"][0]["stores"][0]["records"]
            require(records == [{"value": "blob fixture value", "key": "key"}], "compressed value must round-trip")


def test_indexeddb_imports_current_values_without_resurrecting_history() -> None:
    for deleted in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            chromium_blob_profile(profile, history=True, deleted=deleted)
            origins, warnings = MODULE.collect_indexeddb(profile, ".youtube.com")
            if deleted:
                require(origins == {}, "a deleted record must not reappear from history")
            else:
                records = origins["https://www.youtube.com"][0]["stores"][0]["records"]
                require(records == [{"value": "blob fixture value", "key": "key"}], "only the latest value is imported")


def test_typed_array_blob_preserves_type_and_bytes_without_integer_expansion() -> None:
    for compressed in (False, True):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            chromium_blob_profile(profile, typed_array=True, compressed=compressed)
            origins, warnings = MODULE.collect_indexeddb(profile, ".youtube.com")
            records = origins["https://www.youtube.com"][0]["stores"][0]["records"]
            require(not warnings, "binary records must be restored, not skipped")
            require(records == [{"valueEncoded": {"ta": {"k": "ui8", "b": "Af4="}}, "key": "key"}], "view kind, offset and bytes must survive")


def test_nested_typed_arrays_use_playwright_storage_encoding() -> None:
    typed = MODULE.TypedArrayValue("ui16", b"\x01\x00\xff\x00")
    payload = {"bytes": typed, "plain": ["text", 3, False, None]}
    encoded = MODULE.to_playwright_encoded(payload)
    require(encoded == {"o": [
        {"k": "bytes", "v": {"ta": {"k": "ui16", "b": "AQD/AA=="}}},
        {"k": "plain", "v": {"a": ["text", 3, False, {"v": "null"}], "id": 2}},
    ], "id": 1}, "native storageScript encoding must preserve containers and primitives")
    large = MODULE.TypedArrayValue("ui8", b"\x00" * (1024 * 1024))
    serialized = json.dumps(MODULE.to_playwright_encoded(large))
    require(len(serialized) < 1400000, "one MiB must stay near base64 size, not expand to JSON integers")
    require(base64.b64decode(json.loads(serialized)["ta"]["b"]) == large.data, "binary round trip must be lossless")


def test_corrupt_compressed_blob_refuses() -> None:
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        db = chromium_blob_profile(profile, compressed=True)
        (db.with_suffix(".blob") / "1/00/1").write_bytes(b"\xff\x11\x02\x7f\x00")
        try:
            MODULE.collect_indexeddb(profile, ".youtube.com")
            raise AssertionError("corrupt compressed blob must not be skipped")
        except MODULE.ImportRefused as exc:
            require(exc.code == "BROWSER_STORAGE_UNREADABLE", str(exc))


def test_session_storage_uses_current_namespace_and_value_snapshot() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory)
        write_leveldb_log(db, [
            (b"namespace-old-https://old.example.com/", b"7"),
            (b"map-7-deleted", "obsolete".encode("utf-16-le")),
            (b"namespace-old-https://old.example.com/", None),
            (b"namespace-current-https://www.youtube.com/", b"7"),
            (b"map-7-deleted", None),
            (b"map-7-current", "old".encode("utf-16-le")),
            (b"map-7-current", "fresh".encode("utf-16-le")),
        ])
        actual = MODULE.collect_session_storage(db, ".youtube.com")
        require(actual == {"https://www.youtube.com": {"current": "fresh"}}, "history and tombstones must not leak into current session")


def test_live_session_map_collision_refuses() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory)
        write_leveldb_log(db, [
            (b"namespace-one-https://example.com/", b"7"),
            (b"namespace-two-https://www.youtube.com/", b"7"),
        ])
        try:
            MODULE.collect_session_storage(db, ".youtube.com")
            raise AssertionError("a real live collision must refuse")
        except MODULE.ImportRefused as exc:
            require(exc.code == "BROWSER_STORAGE_UNREADABLE", str(exc))


def test_partitioned_session_storage_cannot_be_flattened() -> None:
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory)
        write_leveldb_log(db, [(b"namespace-one-https://www.youtube.com/^0https://example.com", b"7")])
        require(MODULE.collect_session_storage(db, ".unrelated.test") == {}, "domain filter must exclude unrelated storage")
        try:
            MODULE.collect_session_storage(db, ".youtube.com")
            raise AssertionError("partition isolation must be preserved")
        except MODULE.ImportRefused as exc:
            require(exc.code == "BROWSER_STORAGE_UNSUPPORTED", str(exc))


def test_dependency_diagnostics_do_not_leak_or_corrupt_json() -> None:
    def noisy_reader(*_):
        print("secret-browser-record")
        return {}, {}
    with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, "HOME", Path(directory)), patch.object(MODULE, "read_browser_session", noisy_reader):
        with patch.object(sys, "argv", ["import_browser.py", "--session", "fixture"]):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                result = MODULE.main()
        require(result == 2 and out.getvalue() == "", "diagnostic-only partial import must refuse")
        require(json.loads(err.getvalue())["code"] == "BROWSER_READER_DIAGNOSTIC", err.getvalue())
        require("secret-browser-record" not in err.getvalue(), "reader diagnostics must stay private")


def test_concurrent_import_cannot_publish_over_an_active_attempt() -> None:
    with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, "HOME", Path(directory)):
        saved = MODULE.session_path("fixture")
        saved.mkdir(parents=True)
        MODULE.write_json_atomic(saved / "import-status.json", {"status": "importing", "attempt": "owner"})
        with (saved / ".import.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(MODULE, "read_browser_session") as reader:
                try:
                    MODULE.import_browser_session("fixture", "arc", None)
                    raise AssertionError("competing import must refuse")
                except MODULE.ImportRefused as exc:
                    require(exc.code == "BROWSER_IMPORT_BUSY", str(exc))
                reader.assert_not_called()
        require(json.loads((saved / "import-status.json").read_text())["attempt"] == "owner", "busy refusal must preserve owner")


def test_import_attempt_invalidates_old_session_and_recovers() -> None:
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        profile = home / "profile"
        chromium_blob_profile(profile)
        config = {"arc": {"profile_candidates": [profile]}}
        cookie = {"name": "SID", "value": "synthetic-only", "domain": ".youtube.com", "path": "/", "secure": True}
        with patch.object(MODULE, "HOME", home), patch.object(MODULE, "BROWSERS", config), patch.object(MODULE, "extract_cookies", return_value=[cookie]):
            result = MODULE.import_browser_session("fixture", "arc", ".youtube.com")
            require(result["imported"] and result["authentication"] == "unverified", "import is not authentication")
            saved = home / ".agent-browse/sessions/fixture"
            previous = (saved / "storage.json").read_bytes()
            require((saved / "storage.json").stat().st_mode & 0o777 == 0o600, "credentials must be private")
            with patch.object(MODULE, "extract_cookies", side_effect=ValueError("secret-must-not-be-logged")):
                with patch.object(sys, "argv", ["import_browser.py", "--session", "fixture", "--browser", "arc"]):
                    out, err = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        exit_code = MODULE.main()
                require(exit_code == 2 and out.getvalue() == "", "failure must exit nonzero without success JSON")
                refusal = json.loads(err.getvalue())
                require(refusal["code"] == "BROWSER_COOKIES_UNREADABLE", err.getvalue())
                require("secret-must-not-be-logged" not in err.getvalue() and "Traceback" not in err.getvalue(), "refusal must not leak dependency details")
            require((saved / "storage.json").read_bytes() == previous, "failed read must preserve previous bytes")
            require(json.loads((saved / "import-status.json").read_text())["status"] == "failed", "failed attempt must persist")
            # Exercise the actual shell -> Node export path with no daemon.
            env = {**os.environ, "HOME": str(home)}
            target = home / "export.json"
            target.write_text("previous-export")
            command = ["bash", str(ROOT / "tools/agent-browse/agent-browse"), "session", "export", "fixture", str(target)]
            refusal = subprocess.run(command, env=env, text=True, capture_output=True, timeout=10)
            require(refusal.returncode == 2 and "BROWSER_IMPORT_STALE" in refusal.stderr, refusal.stderr)
            require(target.read_text() == "previous-export", "refused export must not touch output")
            MODULE.import_browser_session("fixture", "arc", ".youtube.com")
            exported = subprocess.run(command, env=env, text=True, capture_output=True, timeout=10)
            require(exported.returncode == 0, exported.stderr)
            require(json.loads(target.read_text())["storage"]["cookies"][0]["value"] == "synthetic-only", "fresh export must contain current state")


def test_interrupted_publication_stays_failed() -> None:
    with tempfile.TemporaryDirectory() as directory, patch.object(MODULE, "HOME", Path(directory)):
        original_write = MODULE.write_json_atomic
        def failing_write(file, value):
            if file.name == "state.json":
                raise OSError("disk full")
            return original_write(file, value)
        files = {"storage.json": {"cookies": [], "origins": []}, "state.json": {}}
        with patch.object(MODULE, "read_browser_session", return_value=(files, {})), patch.object(MODULE, "write_json_atomic", side_effect=failing_write):
            try:
                MODULE.import_browser_session("fixture", "arc", None)
                raise AssertionError("partial write must not succeed")
            except MODULE.ImportRefused as exc:
                require(exc.code == "BROWSER_IMPORT_FAILED", str(exc))
        status = json.loads((Path(directory) / ".agent-browse/sessions/fixture/import-status.json").read_text())
        require(status["status"] == "failed", "partial writes must remain unusable")


def test_network_cookie_path_and_invalid_names() -> None:
    with tempfile.TemporaryDirectory() as directory:
        profile = Path(directory)
        (profile / "Network").mkdir()
        (profile / "Network/Cookies").write_bytes(b"fixture")
        require(MODULE.resolve_profile_root({"profile_candidates": [profile]}) == profile, "Network/Cookies profile must resolve")
        require(MODULE.resolve_cookie_file(profile) == profile / "Network/Cookies", "network cookie path must resolve")
    for name in ("", ".", "..", "../escape", "a/b", "a\\b"):
        try:
            MODULE.session_path(name)
            raise AssertionError(f"invalid name accepted: {name}")
        except MODULE.ImportRefused:
            pass


def main() -> int:
    tests = [value for key, value in globals().items() if key.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"browser import tests passed: {len(tests)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
