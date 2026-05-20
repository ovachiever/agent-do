"""Transcription engines.

Default method order (quality-first):
  1. whisper-api      OpenAI Whisper API ($0.006/min, high quality)
  2. local-whisper    Local whisper CLI / openai-whisper package (free, slow)
  3. captions         YouTube auto-captions via youtube-transcript (free, rough)
  4. vtt              yt-dlp VTT subtitles with rolling-dedup (free, lowest)

`--prefer-free` reorders to: captions, vtt, local-whisper, whisper-api.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .ytdlp import add_ytdlp_auth_args

WHISPER_API_MODEL = "whisper-1"
WHISPER_API_RATE_USD_PER_MIN = 0.006
WHISPER_API_MAX_BYTES = 24 * 1024 * 1024  # 24MB chunk cap (Whisper hard limit 25MB)


# ---------------------------------------------------------------------------
# Method ordering
# ---------------------------------------------------------------------------

ALL_METHODS = ("whisper-api", "local-whisper", "captions", "vtt")


def order_methods(method: str, prefer_free: bool, prefer: Optional[str]) -> list[str]:
    if method != "auto":
        return [method]
    if prefer_free:
        return ["captions", "vtt", "local-whisper", "whisper-api"]
    if prefer == "captions":
        return ["captions", "whisper-api", "local-whisper", "vtt"]
    if prefer == "vtt":
        return ["vtt", "whisper-api", "local-whisper", "captions"]
    if prefer == "whisper":
        return ["whisper-api", "local-whisper", "captions", "vtt"]
    return list(ALL_METHODS)


def dependency_check() -> dict:
    return {
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "yt_dlp": shutil.which("yt-dlp") is not None,
        "openai_sdk": _has_module("openai"),
        "local_whisper": _has_module("whisper") or shutil.which("whisper") is not None,
        "node": shutil.which("node") is not None,
        "npx": shutil.which("npx") is not None,
        "macos_screen_capture_current_process": _macos_screen_capture_preflight(),
    }


def _has_module(name: str) -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _macos_screen_capture_preflight() -> Optional[bool]:
    if sys.platform != "darwin" or not shutil.which("swift"):
        return None
    try:
        proc = subprocess.run(
            ["swift", "-e", "import CoreGraphics; print(CGPreflightScreenCaptureAccess())"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = proc.stdout.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


# ---------------------------------------------------------------------------
# Whisper API
# ---------------------------------------------------------------------------

def whisper_api_transcribe(audio_path: Path, language: str = "en",
                           progress=None) -> dict:
    """Transcribe via OpenAI Whisper API, chunking if needed.

    Returns {success, text, segments, cost_usd, error?}.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "error": "OPENAI_API_KEY not set"}
    if not audio_path.exists():
        return {"success": False, "error": f"audio not found: {audio_path}"}

    try:
        from openai import OpenAI
    except ImportError:
        return {"success": False, "error": "openai SDK not installed (pip install openai)"}

    client = OpenAI(api_key=api_key)
    file_size = audio_path.stat().st_size
    chunks = [audio_path]
    cleanup_dir: Optional[Path] = None

    if file_size > WHISPER_API_MAX_BYTES:
        if progress:
            progress(f"chunking {file_size // 1024 // 1024}MB audio")
        cleanup_dir = Path(tempfile.mkdtemp(prefix="agent-transcribe-chunks-"))
        try:
            chunks = _chunk_audio(audio_path, cleanup_dir, file_size)
        except RuntimeError as exc:
            _safe_rmtree(cleanup_dir)
            return {"success": False, "error": str(exc)}

    full_text_parts: list[str] = []
    full_segments: list[dict] = []
    chunk_offset = 0.0
    total_duration = 0.0

    try:
        for i, chunk in enumerate(chunks, start=1):
            if progress:
                progress(f"whisper api chunk {i}/{len(chunks)}")
            try:
                with chunk.open("rb") as fh:
                    resp = client.audio.transcriptions.create(
                        file=fh,
                        model=WHISPER_API_MODEL,
                        language=language,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                    )
            except Exception as exc:  # noqa: BLE001 — surface real API errors
                return {"success": False, "error": f"whisper api: {exc}"}

            text = (resp.text or "").strip()
            if text:
                full_text_parts.append(text)
            chunk_duration = float(getattr(resp, "duration", 0.0) or 0.0)
            for seg in getattr(resp, "segments", []) or []:
                seg_dict = seg if isinstance(seg, dict) else seg.model_dump()
                full_segments.append({
                    "start": float(seg_dict.get("start", 0.0)) + chunk_offset,
                    "duration": float(seg_dict.get("end", 0.0)) - float(seg_dict.get("start", 0.0)),
                    "text": seg_dict.get("text", "").strip(),
                })
            chunk_offset += chunk_duration
            total_duration += chunk_duration
    finally:
        if cleanup_dir:
            _safe_rmtree(cleanup_dir)

    cost = (total_duration / 60.0) * WHISPER_API_RATE_USD_PER_MIN
    return {
        "success": True,
        "method": "whisper-api",
        "model": WHISPER_API_MODEL,
        "text": " ".join(full_text_parts),
        "segments": full_segments,
        "cost_usd": round(cost, 4),
        "duration_seconds": total_duration,
        "chunks": len(chunks),
    }


def _chunk_audio(audio_path: Path, out_dir: Path, file_size: int) -> list[Path]:
    duration = _ffprobe_duration(audio_path)
    if duration <= 0:
        raise RuntimeError("ffprobe could not determine audio duration for chunking")

    chunks_needed = max(1, math.ceil(file_size / WHISPER_API_MAX_BYTES))
    chunk_duration = math.ceil(duration / chunks_needed)
    chunks: list[Path] = []

    for i in range(chunks_needed):
        start = i * chunk_duration
        out_path = out_dir / f"chunk_{i:03d}.mp3"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(audio_path),
            "-ss", str(start), "-t", str(chunk_duration),
            "-acodec", "libmp3lame", "-q:a", "5",
            str(out_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0 or not out_path.exists():
            raise RuntimeError(f"ffmpeg chunk {i} failed: {proc.stderr.strip()[:200]}")
        chunks.append(out_path)
    return chunks


def _ffprobe_duration(path: Path) -> float:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=15, check=False,
        )
        return float(proc.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def _safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Local Whisper (CLI or openai-whisper package)
# ---------------------------------------------------------------------------

def local_whisper_transcribe(audio_path: Path, language: str = "en",
                             progress=None) -> dict:
    if not audio_path.exists():
        return {"success": False, "error": f"audio not found: {audio_path}"}

    # Prefer Python package (no extra subprocess output to parse)
    if _has_module("whisper"):
        try:
            import whisper  # type: ignore
            if progress:
                progress("loading local whisper model (base)")
            model = whisper.load_model("base")
            if progress:
                progress("local whisper transcribing")
            result = model.transcribe(str(audio_path), language=language, verbose=False)
            segments = [
                {"start": float(s["start"]),
                 "duration": float(s["end"]) - float(s["start"]),
                 "text": (s.get("text") or "").strip()}
                for s in result.get("segments", [])
            ]
            return {
                "success": True,
                "method": "local-whisper",
                "model": "whisper-base-local",
                "text": (result.get("text") or "").strip(),
                "segments": segments,
                "cost_usd": 0.0,
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"local whisper: {exc}"}

    if shutil.which("whisper"):
        try:
            out_dir = Path(tempfile.mkdtemp(prefix="agent-transcribe-local-"))
            try:
                proc = subprocess.run(
                    ["whisper", str(audio_path), "--model", "base",
                     "--language", language, "--output_dir", str(out_dir),
                     "--output_format", "json"],
                    capture_output=True, text=True, check=False,
                )
                if proc.returncode != 0:
                    return {"success": False, "error": f"whisper CLI: {proc.stderr.strip()[:200]}"}
                json_files = list(out_dir.glob("*.json"))
                if not json_files:
                    return {"success": False, "error": "whisper CLI produced no JSON output"}
                data = json.loads(json_files[0].read_text())
                segments = [
                    {"start": float(s["start"]),
                     "duration": float(s["end"]) - float(s["start"]),
                     "text": (s.get("text") or "").strip()}
                    for s in data.get("segments", [])
                ]
                return {
                    "success": True,
                    "method": "local-whisper",
                    "model": "whisper-base-cli",
                    "text": (data.get("text") or "").strip(),
                    "segments": segments,
                    "cost_usd": 0.0,
                }
            finally:
                _safe_rmtree(out_dir)
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"whisper CLI: {exc}"}

    return {"success": False, "error": "local whisper not installed"}


# ---------------------------------------------------------------------------
# Captions (youtube-transcript via npx)
# ---------------------------------------------------------------------------

YT_TRANSCRIPT_SCRIPT = r"""
const { YoutubeTranscript } = require('youtube-transcript');
YoutubeTranscript.fetchTranscript(process.argv[2])
  .then(t => {
    if (!t || t.length === 0) { process.exit(2); }
    process.stdout.write(JSON.stringify(t));
  })
  .catch(err => {
    process.stderr.write(err.message || String(err));
    process.exit(1);
  });
"""

NPM_CACHE_DIR = Path.home() / ".agent-do" / "transcribe" / "npm-cache"


def _ensure_youtube_transcript_installed() -> Optional[Path]:
    """Install youtube-transcript into a cached node_modules. Returns node_modules path."""
    node_modules = NPM_CACHE_DIR / "node_modules" / "youtube-transcript"
    if node_modules.exists():
        return NPM_CACHE_DIR / "node_modules"
    if not shutil.which("npm"):
        return None
    NPM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pkg = NPM_CACHE_DIR / "package.json"
    if not pkg.exists():
        pkg.write_text('{"name":"agent-transcribe-deps","private":true}\n')
    proc = subprocess.run(
        ["npm", "install", "--silent", "--no-audit", "--no-fund", "youtube-transcript"],
        cwd=str(NPM_CACHE_DIR), capture_output=True, text=True, timeout=120, check=False,
    )
    if proc.returncode != 0 or not node_modules.exists():
        return None
    return NPM_CACHE_DIR / "node_modules"


def captions_transcribe(video_id: str, progress=None) -> dict:
    if not video_id:
        return {"success": False, "error": "captions method requires a YouTube video id"}
    if not shutil.which("node"):
        return {"success": False, "error": "node not installed (need Node.js for youtube-transcript)"}

    if progress:
        progress("preparing youtube-transcript")
    node_modules = _ensure_youtube_transcript_installed()
    if node_modules is None:
        return {"success": False, "error": "could not install youtube-transcript via npm"}

    if progress:
        progress("fetching youtube auto-captions")

    script_path = Path(tempfile.mkstemp(prefix="agent-transcribe-yt-", suffix=".js")[1])
    try:
        script_path.write_text(YT_TRANSCRIPT_SCRIPT)
        env = os.environ.copy()
        env["NODE_PATH"] = str(node_modules)
        proc = subprocess.run(
            ["node", str(script_path), video_id],
            capture_output=True, text=True, timeout=60, check=False, env=env,
        )
    finally:
        try:
            script_path.unlink(missing_ok=True)
        except OSError:
            pass

    if proc.returncode == 2:
        return {"success": False, "error": "no captions available"}
    if proc.returncode != 0:
        return {"success": False, "error": (proc.stderr or "youtube-transcript failed").strip()[:200]}

    try:
        segments_raw = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"success": False, "error": "youtube-transcript returned non-JSON"}

    text_parts = []
    segments = []
    for seg in segments_raw:
        text = (seg.get("text") or "").strip()
        if text:
            text_parts.append(text)
        segments.append({
            "start": float(seg.get("offset", 0)) / 1000.0,
            "duration": float(seg.get("duration", 0)) / 1000.0,
            "text": text,
        })

    return {
        "success": True,
        "method": "captions",
        "model": "youtube-auto-captions",
        "text": " ".join(text_parts),
        "segments": segments,
        "cost_usd": 0.0,
    }


# ---------------------------------------------------------------------------
# VTT (yt-dlp subtitles with rolling dedup)
# ---------------------------------------------------------------------------

VTT_TIME_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)
VTT_TAG_RE = re.compile(r"<[^>]+>")


def vtt_transcribe(url: str, cookies_path: Optional[str] = None,
                   extractor_args: Optional[list[str]] = None,
                   progress=None) -> dict:
    if not shutil.which("yt-dlp"):
        return {"success": False, "error": "yt-dlp not installed"}

    work_dir = Path(tempfile.mkdtemp(prefix="agent-transcribe-vtt-"))
    try:
        if progress:
            progress("downloading vtt subtitles")
        cmd = ["yt-dlp", "--write-auto-sub", "--sub-lang", "en",
               "--skip-download", "--sub-format", "vtt",
               "--no-warnings", "--socket-timeout", "30",
               "-o", str(work_dir / "sub")]
        add_ytdlp_auth_args(cmd, cookies_path, extractor_args)
        cmd.append(url)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
        if proc.returncode != 0:
            return {"success": False, "error": (proc.stderr or "yt-dlp vtt failed").strip()[:200]}

        vtt_files = list(work_dir.glob("*.vtt"))
        if not vtt_files:
            return {"success": False, "error": "no VTT file produced"}
        return _parse_vtt(vtt_files[0])
    finally:
        _safe_rmtree(work_dir)


def _parse_vtt(path: Path) -> dict:
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    segments: list[dict] = []
    text_parts: list[str] = []
    prev_text = ""
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            i += 1
            continue
        if line.isdigit():
            i += 1
            continue
        time_match = VTT_TIME_RE.match(line)
        if not time_match:
            i += 1
            continue
        start = (int(time_match.group(1)) * 3600 +
                 int(time_match.group(2)) * 60 +
                 int(time_match.group(3)) +
                 int(time_match.group(4)) / 1000.0)
        end = (int(time_match.group(5)) * 3600 +
               int(time_match.group(6)) * 60 +
               int(time_match.group(7)) +
               int(time_match.group(8)) / 1000.0)
        i += 1
        cue_lines = []
        while i < len(lines) and lines[i].strip():
            cue_lines.append(VTT_TAG_RE.sub("", lines[i]).strip())
            i += 1
        cue_text = " ".join(cl for cl in cue_lines if cl).strip()
        if not cue_text:
            continue

        new_text = cue_text
        if prev_text and new_text.startswith(prev_text):
            new_text = new_text[len(prev_text):].strip()
        if new_text:
            segments.append({"start": start, "duration": end - start, "text": new_text})
            text_parts.append(new_text)
        prev_text = cue_text

    if not text_parts:
        return {"success": False, "error": "VTT parsed but contained no text"}

    return {
        "success": True,
        "method": "vtt",
        "model": "yt-dlp-vtt",
        "text": " ".join(text_parts),
        "segments": segments,
        "cost_usd": 0.0,
    }


# ---------------------------------------------------------------------------
# Audio download (shared by whisper-api and local-whisper)
# ---------------------------------------------------------------------------

def download_audio(url: str, work_dir: Path, cookies_path: Optional[str] = None,
                   extractor_args: Optional[list[str]] = None,
                   progress=None) -> dict:
    if not shutil.which("yt-dlp"):
        return {"success": False, "error": "yt-dlp not installed"}
    if not shutil.which("ffmpeg"):
        return {"success": False, "error": "ffmpeg not installed (needed for audio extraction)"}

    if progress:
        if extractor_args:
            progress(f"downloading audio via yt-dlp ({', '.join(extractor_args)})")
        else:
            progress("downloading audio via yt-dlp")
    out_template = str(work_dir / "audio.%(ext)s")
    cmd = ["yt-dlp", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "5",
           "--no-playlist", "--socket-timeout", "30", "--no-warnings",
           "-o", out_template]
    add_ytdlp_auth_args(cmd, cookies_path, extractor_args)
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0:
        stderr = (proc.stderr or "yt-dlp audio download failed").strip()
        auth_required = bool(re.search(
            r"(members?-only|join this channel|sign in|login required|private video|"
            r"not a bot|confirm.*bot|requires.*authentication|available to .*members|"
            r"HTTP Error 403|Forbidden)",
            stderr, re.IGNORECASE,
        ))
        return {"success": False, "error": stderr[:300], "requires_auth": auth_required}

    candidates = list(work_dir.glob("audio.*"))
    audio = next((c for c in candidates if c.suffix == ".mp3"), None) or (candidates[0] if candidates else None)
    if audio is None:
        return {"success": False, "error": "yt-dlp succeeded but no audio file produced"}
    return {"success": True, "path": audio, "size_bytes": audio.stat().st_size}


def browser_capture_audio(url: str, work_dir: Path, browse_session: str,
                          capture_seconds: Optional[float] = None,
                          capture_buffer_seconds: float = 5.0,
                          progress=None) -> dict:
    """Capture authenticated tab audio through Chromium and MediaRecorder."""
    if not shutil.which("node"):
        return {"success": False, "error": "node not installed (needed for browser capture)"}

    script_path = Path(__file__).resolve().parent / "browser_capture.mjs"
    if not script_path.exists():
        return {"success": False, "error": f"browser capture script missing: {script_path}"}

    out_path = work_dir / "browser-capture.webm"
    cmd = [
        "node", str(script_path),
        "--url", url,
        "--session", browse_session,
        "--output", str(out_path),
        "--buffer-seconds", str(capture_buffer_seconds),
    ]
    if capture_seconds:
        cmd.extend(["--duration-seconds", str(capture_seconds)])

    if progress:
        if capture_seconds:
            progress(f"capturing browser tab audio for {capture_seconds:g}s")
        else:
            progress("capturing browser tab audio until video end")

    timeout = int((capture_seconds or 3600) + 180)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "browser capture timed out"}

    try:
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        stderr = (proc.stderr or "").strip()
        return {"success": False, "error": f"browser capture returned no JSON: {stderr[:300]}"}

    if proc.returncode != 0 or not payload.get("success"):
        return {
            "success": False,
            "error": payload.get("error") or (proc.stderr or "browser capture failed").strip()[:300],
            "requires_auth": True,
        }

    audio_path = Path(payload["path"])
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return {"success": False, "error": "browser capture produced no audio file"}

    duration = _ffprobe_duration(audio_path)
    if duration <= 0:
        return {"success": False, "error": "browser capture audio could not be probed by ffprobe"}

    return {
        "success": True,
        "path": audio_path,
        "size_bytes": audio_path.stat().st_size,
        "duration_seconds": duration,
        "capture": payload,
        "source": "browser-capture",
    }
