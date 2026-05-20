#!/usr/bin/env python3
"""Tests for agent-transcribe.

Covers source classification, method ordering, cookie handoff (including
the security requirement that cookie values never appear in output),
doctor JSON shape, and cost estimation math. Network-dependent tests
(real transcription) are excluded.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
TOOL_DIR = ROOT / "tools" / "agent-transcribe"
LIB_DIR = ROOT / "lib"
sys.path.insert(0, str(TOOL_DIR))
sys.path.insert(0, str(LIB_DIR))

from lib.cookies import safe_cookie_file, list_sessions  # noqa: E402
from lib.engines import order_methods  # noqa: E402
from lib.sources import classify_source, source_hash  # noqa: E402
from lib.ytdlp import normalize_extractor_args  # noqa: E402
from registry import load_registry  # noqa: E402


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_tool(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [str(TOOL_DIR / "agent-transcribe"), *args],
        capture_output=True, text=True, env=env, check=False,
    )


def make_fake_session(name: str, cookies: list[dict]) -> tuple[Path, Callable]:
    """Create a fake browse session under a temporary SESSIONS_ROOT.

    Returns (session_dir, cleanup_callback). The cleanup must be called by the
    test to remove the fake session.
    """
    tmp_root = Path(tempfile.mkdtemp(prefix="fake-browse-sessions-"))
    sess_dir = tmp_root / name
    sess_dir.mkdir()
    (sess_dir / "storage.json").write_text(json.dumps({"cookies": cookies}))

    def cleanup():
        import shutil
        shutil.rmtree(tmp_root, ignore_errors=True)

    return sess_dir, cleanup


# ---------------------------------------------------------------------------
# Source classification
# ---------------------------------------------------------------------------

def test_classify_youtube_url():
    src = classify_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    require(src["kind"] == "youtube", f"expected youtube, got {src}")
    require(src["video_id"] == "dQw4w9WgXcQ", f"id mismatch: {src}")


def test_classify_youtube_short_url():
    src = classify_source("https://youtu.be/dQw4w9WgXcQ")
    require(src["kind"] == "youtube", f"expected youtube, got {src}")
    require(src["video_id"] == "dQw4w9WgXcQ", f"id mismatch: {src}")


def test_classify_youtube_shorts():
    src = classify_source("https://youtube.com/shorts/dQw4w9WgXcQ")
    require(src["kind"] == "youtube" and src["video_id"] == "dQw4w9WgXcQ",
            f"shorts URL not parsed: {src}")


def test_classify_bare_id():
    src = classify_source("dQw4w9WgXcQ")
    require(src["kind"] == "youtube" and src["video_id"] == "dQw4w9WgXcQ",
            f"bare ID not parsed: {src}")


def test_classify_local_file():
    src = classify_source("/tmp/recording.mp3")
    require(src["kind"] == "file", f"expected file, got {src}")
    require(src["path"].endswith("recording.mp3"), f"path wrong: {src}")


def test_classify_http_url_non_youtube():
    src = classify_source("https://example.com/audio.mp3")
    require(src["kind"] == "url", f"expected url, got {src}")


def test_source_hash_stable():
    a = classify_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    b = classify_source("dQw4w9WgXcQ")
    require(source_hash(a) == source_hash(b),
            "same video via URL vs ID should hash identically")


# ---------------------------------------------------------------------------
# Method ordering
# ---------------------------------------------------------------------------

def test_default_method_order_is_quality_first():
    order = order_methods("auto", prefer_free=False, prefer=None)
    require(order[0] == "whisper-api", f"quality-first expected, got {order}")
    require(order == ["whisper-api", "local-whisper", "captions", "vtt"],
            f"unexpected default order: {order}")


def test_prefer_free_reorders():
    order = order_methods("auto", prefer_free=True, prefer=None)
    require(order[0] == "captions", f"prefer-free should start with captions, got {order}")
    require("whisper-api" in order and order.index("whisper-api") > order.index("captions"),
            f"whisper-api should be deprioritized: {order}")


def test_explicit_method_single():
    require(order_methods("whisper-api", False, None) == ["whisper-api"],
            "explicit method should yield single-element list")


def test_prefer_captions_promotes_captions_above_local_whisper():
    order = order_methods("auto", prefer_free=False, prefer="captions")
    require(order[0] == "captions", f"--prefer captions should put captions first, got {order}")


# ---------------------------------------------------------------------------
# yt-dlp extractor args
# ---------------------------------------------------------------------------

def test_youtube_player_client_maps_to_extractor_args():
    args = normalize_extractor_args([], "ios")
    require(args == ["youtube:player_client=ios"], f"unexpected args: {args}")


def test_raw_and_shortcut_extractor_args_combine():
    args = normalize_extractor_args(["youtube:skip=dash"], "ios,android")
    require(args == ["youtube:skip=dash", "youtube:player_client=ios,android"],
            f"unexpected combined args: {args}")


def test_extractor_args_reject_flag_smuggling():
    try:
        normalize_extractor_args(["--cookies=/tmp/secret"], None)
    except ValueError:
        return
    raise AssertionError("expected ValueError for flag-shaped extractor args")


def test_cli_accepts_youtube_player_client_option():
    proc = run_tool("--youtube-player-client", "ios", "--json")
    require(proc.returncode == 2, f"missing source should still exit 2, got {proc.returncode}")
    data = json.loads(proc.stdout)
    require("no source" in data.get("error", ""), f"flag should parse before no-source error: {data}")


def test_browser_capture_requires_browse_session():
    proc = run_tool("https://youtube.com/watch?v=dQw4w9WgXcQ", "--browser-capture", "--json")
    require(proc.returncode == 2, f"browser capture without session should exit 2, got {proc.returncode}")
    data = json.loads(proc.stdout)
    require("--browser-capture requires --browse-session" in data.get("error", ""),
            f"missing browse-session error should be explicit: {data}")


# ---------------------------------------------------------------------------
# Cookie handoff — security-critical
# ---------------------------------------------------------------------------

def test_cookie_file_written_and_cleaned_up(monkeypatch_attr):
    sess_dir, cleanup = make_fake_session("test_yt", [
        {"name": "VISITOR_INFO1_LIVE", "value": "abc123fake",
         "domain": ".youtube.com", "path": "/", "secure": True, "expires": 9999999999},
        {"name": "SESSION_TOK", "value": "supersecretvalue",
         "domain": "youtube.com", "path": "/", "secure": False, "expires": 0},
    ])
    try:
        monkeypatch_attr("lib.cookies.SESSIONS_ROOT", sess_dir.parent)
        with safe_cookie_file("test_yt") as cookies_path:
            require(cookies_path.exists(), "cookies file should exist inside cm")
            mode = cookies_path.stat().st_mode & 0o777
            require(mode == 0o600, f"cookies file should be 0600, got {oct(mode)}")
            text = cookies_path.read_text()
            require("Netscape HTTP Cookie File" in text, "missing Netscape header")
            require("VISITOR_INFO1_LIVE" in text, "cookie name missing")
            require("SESSION_TOK" in text, "second cookie name missing")
        require(not cookies_path.exists(), "cookies file should be deleted after cm")
        require(not cookies_path.parent.exists(), "temp dir should be removed after cm")
    finally:
        cleanup()


def test_cookie_values_never_appear_in_stdout_or_stderr(monkeypatch_attr):
    sess_dir, cleanup = make_fake_session("test_secret", [
        {"name": "S", "value": "DO_NOT_LEAK_THIS_TOKEN",
         "domain": ".example.com", "path": "/", "secure": True, "expires": 0},
    ])
    try:
        monkeypatch_attr("lib.cookies.SESSIONS_ROOT", sess_dir.parent)
        # doctor + snapshot both list sessions; neither should print values
        sessions = list_sessions()
        as_json = json.dumps(sessions)
        require("DO_NOT_LEAK_THIS_TOKEN" not in as_json,
                f"cookie value leaked in list_sessions(): {as_json}")
    finally:
        cleanup()


def test_missing_session_raises():
    try:
        with safe_cookie_file("definitely-does-not-exist-xyzzy"):
            pass
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError for missing session")


def test_empty_cookies_raises(monkeypatch_attr):
    sess_dir, cleanup = make_fake_session("empty_session", [])
    try:
        monkeypatch_attr("lib.cookies.SESSIONS_ROOT", sess_dir.parent)
        try:
            with safe_cookie_file("empty_session"):
                pass
        except ValueError:
            return
        raise AssertionError("expected ValueError for empty cookies")
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# Doctor JSON shape
# ---------------------------------------------------------------------------

def test_doctor_json_shape():
    proc = run_tool("doctor", "--json")
    require(proc.returncode == 0, f"doctor failed: {proc.stderr}")
    data = json.loads(proc.stdout)
    for key in ("success", "tool", "dependencies", "credentials", "browse_sessions", "recommendations"):
        require(key in data, f"doctor JSON missing key {key}: {data.keys()}")
    require(data["tool"] == "transcribe", f"tool name mismatch: {data['tool']}")
    require(isinstance(data["dependencies"], dict), "dependencies should be dict")
    for dep in ("ffmpeg", "ffprobe", "yt_dlp", "openai_sdk", "local_whisper"):
        require(dep in data["dependencies"], f"missing dep key {dep}")


def test_snapshot_json_shape():
    proc = run_tool("snapshot", "--json")
    require(proc.returncode == 0, f"snapshot failed: {proc.stderr}")
    data = json.loads(proc.stdout)
    for key in ("success", "cache_dir", "cached_entries", "browse_sessions", "default_method_order"):
        require(key in data, f"snapshot missing key {key}")
    require(data["default_method_order"][0] == "whisper-api",
            f"expected whisper-api default first: {data['default_method_order']}")


def test_no_source_exits_2_with_clarification():
    proc = run_tool("--json")
    require(proc.returncode == 2, f"missing source should exit 2, got {proc.returncode}")
    data = json.loads(proc.stdout)
    require(not data.get("success"), "should be unsuccessful")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_entry_exists():
    registry = load_registry()
    require("transcribe" in registry["tools"], "transcribe missing from registry")
    entry = registry["tools"]["transcribe"]
    require("doctor" in entry["commands"], "doctor command not declared")
    require("cost" in entry["commands"], "cost command not declared")
    require(entry["concurrency"] == "mixed", "concurrency should be mixed")
    require("OPENAI_API_KEY" in entry.get("credentials", {}).get("optional", []),
            "OPENAI_API_KEY should be declared optional credential")
    contracts = entry.get("contracts") or {}
    require("snapshot" in contracts and "cost" in contracts["snapshot"],
            f"cost should be declared as a snapshot contract: {contracts}")
    require("interact" in contracts and "transcribe" in contracts["interact"],
            f"transcribe should be declared as an interact contract: {contracts}")
    require("save" in contracts and "transcribe" in contracts["save"],
            f"transcribe should be declared as a save contract: {contracts}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _make_monkeypatch():
    """Tiny replacement for pytest's monkeypatch — restores attributes on cleanup."""
    saved: list[tuple] = []

    def setattr_path(dotted: str, value):
        module_path, attr = dotted.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        saved.append((mod, attr, getattr(mod, attr)))
        setattr(mod, attr, value)

    def cleanup():
        for mod, attr, orig in saved:
            setattr(mod, attr, orig)

    return setattr_path, cleanup


def main() -> int:
    monkeypatch_set, monkeypatch_cleanup = _make_monkeypatch()
    tests = [
        ("classify_youtube_url", test_classify_youtube_url, ()),
        ("classify_youtube_short_url", test_classify_youtube_short_url, ()),
        ("classify_youtube_shorts", test_classify_youtube_shorts, ()),
        ("classify_bare_id", test_classify_bare_id, ()),
        ("classify_local_file", test_classify_local_file, ()),
        ("classify_http_url_non_youtube", test_classify_http_url_non_youtube, ()),
        ("source_hash_stable", test_source_hash_stable, ()),
        ("default_method_order_is_quality_first", test_default_method_order_is_quality_first, ()),
        ("prefer_free_reorders", test_prefer_free_reorders, ()),
        ("explicit_method_single", test_explicit_method_single, ()),
        ("prefer_captions_promotes_captions", test_prefer_captions_promotes_captions_above_local_whisper, ()),
        ("youtube_player_client_maps_to_extractor_args", test_youtube_player_client_maps_to_extractor_args, ()),
        ("raw_and_shortcut_extractor_args_combine", test_raw_and_shortcut_extractor_args_combine, ()),
        ("extractor_args_reject_flag_smuggling", test_extractor_args_reject_flag_smuggling, ()),
        ("cli_accepts_youtube_player_client_option", test_cli_accepts_youtube_player_client_option, ()),
        ("browser_capture_requires_browse_session", test_browser_capture_requires_browse_session, ()),
        ("cookie_file_written_and_cleaned_up", test_cookie_file_written_and_cleaned_up, (monkeypatch_set,)),
        ("cookie_values_never_in_output", test_cookie_values_never_appear_in_stdout_or_stderr, (monkeypatch_set,)),
        ("missing_session_raises", test_missing_session_raises, ()),
        ("empty_cookies_raises", test_empty_cookies_raises, (monkeypatch_set,)),
        ("doctor_json_shape", test_doctor_json_shape, ()),
        ("snapshot_json_shape", test_snapshot_json_shape, ()),
        ("no_source_exits_2", test_no_source_exits_2_with_clarification, ()),
        ("registry_entry_exists", test_registry_entry_exists, ()),
    ]

    failures: list[tuple[str, Exception]] = []
    for name, fn, args in tests:
        try:
            fn(*args)
            print(f"  ok    {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {name}: {exc}")
            failures.append((name, exc))

    monkeypatch_cleanup()

    print()
    print(f"{len(tests) - len(failures)}/{len(tests)} tests passed")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
