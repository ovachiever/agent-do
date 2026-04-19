#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


HOME = Path.home()


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
        cookie_file = candidate / "Cookies"
        if cookie_file.exists() and cookie_file.stat().st_size > 0:
            return candidate
    for candidate in profiles:
        if candidate.exists():
            return candidate
    return None


def resolve_cookie_file(profile_root: Path | None) -> Path | None:
    if not profile_root:
        return None
    cookie_file = profile_root / "Cookies"
    if cookie_file.exists():
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
    extractor = getattr(browser_cookie3, extractor_name, None)
    if extractor is None:
        raise RuntimeError(f"browser_cookie3 does not support extractor '{extractor_name}'")

    original_fn = browser_cookie3._get_osx_keychain_password
    try:
        browser_cookie3, original_fn = _patch_cookie3_keychain(config, extractor_name)
        cookie_jar = extractor(domain_name=domain_filter or None, cookie_file=str(cookie_file))
        return list(cookie_jar)
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


def import_storage(profile_root: Path | None, domain_filter: str | None):
    warnings: list[str] = []
    playwright_origins: list[dict] = []
    session_by_origin: dict[str, dict[str, str]] = {}

    if not profile_root:
        return playwright_origins, session_by_origin, warnings

    try:
        from ccl_chromium_reader import ccl_chromium_localstorage, ccl_chromium_sessionstorage
    except ModuleNotFoundError:
        warnings.append(
            "ccl_chromium_reader is not installed; imported browser session will include cookies only."
        )
        return playwright_origins, session_by_origin, warnings

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
                    playwright_origins.append(
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
        with ccl_chromium_sessionstorage.SessionStoreDb(session_storage_dir) as db:
            for host in db.iter_hosts():
                origin = normalize_origin(str(host))
                if not origin or not origin_matches_domain(origin, domain_filter):
                    continue
                values = choose_live_values(
                    db.iter_records_for_host(host),
                    key_attr="key",
                    value_attr="value",
                    seq_attr="leveldb_sequence_number",
                    live_predicate=lambda rec: not getattr(rec, "is_deleted", False),
                )
                if values:
                    session_by_origin[origin] = values

    return playwright_origins, session_by_origin, warnings


def choose_primary_url(domain_filter: str | None, cookies: list[dict], origins: list[dict], session_by_origin: dict[str, dict[str, str]]) -> str:
    primary_domain = domain_filter.lstrip(".") if domain_filter else ""
    if not primary_domain and cookies:
        primary_domain = cookies[0]["domain"].lstrip(".")
    if primary_domain:
        return f"https://{primary_domain}"

    candidates = [origin["origin"] for origin in origins] + list(session_by_origin)
    return sorted(candidates)[0] if candidates else "about:blank"


def import_browser_session(session_name: str, browser_type: str, domain_filter: str | None):
    if browser_type not in BROWSERS:
        raise RuntimeError(f"Unknown browser '{browser_type}'. Use: {', '.join(sorted(BROWSERS))}")

    config = BROWSERS[browser_type]
    profile_root = resolve_profile_root(config)
    cookie_file = resolve_cookie_file(profile_root)
    if not cookie_file:
        tried = ", ".join(str(candidate / 'Cookies') for candidate in config.get("profile_candidates", []))
        raise RuntimeError(f"{browser_type} cookie file not found. Tried: {tried}")

    raw_cookies = extract_cookies(config, cookie_file, domain_filter)
    if not raw_cookies:
        filter_msg = f" matching '{domain_filter}'" if domain_filter else ""
        raise RuntimeError(f"No cookies found in {browser_type}{filter_msg}")

    cookies: list[dict] = []
    for c in raw_cookies:
        cookie = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
        }
        if c.secure:
            cookie["secure"] = True
        if c.expires and c.expires > 0:
            cookie["expires"] = c.expires
        cookies.append(cookie)

    origins, session_by_origin, warnings = import_storage(profile_root, domain_filter)
    url = choose_primary_url(domain_filter, cookies, origins, session_by_origin)

    session_dir = HOME / ".agent-browse" / "sessions" / session_name
    session_dir.mkdir(parents=True, exist_ok=True)

    storage_state = {"cookies": cookies, "origins": origins}
    (session_dir / "storage.json").write_text(json.dumps(storage_state, indent=2))
    (session_dir / "state.json").write_text(
        json.dumps(
            {
                "url": url,
                "viewport": {"width": 1920, "height": 1080},
                "scroll": {"x": 0, "y": 0},
            },
            indent=2,
        )
    )
    (session_dir / "meta.json").write_text(
        json.dumps(
            {
                "name": session_name,
                "description": f"Imported from {browser_type}" + (f" ({domain_filter})" if domain_filter else ""),
                "created": now_iso(),
                "lastUsed": now_iso(),
                "url": url,
                "cookieCount": len(cookies),
                "originsCount": len(origins),
                "sessionOriginsCount": len(session_by_origin),
            },
            indent=2,
        )
    )
    session_storage_payload = {"origins": session_by_origin} if session_by_origin else {}
    (session_dir / "session-storage.json").write_text(json.dumps(session_storage_payload, indent=2))

    return {
        "imported": True,
        "session": session_name,
        "browser": browser_type,
        "domain": domain_filter or "(all)",
        "cookieCount": len(cookies),
        "originsCount": len(origins),
        "sessionOriginsCount": len(session_by_origin),
        "storageImported": bool(origins or session_by_origin),
        "profileRoot": str(profile_root),
        "url": url,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import browser cookies and storage into agent-browse")
    parser.add_argument("--session", required=True)
    parser.add_argument("--browser", default="comet", choices=sorted(BROWSERS))
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
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
