#!/usr/bin/env python3
"""agent-transcribe — source-to-transcript pipeline for AI agents.

See tools/agent-transcribe/agent-transcribe for the command surface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from lib.cookies import list_sessions, safe_cookie_file  # noqa: E402
from lib.engines import (  # noqa: E402
    WHISPER_API_RATE_USD_PER_MIN,
    browser_capture_audio,
    captions_transcribe,
    dependency_check,
    download_audio,
    local_whisper_transcribe,
    order_methods,
    vtt_transcribe,
    whisper_api_transcribe,
)
from lib.sources import classify_source, probe_metadata, source_hash  # noqa: E402
from lib.ytdlp import normalize_extractor_args  # noqa: E402

CACHE_ROOT = Path.home() / ".agent-do" / "transcribe"
SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def emit_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def emit_error(message: str, *, exit_code: int = 1, json_mode: bool = False,
               extra: Optional[dict] = None) -> None:
    payload = {"success": False, "error": message}
    if extra:
        payload.update(extra)
    if json_mode:
        emit_json(payload)
    else:
        print(f"error: {message}", file=sys.stderr)
    sys.exit(exit_code)


def progress(msg: str) -> None:
    print(f"[transcribe] {msg}", file=sys.stderr, flush=True)


def ytdlp_extractor_args(args: argparse.Namespace, *, json_mode: bool) -> list[str]:
    try:
        return normalize_extractor_args(
            getattr(args, "extractor_args", None),
            getattr(args, "youtube_player_client", None),
        )
    except ValueError as exc:
        emit_error(str(exc), exit_code=2, json_mode=json_mode)
    return []  # unreachable


def auth_recovery_hint(cookies_file: Optional[str]) -> str:
    if cookies_file:
        return "cookies are present; for YouTube member-tier player API blocks, retry with --browser-capture and --browse-session"
    return "pass --browse-session <name> or --cookies <path>"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def cache_path(src: dict, method: str) -> Path:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return CACHE_ROOT / f"{source_hash(src)}-{method}.json"


def cache_load(src: dict, method: str) -> Optional[dict]:
    path = cache_path(src, method)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def cache_save(src: dict, method: str, payload: dict) -> None:
    try:
        cache_path(src, method).write_text(json.dumps(payload, indent=2, default=str))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Result shape (matches the spec in the review note)
# ---------------------------------------------------------------------------

def build_result(src: dict, meta: dict, engine_result: dict,
                 audio_path: Optional[Path], audio_kept: bool,
                 text_path: Optional[Path], json_path: Optional[Path]) -> dict:
    return {
        "success": True,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "kind": src["kind"],
            "url": src.get("url"),
            "video_id": src.get("video_id"),
            "path": src.get("path"),
            "title": meta.get("title"),
            "channel": meta.get("channel"),
            "duration_seconds": meta.get("duration_seconds"),
            "requires_auth": meta.get("requires_auth"),
        },
        "method": engine_result.get("method"),
        "model": engine_result.get("model"),
        "audio": {
            "downloaded": audio_path is not None and src["kind"] != "file",
            "path": str(audio_path) if (audio_path and audio_kept) else None,
            "kept": audio_kept,
            "duration_seconds": engine_result.get("duration_seconds") or meta.get("duration_seconds"),
        },
        "transcript": {
            "text_path": str(text_path) if text_path else None,
            "json_path": str(json_path) if json_path else None,
            "word_count": len(engine_result.get("text", "").split()),
            "text": engine_result.get("text", ""),
            "segments": engine_result.get("segments", []),
        },
        "cost": {
            "estimated_usd": None,
            "actual_usd": engine_result.get("cost_usd"),
        },
    }


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    deps = dependency_check()
    creds = {"OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY"))}
    sessions = list_sessions()

    recommendations: list[str] = []
    youtube_sessions = [s for s in sessions if any("youtube.com" in d for d in s["domains"])]
    # Prefer sessions whose name signals YouTube, then those with the most cookies.
    youtube_sessions.sort(key=lambda s: (
        0 if "youtube" in s["name"].lower() else 1,
        -s["cookie_count"],
    ))
    if youtube_sessions:
        recommendations.append(
            f"use --browse-session {youtube_sessions[0]['name']} for members-only YouTube URLs"
        )
        recommendations.append(
            "if yt-dlp cannot extract authenticated YouTube audio, use --browser-capture with that browse session"
        )
    if deps.get("macos_screen_capture_current_process") is False:
        recommendations.append(
            "browser capture may require Screen & System Audio Recording permission for Chrome or Chrome for Testing"
        )
    if not creds["OPENAI_API_KEY"]:
        recommendations.append(
            "set OPENAI_API_KEY (or agent-do creds store OPENAI_API_KEY --stdin) for whisper-api"
        )
    if not deps["ffmpeg"]:
        recommendations.append("install ffmpeg (brew install ffmpeg)")
    if not deps["yt_dlp"]:
        recommendations.append("install yt-dlp (brew install yt-dlp)")

    payload = {
        "success": True,
        "tool": "transcribe",
        "dependencies": deps,
        "credentials": creds,
        "browse_sessions": sessions,
        "recommendations": recommendations,
    }

    if args.json:
        emit_json(payload)
    else:
        print("agent-transcribe doctor")
        print()
        print("dependencies:")
        for k, v in deps.items():
            print(f"  {'OK ' if v else 'MISS'}  {k}")
        print()
        print("credentials:")
        for k, v in creds.items():
            print(f"  {'OK ' if v else 'MISS'}  {k}")
        print()
        print(f"browse sessions ({len(sessions)}):")
        for s in sessions:
            domains = ", ".join(s["domains"][:5]) or "—"
            print(f"  {s['name']}  ({s['cookie_count']} cookies; {domains})")
        if recommendations:
            print()
            print("recommendations:")
            for r in recommendations:
                print(f"  - {r}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    cache_entries = sorted(CACHE_ROOT.glob("*.json"))
    sessions = list_sessions()

    payload = {
        "success": True,
        "tool": "transcribe",
        "cache_dir": str(CACHE_ROOT),
        "cached_entries": len(cache_entries),
        "recent_cache": [
            {"file": p.name, "size_bytes": p.stat().st_size, "mtime": int(p.stat().st_mtime)}
            for p in sorted(cache_entries, key=lambda p: p.stat().st_mtime, reverse=True)[:10]
        ],
        "browse_sessions": sessions,
        "default_method_order": ["whisper-api", "local-whisper", "captions", "vtt"],
    }

    if args.json:
        emit_json(payload)
    else:
        print(f"cache: {payload['cached_entries']} entries at {payload['cache_dir']}")
        print(f"browse sessions: {len(sessions)}")
        for s in sessions:
            print(f"  {s['name']} ({s['cookie_count']} cookies)")
    return 0


def _estimate_cost(meta: dict) -> dict:
    duration = meta.get("duration_seconds")
    if not duration:
        return {"estimated_usd": None, "duration_seconds": None, "note": "duration unknown"}
    minutes = float(duration) / 60.0
    return {
        "estimated_usd": round(minutes * WHISPER_API_RATE_USD_PER_MIN, 4),
        "duration_seconds": float(duration),
        "minutes": round(minutes, 2),
        "rate_usd_per_min": WHISPER_API_RATE_USD_PER_MIN,
        "method": "whisper-api",
    }


def cmd_cost(args: argparse.Namespace) -> int:
    extractor_args = ytdlp_extractor_args(args, json_mode=args.json)
    cookies_file = None
    cookies_cm = None
    if args.browse_session:
        try:
            cookies_cm = safe_cookie_file(args.browse_session)
            cookies_file = str(cookies_cm.__enter__())
        except (FileNotFoundError, ValueError) as exc:
            emit_error(str(exc), exit_code=1, json_mode=args.json)
    elif args.cookies:
        cookies_file = args.cookies

    try:
        sources = _resolve_sources(args, json_mode=args.json)
        per_source = []
        total = 0.0
        unknown_count = 0
        for raw in sources:
            src = classify_source(raw)
            meta = probe_metadata(src, cookies_file, extractor_args)
            estimate = _estimate_cost(meta)
            per_source.append({
                "source": raw,
                "video_id": src.get("video_id"),
                "title": meta.get("title"),
                "requires_auth": meta.get("requires_auth"),
                **estimate,
            })
            if estimate.get("estimated_usd") is None:
                unknown_count += 1
            else:
                total += estimate["estimated_usd"]

        payload = {
            "success": True,
            "tool": "transcribe",
            "method": "whisper-api",
            "rate_usd_per_min": WHISPER_API_RATE_USD_PER_MIN,
            "total_estimated_usd": round(total, 4),
            "sources_known": len(per_source) - unknown_count,
            "sources_unknown_duration": unknown_count,
            "yt_dlp": {
                "extractor_args": extractor_args,
            },
            "sources": per_source,
        }

        if args.json:
            emit_json(payload)
        else:
            print(f"estimate: {len(per_source)} sources, ${payload['total_estimated_usd']} (whisper-api)")
            for s in per_source:
                cost = f"${s['estimated_usd']}" if s["estimated_usd"] is not None else "unknown"
                title = s.get("title") or s["source"]
                print(f"  {cost}\t{title}")
            if unknown_count:
                print(f"\nnote: {unknown_count} source(s) had unknown duration (probe failed or auth required)")
        return 0
    finally:
        if cookies_cm is not None:
            cookies_cm.__exit__(None, None, None)


def _resolve_sources(args: argparse.Namespace, *, json_mode: bool) -> list[str]:
    if args.batch_file:
        path = Path(args.batch_file).expanduser()
        if not path.exists():
            emit_error(f"batch-file not found: {path}", json_mode=json_mode)
        return [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.strip().startswith("#")]
    if args.batch:
        return [line.strip() for line in sys.stdin if line.strip() and not line.strip().startswith("#")]
    if args.source:
        return [args.source]
    emit_error("no source provided (URL, ID, path, or --batch/--batch-file)", exit_code=2, json_mode=json_mode)
    return []  # unreachable


# ---------------------------------------------------------------------------
# Single-source transcription orchestration
# ---------------------------------------------------------------------------

def _run_engine(method: str, src: dict, audio_path: Optional[Path],
                cookies_file: Optional[str],
                extractor_args: Optional[list[str]]) -> dict:
    if method == "whisper-api":
        if audio_path is None:
            return {"success": False, "error": "whisper-api requires audio (download failed)"}
        return whisper_api_transcribe(audio_path, progress=progress)
    if method == "local-whisper":
        if audio_path is None:
            return {"success": False, "error": "local-whisper requires audio (download failed)"}
        return local_whisper_transcribe(audio_path, progress=progress)
    if method == "captions":
        if src["kind"] != "youtube":
            return {"success": False, "error": "captions method only supports YouTube sources"}
        return captions_transcribe(src["video_id"], progress=progress)
    if method == "vtt":
        if src["kind"] != "youtube":
            return {"success": False, "error": "vtt method only supports YouTube sources"}
        return vtt_transcribe(src.get("url") or "", cookies_file, extractor_args, progress=progress)
    return {"success": False, "error": f"unknown method: {method}"}


def transcribe_one(raw_source: str, args: argparse.Namespace,
                   cookies_file: Optional[str], output_dir: Optional[Path],
                   extractor_args: Optional[list[str]]) -> dict:
    src = classify_source(raw_source)
    meta = probe_metadata(src, cookies_file, extractor_args)

    if not meta.get("success") and src["kind"] != "file":
        return {
            "success": False,
            "source": {"raw": raw_source, **src},
            "error": meta.get("error", "metadata probe failed"),
            "requires_auth": meta.get("requires_auth"),
            "hint": auth_recovery_hint(cookies_file),
        }

    method_order = order_methods(args.method, args.prefer_free, args.prefer)
    needs_audio = any(m in {"whisper-api", "local-whisper"} for m in method_order)

    work_dir: Optional[Path] = None
    audio_path: Optional[Path] = None
    download_error: Optional[dict] = None
    download_info: Optional[dict] = None

    try:
        if src["kind"] == "file":
            audio_path = Path(src["path"]).expanduser()
        elif needs_audio:
            work_dir = Path(tempfile.mkdtemp(prefix="agent-transcribe-work-"))
            if args.browser_capture:
                if not args.browse_session:
                    return {
                        "success": False,
                        "source": {"raw": raw_source, **src},
                        "error": "--browser-capture requires --browse-session <name>",
                        "hint": "save browser auth with agent-do browse login done --save <name>, then pass --browse-session <name>",
                    }
                dl = browser_capture_audio(
                    src.get("url") or "",
                    work_dir,
                    args.browse_session,
                    capture_seconds=args.capture_seconds,
                    capture_buffer_seconds=args.capture_buffer_seconds,
                    progress=progress,
                )
            else:
                dl = download_audio(src.get("url") or "", work_dir, cookies_file, extractor_args, progress=progress)
            if not dl["success"]:
                if dl.get("requires_auth"):
                    return {
                        "success": False,
                        "source": {"raw": raw_source, **src},
                        "error": dl["error"],
                        "requires_auth": True,
                        "hint": auth_recovery_hint(cookies_file),
                    }
                progress(f"audio download failed: {dl['error'][:120]}")
                download_error = dl
            else:
                audio_path = dl["path"]
                download_info = dl

        attempted: list[dict] = []
        engine_result: Optional[dict] = None
        used_method: Optional[str] = None

        for method in method_order:
            if not args.no_cache:
                cached = cache_load(src, method)
                if cached:
                    progress(f"cache hit: {method}")
                    engine_result = cached
                    used_method = method
                    break

            progress(f"trying method: {method}")
            result = _run_engine(method, src, audio_path, cookies_file, extractor_args)
            attempted.append({"method": method, "success": result.get("success"),
                              "error": result.get("error")})
            if result.get("success"):
                cache_save(src, method, result)
                engine_result = result
                used_method = method
                break

        if engine_result is None:
            return {
                "success": False,
                "source": {"raw": raw_source, **src},
                "error": "all transcription methods failed",
                "download_error": download_error,
                "download": download_info,
                "hint": auth_recovery_hint(cookies_file) if src["kind"] == "youtube" else None,
                "attempted": attempted,
            }

        text_path: Optional[Path] = None
        json_path: Optional[Path] = None
        if output_dir is not None:
            stem = src.get("video_id") or hashlib.sha256(raw_source.encode()).hexdigest()[:12]
            output_dir.mkdir(parents=True, exist_ok=True)
            text_path = output_dir / f"{stem}.txt"
            json_path = output_dir / f"{stem}.json"
            text_path.write_text(engine_result.get("text", ""))

        result = build_result(src, meta, engine_result, audio_path,
                              audio_kept=args.keep_audio, text_path=text_path, json_path=json_path)
        result["attempted_methods"] = attempted
        result["method_used"] = used_method
        if download_info:
            result["audio"]["source"] = download_info.get("source") or "yt-dlp"
            result["audio"]["capture"] = download_info.get("capture")
        result["yt_dlp"] = {
            "extractor_args": extractor_args or [],
        }

        if json_path is not None:
            json_path.write_text(json.dumps(result, indent=2, default=str))

        return result
    finally:
        if work_dir is not None and not args.keep_audio:
            try:
                import shutil
                shutil.rmtree(work_dir, ignore_errors=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Single + batch commands
# ---------------------------------------------------------------------------

def cmd_transcribe(args: argparse.Namespace) -> int:
    extractor_args = ytdlp_extractor_args(args, json_mode=args.json)
    if args.browser_capture and not args.browse_session:
        emit_error(
            "--browser-capture requires --browse-session <name>",
            exit_code=2,
            json_mode=args.json,
            extra={"hint": "save browser auth with agent-do browse login done --save <name>"},
        )
    cookies_cm = None
    cookies_file: Optional[str] = None
    if args.browse_session:
        try:
            cookies_cm = safe_cookie_file(args.browse_session)
            cookies_file = str(cookies_cm.__enter__())
        except (FileNotFoundError, ValueError) as exc:
            emit_error(str(exc), exit_code=1, json_mode=args.json)
    elif args.cookies:
        cookies_file = args.cookies

    try:
        sources = _resolve_sources(args, json_mode=args.json)
        output_dir = Path(args.output_dir).expanduser() if args.output_dir else None

        if len(sources) == 1 and output_dir is None and not args.batch and not args.batch_file:
            result = transcribe_one(sources[0], args, cookies_file, None, extractor_args)
            if not result.get("success"):
                if args.json:
                    emit_json(result)
                else:
                    print(f"error: {result.get('error')}", file=sys.stderr)
                    if result.get("hint"):
                        print(f"hint: {result['hint']}", file=sys.stderr)
                return 2 if result.get("requires_auth") else 1

            if args.json:
                emit_json(result)
            elif args.output:
                Path(args.output).expanduser().write_text(result["transcript"]["text"])
                progress(f"wrote {len(result['transcript']['text'])} chars to {args.output}")
            else:
                sys.stdout.write(result["transcript"]["text"])
                sys.stdout.write("\n")
            return 0

        # Batch / output-dir path
        if output_dir is None:
            output_dir = Path.cwd()
        results: list[dict] = []
        successes = 0
        failures = 0
        for i, raw in enumerate(sources, 1):
            progress(f"[{i}/{len(sources)}] {raw}")
            result = transcribe_one(raw, args, cookies_file, output_dir, extractor_args)
            results.append(result)
            if result.get("success"):
                successes += 1
            else:
                failures += 1

        summary = {
            "success": failures == 0,
            "total": len(sources),
            "succeeded": successes,
            "failed": failures,
            "output_dir": str(output_dir),
            "results": results,
        }
        if args.json:
            emit_json(summary)
        else:
            print(f"batch: {successes}/{len(sources)} succeeded; output: {output_dir}")
            for r in results:
                if r.get("success"):
                    src = r["source"]
                    title = src.get("title") or src.get("video_id") or src.get("url")
                    print(f"  OK    {r.get('method_used'):>13}  {title}")
                else:
                    src = r.get("source") or {}
                    label = src.get("raw") or src.get("url") or "?"
                    print(f"  FAIL                  {label}  ({r.get('error', 'unknown')})")
        return 0 if failures == 0 else 1
    finally:
        if cookies_cm is not None:
            cookies_cm.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-transcribe", add_help=True)
    parser.add_argument("--json", action="store_true",
                        help="emit structured JSON to stdout")

    sub = parser.add_subparsers(dest="verb")

    # doctor
    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--json", action="store_true")

    # snapshot
    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("--json", action="store_true")

    # cost
    p_cost = sub.add_parser("cost")
    p_cost.add_argument("source", nargs="?")
    p_cost.add_argument("--batch", action="store_true")
    p_cost.add_argument("--batch-file")
    p_cost.add_argument("--browse-session")
    p_cost.add_argument("--cookies")
    p_cost.add_argument("--extractor-args", action="append",
                        help="pass a yt-dlp extractor args spec, e.g. youtube:player_client=ios")
    p_cost.add_argument("--youtube-player-client",
                        help="shortcut for --extractor-args youtube:player_client=<client>")
    p_cost.add_argument("--json", action="store_true")

    return parser


def parse_top_level(argv: list[str]) -> tuple[str, list[str]]:
    """Decide whether argv[0] is a known verb or an implicit transcribe source."""
    if not argv:
        return ("transcribe", [])
    first = argv[0]
    if first in {"doctor", "snapshot", "cost"}:
        return (first, argv[1:])
    return ("transcribe", argv)


def parse_transcribe_args(rest: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent-transcribe transcribe", add_help=True)
    parser.add_argument("source", nargs="?")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--batch-file")
    parser.add_argument("--browse-session")
    parser.add_argument("--cookies")
    parser.add_argument("--extractor-args", action="append",
                        help="pass a yt-dlp extractor args spec, e.g. youtube:player_client=ios")
    parser.add_argument("--youtube-player-client",
                        help="shortcut for --extractor-args youtube:player_client=<client>")
    parser.add_argument("--browser-capture", action="store_true",
                        help="capture authenticated tab audio via saved browser session instead of yt-dlp")
    parser.add_argument("--capture-seconds", type=float,
                        help="limit browser capture duration; default is video duration plus buffer")
    parser.add_argument("--capture-buffer-seconds", type=float, default=5.0,
                        help="extra seconds after detected video duration for browser capture")
    parser.add_argument("--method", default="auto",
                        choices=["auto", "whisper-api", "local-whisper", "captions", "vtt"])
    parser.add_argument("--prefer-free", action="store_true")
    parser.add_argument("--prefer", choices=["captions", "whisper", "vtt"])
    parser.add_argument("--output")
    parser.add_argument("--output-dir")
    parser.add_argument("--language", default="en")
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(rest)


def main() -> None:
    argv = sys.argv[1:]
    verb, rest = parse_top_level(argv)

    if verb == "doctor":
        args = build_parser().parse_args(["doctor", *rest])
        sys.exit(cmd_doctor(args))
    if verb == "snapshot":
        args = build_parser().parse_args(["snapshot", *rest])
        sys.exit(cmd_snapshot(args))
    if verb == "cost":
        args = build_parser().parse_args(["cost", *rest])
        sys.exit(cmd_cost(args))

    args = parse_transcribe_args(rest)
    sys.exit(cmd_transcribe(args))


if __name__ == "__main__":
    main()
