#!/usr/bin/env python3
"""AppleEvents automation surface for agent-do."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
LIB_DIR = ROOT_DIR / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from live.errors import LiveApprovalRequiredError  # noqa: E402
from live.policy import require_live_control  # noqa: E402


EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_APP_NOT_FOUND = 3
EXIT_COMPILE_FAILED = 4
EXIT_RUN_FAILED = 5
EXIT_UNSUPPORTED = 6
EXIT_TIMEOUT = 7

AGENT_DO_HOME = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do"))
CACHE_DIR = AGENT_DO_HOME / "appleevents" / "dictionaries"

APP_SEARCH_DIRS = (
    Path("/Applications"),
    Path.home() / "Applications",
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path("/System/Library/CoreServices"),
)

STATUS_MAP = {
    -1743: {
        "state": "denied",
        "name": "errAEEventNotPermitted",
        "message": "Automation denied, not granted, or blocked by TCC",
    },
    -600: {
        "state": "not_running",
        "name": "procNotFound",
        "message": "Target process is not running or cannot be addressed",
    },
    -1728: {
        "state": "object_error",
        "name": "errAENoSuchObject",
        "message": "Script ran, but the addressed object or reference does not exist",
    },
    -1708: {
        "state": "event_not_handled",
        "name": "errAEEventNotHandled",
        "message": "Target does not handle the requested AppleEvent",
    },
}


class ToolError(RuntimeError):
    def __init__(self, message: str, exit_code: int = EXIT_ERROR, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.details = details


def emit(payload: dict[str, Any], exit_code: int = EXIT_SUCCESS) -> None:
    print(json.dumps(payload, indent=2, sort_keys=False))
    raise SystemExit(exit_code)


def fail(message: str, exit_code: int = EXIT_ERROR, **details: Any) -> None:
    payload: dict[str, Any] = {"ok": False, "error": message}
    payload.update(details)
    emit(payload, exit_code)


def require_macos() -> None:
    if platform.system() != "Darwin":
        raise ToolError(
            "agent-appleevents is only supported on macOS",
            EXIT_UNSUPPORTED,
            platform=platform.system(),
        )


def normalize_language(value: str | None) -> tuple[str, str]:
    raw = (value or "applescript").strip().lower()
    if raw in {"applescript", "apple-script", "osa"}:
        return "applescript", "AppleScript"
    if raw in {"javascript", "java-script", "jxa"}:
        return "javascript", "JavaScript"
    raise ToolError(f"Unsupported language: {value}", EXIT_USAGE)


class TimedOutProcess(subprocess.CompletedProcess):
    """A process this wrapper stopped because it outran the caller's --timeout."""


def run_command(
    argv: list[str],
    *,
    input_text: str | None = None,
    timeout: float | None = 15.0,
) -> tuple[subprocess.CompletedProcess[str] | None, int]:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return proc, int((time.monotonic() - start) * 1000)
    except subprocess.TimeoutExpired as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        stderr = str(exc.stderr or "")
        stdout = str(exc.stdout or "")
        proc = TimedOutProcess(argv, 124, stdout=stdout, stderr=stderr or "Command timed out")
        return proc, elapsed


def truthy_plist(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def read_info_plist(app_path: Path) -> dict[str, Any]:
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return {}
    try:
        with plist_path.open("rb") as fh:
            data = plistlib.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def app_metadata(app_path: Path) -> dict[str, Any]:
    info = read_info_plist(app_path)
    name = (
        info.get("CFBundleDisplayName")
        or info.get("CFBundleName")
        or app_path.stem
    )
    bundle_id = info.get("CFBundleIdentifier")
    executable = info.get("CFBundleExecutable")
    version = info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    script_enabled = truthy_plist(info.get("NSAppleScriptEnabled"))
    sdef_name = info.get("OSAScriptingDefinition")
    sdef_path = None
    if sdef_name:
        candidate_paths = [
            app_path / "Contents" / "Resources" / str(sdef_name),
            app_path / "Contents" / "Resources" / "English.lproj" / str(sdef_name),
        ]
        sdef_path = next((str(path) for path in candidate_paths if path.exists()), str(sdef_name))
    return {
        "name": str(name),
        "bundle_id": str(bundle_id) if bundle_id else None,
        "path": str(app_path),
        "executable": str(executable) if executable else None,
        "version": str(version) if version else None,
        "cf_bundle_short_version": str(info.get("CFBundleShortVersionString")) if info.get("CFBundleShortVersionString") else None,
        "cf_bundle_version": str(info.get("CFBundleVersion")) if info.get("CFBundleVersion") else None,
        "scriptable_hint": bool(script_enabled or sdef_name),
        "scriptability": {
            "NSAppleScriptEnabled": info.get("NSAppleScriptEnabled"),
            "OSAScriptingDefinition": str(sdef_name) if sdef_name else None,
            "sdef_path": sdef_path,
        },
    }


def is_app_bundle(path: Path) -> bool:
    return path.exists() and path.is_dir() and path.suffix.lower() == ".app"


def iter_known_app_bundles() -> list[Path]:
    seen: set[str] = set()
    apps: list[Path] = []

    def add(path: Path) -> None:
        if not path.is_dir():
            return
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        apps.append(path)

    for root in APP_SEARCH_DIRS:
        if not root.exists():
            continue
        for path in root.glob("*.app"):
            add(path)
        for child in root.iterdir():
            if child.suffix.lower() == ".app" or not child.is_dir():
                continue
            for path in child.glob("*.app"):
                add(path)
    return apps


def mdfind_bundle_id(bundle_id: str) -> list[Path]:
    if not shutil.which("mdfind"):
        return []
    query = f"kMDItemCFBundleIdentifier == '{bundle_id}'"
    proc, _elapsed = run_command(["mdfind", query], timeout=5.0)
    if not proc or proc.returncode != 0:
        return []
    return [Path(line.strip()) for line in proc.stdout.splitlines() if line.strip().endswith(".app")]


def mdfind_app_name(name: str) -> list[Path]:
    if not shutil.which("mdfind"):
        return []
    app_name = name if name.endswith(".app") else f"{name}.app"
    query = f"kMDItemContentType == 'com.apple.application-bundle' && kMDItemFSName == '{app_name}'"
    proc, _elapsed = run_command(["mdfind", query], timeout=5.0)
    if not proc or proc.returncode != 0:
        return []
    return [Path(line.strip()) for line in proc.stdout.splitlines() if line.strip().endswith(".app")]


def resolve_app(query: str) -> dict[str, Any]:
    raw = query.strip()
    if not raw:
        raise ToolError("App name, bundle id, or .app path is required", EXIT_USAGE)

    candidate = Path(raw).expanduser()
    if is_app_bundle(candidate):
        return app_metadata(candidate.resolve())

    paths: list[Path] = []
    if "." in raw and "/" not in raw:
        paths.extend(mdfind_bundle_id(raw))
    paths.extend(mdfind_app_name(raw))

    normalized = raw[:-4] if raw.lower().endswith(".app") else raw
    normalized_lower = normalized.lower()

    for path in paths:
        if is_app_bundle(path):
            return app_metadata(path.resolve())

    for path in iter_known_app_bundles():
        meta = app_metadata(path)
        names = {
            str(meta.get("name") or "").lower(),
            path.stem.lower(),
            path.name.lower(),
            str(meta.get("bundle_id") or "").lower(),
        }
        if normalized_lower in names:
            return meta

    raise ToolError(f"App not found: {query}", EXIT_APP_NOT_FOUND, query=query)


def list_apps() -> dict[str, Any]:
    items = [app_metadata(path) for path in iter_known_app_bundles()]
    items.sort(key=lambda item: (not bool(item.get("scriptable_hint")), str(item.get("name") or "").lower()))
    scriptable_hint_count = sum(1 for item in items if item.get("scriptable_hint"))
    return {
        "ok": True,
        "apps": items,
        "count": len(items),
        "scriptable_hint_count": scriptable_hint_count,
        "discovery": "Info.plist bundle metadata; sdef is not run by apps",
    }


def safe_cache_id(meta: dict[str, Any]) -> str:
    bundle_id = str(meta.get("bundle_id") or meta.get("path") or "unknown")
    version = str(meta.get("cf_bundle_short_version") or meta.get("version") or meta.get("cf_bundle_version") or "unknown")
    digest = hashlib.sha1(f"{bundle_id}|{version}".encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", bundle_id).strip("-") or "app"
    return f"{slug}-{version}-{digest}"


def cache_files(meta: dict[str, Any]) -> tuple[Path, Path]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_id = safe_cache_id(meta)
    return CACHE_DIR / f"{cache_id}.sdef.xml", CACHE_DIR / f"{cache_id}.parsed.json"


def parse_sdef(xml_text: str) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    suites = []
    totals = {"suites": 0, "commands": 0, "classes": 0, "properties": 0}
    for suite in root.findall("suite"):
        suite_info: dict[str, Any] = {
            "name": suite.attrib.get("name"),
            "code": suite.attrib.get("code"),
            "description": suite.attrib.get("description"),
            "commands": [],
            "classes": [],
        }
        for command in suite.findall("command"):
            command_info = {
                "name": command.attrib.get("name"),
                "code": command.attrib.get("code"),
                "description": command.attrib.get("description"),
                "parameters": [
                    {
                        "name": parameter.attrib.get("name"),
                        "type": parameter.attrib.get("type"),
                        "optional": parameter.attrib.get("optional"),
                        "description": parameter.attrib.get("description"),
                    }
                    for parameter in command.findall("parameter")
                ],
                "direct_parameter": [
                    {
                        "type": parameter.attrib.get("type"),
                        "optional": parameter.attrib.get("optional"),
                        "description": parameter.attrib.get("description"),
                    }
                    for parameter in command.findall("direct-parameter")
                ],
            }
            suite_info["commands"].append(command_info)
        for cls in suite.findall("class"):
            properties = [
                {
                    "name": prop.attrib.get("name"),
                    "code": prop.attrib.get("code"),
                    "type": prop.attrib.get("type"),
                    "access": prop.attrib.get("access"),
                    "description": prop.attrib.get("description"),
                }
                for prop in cls.findall("property")
            ]
            class_info = {
                "name": cls.attrib.get("name"),
                "code": cls.attrib.get("code"),
                "description": cls.attrib.get("description"),
                "properties": properties,
            }
            suite_info["classes"].append(class_info)
            totals["properties"] += len(properties)
        totals["commands"] += len(suite_info["commands"])
        totals["classes"] += len(suite_info["classes"])
        suites.append(suite_info)
    totals["suites"] = len(suites)
    return {"suites": suites, "counts": totals}


def sdef_for_app(meta: dict[str, Any], *, refresh: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    xml_path, parsed_path = cache_files(meta)
    if not refresh and xml_path.exists() and parsed_path.exists():
        try:
            parsed = json.loads(parsed_path.read_text(encoding="utf-8"))
            return {"ok": True, "cached": True, "xml": xml_path.read_text(encoding="utf-8"), "parsed": parsed}
        except Exception:
            pass

    if not shutil.which("sdef"):
        raise ToolError("sdef is not available on this host", EXIT_UNSUPPORTED)

    proc, elapsed = run_command(["sdef", str(meta["path"])], timeout=timeout)
    if not proc:
        raise ToolError("sdef failed", EXIT_ERROR)
    if proc.returncode != 0:
        return {
            "ok": False,
            "cached": False,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "duration_ms": elapsed,
        }
    xml_text = proc.stdout
    parsed = parse_sdef(xml_text)
    xml_path.write_text(xml_text, encoding="utf-8")
    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return {"ok": True, "cached": False, "xml": xml_text, "parsed": parsed, "duration_ms": elapsed}


def dictionary_payload(app: str, *, refresh: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    meta = resolve_app(app)
    result = sdef_for_app(meta, refresh=refresh, timeout=timeout)
    if not result.get("ok"):
        return {
            "ok": False,
            "app": meta,
            "dictionary": {
                "available": False,
                "cached": False,
                "error": result.get("stderr") or result.get("stdout") or "sdef failed",
                "exit_code": result.get("exit_code"),
            },
        }
    return {
        "ok": True,
        "app": meta,
        "dictionary": {
            "available": True,
            "cached": bool(result.get("cached")),
            "counts": result["parsed"]["counts"],
            "suites": result["parsed"]["suites"],
        },
    }


def render_dictionary_markdown(payload: dict[str, Any]) -> str:
    app = payload["app"]
    lines = [f"# {app.get('name')} Scripting Dictionary", ""]
    counts = payload["dictionary"]["counts"]
    lines.append(f"Suites: {counts['suites']}  Commands: {counts['commands']}  Classes: {counts['classes']}  Properties: {counts['properties']}")
    lines.append("")
    for suite in payload["dictionary"]["suites"]:
        lines.append(f"## {suite.get('name') or 'Unnamed Suite'}")
        if suite.get("description"):
            lines.append(str(suite["description"]))
            lines.append("")
        if suite["commands"]:
            lines.append("Commands:")
            for command in suite["commands"]:
                lines.append(f"- `{command.get('name')}`: {command.get('description') or ''}".rstrip())
            lines.append("")
        if suite["classes"]:
            lines.append("Classes:")
            for cls in suite["classes"]:
                lines.append(f"- `{cls.get('name')}`: {cls.get('description') or ''}".rstrip())
                for prop in cls.get("properties", []):
                    lines.append(f"  - `{prop.get('name')}` ({prop.get('type') or 'any'})")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def probe(app: str, *, refresh: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    meta = resolve_app(app)
    dictionary_result = sdef_for_app(meta, refresh=refresh, timeout=timeout)
    dictionary: dict[str, Any]
    if dictionary_result.get("ok"):
        counts = dictionary_result["parsed"]["counts"]
        dictionary = {
            "available": True,
            "suites": counts["suites"],
            "commands": counts["commands"],
            "classes": counts["classes"],
            "properties": counts["properties"],
            "cached": bool(dictionary_result.get("cached")),
        }
    else:
        dictionary = {
            "available": False,
            "error": dictionary_result.get("stderr") or dictionary_result.get("stdout") or "sdef failed",
            "exit_code": dictionary_result.get("exit_code"),
            "cached": False,
        }
    return {
        "ok": True,
        "app": meta["name"],
        "bundle_id": meta.get("bundle_id"),
        "path": meta.get("path"),
        "scriptable": bool(meta.get("scriptable_hint") or dictionary.get("available")),
        "scriptability": meta.get("scriptability"),
        "dictionary": dictionary,
        "permissions": {
            "automation": "unknown",
            "reason": "macOS does not expose reliable read-only Automation grant state",
        },
        "sent_event": False,
    }


def terms(app: str, query: str | None, *, refresh: bool = False, timeout: float = 20.0) -> dict[str, Any]:
    payload = dictionary_payload(app, refresh=refresh, timeout=timeout)
    if not payload.get("ok"):
        return payload
    query_lower = (query or "").lower()
    matches: list[dict[str, Any]] = []
    for suite in payload["dictionary"]["suites"]:
        suite_name = suite.get("name")
        for command in suite.get("commands", []):
            name = str(command.get("name") or "")
            haystack = f"{name} {command.get('description') or ''}".lower()
            if not query_lower or query_lower in haystack:
                matches.append({"type": "command", "suite": suite_name, "name": name, "description": command.get("description")})
        for cls in suite.get("classes", []):
            name = str(cls.get("name") or "")
            haystack = f"{name} {cls.get('description') or ''}".lower()
            if not query_lower or query_lower in haystack:
                matches.append({"type": "class", "suite": suite_name, "name": name, "description": cls.get("description")})
            for prop in cls.get("properties", []):
                prop_name = str(prop.get("name") or "")
                prop_haystack = f"{prop_name} {prop.get('description') or ''}".lower()
                if not query_lower or query_lower in prop_haystack:
                    matches.append({
                        "type": "property",
                        "suite": suite_name,
                        "class": name,
                        "name": prop_name,
                        "value_type": prop.get("type"),
                        "description": prop.get("description"),
                    })
    return {"ok": True, "app": payload["app"], "query": query, "matches": matches, "count": len(matches)}


def parse_source_options(args: list[str], *, allow_target: bool = False) -> dict[str, Any]:
    language = "applescript"
    source_mode = None
    source_value = None
    target = None
    # No wrapper deadline unless the caller asks: a long whose-query is legitimate,
    # and the script's own `with timeout` already governs each AppleEvent reply.
    timeout = None
    launch = False
    refresh = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--language" and i + 1 < len(args):
            language = args[i + 1]
            i += 2
        elif arg == "--file" and i + 1 < len(args):
            source_mode = "file"
            source_value = args[i + 1]
            i += 2
        elif arg == "--stdin":
            source_mode = "stdin"
            i += 1
        elif arg == "--script" and i + 1 < len(args):
            source_mode = "script"
            source_value = args[i + 1]
            i += 2
        elif allow_target and arg == "--target" and i + 1 < len(args):
            target = args[i + 1]
            i += 2
        elif arg == "--timeout" and i + 1 < len(args):
            timeout = float(args[i + 1])
            i += 2
        elif arg == "--launch":
            launch = True
            i += 1
        elif arg == "--no-launch":
            launch = False
            i += 1
        elif arg == "--refresh":
            refresh = True
            i += 1
        elif arg == "--json":
            i += 1
        else:
            raise ToolError(f"Unknown option: {arg}", EXIT_USAGE)

    if source_mode == "file":
        path = Path(str(source_value)).expanduser()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"Could not read script file: {path}", EXIT_USAGE, detail=str(exc)) from exc
        source_label = str(path)
    elif source_mode == "stdin":
        source = sys.stdin.read()
        source_label = "stdin"
    elif source_mode == "script":
        source = str(source_value or "")
        source_label = "inline"
    else:
        raise ToolError("Script source is required: use --file, --stdin, or --script", EXIT_USAGE)

    return {
        "language": language,
        "source": source,
        "source_label": source_label,
        "target": target,
        "timeout": timeout,
        "launch": launch,
        "refresh": refresh,
    }


def script_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def write_temp_source(source: str, language: str) -> Path:
    suffix = ".js" if language == "javascript" else ".applescript"
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=suffix, delete=False)
    with handle:
        handle.write(source)
    return Path(handle.name)


def compile_source(source: str, language: str, *, timeout: float | None = 15.0) -> dict[str, Any]:
    _normalized, osalang = normalize_language(language)
    if not shutil.which("osacompile"):
        raise ToolError("osacompile is not available on this host", EXIT_UNSUPPORTED)
    source_path = write_temp_source(source, _normalized)
    compiled_path = Path(tempfile.mktemp(suffix=".scpt"))
    try:
        proc, elapsed = run_command(
            ["osacompile", "-l", osalang, "-o", str(compiled_path), str(source_path)],
            timeout=timeout,
        )
        assert proc is not None
        return {
            "ok": proc.returncode == 0,
            "language": _normalized,
            "script_sha256": script_hash(source),
            "compiled": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "duration_ms": elapsed,
        }
    finally:
        source_path.unlink(missing_ok=True)
        compiled_path.unlink(missing_ok=True)


def is_app_running(meta: dict[str, Any]) -> bool:
    executable = meta.get("executable")
    if executable and shutil.which("pgrep"):
        proc, _elapsed = run_command(["pgrep", "-x", str(executable)], timeout=3.0)
        if proc and proc.returncode == 0:
            return True
    return False


def extract_osstatus(stderr: str) -> int | None:
    matches = re.findall(r"\((-?\d{3,5})\)", stderr or "")
    if not matches:
        matches = re.findall(r"\b(-1[0-9]{3}|-[0-9]{3,5})\b", stderr or "")
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def classify_appleevent_result(returncode: int, stderr: str) -> dict[str, Any]:
    if returncode == 0:
        return {"automation": "allowed", "osstatus": None, "name": None, "message": "AppleEvent completed"}
    status = extract_osstatus(stderr)
    mapped = STATUS_MAP.get(status)
    if mapped:
        return {
            "automation": mapped["state"],
            "osstatus": status,
            "name": mapped["name"],
            "message": mapped["message"],
        }
    return {
        "automation": "unknown_error",
        "osstatus": status,
        "name": None,
        "message": "AppleEvent failed with an unclassified error",
    }


def wrap_applescript_for_target(source: str, meta: dict[str, Any]) -> str:
    bundle_id = meta.get("bundle_id")
    app_ref = f'application id "{bundle_id}"' if bundle_id else f'application "{meta["name"]}"'
    return f"tell {app_ref}\n{source}\nend tell\n"


def wrap_jxa_for_target(source: str, meta: dict[str, Any]) -> str:
    bundle_id = meta.get("bundle_id") or meta.get("name")
    escaped = str(bundle_id).replace("\\", "\\\\").replace('"', '\\"')
    return f'const app = Application("{escaped}");\n{source}\n'


def maybe_wrap_for_target(source: str, language: str, meta: dict[str, Any], *, wrap_target: bool) -> str:
    if not wrap_target:
        return source
    if language == "javascript":
        return wrap_jxa_for_target(source, meta)
    return wrap_applescript_for_target(source, meta)


def execute_script(
    *,
    source: str,
    language: str,
    target: str | None,
    launch: bool,
    timeout: float | None,
    wrap_target: bool = False,
) -> dict[str, Any]:
    normalized, osalang = normalize_language(language)
    target_meta = resolve_app(target) if target else None
    if target_meta and not launch and not is_app_running(target_meta):
        return {
            "ok": False,
            "target": target_meta,
            "language": normalized,
            "launch_policy": "no-launch",
            "sent_event": False,
            "automation": "not_running",
            "osstatus": -600,
            "stderr": "",
            "exit_code": -600,
            "message": "Target app is not running and --no-launch is active",
        }

    execution_source = maybe_wrap_for_target(
        source,
        normalized,
        target_meta,
        wrap_target=bool(target_meta and wrap_target),
    )
    compile_result = compile_source(execution_source, normalized, timeout=timeout)
    if not compile_result["compiled"]:
        return {
            "ok": False,
            "target": target_meta,
            "language": normalized,
            "script_sha256": script_hash(execution_source),
            "compiled": False,
            "ran": False,
            "stdout": compile_result.get("stdout", ""),
            "stderr": compile_result.get("stderr", ""),
            "exit_code": compile_result.get("exit_code"),
            "duration_ms": compile_result.get("duration_ms"),
        }

    if not shutil.which("osascript"):
        raise ToolError("osascript is not available on this host", EXIT_UNSUPPORTED)

    source_path = write_temp_source(execution_source, normalized)
    try:
        proc, elapsed = run_command(["osascript", "-l", osalang, str(source_path)], timeout=timeout)
        assert proc is not None
        if isinstance(proc, TimedOutProcess):
            classification = {
                "automation": "timed_out",
                "osstatus": None,
                "name": None,
                "message": f"Script outran --timeout {timeout:g}s; the wrapper stopped osascript",
            }
        else:
            classification = classify_appleevent_result(proc.returncode, proc.stderr)
        return {
            "ok": proc.returncode == 0,
            "target": target_meta,
            "language": normalized,
            "script_sha256": script_hash(execution_source),
            "compiled": True,
            "ran": True,
            "sent_event": True,
            "launch_policy": "launch" if launch else "no-launch",
            "target_wrapped": bool(target_meta and wrap_target),
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "duration_ms": elapsed,
            "timeout_s": timeout,
            **classification,
        }
    finally:
        source_path.unlink(missing_ok=True)


def run_exit_code(result: dict[str, Any]) -> int:
    if result.get("ok"):
        return EXIT_SUCCESS
    if result.get("automation") == "timed_out":
        return EXIT_TIMEOUT
    return EXIT_RUN_FAILED


def permission_probe(app: str, *, launch: bool = False, timeout: float = 10.0) -> dict[str, Any]:
    meta = resolve_app(app)
    if not launch and not is_app_running(meta):
        return {
            "ok": False,
            "target": meta,
            "probe_event": "get name",
            "launch_policy": "no-launch",
            "sent_event": False,
            "automation": "not_running",
            "osstatus": -600,
            "stderr": "",
            "duration_ms": 0,
            "message": "Target app is not running and --no-launch is active",
        }
    result = execute_script(
        source="get name",
        language="applescript",
        target=app,
        launch=launch,
        timeout=timeout,
        wrap_target=True,
    )
    return {
        "ok": result.get("ok", False),
        "target": meta,
        "probe_event": "get name",
        "launch_policy": "launch" if launch else "no-launch",
        "sent_event": bool(result.get("sent_event")),
        "automation": result.get("automation"),
        "osstatus": result.get("osstatus"),
        "name": result.get("name"),
        "message": result.get("message"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "duration_ms": result.get("duration_ms", 0),
    }


def parse_simple_options(args: list[str]) -> dict[str, Any]:
    options: dict[str, Any] = {"timeout": 20.0, "refresh": False, "format": "json", "launch": False}
    rest: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--timeout" and i + 1 < len(args):
            options["timeout"] = float(args[i + 1])
            i += 2
        elif arg == "--refresh":
            options["refresh"] = True
            i += 1
        elif arg == "--format" and i + 1 < len(args):
            options["format"] = args[i + 1]
            i += 2
        elif arg == "--launch":
            options["launch"] = True
            i += 1
        elif arg == "--no-launch":
            options["launch"] = False
            i += 1
        elif arg == "--json":
            i += 1
        else:
            rest.append(arg)
            i += 1
    options["args"] = rest
    return options


def cache_status() -> dict[str, Any]:
    files = sorted(CACHE_DIR.glob("*")) if CACHE_DIR.exists() else []
    return {
        "ok": True,
        "cache_dir": str(CACHE_DIR),
        "files": [str(path) for path in files],
        "count": len(files),
    }


def cache_clear(app: str | None = None) -> dict[str, Any]:
    removed: list[str] = []
    if app:
        meta = resolve_app(app)
        paths = list(cache_files(meta))
    else:
        paths = sorted(CACHE_DIR.glob("*")) if CACHE_DIR.exists() else []
    for path in paths:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    return {"ok": True, "removed": removed, "count": len(removed)}


def enforce_live(cmd: str, args: list[str]) -> None:
    app = None
    if cmd == "permissions" and len(args) > 1:
        app = args[1]
    elif cmd == "tell" and len(args) > 1:
        app = args[1]
    elif cmd == "run":
        for i, arg in enumerate(args):
            if arg == "--target" and i + 1 < len(args):
                app = args[i + 1]
                break
    require_live_control(scope="desktop", tool="appleevents", argv=args, app=app, reason=f"appleevents:{cmd}")


def handle_command(raw_args: list[str]) -> None:
    args = list(raw_args)
    if not args:
        raise ToolError("No command specified", EXIT_USAGE)
    cmd = args[0].lower()

    if cmd in {"permissions", "run", "tell"}:
        enforce_live(cmd, args)

    require_macos()

    if cmd == "apps":
        emit(list_apps())
    if cmd == "probe":
        options = parse_simple_options(args[1:])
        rest = options["args"]
        if not rest:
            raise ToolError("Usage: agent-appleevents probe <app-or-bundle-id>", EXIT_USAGE)
        emit(probe(rest[0], refresh=options["refresh"], timeout=options["timeout"]))
    if cmd == "dictionary":
        options = parse_simple_options(args[1:])
        rest = options["args"]
        if not rest:
            raise ToolError("Usage: agent-appleevents dictionary <app> [--format json|markdown|raw]", EXIT_USAGE)
        fmt = str(options["format"]).lower()
        payload = dictionary_payload(rest[0], refresh=options["refresh"], timeout=options["timeout"])
        if fmt == "json":
            emit(payload, EXIT_SUCCESS if payload.get("ok") else EXIT_ERROR)
        if fmt == "markdown":
            if not payload.get("ok"):
                emit(payload, EXIT_ERROR)
            print(render_dictionary_markdown(payload), end="")
            raise SystemExit(EXIT_SUCCESS)
        if fmt == "raw":
            meta = resolve_app(rest[0])
            result = sdef_for_app(meta, refresh=options["refresh"], timeout=options["timeout"])
            if not result.get("ok"):
                emit(result, EXIT_ERROR)
            print(result["xml"], end="")
            raise SystemExit(EXIT_SUCCESS)
        raise ToolError(f"Unsupported dictionary format: {fmt}", EXIT_USAGE)
    if cmd == "terms":
        options = parse_simple_options(args[1:])
        rest = options["args"]
        if not rest:
            raise ToolError("Usage: agent-appleevents terms <app> [query]", EXIT_USAGE)
        query = " ".join(rest[1:]) if len(rest) > 1 else None
        emit(terms(rest[0], query, refresh=options["refresh"], timeout=options["timeout"]))
    if cmd == "compile":
        source_opts = parse_source_options(args[1:], allow_target=False)
        result = compile_source(source_opts["source"], source_opts["language"], timeout=source_opts["timeout"])
        result["ok"] = bool(result["compiled"])
        result["source"] = source_opts["source_label"]
        emit(result, EXIT_SUCCESS if result["compiled"] else EXIT_COMPILE_FAILED)
    if cmd == "permissions":
        options = parse_simple_options(args[1:])
        rest = options["args"]
        if not rest:
            raise ToolError("Usage: agent-appleevents permissions <app> [--launch|--no-launch]", EXIT_USAGE)
        result = permission_probe(rest[0], launch=options["launch"], timeout=options["timeout"])
        emit(result, EXIT_SUCCESS if result.get("automation") in {"allowed", "not_running"} else EXIT_RUN_FAILED)
    if cmd == "run":
        source_opts = parse_source_options(args[1:], allow_target=True)
        result = execute_script(
            source=source_opts["source"],
            language=source_opts["language"],
            target=source_opts["target"],
            launch=source_opts["launch"],
            timeout=source_opts["timeout"],
            wrap_target=False,
        )
        result["source"] = source_opts["source_label"]
        emit(result, run_exit_code(result))
    if cmd == "tell":
        if len(args) < 2:
            raise ToolError("Usage: agent-appleevents tell <app> --script <script>", EXIT_USAGE)
        app = args[1]
        source_opts = parse_source_options(args[2:], allow_target=False)
        result = execute_script(
            source=source_opts["source"],
            language=source_opts["language"],
            target=app,
            launch=source_opts["launch"],
            timeout=source_opts["timeout"],
            wrap_target=True,
        )
        result["source"] = source_opts["source_label"]
        emit(result, run_exit_code(result))
    if cmd == "cache":
        if len(args) < 2:
            raise ToolError("Usage: agent-appleevents cache <status|clear> [app]", EXIT_USAGE)
        sub = args[1].lower()
        if sub == "status":
            emit(cache_status())
        if sub == "clear":
            app = args[2] if len(args) > 2 else None
            emit(cache_clear(app))
        raise ToolError(f"Unknown cache command: {sub}", EXIT_USAGE)
    raise ToolError(f"Unknown command: {cmd}", EXIT_USAGE)


def main() -> None:
    try:
        handle_command(sys.argv[1:])
    except LiveApprovalRequiredError as exc:
        payload = {"ok": False, "error": str(exc)}
        payload.update(exc.payload())
        emit(payload, EXIT_ERROR)
    except ToolError as exc:
        fail(exc.message, exc.exit_code, **exc.details)
    except ET.ParseError as exc:
        fail("Could not parse scripting dictionary", EXIT_ERROR, detail=str(exc))
    except KeyboardInterrupt:
        fail("Interrupted", EXIT_ERROR)


if __name__ == "__main__":
    main()
