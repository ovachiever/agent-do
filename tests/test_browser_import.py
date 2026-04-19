#!/usr/bin/env python3
"""Unit coverage for browser-profile import helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


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


def main() -> int:
    test_normalize_origin()
    test_domain_matching()
    test_parse_indexeddb_origin_dirname()
    test_to_playwright_json_handles_plain_values()
    test_merge_origin_state_attaches_indexeddb()
    test_choose_live_values_prefers_latest_non_deleted()
    test_choose_live_values_for_session_records()
    test_choose_primary_url_prefers_domain_root_when_available()
    print("browser import tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
