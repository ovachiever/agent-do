#!/usr/bin/env python3
"""Local-vault engine for agent-obsidian v2.

The bash wrapper remains the public tool surface and obsidian-cli fallback.
This module handles commands that can operate directly on an Obsidian vault on
disk: indexing, structured reads/searches, saves, tasks, graph, audit, and
journaled multi-file rewrites.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
    from ai_router import call_json_model  # type: ignore
except Exception:  # pragma: no cover
    call_json_model = None


NO_LOCAL_VAULT = 3
NEEDS_CLARIFICATION = 2
AGENT_DIR = ".agent-do"
OBSIDIAN_DIR = ".obsidian"
NOTE_SUFFIX = ".md"
EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".obsidian",
    ".trash",
    ".agent-do",
    "node_modules",
}


MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "synthesis": {
        "provider": "openai",
        "model": "gpt-5.5",
        "env": "OPENAI_API_KEY",
        "reasoning_effort": "high",
        "source": "https://developers.openai.com/api/docs/guides/latest-model",
        "reason": "current OpenAI latest-model guidance for complex grounded assistants",
    },
    "embedding": {
        "provider": "voyage",
        "model": "voyage-4-large",
        "env": "VOYAGE_API_KEY",
        "dimension": 1024,
        "max_input_tokens": 32000,
        "max_batch_items": 1000,
        "max_batch_tokens": 120000,
        "max_batch_chars": 120000,
        "source": "https://docs.voyageai.com/docs/embeddings",
        "reason": "best general-purpose and multilingual retrieval quality in Voyage 4 family",
    },
    "embedding_fallback": {
        "provider": "openai",
        "model": "text-embedding-3-large",
        "env": "OPENAI_API_KEY",
        "dimension": 3072,
        "max_input_tokens": 8192,
        "source": "https://developers.openai.com/api/docs/guides/embeddings",
        "reason": "OpenAI high-quality fallback embedding model",
    },
    "reranker": {
        "provider": "voyage",
        "model": "rerank-2.5",
        "env": "VOYAGE_API_KEY",
        "max_query_tokens": 8000,
        "max_document_tokens": 32000,
        "max_documents": 1000,
        "source": "https://docs.voyageai.com/docs/reranker",
        "reason": "Voyage generalist reranker optimized for quality",
    },
    "multimodal_embedding": {
        "provider": "cohere",
        "model": "embed-v4.0",
        "env": "COHERE_API_KEY",
        "dimension": 1024,
        "source": "https://docs.cohere.com/docs/embeddings",
        "reason": "content-rich image and text embedding path for future multimodal vault assets",
    },
}


class AgentObsidianError(Exception):
    def __init__(self, message: str, code: int = 1, **payload: Any) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.payload = payload


@dataclasses.dataclass
class Runtime:
    vault: Path
    json_mode: bool
    repo_root: Path

    @property
    def agent_root(self) -> Path:
        return self.vault / AGENT_DIR

    @property
    def obsidian_root(self) -> Path:
        return self.agent_root / "obsidian"

    @property
    def db_path(self) -> Path:
        return self.obsidian_root / "index.db"

    @property
    def lock_path(self) -> Path:
        return self.obsidian_root / ".write-lock"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return dt.date.today().isoformat()


def json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False)


def emit(data: Any, json_mode: bool = True) -> None:
    if json_mode:
        print(json_dump(data))
    elif isinstance(data, str):
        print(data)
    else:
        print(json_dump(data))


def fail(message: str, *, code: int = 1, json_mode: bool = False, **payload: Any) -> int:
    body = {"success": False, "error": message, "code": code, **payload}
    if json_mode:
        print(json_dump(body))
    else:
        print(f"Error: {message}", file=sys.stderr)
    return code


def resolve_vault(vault_arg: str | None) -> Path | None:
    env_path = os.environ.get("AGENT_OBSIDIAN_VAULT_PATH") or os.environ.get("AGENT_OBSIDIAN_VAULT")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())
    if vault_arg:
        expanded = Path(vault_arg).expanduser()
        if expanded.exists() or "/" in vault_arg or vault_arg.startswith(".") or vault_arg.startswith("~"):
            candidates.append(expanded)

    cwd = Path.cwd()
    candidates.append(cwd)
    candidates.extend(cwd.parents)

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_dir():
            continue
        if (resolved / OBSIDIAN_DIR).is_dir() or (resolved / AGENT_DIR / "conventions.yaml").exists():
            return resolved
    return None


def ensure_storage(rt: Runtime) -> None:
    rt.obsidian_root.mkdir(parents=True, exist_ok=True)
    (rt.obsidian_root / "operations" / "journals").mkdir(parents=True, exist_ok=True)
    (rt.obsidian_root / "operations" / "backups").mkdir(parents=True, exist_ok=True)
    (rt.obsidian_root / "templates").mkdir(parents=True, exist_ok=True)
    (rt.obsidian_root / "chat").mkdir(parents=True, exist_ok=True)
    gitignore = rt.agent_root / ".gitignore"
    wanted = [
        "obsidian/index.db",
        "obsidian/index.db-*",
        "obsidian/embeddings.db",
        "obsidian/embeddings.db-*",
        "obsidian/.write-lock",
        "obsidian/chat/",
        "obsidian/operations/",
        "obsidian/relate-validation.jsonl",
    ]
    existing = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    changed = False
    for line in wanted:
        if line not in existing:
            existing.append(line)
            changed = True
    if changed:
        gitignore.write_text("\n".join(existing).rstrip() + "\n", encoding="utf-8")


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    # Small fallback: enough for the defaults this tool writes.
    result: dict[str, Any] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def default_conventions() -> dict[str, Any]:
    return {
        "inbox_folder": "+",
        "default_frontmatter": {
            "up": "",
            "related": [],
            "created": "{today}",
            "log": "[[{today}]]",
            "tags": [],
            "scope": "local",
        },
        "folders": {
            "inbox": "+",
            "projects": "Projects",
            "daily": "Daily",
            "weekly": "Weekly",
            "tasks": "Tasks",
            "archive": "Archive",
        },
        "task_default_style": "frontmatter",
        "task_next_weights": {
            "priority_weight": 0.35,
            "due_proximity_weight": 0.30,
            "resonance_weight": 0.20,
            "project_focus_weight": 0.15,
        },
        "related_find": {
            "default_limit": 5,
            "scope": "inbox",
            "score_weights": {
                "title_similarity": 0.4,
                "tag_overlap": 0.3,
                "folder_proximity": 0.15,
                "link_graph": 0.15,
            },
            "validation_corpus": ".agent-do/obsidian/relate-validation.jsonl",
        },
        "models": MODEL_REGISTRY,
        "save": {
            "default_folder_token": "inbox",
            "auto_related": True,
            "auto_related_limit": 5,
        },
    }


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_conventions(rt: Runtime) -> dict[str, Any]:
    home_default = Path(os.environ.get("AGENT_DO_HOME", Path.home() / ".agent-do")) / "obsidian" / "conventions.yaml"
    vault_default = rt.agent_root / "conventions.yaml"
    cfg = default_conventions()
    cfg = deep_merge(cfg, load_yaml_file(home_default))
    cfg = deep_merge(cfg, load_yaml_file(vault_default))
    return cfg


def model_registry(rt: Runtime) -> dict[str, dict[str, Any]]:
    cfg = load_conventions(rt)
    configured = cfg.get("models") or {}
    registry = deep_merge(MODEL_REGISTRY, configured if isinstance(configured, dict) else {})
    embedding = dict(registry.get("embedding") or {})
    if os.environ.get("AGENT_OBSIDIAN_EMBED_PROVIDER"):
        embedding["provider"] = os.environ["AGENT_OBSIDIAN_EMBED_PROVIDER"]
    if os.environ.get("AGENT_OBSIDIAN_EMBED_MODEL"):
        embedding["model"] = os.environ["AGENT_OBSIDIAN_EMBED_MODEL"]
    if os.environ.get("AGENT_OBSIDIAN_EMBED_DIMENSION"):
        with contextlib.suppress(ValueError):
            embedding["dimension"] = int(os.environ["AGENT_OBSIDIAN_EMBED_DIMENSION"])
    registry["embedding"] = embedding

    synthesis = dict(registry.get("synthesis") or {})
    if os.environ.get("AGENT_OBSIDIAN_SYNTHESIS_MODEL"):
        synthesis["model"] = os.environ["AGENT_OBSIDIAN_SYNTHESIS_MODEL"]
    registry["synthesis"] = synthesis

    reranker = dict(registry.get("reranker") or {})
    if os.environ.get("AGENT_OBSIDIAN_RERANK_MODEL"):
        reranker["model"] = os.environ["AGENT_OBSIDIAN_RERANK_MODEL"]
    registry["reranker"] = reranker
    return registry


def model_profile(rt: Runtime, role: str) -> dict[str, Any]:
    registry = model_registry(rt)
    if role not in registry:
        raise AgentObsidianError(f"unknown model role: {role}", code=NEEDS_CLARIFICATION)
    return dict(registry[role])


def credential_status(profile: dict[str, Any]) -> dict[str, Any]:
    env_name = str(profile.get("env") or "")
    return {
        "env": env_name,
        "available": bool(env_name and os.environ.get(env_name)),
    }


def credential_contract(rt: Runtime) -> dict[str, Any]:
    registry = model_registry(rt)
    keys: dict[str, dict[str, Any]] = {}
    for role, profile in registry.items():
        if not isinstance(profile, dict):
            continue
        env_name = str(profile.get("env") or "")
        if not env_name:
            continue
        entry = keys.setdefault(
            env_name,
            {
                "present": bool(os.environ.get(env_name)),
                "source": "env" if os.environ.get(env_name) else "missing",
                "roles": [],
                "models": [],
            },
        )
        entry["roles"].append(role)
        model = profile.get("model")
        if model and model not in entry["models"]:
            entry["models"].append(model)
    return keys


def feature_readiness(rt: Runtime) -> dict[str, Any]:
    primary = model_profile(rt, "embedding")
    fallback = model_profile(rt, "embedding_fallback")
    synthesis = model_profile(rt, "synthesis")
    multimodal = model_profile(rt, "multimodal_embedding")
    primary_count = embedding_current_count(rt, primary)
    fallback_count = embedding_current_count(rt, fallback)
    return {
        "read_save_keyword_index": {"ready": True, "requires": []},
        "semantic_search": {
            "ready": primary_count > 0 or fallback_count > 0 or credential_status(primary)["available"] or credential_status(fallback)["available"],
            "requires_any": [str(primary.get("env")), str(fallback.get("env"))],
            "current_embeddings": primary_count or fallback_count,
        },
        "vault_chat": {
            "ready": credential_status(synthesis)["available"],
            "requires": [str(synthesis.get("env"))],
            "model": synthesis.get("model"),
        },
        "multimodal_assets": {
            "ready": credential_status(multimodal)["available"],
            "requires": [str(multimodal.get("env"))],
            "model": multimodal.get("model"),
        },
    }


def require_api_key(profile: dict[str, Any]) -> str:
    env_name = str(profile.get("env") or "")
    value = os.environ.get(env_name) if env_name else ""
    if not value:
        raise AgentObsidianError(
            f"missing required credential: {env_name}",
            code=NEEDS_CLARIFICATION,
            provider=profile.get("provider"),
            model=profile.get("model"),
            env=env_name,
        )
    return value


def dump_frontmatter(data: dict[str, Any]) -> str:
    clean = {k: v for k, v in data.items() if v not in (None, "", [], {})}
    if yaml is not None:
        return yaml.safe_dump(clean, sort_keys=False, allow_unicode=True).strip()
    lines: list[str] = []
    for key, value in clean.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    if yaml is not None:
        try:
            data = yaml.safe_load(raw) or {}
            if isinstance(data, dict):
                return data, body
        except Exception:
            return {}, body
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            data.setdefault(current_key, []).append(line[4:].strip())
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            data[current_key] = [] if value == "" else value.strip('"').strip("'")
    return data, body


def render_note(frontmatter: dict[str, Any], body: str) -> str:
    fm = dump_frontmatter(frontmatter)
    if fm:
        return f"---\n{fm}\n---\n\n{body.rstrip()}\n"
    return body.rstrip() + "\n"


def relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def scan_diagnostics() -> dict[str, Any]:
    return {
        "directories_seen": 0,
        "files_seen": 0,
        "markdown_files": 0,
        "non_markdown_files": 0,
        "excluded_dirs": [],
        "walk_errors": [],
    }


def walk_error_payload(exc: OSError) -> dict[str, Any]:
    return {
        "path": str(getattr(exc, "filename", "") or ""),
        "error": str(exc),
        "errno": getattr(exc, "errno", None),
        "type": exc.__class__.__name__,
    }


def permission_recommendation() -> str:
    return (
        "grant this terminal/agent process Files and Folders or Full Disk Access "
        "for the vault path, or move the vault to a readable location"
    )


def raise_walk_errors(vault: Path, diagnostics: dict[str, Any]) -> None:
    errors = diagnostics.get("walk_errors") or []
    if not errors:
        return
    raise AgentObsidianError(
        "vault scan failed",
        code=1,
        vault=str(vault),
        walk_errors=errors,
        recommendation=permission_recommendation(),
    )


def vault_access_error(vault: Path) -> dict[str, Any] | None:
    try:
        if not vault.exists():
            return {
                "path": str(vault),
                "error": "vault path does not exist",
                "errno": None,
                "type": "FileNotFoundError",
            }
        if not vault.is_dir():
            return {
                "path": str(vault),
                "error": "vault path is not a directory",
                "errno": None,
                "type": "NotADirectoryError",
            }
        if not os.access(vault, os.R_OK):
            return {
                "path": str(vault),
                "error": "vault path is not readable",
                "errno": None,
                "type": "PermissionError",
            }
        return None
    except OSError as exc:
        return walk_error_payload(exc)


def note_files(vault: Path, diagnostics: dict[str, Any] | None = None) -> Iterable[Path]:
    def onerror(exc: OSError) -> None:
        payload = walk_error_payload(exc)
        if diagnostics is not None:
            diagnostics.setdefault("walk_errors", []).append(payload)
            return
        raise AgentObsidianError(
            "vault scan failed",
            code=1,
            vault=str(vault),
            walk_errors=[payload],
            recommendation=permission_recommendation(),
        )

    for root, dirs, files in os.walk(vault, onerror=onerror):
        root_path = Path(root)
        if diagnostics is not None:
            diagnostics["directories_seen"] += 1
            diagnostics["files_seen"] += len(files)
        kept_dirs = []
        for dirname in dirs:
            if dirname in EXCLUDED_DIRS or dirname.startswith("."):
                if diagnostics is not None:
                    diagnostics["excluded_dirs"].append(relpath(root_path / dirname, vault))
                continue
            kept_dirs.append(dirname)
        dirs[:] = kept_dirs
        for name in files:
            if name.endswith(NOTE_SUFFIX):
                if diagnostics is not None:
                    diagnostics["markdown_files"] += 1
                yield root_path / name
            elif diagnostics is not None:
                diagnostics["non_markdown_files"] += 1


def stat_payload(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"path": path, "mtime_ns": st.st_mtime_ns, "mtime": st.st_mtime, "size": st.st_size}


def extract_title(path: Path, frontmatter: dict[str, Any], body: str) -> str:
    title = frontmatter.get("title")
    if title:
        return str(title)
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or path.stem
    return path.stem


TAG_RE = re.compile(r"(?<![\w/])#([A-Za-z0-9_/-]+)")
LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TASK_RE = re.compile(r"^\s*[-*]\s+\[(?P<status>[ xX])\]\s+(?P<text>.+?)\s*$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def normalize_tags(value: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            raw_items = [item.strip() for item in stripped[1:-1].split(",")]
        else:
            raw_items = re.split(r"[,\s]+", value)
    else:
        raw_items = []
    for item in raw_items:
        tag = str(item).strip().strip("[]").strip().lstrip("#")
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def extract_tags(frontmatter: dict[str, Any], body: str) -> list[str]:
    tags = normalize_tags(frontmatter.get("tags"))
    for match in TAG_RE.finditer(body):
        tag = match.group(1).strip("/")
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def extract_links(body: str) -> list[str]:
    links: list[str] = []
    for match in LINK_RE.finditer(body):
        target = match.group(1).strip()
        if target and target not in links:
            links.append(target)
    return links


def task_id(path: str, line_no: int, text: str) -> str:
    return hashlib.sha1(f"{path}:{line_no}:{text}".encode("utf-8")).hexdigest()[:16]


def parse_inline_task_metadata(text: str) -> dict[str, Any]:
    priority = ""
    if "⏫" in text:
        priority = "highest"
    elif "🔼" in text:
        priority = "high"
    elif "🔽" in text:
        priority = "medium"
    elif "⏬" in text:
        priority = "low"
    due = ""
    scheduled = ""
    for marker, key in (("📅", "due"), ("⏳", "scheduled")):
        idx = text.find(marker)
        if idx >= 0:
            m = DATE_RE.search(text[idx:])
            if m:
                if key == "due":
                    due = m.group(0)
                else:
                    scheduled = m.group(0)
    return {"priority": priority, "due": due, "scheduled": scheduled}


def extract_tasks(path: str, frontmatter: dict[str, Any], body: str, tags: list[str]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    if str(frontmatter.get("type", "")).lower() == "task":
        text = str(frontmatter.get("text") or frontmatter.get("title") or Path(path).stem)
        tasks.append(
            {
                "id": task_id(path, 0, text),
                "text": text,
                "status": str(frontmatter.get("status") or "open"),
                "priority": str(frontmatter.get("priority") or ""),
                "due": str(frontmatter.get("due") or ""),
                "scheduled": str(frontmatter.get("scheduled") or ""),
                "project": str(frontmatter.get("project") or ""),
                "resonance": int(frontmatter.get("resonance") or 0),
                "tags": tags,
                "source_note": path,
                "source_line": 0,
                "style": "frontmatter",
            }
        )
    for idx, line in enumerate(body.splitlines(), start=1):
        match = TASK_RE.match(line)
        if not match:
            continue
        text = match.group("text").strip()
        meta = parse_inline_task_metadata(text)
        tasks.append(
            {
                "id": task_id(path, idx, text),
                "text": text,
                "status": "done" if match.group("status").lower() == "x" else "open",
                "priority": meta["priority"],
                "due": meta["due"],
                "scheduled": meta["scheduled"],
                "project": str(frontmatter.get("project") or ""),
                "resonance": int(frontmatter.get("resonance") or 0),
                "tags": tags,
                "source_note": path,
                "source_line": idx,
                "style": "inline",
            }
        )
    return tasks


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS notes (
          path TEXT PRIMARY KEY,
          title TEXT,
          folder TEXT,
          mtime_ns INTEGER,
          size INTEGER,
          frontmatter_json TEXT,
          body_excerpt TEXT,
          body TEXT,
          scope TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
          path UNINDEXED,
          title,
          body
        );
        CREATE TABLE IF NOT EXISTS tags (
          tag TEXT,
          note_path TEXT,
          PRIMARY KEY (tag, note_path)
        );
        CREATE TABLE IF NOT EXISTS links (
          src_path TEXT,
          target_name TEXT,
          resolved_path TEXT,
          PRIMARY KEY (src_path, target_name)
        );
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY,
          text TEXT,
          status TEXT,
          priority TEXT,
          due TEXT,
          scheduled TEXT,
          project TEXT,
          resonance INTEGER,
          tags_json TEXT,
          source_note TEXT,
          source_line INTEGER,
          style TEXT
        );
        CREATE TABLE IF NOT EXISTS chunks (
          chunk_id TEXT PRIMARY KEY,
          note_path TEXT,
          ordinal INTEGER,
          title TEXT,
          heading_path TEXT,
          start_line INTEGER,
          end_line INTEGER,
          text TEXT,
          content_hash TEXT,
          token_estimate INTEGER,
          mtime_ns INTEGER
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
          chunk_id UNINDEXED,
          note_path UNINDEXED,
          title,
          heading_path,
          text
        );
        CREATE TABLE IF NOT EXISTS embeddings (
          chunk_id TEXT,
          provider TEXT,
          model TEXT,
          dimension INTEGER,
          content_hash TEXT,
          embedding_json TEXT,
          embedded_at TEXT,
          PRIMARY KEY (chunk_id, provider, model, dimension)
        );
        CREATE TABLE IF NOT EXISTS retrieval_feedback (
          id TEXT PRIMARY KEY,
          created_at TEXT,
          query TEXT,
          chunk_id TEXT,
          signal TEXT,
          payload_json TEXT
        );
        CREATE TABLE IF NOT EXISTS state (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        CREATE INDEX IF NOT EXISTS notes_mtime ON notes (mtime_ns);
        CREATE INDEX IF NOT EXISTS notes_folder ON notes (folder);
        CREATE INDEX IF NOT EXISTS notes_scope ON notes (scope);
        CREATE INDEX IF NOT EXISTS tags_tag ON tags (tag);
        CREATE INDEX IF NOT EXISTS links_target ON links (target_name);
        CREATE INDEX IF NOT EXISTS tasks_status ON tasks (status);
        CREATE INDEX IF NOT EXISTS tasks_due ON tasks (due);
        CREATE INDEX IF NOT EXISTS tasks_project ON tasks (project);
        CREATE INDEX IF NOT EXISTS chunks_note ON chunks (note_path);
        CREATE INDEX IF NOT EXISTS chunks_hash ON chunks (content_hash);
        CREATE INDEX IF NOT EXISTS embeddings_model ON embeddings (provider, model, dimension);
        """
    )


def connect(rt: Runtime) -> sqlite3.Connection:
    ensure_storage(rt)
    conn = sqlite3.connect(rt.db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def note_name_maps_from_paths(paths: Iterable[Path], vault: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for path in paths:
        rp = relpath(path, vault)
        stem = path.stem
        mapping.setdefault(stem.lower(), rp)
        mapping.setdefault(rp.lower(), rp)
        mapping.setdefault(rp[:-3].lower(), rp)
    return mapping


def note_name_maps(vault: Path) -> dict[str, str]:
    return note_name_maps_from_paths(note_files(vault), vault)


def resolve_link(target: str, maps: dict[str, str]) -> str:
    key = target.strip().removesuffix(NOTE_SUFFIX).lower()
    return maps.get(key) or maps.get((target + NOTE_SUFFIX).lower()) or ""


def parse_note(path: Path, vault: Path, maps: dict[str, str] | None = None) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = parse_frontmatter(text)
    rp = relpath(path, vault)
    title = extract_title(path, frontmatter, body)
    tags = extract_tags(frontmatter, body)
    links = extract_links(body)
    maps = maps or note_name_maps(vault)
    resolved = [{"target": target, "resolved_path": resolve_link(target, maps)} for target in links]
    tasks = extract_tasks(rp, frontmatter, body, tags)
    st = path.stat()
    return {
        "path": rp,
        "absolute_path": str(path),
        "title": title,
        "folder": str(Path(rp).parent) if str(Path(rp).parent) != "." else "",
        "mtime_ns": st.st_mtime_ns,
        "mtime": st.st_mtime,
        "size": st.st_size,
        "frontmatter": frontmatter,
        "body": body,
        "body_excerpt": body[:500],
        "scope": str(frontmatter.get("scope") or "local"),
        "tags": tags,
        "links": resolved,
        "tasks": tasks,
    }


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    # This is only used to compare a section with provider-published context
    # limits before sending it to an embedding API. It is not a retrieval budget.
    return max(1, math.ceil(len(text) / 4))


def split_text_for_model(text: str, max_input_tokens: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    # The provider publishes a model token window but this tool intentionally
    # avoids a heavyweight tokenizer dependency. Use a conservative character
    # guard and prefer natural boundaries when a section is too large.
    char_limit = max(1, max_input_tokens)
    if len(text) <= char_limit and estimate_tokens(text) <= max_input_tokens:
        return [text]
    min_boundary = max(1, int(char_limit * 0.55))
    parts: list[str] = []
    start = 0
    length = len(text)
    boundary_markers = ["\n\n", "\n", ". ", "? ", "! ", " "]
    while start < length:
        end = min(length, start + char_limit)
        if end < length:
            window = text[start:end]
            boundary = -1
            marker_len = 0
            for marker in boundary_markers:
                pos = window.rfind(marker)
                if pos >= min_boundary and pos > boundary:
                    boundary = pos
                    marker_len = len(marker)
            if boundary >= 0:
                end = start + boundary + marker_len
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    return parts


def note_chunks(note: dict[str, Any], *, max_input_tokens: int = 32000) -> list[dict[str, Any]]:
    body = note.get("body") or ""
    title = note.get("title") or Path(note["path"]).stem
    lines = body.splitlines()
    chunks: list[dict[str, Any]] = []
    heading_stack: list[str] = [str(title)]
    current_lines: list[str] = []
    current_start = 1
    current_heading = " / ".join(heading_stack)

    def flush(end_line: int) -> None:
        nonlocal current_lines, current_start, current_heading
        text = "\n".join(current_lines).strip()
        if not text:
            current_lines = []
            return
        for part in split_text_for_model(text, max_input_tokens):
            ordinal = len(chunks)
            chunk_id = hashlib.sha1(f"{note['path']}:{ordinal}:{content_hash(part)}".encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "note_path": note["path"],
                    "ordinal": ordinal,
                    "title": title,
                    "heading_path": current_heading,
                    "start_line": current_start,
                    "end_line": end_line,
                    "text": part,
                    "content_hash": content_hash(part),
                    "token_estimate": estimate_tokens(part),
                    "mtime_ns": note["mtime_ns"],
                }
            )
        current_lines = []

    for idx, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if match:
            flush(idx - 1)
            level = len(match.group(1))
            label = match.group(2).strip()
            heading_stack = heading_stack[:level]
            while len(heading_stack) < level:
                heading_stack.append("")
            if len(heading_stack) == level:
                heading_stack.append(label)
            else:
                heading_stack[level] = label
            current_heading = " / ".join(part for part in heading_stack if part)
            current_start = idx
        elif not current_lines:
            current_start = idx
        current_lines.append(line)
    flush(len(lines))
    if not chunks and body.strip():
        part = body.strip()
        chunk_id = hashlib.sha1(f"{note['path']}:0:{content_hash(part)}".encode("utf-8")).hexdigest()
        chunks.append(
            {
                "chunk_id": chunk_id,
                "note_path": note["path"],
                "ordinal": 0,
                "title": title,
                "heading_path": str(title),
                "start_line": 1,
                "end_line": max(1, len(lines)),
                "text": part,
                "content_hash": content_hash(part),
                "token_estimate": estimate_tokens(part),
                "mtime_ns": note["mtime_ns"],
            }
        )
    return chunks


def delete_chunks_for_note(conn: sqlite3.Connection, path: str) -> None:
    chunk_ids = [r["chunk_id"] for r in conn.execute("SELECT chunk_id FROM chunks WHERE note_path=?", (path,))]
    for chunk_id in chunk_ids:
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
        conn.execute("DELETE FROM embeddings WHERE chunk_id=?", (chunk_id,))
    conn.execute("DELETE FROM chunks WHERE note_path=?", (path,))


def delete_index_rows(conn: sqlite3.Connection, path: str) -> None:
    delete_chunks_for_note(conn, path)
    conn.execute("DELETE FROM notes WHERE path = ?", (path,))
    conn.execute("DELETE FROM notes_fts WHERE path = ?", (path,))
    conn.execute("DELETE FROM tags WHERE note_path = ?", (path,))
    conn.execute("DELETE FROM links WHERE src_path = ?", (path,))
    conn.execute("DELETE FROM tasks WHERE source_note = ?", (path,))


def upsert_note(conn: sqlite3.Connection, note: dict[str, Any], *, delete_existing: bool = True) -> None:
    path = note["path"]
    if delete_existing:
        delete_index_rows(conn, path)
    conn.execute(
        """
        INSERT INTO notes(path,title,folder,mtime_ns,size,frontmatter_json,body_excerpt,body,scope)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (
            path,
            note["title"],
            note["folder"],
            note["mtime_ns"],
            note["size"],
            json.dumps(note["frontmatter"], ensure_ascii=False),
            note["body_excerpt"],
            note["body"],
            note["scope"],
        ),
    )
    conn.execute(
        "INSERT INTO notes_fts(path,title,body) VALUES(?,?,?)",
        (path, note["title"], note["body"]),
    )
    for tag in note["tags"]:
        conn.execute("INSERT OR IGNORE INTO tags(tag,note_path) VALUES(?,?)", (tag, path))
    for link in note["links"]:
        conn.execute(
            "INSERT OR IGNORE INTO links(src_path,target_name,resolved_path) VALUES(?,?,?)",
            (path, link["target"], link["resolved_path"]),
        )
    for task in note["tasks"]:
        conn.execute(
            """
            INSERT OR REPLACE INTO tasks
            (id,text,status,priority,due,scheduled,project,resonance,tags_json,source_note,source_line,style)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                task["id"],
                task["text"],
                task["status"],
                task["priority"],
                task["due"],
                task["scheduled"],
                task["project"],
                task["resonance"],
                json.dumps(task["tags"], ensure_ascii=False),
                task["source_note"],
                task["source_line"],
                task["style"],
            ),
        )
    max_tokens = int((MODEL_REGISTRY.get("embedding") or {}).get("max_input_tokens") or 32000)
    for chunk in note_chunks(note, max_input_tokens=max_tokens):
        conn.execute(
            """
            INSERT OR REPLACE INTO chunks
            (chunk_id,note_path,ordinal,title,heading_path,start_line,end_line,text,content_hash,token_estimate,mtime_ns)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                chunk["chunk_id"],
                chunk["note_path"],
                chunk["ordinal"],
                chunk["title"],
                chunk["heading_path"],
                chunk["start_line"],
                chunk["end_line"],
                chunk["text"],
                chunk["content_hash"],
                chunk["token_estimate"],
                chunk["mtime_ns"],
            ),
        )
        conn.execute(
            "INSERT INTO chunks_fts(chunk_id,note_path,title,heading_path,text) VALUES(?,?,?,?,?)",
            (chunk["chunk_id"], chunk["note_path"], chunk["title"], chunk["heading_path"], chunk["text"]),
        )


def refresh(rt: Runtime, *, full: bool = False, verbose: bool = False) -> dict[str, Any]:
    diagnostics = scan_diagnostics()
    paths = list(note_files(rt.vault, diagnostics=diagnostics))
    raise_walk_errors(rt.vault, diagnostics)
    maps = note_name_maps_from_paths(paths, rt.vault)
    parsed = 0
    deleted = 0
    started = time.time()
    with connect(rt) as conn:
        if full:
            for table in ("notes", "notes_fts", "tags", "links", "tasks", "chunks", "chunks_fts", "embeddings"):
                conn.execute(f"DELETE FROM {table}")
        indexed = {
            row["path"]: (int(row["mtime_ns"]), int(row["size"]))
            for row in conn.execute("SELECT path,mtime_ns,size FROM notes")
        }
        seen: set[str] = set()
        for path in paths:
            rp = relpath(path, rt.vault)
            seen.add(rp)
            st = path.stat()
            if not full and indexed.get(rp) == (st.st_mtime_ns, st.st_size):
                continue
            upsert_note(conn, parse_note(path, rt.vault, maps), delete_existing=not full)
            parsed += 1
        for rp in sorted(set(indexed) - seen):
            delete_index_rows(conn, rp)
            deleted += 1
        conn.execute("INSERT OR REPLACE INTO state(key,value) VALUES('last_refresh',?)", (utc_now(),))
        conn.commit()
        counts = index_counts(conn)
    payload = {
        "success": True,
        "vault": str(rt.vault),
        "full": full,
        "parsed": parsed,
        "deleted": deleted,
        "runtime_ms": int((time.time() - started) * 1000),
        **counts,
    }
    if verbose:
        payload["scan"] = diagnostics
    return payload


def ensure_fresh(rt: Runtime) -> None:
    refresh(rt, full=False)


def index_counts(conn: sqlite3.Connection) -> dict[str, Any]:
    def count(sql: str) -> int:
        return int(conn.execute(sql).fetchone()[0])

    broken = count("SELECT COUNT(*) FROM links WHERE COALESCE(resolved_path,'') = ''")
    last = conn.execute("SELECT value FROM state WHERE key='last_refresh'").fetchone()
    return {
        "note_count": count("SELECT COUNT(*) FROM notes"),
        "tag_count": count("SELECT COUNT(DISTINCT tag) FROM tags"),
        "task_count": count("SELECT COUNT(*) FROM tasks"),
        "link_count": count("SELECT COUNT(*) FROM links"),
        "broken_link_count": broken,
        "chunk_count": count("SELECT COUNT(*) FROM chunks"),
        "embedding_count": count("SELECT COUNT(*) FROM embeddings"),
        "last_refresh": last["value"] if last else None,
    }


def row_to_note(row: sqlite3.Row, *, include_body: bool = False) -> dict[str, Any]:
    fm = json.loads(row["frontmatter_json"] or "{}")
    payload = {
        "path": row["path"],
        "title": row["title"],
        "folder": row["folder"],
        "mtime_ns": row["mtime_ns"],
        "size": row["size"],
        "frontmatter": fm,
        "body_excerpt": row["body_excerpt"] or "",
        "scope": row["scope"] or "local",
    }
    if include_body:
        payload["body"] = row["body"] or ""
    return payload


def resolve_note_path(rt: Runtime, name: str | None = None, path_arg: str | None = None) -> str:
    if path_arg:
        candidate = path_arg.removesuffix(NOTE_SUFFIX) + NOTE_SUFFIX
        if (rt.vault / candidate).exists():
            return candidate
        raise AgentObsidianError(f"note path not found: {path_arg}", code=1)
    if not name:
        raise AgentObsidianError("note name required", code=NEEDS_CLARIFICATION)
    with connect(rt) as conn:
        rows = list(conn.execute("SELECT path,title FROM notes"))
    lowered = name.lower().removesuffix(NOTE_SUFFIX)
    for row in rows:
        path = row["path"]
        if path.lower() == name.lower() or path.lower().removesuffix(NOTE_SUFFIX) == lowered:
            return path
    matches = [row["path"] for row in rows if Path(row["path"]).stem.lower() == lowered or str(row["title"]).lower() == name.lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AgentObsidianError("ambiguous note name", code=NEEDS_CLARIFICATION, matches=matches)
    raise AgentObsidianError(f"note not found: {name}", code=1)


def cmd_snapshot(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    with connect(rt) as conn:
        counts = index_counts(conn)
    access_error = vault_access_error(rt.vault)
    ok = access_error is None
    payload = {
        "tool": "obsidian",
        "ok": ok,
        "mode": "local-index",
        "vault": str(rt.vault),
        "vault_readable": ok,
        "index": {"path": str(rt.db_path), **counts},
    }
    if access_error:
        payload["scan_error"] = access_error
        payload["recommendation"] = permission_recommendation()
    emit(payload, True)
    return 0 if ok else 1


def cmd_doctor(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_storage(rt)
    with connect(rt) as conn:
        counts = index_counts(conn)
    access_error = vault_access_error(rt.vault)
    ok = access_error is None
    payload = {
        "ok": ok,
        "mode": "local-index",
        "vault": str(rt.vault),
        "vault_readable": ok,
        "index_path": str(rt.db_path),
        "conventions_path": str(rt.agent_root / "conventions.yaml"),
        "write_lock": str(rt.lock_path),
        "credentials": credential_contract(rt),
        "features": feature_readiness(rt),
        **counts,
    }
    if access_error:
        payload["scan_error"] = access_error
        payload["recommendation"] = permission_recommendation()
    emit(payload, rt.json_mode)
    return 0 if ok else 1


def cmd_refresh(rt: Runtime, args: argparse.Namespace) -> int:
    emit(refresh(rt, full=args.full, verbose=args.verbose), rt.json_mode)
    return 0


def cmd_read(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    note_path = resolve_note_path(rt, args.name, args.path)
    with connect(rt) as conn:
        row = conn.execute("SELECT * FROM notes WHERE path = ?", (note_path,)).fetchone()
        note = row_to_note(row, include_body=True)
        note["tags"] = [r["tag"] for r in conn.execute("SELECT tag FROM tags WHERE note_path=? ORDER BY tag", (note_path,))]
        note["outgoing_links"] = [
            {"target": r["target_name"], "resolved_path": r["resolved_path"]}
            for r in conn.execute("SELECT target_name,resolved_path FROM links WHERE src_path=? ORDER BY target_name", (note_path,))
        ]
        note["backlinks_count"] = int(
            conn.execute("SELECT COUNT(*) FROM links WHERE resolved_path=?", (note_path,)).fetchone()[0]
        )
    if rt.json_mode:
        emit({"success": True, "note": note}, True)
    else:
        print(note["body"], end="" if note["body"].endswith("\n") else "\n")
    return 0


def fts_query(query: str) -> str:
    terms = [t for t in re.findall(r"[\w/-]+", query) if t]
    return " ".join(f'"{t}"' for t in terms) or query


def api_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            decoded = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AgentObsidianError("provider API request failed", code=1, status=exc.code, detail=detail[:2000], url=url) from exc
    except OSError as exc:
        raise AgentObsidianError("provider API request failed", code=1, detail=str(exc), url=url) from exc
    try:
        result = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise AgentObsidianError("provider API returned non-JSON response", code=1, detail=decoded[:2000], url=url) from exc
    if not isinstance(result, dict):
        raise AgentObsidianError("provider API returned unexpected response", code=1, url=url)
    return result


def embedding_batches(items: list[dict[str, Any]], profile: dict[str, Any]) -> Iterable[list[dict[str, Any]]]:
    max_items = int(profile.get("max_batch_items") or 1)
    max_tokens = int(profile.get("max_batch_tokens") or profile.get("max_input_tokens") or 1)
    max_chars = int(profile.get("max_batch_chars") or 0)
    batch: list[dict[str, Any]] = []
    token_count = 0
    char_count = 0
    for item in items:
        text = item.get("text") or ""
        item_tokens = int(item.get("token_estimate") or estimate_tokens(text))
        item_chars = len(text)
        if batch and (
            len(batch) >= max_items
            or token_count + item_tokens > max_tokens
            or (max_chars and char_count + item_chars > max_chars)
        ):
            yield batch
            batch = []
            token_count = 0
            char_count = 0
        batch.append(item)
        token_count += item_tokens
        char_count += item_chars
    if batch:
        yield batch


def extract_embedding_list(payload: dict[str, Any]) -> list[list[float]]:
    if isinstance(payload.get("embeddings"), list):
        return [[float(v) for v in row] for row in payload["embeddings"]]
    data = payload.get("data")
    if isinstance(data, list):
        rows = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                rows.append([float(v) for v in item["embedding"]])
        if rows:
            return rows
    raise AgentObsidianError("embedding provider returned no embeddings", code=1, payload=payload)


def embed_texts(profile: dict[str, Any], texts: list[str], *, input_type: str) -> list[list[float]]:
    provider = str(profile.get("provider") or "")
    model = str(profile.get("model") or "")
    if provider == "voyage":
        key = require_api_key(profile)
        payload: dict[str, Any] = {
            "input": texts,
            "model": model,
            "input_type": input_type,
            "truncation": False,
            "output_dtype": "float",
        }
        if profile.get("dimension"):
            payload["output_dimension"] = int(profile["dimension"])
        response = api_json(
            "https://api.voyageai.com/v1/embeddings",
            payload,
            {"Authorization": f"Bearer {key}"},
        )
        return extract_embedding_list(response)
    if provider == "openai":
        key = require_api_key(profile)
        payload = {"input": texts, "model": model, "encoding_format": "float"}
        if profile.get("dimension"):
            payload["dimensions"] = int(profile["dimension"])
        response = api_json(
            "https://api.openai.com/v1/embeddings",
            payload,
            {"Authorization": f"Bearer {key}"},
        )
        return extract_embedding_list(response)
    raise AgentObsidianError(f"unsupported embedding provider: {provider}", code=NEEDS_CLARIFICATION)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    mag_a = math.sqrt(sum(a[i] * a[i] for i in range(n)))
    mag_b = math.sqrt(sum(b[i] * b[i] for i in range(n)))
    if not mag_a or not mag_b:
        return 0.0
    return dot / (mag_a * mag_b)


def chunk_result(row: sqlite3.Row, *, score: float, source: str) -> dict[str, Any]:
    text = row["text"] or ""
    snippet = text.replace("\n", " ").strip()
    if len(snippet) > 360:
        snippet = snippet[:357].rstrip() + "..."
    return {
        "path": row["note_path"],
        "title": row["title"],
        "folder": row["folder"],
        "scope": row["scope"] or "local",
        "chunk_id": row["chunk_id"],
        "heading_path": row["heading_path"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
        "snippet": snippet,
        "score": round(float(score), 6),
        "score_source": source,
    }


def keyword_chunk_candidates(conn: sqlite3.Connection, query: str, *, limit: int) -> list[dict[str, Any]]:
    rows: list[sqlite3.Row] = []
    try:
        rows = list(
            conn.execute(
                """
                SELECT c.*, n.folder, n.scope, bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
                JOIN notes n ON n.path = c.note_path
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query(query), limit),
            )
        )
    except sqlite3.Error:
        rows = []
    if not rows:
        like = f"%{query.lower()}%"
        rows = list(
            conn.execute(
                """
                SELECT c.*, n.folder, n.scope, 0.0 AS rank
                FROM chunks c JOIN notes n ON n.path = c.note_path
                WHERE lower(c.title) LIKE ? OR lower(c.heading_path) LIKE ? OR lower(c.text) LIKE ?
                ORDER BY c.mtime_ns DESC
                LIMIT ?
                """,
                (like, like, like, limit),
            )
        )
    if not rows:
        return []
    ranks = [abs(float(row["rank"] or 0.0)) for row in rows]
    max_rank = max(ranks) if ranks else 0.0
    results = []
    for row in rows:
        rank = abs(float(row["rank"] or 0.0))
        score = 1.0 if max_rank == 0 else 1.0 - (rank / max_rank)
        results.append(chunk_result(row, score=max(0.0, score), source="keyword"))
    return results


def stored_embedding_candidates(rt: Runtime, query: str, *, limit: int) -> list[dict[str, Any]]:
    profile = effective_embedding_profile(rt)
    provider = str(profile.get("provider") or "")
    model = str(profile.get("model") or "")
    dimension = int(profile.get("dimension") or 0)
    ensure_fresh(rt)
    with connect(rt) as conn:
        available = conn.execute(
            """
            SELECT COUNT(*) FROM embeddings e
            JOIN chunks c ON c.chunk_id = e.chunk_id
            WHERE e.provider=? AND e.model=? AND e.dimension=? AND e.content_hash=c.content_hash
            """,
            (provider, model, dimension),
        ).fetchone()[0]
        if not available:
            raise AgentObsidianError(
                "semantic index is empty or stale; run agent-do obsidian embed refresh --json",
                code=NEEDS_CLARIFICATION,
                provider=provider,
                model=model,
                dimension=dimension,
            )
    query_embedding = embed_texts(profile, [query], input_type="query")[0]
    with connect(rt) as conn:
        rows = list(
            conn.execute(
                """
                SELECT c.*, n.folder, n.scope, e.embedding_json
                FROM embeddings e
                JOIN chunks c ON c.chunk_id = e.chunk_id
                JOIN notes n ON n.path = c.note_path
                WHERE e.provider=? AND e.model=? AND e.dimension=? AND e.content_hash=c.content_hash
                """,
                (provider, model, dimension),
            )
        )
    scored = []
    for row in rows:
        vector = json.loads(row["embedding_json"] or "[]")
        scored.append(chunk_result(row, score=cosine(query_embedding, vector), source="semantic"))
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def merge_ranked_candidates(keyword: list[dict[str, Any]], semantic: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in keyword:
        record = dict(item)
        record["score_components"] = {"keyword": item["score"], "semantic": 0.0, "graph": 0.0}
        record["score"] = 0.45 * float(item["score"])
        merged[item["chunk_id"]] = record
    for item in semantic:
        record = merged.get(item["chunk_id"], dict(item))
        components = dict(record.get("score_components") or {"keyword": 0.0, "semantic": 0.0, "graph": 0.0})
        components["semantic"] = float(item["score"])
        record.update({k: v for k, v in item.items() if k not in {"score", "score_source"}})
        record["score_components"] = components
        record["score"] = 0.45 * float(components.get("keyword") or 0.0) + 0.45 * float(components.get("semantic") or 0.0)
        record["score_source"] = "hybrid"
        merged[item["chunk_id"]] = record
    ranked = list(merged.values())
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def parse_rerank_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results") or payload.get("data")
    if not isinstance(results, list):
        raise AgentObsidianError("reranker provider returned no results", code=1, payload=payload)
    parsed = []
    for item in results:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        score = item.get("relevance_score")
        if idx is None or score is None:
            continue
        parsed.append({"index": int(idx), "score": float(score)})
    return parsed


def rerank_candidates(rt: Runtime, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    profile = model_profile(rt, "reranker")
    if not credential_status(profile)["available"]:
        return [{**item, "rerank_used": False, "rerank_reason": f"missing {profile.get('env')}"} for item in candidates]
    max_documents = int(profile.get("max_documents") or len(candidates))
    hydrated = hydrate_candidate_text(rt, candidates[:max_documents])
    documents = [
        "\n".join(
            part
            for part in [
                str(item.get("title") or ""),
                str(item.get("heading_path") or ""),
                str(item.get("text") or item.get("snippet") or ""),
            ]
            if part
        )
        for item in hydrated
    ]
    key = require_api_key(profile)
    try:
        payload = api_json(
            "https://api.voyageai.com/v1/rerank",
            {
                "query": query,
                "documents": documents,
                "model": profile.get("model"),
                "top_k": len(documents),
                "truncation": False,
            },
            {"Authorization": f"Bearer {key}"},
        )
    except AgentObsidianError as exc:
        return [
            {
                **item,
                "rerank_used": False,
                "rerank_reason": f"{profile.get('provider')} {profile.get('model')} unavailable: {exc.message}",
            }
            for item in candidates
        ]
    indexed = {idx: item for idx, item in enumerate(hydrated)}
    reranked = []
    for result in parse_rerank_results(payload):
        item = indexed.get(result["index"])
        if not item:
            continue
        updated = dict(item)
        updated["rerank_used"] = True
        updated["rerank_model"] = profile.get("model")
        updated["rerank_score"] = result["score"]
        updated["score"] = result["score"]
        updated.pop("text", None)
        reranked.append(updated)
    if len(candidates) > max_documents:
        reranked.extend({**item, "rerank_used": False, "rerank_reason": "outside provider max_documents"} for item in candidates[max_documents:])
    return reranked or candidates


def search_chunks(rt: Runtime, query: str, *, limit: int, mode: str) -> list[dict[str, Any]]:
    ensure_fresh(rt)
    candidate_limit = max(limit, min(1000, limit * 10))
    if mode in {"keyword", "fts", "exact"}:
        with connect(rt) as conn:
            return keyword_chunk_candidates(conn, query, limit=limit)
    if mode == "semantic":
        return rerank_candidates(rt, query, stored_embedding_candidates(rt, query, limit=limit))[:limit]
    if mode == "hybrid":
        with connect(rt) as conn:
            keyword = keyword_chunk_candidates(conn, query, limit=candidate_limit)
        semantic = stored_embedding_candidates(rt, query, limit=candidate_limit)
        return rerank_candidates(rt, query, merge_ranked_candidates(keyword, semantic, limit=candidate_limit))[:limit]
    raise AgentObsidianError(f"unknown search mode: {mode}", code=NEEDS_CLARIFICATION)


def search_notes(rt: Runtime, query: str, *, limit: int = 10, folder: str = "", tag: str = "", mode: str = "fts") -> list[dict[str, Any]]:
    if mode in {"semantic", "hybrid"}:
        chunks = search_chunks(rt, query, limit=max(limit, limit * 2), mode=mode)
        if folder:
            chunks = [item for item in chunks if str(item.get("folder") or "").startswith(folder)]
        if tag:
            wanted = tag.lstrip("#")
            with connect(rt) as conn:
                tagged = {r["note_path"] for r in conn.execute("SELECT note_path FROM tags WHERE tag=?", (wanted,))}
            chunks = [item for item in chunks if item["path"] in tagged]
        chunks = chunks[:limit]
        return chunks
    if mode == "keyword":
        mode = "fts"
    ensure_fresh(rt)
    with connect(rt) as conn:
        rows: list[sqlite3.Row] = []
        if mode == "fts":
            try:
                sql = """
                    SELECT n.*, bm25(notes_fts) AS score
                    FROM notes_fts JOIN notes n ON notes_fts.path = n.path
                    WHERE notes_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                """
                rows = list(conn.execute(sql, (fts_query(query), limit * 4)))
            except sqlite3.Error:
                rows = []
        if not rows:
            like = f"%{query.lower()}%"
            rows = list(
                conn.execute(
                    """
                    SELECT *, 0.0 AS score FROM notes
                    WHERE lower(title) LIKE ? OR lower(body) LIKE ?
                    ORDER BY mtime_ns DESC
                    LIMIT ?
                    """,
                    (like, like, limit * 4),
                )
            )
        results: list[dict[str, Any]] = []
        for row in rows:
            if folder and not str(row["folder"]).startswith(folder):
                continue
            if tag:
                found = conn.execute("SELECT 1 FROM tags WHERE note_path=? AND tag=?", (row["path"], tag.lstrip("#"))).fetchone()
                if not found:
                    continue
            body = row["body"] or ""
            idx = body.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 80)
                end = min(len(body), idx + len(query) + 160)
                snippet = body[start:end].replace("\n", " ").strip()
            else:
                snippet = (row["body_excerpt"] or "").replace("\n", " ").strip()
            item = row_to_note(row)
            item["snippet"] = snippet
            item["score"] = float(row["score"] or 0.0)
            results.append(item)
            if len(results) >= limit:
                break
        return results


def cmd_search(rt: Runtime, args: argparse.Namespace) -> int:
    results = search_notes(rt, args.query, limit=args.limit, folder=args.folder or "", tag=args.tag or "", mode=args.mode)
    if args.total:
        emit({"success": True, "count": len(results)}, rt.json_mode)
    elif rt.json_mode:
        emit({"success": True, "query": args.query, "count": len(results), "results": results}, True)
    else:
        for item in results:
            print(f"{item['path']}\t{item['title']}\t{item.get('snippet','')}")
    return 0


def slugify(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9 _.-]+", "", title).strip().replace("/", "-")
    slug = re.sub(r"\s+", " ", slug)
    return slug[:100] or f"note-{today()}"


def derive_title(content: str) -> str:
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:100] or "Untitled"
    for part in re.split(r"(?<=[.!?])\s+", content.strip()):
        clean = re.sub(r"\s+", " ", part).strip("# ").strip()
        if clean:
            return clean[:60]
    return f"Note {today()}"


def folder_from_token(cfg: dict[str, Any], token: str | None) -> str:
    token = token or cfg.get("save", {}).get("default_folder_token") or "inbox"
    folders = cfg.get("folders") or {}
    return str(folders.get(token, token)).strip("/")


def normalize_related(value: str | None) -> list[str] | str:
    if not value:
        return []
    if value == "auto":
        return "auto"
    return [item.strip().strip("[]") for item in value.split(",") if item.strip()]


@contextlib.contextmanager
def write_lock(rt: Runtime, operation: str, paths: list[str]) -> Iterable[None]:
    ensure_storage(rt)
    payload = {
        "pid": os.getpid(),
        "timestamp": utc_now(),
        "operation": operation,
        "paths": paths,
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd: int | None = None
    try:
        try:
            fd = os.open(rt.lock_path, flags, 0o644)
        except FileExistsError as exc:
            existing = {}
            with contextlib.suppress(Exception):
                existing = json.loads(rt.lock_path.read_text(encoding="utf-8"))
            pid = existing.get("pid")
            stale = False
            if isinstance(pid, int):
                try:
                    os.kill(pid, 0)
                except OSError:
                    stale = True
            if stale:
                rt.lock_path.unlink(missing_ok=True)
                fd = os.open(rt.lock_path, flags, 0o644)
            else:
                raise AgentObsidianError("vault write-lock already held", code=NEEDS_CLARIFICATION, lock=existing) from exc
        os.write(fd, json.dumps(payload, indent=2).encode("utf-8"))
        os.close(fd)
        fd = None
        yield
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            rt.lock_path.unlink()


def write_note_file(path: Path, frontmatter: dict[str, Any], body: str, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise AgentObsidianError(f"refusing to overwrite existing note: {path}", code=NEEDS_CLARIFICATION)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_note(frontmatter, body), encoding="utf-8")


def full_note_record(rt: Runtime, path: Path) -> dict[str, Any]:
    maps = note_name_maps(rt.vault)
    note = parse_note(path, rt.vault, maps)
    with connect(rt) as conn:
        upsert_note(conn, note)
        conn.commit()
    return {
        "path": note["path"],
        "title": note["title"],
        "frontmatter": note["frontmatter"],
        "body": note["body"],
        "tags": note["tags"],
        "outgoing_links": note["links"],
    }


def cmd_save(rt: Runtime, args: argparse.Namespace) -> int:
    if not args.content:
        raise AgentObsidianError("save requires --content", code=NEEDS_CLARIFICATION)
    cfg = load_conventions(rt)
    title = args.title or derive_title(args.content)
    folder = folder_from_token(cfg, args.folder)
    note_path = rt.vault / folder / f"{slugify(title)}.md"
    related = normalize_related(args.related)
    if related == "auto":
        related = [item["title"] for item in search_notes(rt, args.content[:200], limit=int(cfg.get("save", {}).get("auto_related_limit", 5)))]
    tags = normalize_tags(args.tags or [])
    defaults = dict(cfg.get("default_frontmatter") or {})
    def expand(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace("{today}", today()).replace("{now}", utc_now())
        return value

    fm = {key: expand(value) for key, value in defaults.items()}
    fm.update({"title": title, "created": fm.get("created") or today(), "scope": args.scope or fm.get("scope") or "local"})
    if args.up:
        fm["up"] = args.up
    if related:
        fm["related"] = related
    if tags:
        fm["tags"] = tags
    with write_lock(rt, "save", [relpath(note_path, rt.vault)]):
        write_note_file(note_path, fm, args.content, overwrite=args.overwrite)
        record = full_note_record(rt, note_path)
    emit({"success": True, "record": record}, rt.json_mode)
    return 0


def cmd_save_group(rt: Runtime, args: argparse.Namespace) -> int:
    if not args.child:
        raise AgentObsidianError("save-group requires at least one --child name:content", code=NEEDS_CLARIFICATION)
    hub_title = args.hub_name
    children: list[tuple[str, str]] = []
    for child in args.child:
        if ":" not in child:
            raise AgentObsidianError("--child must be name:content", code=NEEDS_CLARIFICATION, child=child)
        name, body = child.split(":", 1)
        children.append((name.strip(), body))
    overrides: dict[str, str] = {}
    for item in args.child_scope or []:
        if ":" not in item:
            raise AgentObsidianError("--child-scope must be name:scope", code=NEEDS_CLARIFICATION, child_scope=item)
        name, scope = item.split(":", 1)
        overrides[name.strip()] = scope.strip()
    cfg = load_conventions(rt)
    folder = folder_from_token(cfg, args.folder)
    tags = normalize_tags(args.tags or [])
    hub_path = rt.vault / folder / f"{slugify(hub_title)}.md"
    child_paths = [rt.vault / folder / f"{slugify(name)}.md" for name, _ in children]
    with write_lock(rt, "save-group", [relpath(p, rt.vault) for p in [hub_path, *child_paths]]):
        hub_links = [f"[[{name}]]" for name, _ in children]
        hub_fm = {"title": hub_title, "created": today(), "scope": args.scope, "related": [name for name, _ in children], "tags": tags}
        write_note_file(hub_path, hub_fm, "\n".join(f"- {link}" for link in hub_links), overwrite=args.overwrite)
        records = [full_note_record(rt, hub_path)]
        for (name, body), path in zip(children, child_paths):
            scope = overrides.get(name, args.scope)
            fm = {"title": name, "created": today(), "scope": scope, "up": hub_title, "related": [hub_title], "tags": tags}
            write_note_file(path, fm, body, overwrite=args.overwrite)
            records.append(full_note_record(rt, path))
    emit({"success": True, "count": len(records), "records": records}, rt.json_mode)
    return 0


def cmd_create(rt: Runtime, args: argparse.Namespace) -> int:
    content = args.content or ""
    name = args.name
    path = rt.vault / (name if name.endswith(NOTE_SUFFIX) else f"{name}.md")
    fm = {"title": Path(name).stem, "created": today(), "scope": "local"}
    with write_lock(rt, "create", [relpath(path, rt.vault)]):
        write_note_file(path, fm, content, overwrite=args.overwrite)
        record = full_note_record(rt, path)
    emit({"success": True, "record": record}, rt.json_mode)
    return 0


def cmd_append(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    note_path = resolve_note_path(rt, None if args.path_mode else args.target, args.target if args.path_mode else None)
    abs_path = rt.vault / note_path
    before = stat_payload(abs_path)
    with write_lock(rt, "append", [note_path]):
        current = abs_path.read_text(encoding="utf-8")
        if abs_path.stat().st_mtime_ns != before["mtime_ns"] or abs_path.stat().st_size != before["size"]:
            raise AgentObsidianError("file changed since preflight", code=NEEDS_CLARIFICATION, path=note_path)
        content = args.content
        if args.section:
            current = append_to_section(current, args.section, content)
        else:
            current = current.rstrip() + "\n\n" + content.rstrip() + "\n"
        abs_path.write_text(current, encoding="utf-8")
        record = full_note_record(rt, abs_path)
    emit({"success": True, "record": record}, rt.json_mode)
    return 0


def append_to_section(text: str, section: str, content: str) -> str:
    lines = text.splitlines()
    header_re = re.compile(r"^(#+)\s+" + re.escape(section.strip()) + r"\s*$", re.I)
    for idx, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
        level = len(m.group(1))
        insert_at = len(lines)
        for j in range(idx + 1, len(lines)):
            if lines[j].startswith("#") and len(lines[j].split(" ", 1)[0]) <= level:
                insert_at = j
                break
        lines.insert(insert_at, content.rstrip())
        return "\n".join(lines).rstrip() + "\n"
    return text.rstrip() + f"\n\n## {section}\n{content.rstrip()}\n"


def cmd_backlinks(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    note_path = resolve_note_path(rt, args.name, None)
    with connect(rt) as conn:
        rows = [
            row_to_note(r)
            for r in conn.execute(
                "SELECT n.* FROM links l JOIN notes n ON n.path=l.src_path WHERE l.resolved_path=? ORDER BY n.path",
                (note_path,),
            )
        ]
    emit({"success": True, "target": note_path, "count": len(rows), "backlinks": rows}, rt.json_mode)
    return 0


def cmd_tags(rt: Runtime, args: argparse.Namespace) -> int:
    if args.tags_cmd == "rename":
        values = [v for v in (args.from_tag, args.to_tag) if v]
        if len(values) != 2:
            raise AgentObsidianError("tags rename requires <from> <to>", code=NEEDS_CLARIFICATION)
        return tags_rename(rt, values[0], values[1])
    if args.tags_cmd == "merge":
        values = [v for v in [args.from_tag, args.to_tag, *(args.from_tags or [])] if v]
        if len(values) < 2:
            raise AgentObsidianError("tags merge requires <from...> <to>", code=NEEDS_CLARIFICATION)
        return tags_merge(rt, values[:-1], values[-1])

    ensure_fresh(rt)
    with connect(rt) as conn:
        rows = list(conn.execute("SELECT tag, COUNT(*) AS count FROM tags GROUP BY tag"))
    if args.prefix:
        rows = [r for r in rows if str(r["tag"]).startswith(args.prefix)]
    rows.sort(key=lambda r: ((-r["count"], r["tag"]) if args.sort == "count" else (r["tag"], r["count"])))
    items = [{"tag": r["tag"], "count": int(r["count"])} for r in rows]
    if args.total:
        emit({"success": True, "count": len(items)}, rt.json_mode)
    elif rt.json_mode or args.counts:
        emit({"success": True, "count": len(items), "tags": items}, rt.json_mode)
    else:
        for item in items:
            print(item["tag"])
    return 0


def update_note_tags(text: str, replacements: dict[str, str]) -> tuple[str, bool]:
    fm, body = parse_frontmatter(text)
    changed = False
    tags = normalize_tags(fm.get("tags"))
    if tags:
        new_tags = []
        for tag in tags:
            new_tag = replacements.get(tag, tag)
            if new_tag != tag:
                changed = True
            if new_tag not in new_tags:
                new_tags.append(new_tag)
        fm["tags"] = new_tags

    for old, new in replacements.items():
        pattern = re.compile(rf"(?<![\w/])#{re.escape(old)}\b")
        body, count = pattern.subn(f"#{new}", body)
        changed = changed or count > 0
    if not changed:
        return text, False
    return render_note(fm, body), True


def note_paths_for_tags(rt: Runtime, tags: list[str]) -> list[str]:
    ensure_fresh(rt)
    with connect(rt) as conn:
        rows = conn.execute(
            f"SELECT DISTINCT note_path FROM tags WHERE tag IN ({','.join('?' for _ in tags)}) ORDER BY note_path",
            tags,
        )
        return [r["note_path"] for r in rows]


def rewrite_tags(rt: Runtime, replacements: dict[str, str], operation: str) -> dict[str, Any]:
    paths = note_paths_for_tags(rt, sorted(replacements))
    abs_paths = [rt.vault / p for p in paths]
    preflight = {p: stat_payload(rt.vault / p) for p in paths}
    changed: list[str] = []
    with write_lock(rt, operation, paths):
        move_id, journal, backup_dir = make_operation(rt, operation.replace(" ", "-"), abs_paths)
        try:
            for note_path in paths:
                path = rt.vault / note_path
                st = path.stat()
                before = preflight[note_path]
                if st.st_mtime_ns != before["mtime_ns"] or st.st_size != before["size"]:
                    raise AgentObsidianError("file changed since preflight", code=NEEDS_CLARIFICATION, path=note_path, operation_id=move_id)
                backup = backup_dir / note_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
                updated, did_change = update_note_tags(path.read_text(encoding="utf-8"), replacements)
                if did_change:
                    path.write_text(updated, encoding="utf-8")
                    changed.append(note_path)
                    append_journal(journal, "apply-tag-rewrite", {"path": note_path})
            refresh(rt, full=False)
            append_journal(journal, "verify", {"ok": True, "changed": changed})
        except Exception:
            for backup in sorted(backup_dir.rglob("*")):
                if backup.is_file():
                    target = rt.vault / backup.relative_to(backup_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
            append_journal(journal, "rollback", {"ok": True})
            raise
    return {"operation_id": move_id, "changed": changed}


def tags_rename(rt: Runtime, from_tag: str, to_tag: str) -> int:
    result = rewrite_tags(rt, {from_tag.lstrip("#"): to_tag.lstrip("#")}, "tags rename")
    emit({"success": True, "from": from_tag.lstrip("#"), "to": to_tag.lstrip("#"), **result}, rt.json_mode)
    return 0


def tags_merge(rt: Runtime, from_tags: list[str], to_tag: str) -> int:
    replacements = {tag.lstrip("#"): to_tag.lstrip("#") for tag in from_tags}
    result = rewrite_tags(rt, replacements, "tags merge")
    emit({"success": True, "from": list(replacements), "to": to_tag.lstrip("#"), **result}, rt.json_mode)
    return 0


def task_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "text": row["text"],
        "status": row["status"],
        "priority": row["priority"],
        "due": row["due"],
        "scheduled": row["scheduled"],
        "project": row["project"],
        "resonance": int(row["resonance"] or 0),
        "tags": json.loads(row["tags_json"] or "[]"),
        "source_note": row["source_note"],
        "source_line": row["source_line"],
        "style": row["style"],
    }


def cmd_tasks(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    if args.task_cmd == "list":
        return tasks_list(rt, args)
    if args.task_cmd == "next":
        return tasks_next(rt, args)
    if args.task_cmd == "add":
        return tasks_add(rt, args)
    if args.task_cmd == "complete":
        return tasks_update_status(rt, args.id, "done")
    if args.task_cmd == "update":
        return tasks_update_fields(rt, args)
    raise AgentObsidianError("unknown tasks subcommand", code=NEEDS_CLARIFICATION)


def tasks_list(rt: Runtime, args: argparse.Namespace) -> int:
    with connect(rt) as conn:
        rows = [task_row(r) for r in conn.execute("SELECT * FROM tasks")]
    tasks = filter_tasks(rows, args)
    emit({"success": True, "count": len(tasks), "tasks": tasks[: args.limit]}, rt.json_mode)
    return 0


def filter_tasks(tasks: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.status:
        statuses = set(args.status.split(","))
        tasks = [t for t in tasks if t["status"] in statuses]
    if args.priority:
        priorities = set(args.priority.split(","))
        tasks = [t for t in tasks if t["priority"] in priorities]
    if args.project:
        tasks = [t for t in tasks if t["project"] == args.project]
    if args.tag:
        tag = args.tag.lstrip("#")
        tasks = [t for t in tasks if tag in t["tags"]]
    if args.due_before:
        tasks = [t for t in tasks if t["due"] and t["due"] <= args.due_before]
    if args.due_after:
        tasks = [t for t in tasks if t["due"] and t["due"] >= args.due_after]
    sort_fields = [s for s in (args.sort or "due,priority").split(",") if s]
    priority_rank = {"highest": 0, "high": 1, "medium": 2, "low": 3, "": 4}

    def key(task: dict[str, Any]) -> tuple[Any, ...]:
        values = []
        for field in sort_fields:
            if field == "priority":
                values.append(priority_rank.get(task["priority"], 4))
            else:
                values.append(task.get(field) or "9999-99-99")
        return tuple(values)

    return sorted(tasks, key=key)


def tasks_next(rt: Runtime, args: argparse.Namespace) -> int:
    base = argparse.Namespace(**vars(args))
    base.status = "open"
    base.limit = 1000
    with connect(rt) as conn:
        rows = [task_row(r) for r in conn.execute("SELECT * FROM tasks")]
    tasks = filter_tasks(rows, base)
    cfg = load_conventions(rt)
    weights = cfg.get("task_next_weights") or {}
    today_date = dt.date.today()
    priority_score = {"highest": 1.0, "high": 0.8, "medium": 0.5, "low": 0.2, "": 0.0}
    ranked = []
    for task in tasks:
        due_score = 0.0
        if task["due"]:
            with contextlib.suppress(ValueError):
                delta = (dt.date.fromisoformat(task["due"]) - today_date).days
                due_score = 1.0 if delta <= 0 else max(0.0, 1 - (delta / 30))
        resonance = min(1.0, max(0.0, float(task["resonance"] or 0) / 10))
        score = (
            float(weights.get("priority_weight", 0.35)) * priority_score.get(task["priority"], 0)
            + float(weights.get("due_proximity_weight", 0.30)) * due_score
            + float(weights.get("resonance_weight", 0.20)) * resonance
        )
        task = dict(task)
        task["score"] = round(score, 4)
        task["score_components"] = {
            "priority": priority_score.get(task["priority"], 0),
            "due_proximity": due_score,
            "resonance": resonance,
        }
        ranked.append(task)
    ranked.sort(key=lambda t: (-t["score"], t.get("due") or "9999-99-99"))
    emit({"success": True, "count": len(ranked[: args.limit]), "tasks": ranked[: args.limit]}, rt.json_mode)
    return 0


def tasks_add(rt: Runtime, args: argparse.Namespace) -> int:
    cfg = load_conventions(rt)
    style = args.style or cfg.get("task_default_style") or "frontmatter"
    tags = normalize_tags(args.tags or [])
    if style == "inline":
        target = args.into or today()
        content = f"- [ ] {args.text}"
        if args.due:
            content += f" 📅 {args.due}"
        if args.scheduled:
            content += f" ⏳ {args.scheduled}"
        return cmd_append(rt, argparse.Namespace(target=target, content=content, path_mode=False, section="Tasks"))
    folder = folder_from_token(cfg, "tasks")
    path = rt.vault / folder / f"{slugify(args.text)}.md"
    fm = {
        "type": "task",
        "title": args.text,
        "text": args.text,
        "status": "open",
        "priority": args.priority or "",
        "due": args.due or "",
        "scheduled": args.scheduled or "",
        "project": args.project or "",
        "resonance": args.resonance or 0,
        "tags": tags,
        "created": today(),
    }
    with write_lock(rt, "tasks add", [relpath(path, rt.vault)]):
        write_note_file(path, fm, args.text, overwrite=False)
        record = full_note_record(rt, path)
    emit({"success": True, "record": record}, rt.json_mode)
    return 0


def find_task(rt: Runtime, task_id_arg: str) -> dict[str, Any]:
    ensure_fresh(rt)
    with connect(rt) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id_arg,)).fetchone()
    if not row:
        raise AgentObsidianError(f"task not found: {task_id_arg}", code=1)
    return task_row(row)


def tasks_update_status(rt: Runtime, task_id_arg: str, status: str) -> int:
    task = find_task(rt, task_id_arg)
    return update_task(rt, task, {"status": status})


def tasks_update_fields(rt: Runtime, args: argparse.Namespace) -> int:
    fields = parse_key_values(args.set_values)
    task = find_task(rt, args.id)
    return update_task(rt, task, fields)


def update_task(rt: Runtime, task: dict[str, Any], fields: dict[str, Any]) -> int:
    path = rt.vault / task["source_note"]
    with write_lock(rt, "tasks update", [task["source_note"]]):
        text = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if task["style"] == "frontmatter":
            fm.update(fields)
            path.write_text(render_note(fm, body), encoding="utf-8")
        else:
            lines = body.splitlines()
            idx = int(task["source_line"]) - 1
            if 0 <= idx < len(lines):
                if fields.get("status") == "done":
                    lines[idx] = re.sub(r"\[[ xX]\]", "[x]", lines[idx], count=1)
                elif fields.get("status") == "open":
                    lines[idx] = re.sub(r"\[[ xX]\]", "[ ]", lines[idx], count=1)
                body = "\n".join(lines) + "\n"
                path.write_text(render_note(fm, body), encoding="utf-8")
        record = full_note_record(rt, path)
    emit({"success": True, "record": record}, rt.json_mode)
    return 0


def parse_key_values(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise AgentObsidianError("--set values must be k=v", code=NEEDS_CLARIFICATION, value=item)
        key, value = item.split("=", 1)
        result[key] = value
    return result


def note_matches_where(note: dict[str, Any], expr: str) -> bool:
    if not expr:
        return True
    match = re.match(r"(\w+)\s*=\s*['\"]?([^'\"]+)['\"]?", expr)
    if not match:
        raise AgentObsidianError(f"unsupported WHERE expression: {expr}", code=NEEDS_CLARIFICATION)
    key, value = match.group(1), match.group(2)
    if key in note:
        return str(note.get(key)) == value
    return str((note.get("frontmatter") or {}).get(key, "")) == value


def cmd_query(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    q = args.query.strip()
    source = ""
    where = ""
    sort_field = ""
    sort_dir = "ASC"
    limit = args.limit or 50
    m = re.search(r"\bFROM\s+(.+?)(?=\s+WHERE|\s+SORT|\s+LIMIT|$)", q, re.I)
    if m:
        source = m.group(1).strip().strip('"')
    m = re.search(r"\bWHERE\s+(.+?)(?=\s+SORT|\s+LIMIT|$)", q, re.I)
    if m:
        where = m.group(1).strip()
    m = re.search(r"\bSORT\s+(\w+)(?:\s+(ASC|DESC))?", q, re.I)
    if m:
        sort_field = m.group(1)
        sort_dir = (m.group(2) or "ASC").upper()
    m = re.search(r"\bLIMIT\s+(\d+)", q, re.I)
    if m:
        limit = int(m.group(1))
    with connect(rt) as conn:
        notes = [row_to_note(r, include_body=False) for r in conn.execute("SELECT * FROM notes")]
        tag_map: dict[str, set[str]] = {}
        for row in conn.execute("SELECT tag,note_path FROM tags"):
            tag_map.setdefault(row["note_path"], set()).add(row["tag"])
    if source.startswith("#"):
        wanted = source[1:]
        notes = [n for n in notes if wanted in tag_map.get(n["path"], set())]
    elif source and source not in {"/", "notes"}:
        notes = [n for n in notes if n["folder"].startswith(source.strip("/"))]
    notes = [n for n in notes if note_matches_where(n, where)]
    if sort_field:
        notes.sort(key=lambda n: str(n.get(sort_field) or n.get("frontmatter", {}).get(sort_field, "")), reverse=sort_dir == "DESC")
    emit({"success": True, "query": q, "count": len(notes[:limit]), "rows": notes[:limit]}, rt.json_mode)
    return 0


def cmd_relate(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    text = args.content_or_name
    source_tags: set[str] = set()
    source_folder = ""
    source_title = text
    with contextlib.suppress(Exception):
        path = resolve_note_path(rt, text, None)
        with connect(rt) as conn:
            row = conn.execute("SELECT * FROM notes WHERE path=?", (path,)).fetchone()
            source_title = row["title"]
            source_folder = row["folder"]
            source_tags = {r["tag"] for r in conn.execute("SELECT tag FROM tags WHERE note_path=?", (path,))}
            text = row["body"]
    results = search_notes(rt, text[:200], limit=max(args.limit * 4, 10))
    cfg = load_conventions(rt)
    weights = cfg.get("related_find", {}).get("score_weights", {})
    ranked = []
    text_words = set(re.findall(r"\w+", (source_title + " " + text).lower()))
    with connect(rt) as conn:
        for item in results:
            tags = {r["tag"] for r in conn.execute("SELECT tag FROM tags WHERE note_path=?", (item["path"],))}
            title_words = set(re.findall(r"\w+", item["title"].lower()))
            title_similarity = len(text_words & title_words) / max(1, len(text_words | title_words))
            tag_overlap = len(source_tags & tags) / max(1, len(source_tags | tags)) if source_tags or tags else 0.0
            folder_proximity = 1.0 if source_folder and item["folder"] == source_folder else 0.0
            link_graph = 0.0
            score = (
                float(weights.get("title_similarity", 0.4)) * title_similarity
                + float(weights.get("tag_overlap", 0.3)) * tag_overlap
                + float(weights.get("folder_proximity", 0.15)) * folder_proximity
                + float(weights.get("link_graph", 0.15)) * link_graph
            )
            ranked.append({**item, "score": round(score, 4), "score_components": {
                "title_similarity": title_similarity,
                "tag_overlap": tag_overlap,
                "folder_proximity": folder_proximity,
                "link_graph": link_graph,
            }})
    ranked.sort(key=lambda x: -x["score"])
    emit({"success": True, "count": len(ranked[: args.limit]), "candidates": ranked[: args.limit]}, rt.json_mode)
    return 0


def cmd_summarize(rt: Runtime, args: argparse.Namespace) -> int:
    hits = search_notes(rt, args.topic, limit=args.limit)
    source_blob = []
    for hit in hits:
        snippet = hit.get("snippet") or hit.get("body_excerpt") or ""
        if snippet:
            source_blob.append(f"- {hit['path']}: {snippet}")
    summary = " ".join(source_blob[:3])[:1000]
    ai_payload = None
    if call_json_model is not None and source_blob:
        prompt = (
            "Summarize these Obsidian note excerpts for an agent. "
            "Return JSON with keys summary, bullets, gotchas. Cite source paths inline.\n\n"
            f"Topic: {args.topic}\n\n"
            + "\n".join(source_blob[: args.limit])
        )
        ai_payload = call_json_model(
            prompt,
            flag_name="AGENT_OBSIDIAN_SUMMARIZE_AI",
            max_tokens=4000,
            system="You summarize local notes using only provided excerpts. Return strict JSON only.",
        )
    if isinstance(ai_payload, dict) and ai_payload.get("summary"):
        summary = str(ai_payload.get("summary"))
    emit({
        "success": True,
        "topic": args.topic,
        "summary": summary,
        "bullets": ai_payload.get("bullets", []) if isinstance(ai_payload, dict) else [],
        "gotchas": ai_payload.get("gotchas", []) if isinstance(ai_payload, dict) else [],
        "ai_used": isinstance(ai_payload, dict),
        "sources": hits,
    }, rt.json_mode)
    return 0


def profile_from_args(rt: Runtime, role: str, args: argparse.Namespace) -> dict[str, Any]:
    if (
        role == "embedding"
        and not getattr(args, "provider", None)
        and not getattr(args, "model", None)
        and not getattr(args, "dimension", None)
    ):
        return effective_embedding_profile(rt)
    registry = model_registry(rt)
    profile = dict(registry.get(role) or {})
    provider_arg = getattr(args, "provider", None)
    if provider_arg:
        for candidate in registry.values():
            if (
                isinstance(candidate, dict)
                and candidate.get("provider") == provider_arg
                and candidate.get("env")
            ):
                profile = dict(candidate)
                break
        profile["provider"] = provider_arg
    if getattr(args, "model", None):
        profile["model"] = args.model
    if getattr(args, "dimension", None):
        profile["dimension"] = args.dimension
    return profile


def embedding_current_count(rt: Runtime, profile: dict[str, Any]) -> int:
    provider = str(profile.get("provider") or "")
    model = str(profile.get("model") or "")
    dimension = int(profile.get("dimension") or 0)
    with connect(rt) as conn:
        return int(
            conn.execute(
                """
                SELECT COUNT(*) FROM chunks c
                JOIN embeddings e ON e.chunk_id=c.chunk_id
                WHERE e.provider=? AND e.model=? AND e.dimension=? AND e.content_hash=c.content_hash
                """,
                (provider, model, dimension),
            ).fetchone()[0]
        )


def effective_embedding_profile(rt: Runtime) -> dict[str, Any]:
    primary = model_profile(rt, "embedding")
    fallback = model_profile(rt, "embedding_fallback")
    primary_count = embedding_current_count(rt, primary)
    fallback_count = embedding_current_count(rt, fallback)
    if fallback_count > 0 and primary_count == 0:
        return fallback
    if primary_count > 0 or credential_status(primary)["available"]:
        return primary
    if fallback_count > 0 or credential_status(fallback)["available"]:
        return fallback
    return primary


def embedding_status(rt: Runtime, profile: dict[str, Any]) -> dict[str, Any]:
    ensure_fresh(rt)
    provider = str(profile.get("provider") or "")
    model = str(profile.get("model") or "")
    dimension = int(profile.get("dimension") or 0)
    with connect(rt) as conn:
        total_chunks = int(conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
        current = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM chunks c
                JOIN embeddings e ON e.chunk_id=c.chunk_id
                WHERE e.provider=? AND e.model=? AND e.dimension=? AND e.content_hash=c.content_hash
                """,
                (provider, model, dimension),
            ).fetchone()[0]
        )
        by_model = [
            {
                "provider": row["provider"],
                "model": row["model"],
                "dimension": int(row["dimension"]),
                "count": int(row["count"]),
                "last_embedded_at": row["last_embedded_at"],
            }
            for row in conn.execute(
                """
                SELECT provider, model, dimension, COUNT(*) AS count, MAX(embedded_at) AS last_embedded_at
                FROM embeddings
                GROUP BY provider, model, dimension
                ORDER BY provider, model, dimension
                """
            )
        ]
    return {
        "provider": provider,
        "model": model,
        "dimension": dimension,
        "chunk_count": total_chunks,
        "current_embedding_count": current,
        "stale_embedding_count": max(0, total_chunks - current),
        "by_model": by_model,
        "credential": credential_status(profile),
    }


def cmd_embed(rt: Runtime, args: argparse.Namespace) -> int:
    if args.embed_cmd == "status":
        profile = profile_from_args(rt, "embedding", args)
        registry = model_registry(rt)
        emit(
            {
                "success": True,
                "registry": registry,
                "embedding": embedding_status(rt, profile),
            },
            rt.json_mode,
        )
        return 0
    if args.embed_cmd == "refresh":
        return cmd_embed_refresh(rt, args)
    raise AgentObsidianError("unknown embed command", code=NEEDS_CLARIFICATION)


def cmd_embed_refresh(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    profile = profile_from_args(rt, "embedding", args)
    provider = str(profile.get("provider") or "")
    model = str(profile.get("model") or "")
    dimension = int(profile.get("dimension") or 0)
    require_api_key(profile)
    started = time.time()
    with connect(rt) as conn:
        if args.full:
            conn.execute(
                "DELETE FROM embeddings WHERE provider=? AND model=? AND dimension=?",
                (provider, model, dimension),
            )
            conn.commit()
        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT c.*
                FROM chunks c
                LEFT JOIN embeddings e
                  ON e.chunk_id=c.chunk_id
                 AND e.provider=?
                 AND e.model=?
                 AND e.dimension=?
                 AND e.content_hash=c.content_hash
                WHERE e.chunk_id IS NULL
                ORDER BY c.note_path, c.ordinal
                """,
                (provider, model, dimension),
            )
        ]
    embedded = 0
    for batch in embedding_batches(rows, profile):
        vectors = embed_texts(profile, [item["text"] for item in batch], input_type="document")
        if len(vectors) != len(batch):
            raise AgentObsidianError("embedding provider returned wrong number of vectors", code=1)
        with connect(rt) as conn:
            for item, vector in zip(batch, vectors):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO embeddings
                    (chunk_id,provider,model,dimension,content_hash,embedding_json,embedded_at)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        item["chunk_id"],
                        provider,
                        model,
                        dimension,
                        item["content_hash"],
                        json.dumps(vector, ensure_ascii=False),
                        utc_now(),
                    ),
                )
                embedded += 1
            conn.commit()
    status = embedding_status(rt, profile)
    emit(
        {
            "success": True,
            "provider": provider,
            "model": model,
            "dimension": dimension,
            "embedded": embedded,
            "runtime_ms": int((time.time() - started) * 1000),
            "status": status,
        },
        rt.json_mode,
    )
    return 0


def hydrate_candidate_text(rt: Runtime, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    ids = [item["chunk_id"] for item in candidates]
    placeholders = ",".join("?" for _ in ids)
    with connect(rt) as conn:
        rows = {
            row["chunk_id"]: row
            for row in conn.execute(
                f"""
                SELECT c.*, n.folder, n.scope
                FROM chunks c JOIN notes n ON n.path=c.note_path
                WHERE c.chunk_id IN ({placeholders})
                """,
                ids,
            )
        }
    hydrated = []
    for item in candidates:
        row = rows.get(item["chunk_id"])
        full = dict(item)
        if row:
            full["text"] = row["text"]
            full["citation"] = f"{row['note_path']}:{row['start_line']}-{row['end_line']}"
        hydrated.append(full)
    return hydrated


def build_context_payload(rt: Runtime, query: str, *, limit: int, mode: str) -> dict[str, Any]:
    candidates = hydrate_candidate_text(rt, search_chunks(rt, query, limit=limit, mode=mode))
    blocks = []
    sources = []
    for item in candidates:
        citation = item.get("citation") or f"{item['path']}:{item.get('start_line')}-{item.get('end_line')}"
        blocks.append(f"[{citation}] {item.get('heading_path') or item.get('title')}\n{item.get('text') or item.get('snippet')}")
        sources.append(
            {
                "path": item["path"],
                "title": item["title"],
                "chunk_id": item["chunk_id"],
                "heading_path": item.get("heading_path"),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
                "score": item.get("score"),
                "score_components": item.get("score_components"),
            }
        )
    return {
        "success": True,
        "query": query,
        "mode": mode,
        "count": len(candidates),
        "context": "\n\n---\n\n".join(blocks),
        "sources": sources,
    }


def cmd_context(rt: Runtime, args: argparse.Namespace) -> int:
    if args.context_cmd != "build":
        raise AgentObsidianError("unknown context command", code=NEEDS_CLARIFICATION)
    payload = build_context_payload(rt, args.query, limit=args.limit, mode=args.mode)
    emit(payload, rt.json_mode)
    return 0


def extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    texts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict):
                text = content.get("text") or content.get("value")
                if text:
                    texts.append(str(text))
    return "\n".join(texts).strip()


def call_synthesis_model(profile: dict[str, Any], question: str, context: str) -> dict[str, Any]:
    provider = str(profile.get("provider") or "")
    if provider != "openai":
        raise AgentObsidianError(f"unsupported synthesis provider: {provider}", code=NEEDS_CLARIFICATION)
    key = require_api_key(profile)
    prompt = (
        "Answer the question using only the Obsidian vault context below. "
        "Cite source brackets exactly as provided. If the context is insufficient, say what is missing.\n\n"
        f"Question:\n{question}\n\nVault context:\n{context}"
    )
    payload = {
        "model": profile.get("model"),
        "input": prompt,
        "reasoning": {"effort": profile.get("reasoning_effort") or "high"},
        "text": {"verbosity": "medium"},
    }
    response = api_json(
        "https://api.openai.com/v1/responses",
        payload,
        {"Authorization": f"Bearer {key}"},
    )
    return {"model": profile.get("model"), "raw": response, "answer": extract_openai_text(response)}


def cmd_chat(rt: Runtime, args: argparse.Namespace) -> int:
    context_payload = build_context_payload(rt, args.question, limit=args.limit, mode=args.mode)
    synthesis = call_synthesis_model(model_profile(rt, "synthesis"), args.question, context_payload["context"])
    record = {
        "created_at": utc_now(),
        "question": args.question,
        "mode": args.mode,
        "model": synthesis["model"],
        "answer": synthesis["answer"],
        "sources": context_payload["sources"],
    }
    chat_path = rt.obsidian_root / "chat" / f"{utc_now().replace(':', '').replace('-', '')}.jsonl"
    with chat_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    emit({"success": True, "answer": synthesis["answer"], "model": synthesis["model"], "sources": context_payload["sources"], "conversation_path": str(chat_path)}, rt.json_mode)
    return 0


def cmd_connections(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    note_path = resolve_note_path(rt, args.name, None)
    with connect(rt) as conn:
        row = conn.execute("SELECT * FROM notes WHERE path=?", (note_path,)).fetchone()
        if not row:
            raise AgentObsidianError(f"note not found: {args.name}", code=1)
        query = f"{row['title']}\n{row['body']}"
    candidates = [item for item in search_chunks(rt, query, limit=max(args.limit + 1, args.limit * 2), mode=args.mode) if item["path"] != note_path]
    emit({"success": True, "path": note_path, "mode": args.mode, "count": len(candidates[: args.limit]), "connections": candidates[: args.limit]}, rt.json_mode)
    return 0


def cmd_daily(rt: Runtime, args: argparse.Namespace) -> int:
    cfg = load_conventions(rt)
    folder = folder_from_token(cfg, "daily")
    date = args.date or today()
    path = rt.vault / folder / f"{date}.md"
    if args.daily_cmd == "read":
        return cmd_read(rt, argparse.Namespace(name=None, path=relpath(path, rt.vault) if path.exists() else str(Path(folder) / f"{date}.md")))
    if args.daily_cmd == "append":
        if not path.exists():
            write_note_file(path, {"title": date, "created": date, "scope": "local"}, f"# {date}\n", overwrite=False)
        return cmd_append(rt, argparse.Namespace(target=relpath(path, rt.vault), content=args.content, path_mode=True, section=args.section))
    if args.daily_cmd == "list":
        return list_periodic(rt, folder, args.since, args.limit)
    raise AgentObsidianError("unknown daily command", code=NEEDS_CLARIFICATION)


def list_periodic(rt: Runtime, folder: str, since: str | None, limit: int) -> int:
    ensure_fresh(rt)
    with connect(rt) as conn:
        rows = [row_to_note(r) for r in conn.execute("SELECT * FROM notes WHERE folder=? ORDER BY path DESC LIMIT ?", (folder, limit))]
    emit({"success": True, "count": len(rows), "notes": rows}, rt.json_mode)
    return 0


def cmd_weekly(rt: Runtime, args: argparse.Namespace) -> int:
    cfg = load_conventions(rt)
    folder = folder_from_token(cfg, "weekly")
    if args.weekly_cmd == "list":
        return list_periodic(rt, folder, args.since, args.limit)
    date = args.date or today()
    year, week, _ = dt.date.fromisoformat(date).isocalendar()
    path = rt.vault / folder / f"{year}-W{week:02d}.md"
    if args.weekly_cmd == "read":
        return cmd_read(rt, argparse.Namespace(name=None, path=relpath(path, rt.vault)))
    if args.weekly_cmd == "append":
        if not path.exists():
            write_note_file(path, {"title": f"{year}-W{week:02d}", "created": today(), "scope": "local"}, "", overwrite=False)
        return cmd_append(rt, argparse.Namespace(target=relpath(path, rt.vault), content=args.content, path_mode=True, section=args.section))
    raise AgentObsidianError("unknown weekly command", code=NEEDS_CLARIFICATION)


def cmd_period(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    start = dt.datetime.fromisoformat(args.date_from).timestamp()
    end = dt.datetime.fromisoformat(args.date_to).replace(hour=23, minute=59, second=59).timestamp()
    with connect(rt) as conn:
        rows = [
            row_to_note(r)
            for r in conn.execute("SELECT * FROM notes WHERE mtime_ns BETWEEN ? AND ? ORDER BY mtime_ns DESC", (int(start * 1e9), int(end * 1e9)))
        ]
    emit({"success": True, "count": len(rows), "notes": rows}, rt.json_mode)
    return 0


def cmd_prop(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    if args.prop_cmd == "list":
        path = resolve_note_path(rt, args.file, None)
        text = (rt.vault / path).read_text(encoding="utf-8")
        fm, _ = parse_frontmatter(text)
        emit({"success": True, "path": path, "frontmatter": fm}, rt.json_mode)
        return 0
    path = resolve_note_path(rt, args.file, None)
    abs_path = rt.vault / path
    fm, body = parse_frontmatter(abs_path.read_text(encoding="utf-8"))
    if args.prop_cmd == "get":
        emit({"success": True, "path": path, "name": args.name, "value": fm.get(args.name)}, rt.json_mode)
        return 0
    if args.prop_cmd == "set":
        with write_lock(rt, "prop set", [path]):
            fm[args.name] = args.value
            abs_path.write_text(render_note(fm, body), encoding="utf-8")
            record = full_note_record(rt, abs_path)
        emit({"success": True, "record": record}, rt.json_mode)
        return 0
    if args.prop_cmd == "batch":
        return prop_batch(rt, args)
    raise AgentObsidianError("unknown prop command", code=NEEDS_CLARIFICATION)


def prop_batch(rt: Runtime, args: argparse.Namespace) -> int:
    fields = parse_key_values(args.set_values)
    matches = search_notes(rt, args.query, limit=10000)
    changed = []
    with write_lock(rt, "prop batch", [m["path"] for m in matches]):
        for item in matches:
            path = rt.vault / item["path"]
            fm, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            fm.update(fields)
            if not args.dry_run:
                path.write_text(render_note(fm, body), encoding="utf-8")
                full_note_record(rt, path)
            changed.append(item["path"])
    emit({"success": True, "dry_run": args.dry_run, "count": len(changed), "paths": changed}, rt.json_mode)
    return 0


def cmd_templates(rt: Runtime, args: argparse.Namespace) -> int:
    root = rt.obsidian_root / "templates"
    root.mkdir(parents=True, exist_ok=True)
    if args.templates_cmd == "list":
        items = sorted(p.stem for p in root.glob("*.md"))
        emit({"success": True, "count": len(items), "templates": items}, rt.json_mode)
        return 0
    if args.templates_cmd == "show":
        path = root / f"{args.name}.md"
        if not path.exists():
            raise AgentObsidianError(f"template not found: {args.name}", code=1)
        schema = root / f"{args.name}.yaml"
        emit({"success": True, "name": args.name, "content": path.read_text(encoding="utf-8"), "schema": load_yaml_file(schema)}, rt.json_mode)
        return 0
    if args.templates_cmd == "register":
        source = Path(args.source).expanduser()
        if not source.exists():
            raise AgentObsidianError(f"source template not found: {source}", code=1)
        shutil.copyfile(source, root / f"{args.name}.md")
        if args.param_schema:
            shutil.copyfile(Path(args.param_schema).expanduser(), root / f"{args.name}.yaml")
        emit({"success": True, "name": args.name, "path": str(root / f"{args.name}.md")}, rt.json_mode)
        return 0
    if args.templates_cmd == "apply":
        source = root / f"{args.name}.md"
        if not source.exists():
            raise AgentObsidianError(f"template not found: {args.name}", code=1)
        content = source.read_text(encoding="utf-8")
        for item in args.param or []:
            key, value = item.split("=", 1)
            content = content.replace("{{" + key + "}}", value)
        target = rt.vault / args.target
        with write_lock(rt, "templates apply", [relpath(target, rt.vault)]):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            record = full_note_record(rt, target)
        emit({"success": True, "record": record}, rt.json_mode)
        return 0
    raise AgentObsidianError("unknown templates command", code=NEEDS_CLARIFICATION)


def replace_wikilinks(text: str, old: str, new: str) -> str:
    def repl(match: re.Match[str]) -> str:
        target = match.group(1)
        if target == old or target.endswith("/" + old):
            return match.group(0).replace(target, new, 1)
        return match.group(0)

    return LINK_RE.sub(repl, text)


def make_operation(rt: Runtime, op: str, paths: list[Path]) -> tuple[str, Path, Path]:
    move_id = f"{op}-{int(time.time())}-{hashlib.sha1(str(paths).encode()).hexdigest()[:8]}"
    journal = rt.obsidian_root / "operations" / "journals" / f"{move_id}.jsonl"
    backup_dir = rt.obsidian_root / "operations" / "backups" / move_id
    backup_dir.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"phase": "preflight", "timestamp": utc_now(), "paths": [str(p) for p in paths]}) + "\n", encoding="utf-8")
    return move_id, journal, backup_dir


def append_journal(journal: Path, phase: str, payload: dict[str, Any]) -> None:
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"phase": phase, "timestamp": utc_now(), **payload}, ensure_ascii=False) + "\n")


def cmd_move(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    old_path_rel = resolve_note_path(rt, args.source, None)
    old_abs = rt.vault / old_path_rel
    new_rel = args.dest if args.dest.endswith(NOTE_SUFFIX) else f"{args.dest}.md"
    new_abs = rt.vault / new_rel
    old_stem = old_abs.stem
    new_stem = new_abs.stem
    files = [old_abs]
    if args.update_links:
        for path in note_files(rt.vault):
            if path == old_abs:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if f"[[{old_stem}" in text:
                files.append(path)
    preflight = {str(p): stat_payload(p) for p in files if p.exists()}
    with write_lock(rt, "move", [relpath(p, rt.vault) for p in files]):
        move_id, journal, backup_dir = make_operation(rt, "move", files)
        try:
            for path in files:
                if not path.exists():
                    continue
                current = path.stat()
                before = preflight[str(path)]
                if current.st_mtime_ns != before["mtime_ns"] or current.st_size != before["size"]:
                    raise AgentObsidianError("file changed since preflight", code=NEEDS_CLARIFICATION, path=relpath(path, rt.vault), move_id=move_id)
                backup = backup_dir / relpath(path, rt.vault)
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)
            new_abs.parent.mkdir(parents=True, exist_ok=True)
            old_abs.rename(new_abs)
            append_journal(journal, "apply-rename", {"from": old_path_rel, "to": new_rel})
            if args.update_links:
                for path in files:
                    if path == old_abs:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                    updated = replace_wikilinks(text, old_stem, new_stem)
                    if updated != text:
                        path.write_text(updated, encoding="utf-8")
                        append_journal(journal, "apply-link", {"path": relpath(path, rt.vault)})
            refresh(rt, full=False)
            append_journal(journal, "verify", {"ok": True})
        except Exception:
            for backup in sorted(backup_dir.rglob("*")):
                if backup.is_file():
                    target = rt.vault / backup.relative_to(backup_dir)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, target)
            if new_abs.exists() and not old_abs.exists():
                with contextlib.suppress(Exception):
                    new_abs.rename(old_abs)
            append_journal(journal, "rollback", {"ok": True})
            raise
    emit({"success": True, "move_id": move_id, "from": old_path_rel, "to": new_rel, "updated_links": args.update_links}, rt.json_mode)
    return 0


def cmd_delete(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    note_path = resolve_note_path(rt, args.name, None)
    if not args.confirm:
        with connect(rt) as conn:
            backlink_count = int(conn.execute("SELECT COUNT(*) FROM links WHERE resolved_path=?", (note_path,)).fetchone()[0])
        raise AgentObsidianError("delete requires --confirm", code=NEEDS_CLARIFICATION, path=note_path, backlink_count=backlink_count)
    src = rt.vault / note_path
    trash = rt.vault / ".trash" / note_path
    with write_lock(rt, "delete", [note_path]):
        trash.parent.mkdir(parents=True, exist_ok=True)
        src.rename(trash)
        refresh(rt, full=False)
    emit({"success": True, "deleted": note_path, "trash_path": relpath(trash, rt.vault)}, rt.json_mode)
    return 0


def cmd_graph(rt: Runtime, args: argparse.Namespace) -> int:
    ensure_fresh(rt)
    with connect(rt) as conn:
        if args.graph_cmd == "broken-links":
            rows = [dict(r) for r in conn.execute("SELECT * FROM links WHERE COALESCE(resolved_path,'') = '' ORDER BY src_path,target_name")]
            emit({"success": True, "count": len(rows), "links": rows}, rt.json_mode)
            return 0
        if args.graph_cmd == "orphans":
            rows = [
                row_to_note(r)
                for r in conn.execute(
                    """
                    SELECT n.* FROM notes n
                    LEFT JOIN links l ON l.resolved_path=n.path
                    WHERE l.src_path IS NULL
                    ORDER BY n.path
                    """
                )
            ]
            if args.folder:
                rows = [r for r in rows if r["folder"].startswith(args.folder)]
            emit({"success": True, "count": len(rows), "notes": rows}, rt.json_mode)
            return 0
        if args.graph_cmd == "tag-usage":
            rows = [row_to_note(r) for r in conn.execute("SELECT n.* FROM tags t JOIN notes n ON n.path=t.note_path WHERE t.tag=? ORDER BY n.path", (args.tag.lstrip("#"),))]
            emit({"success": True, "tag": args.tag, "count": len(rows), "notes": rows}, rt.json_mode)
            return 0
        if args.graph_cmd in {"clusters", "cluster"}:
            return graph_clusters(rt, args)
    raise AgentObsidianError("unknown graph command", code=NEEDS_CLARIFICATION)


def graph_clusters(rt: Runtime, args: argparse.Namespace) -> int:
    with connect(rt) as conn:
        nodes = {r["path"] for r in conn.execute("SELECT path FROM notes")}
        edges: dict[str, set[str]] = {n: set() for n in nodes}
        for row in conn.execute("SELECT src_path,resolved_path FROM links WHERE COALESCE(resolved_path,'') <> ''"):
            edges.setdefault(row["src_path"], set()).add(row["resolved_path"])
            edges.setdefault(row["resolved_path"], set()).add(row["src_path"])
    if args.graph_cmd == "cluster":
        start = resolve_note_path(rt, args.name, None)
        depth = args.depth
        seen = {start}
        frontier = {start}
        for _ in range(depth):
            nxt = set()
            for node in frontier:
                nxt |= edges.get(node, set())
            nxt -= seen
            seen |= nxt
            frontier = nxt
        emit({"success": True, "root": start, "count": len(seen), "notes": sorted(seen)}, rt.json_mode)
        return 0
    clusters = []
    unseen = set(nodes)
    while unseen:
        start = unseen.pop()
        component = {start}
        frontier = {start}
        while frontier:
            node = frontier.pop()
            for nxt in edges.get(node, set()):
                if nxt in unseen:
                    unseen.remove(nxt)
                    component.add(nxt)
                    frontier.add(nxt)
        if len(component) >= args.min_size:
            clusters.append(sorted(component))
    clusters.sort(key=len, reverse=True)
    emit({"success": True, "count": len(clusters), "clusters": [{"size": len(c), "notes": c} for c in clusters]}, rt.json_mode)
    return 0


def audit_findings(rt: Runtime, scope: str | None = None) -> list[dict[str, Any]]:
    ensure_fresh(rt)
    findings: list[dict[str, Any]] = []
    with connect(rt) as conn:
        for row in conn.execute("SELECT * FROM links WHERE COALESCE(resolved_path,'') = '' ORDER BY src_path,target_name"):
            findings.append({
                "id": hashlib.sha1(f"broken:{row['src_path']}:{row['target_name']}".encode()).hexdigest()[:12],
                "kind": "broken-link",
                "severity": "medium",
                "path": row["src_path"],
                "target": row["target_name"],
                "status": "open",
            })
        for row in conn.execute("SELECT n.* FROM notes n LEFT JOIN links l ON l.resolved_path=n.path WHERE l.src_path IS NULL"):
            note = row_to_note(row)
            if scope and not note["folder"].startswith(scope):
                continue
            findings.append({
                "id": hashlib.sha1(f"orphan:{note['path']}".encode()).hexdigest()[:12],
                "kind": "orphan-note",
                "severity": "low",
                "path": note["path"],
                "status": "open",
            })
        for row in conn.execute("SELECT * FROM notes"):
            note = row_to_note(row)
            if scope and not note["folder"].startswith(scope):
                continue
            if not note["frontmatter"]:
                findings.append({
                    "id": hashlib.sha1(f"frontmatter:{note['path']}".encode()).hexdigest()[:12],
                    "kind": "missing-frontmatter",
                    "severity": "low",
                    "path": note["path"],
                    "status": "open",
                })
    return findings


def write_audit_ledger(rt: Runtime, findings: list[dict[str, Any]]) -> Path:
    ledger = rt.agent_root / "context" / "ledger" / "vault-audit.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        for finding in findings:
            fh.write(json.dumps({"timestamp": utc_now(), "first_seen": utc_now(), **finding}, ensure_ascii=False) + "\n")
    return ledger


def cmd_audit(rt: Runtime, args: argparse.Namespace) -> int:
    if args.audit_cmd == "fix":
        if not args.issue_id:
            raise AgentObsidianError("audit fix requires <issue-id>", code=NEEDS_CLARIFICATION)
        return audit_fix(rt, args.issue_id, dry_run=args.dry_run)
    findings = audit_findings(rt, args.scope)
    ledger = write_audit_ledger(rt, findings)
    emit({"success": True, "count": len(findings), "findings": findings, "ledger": str(ledger)}, rt.json_mode)
    return 0


def audit_fix(rt: Runtime, issue_id: str, *, dry_run: bool) -> int:
    findings = audit_findings(rt)
    finding = next((item for item in findings if item["id"] == issue_id), None)
    if not finding:
        raise AgentObsidianError(f"audit finding not found: {issue_id}", code=1)
    kind = finding.get("kind")
    path = finding.get("path")
    if kind == "missing-frontmatter" and path:
        abs_path = rt.vault / str(path)
        text = abs_path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        if not fm:
            fm = {"title": abs_path.stem, "created": today(), "scope": "local"}
        if dry_run:
            emit({"success": True, "dry_run": True, "finding": finding, "would_set": fm}, rt.json_mode)
            return 0
        with write_lock(rt, "audit fix", [str(path)]):
            abs_path.write_text(render_note(fm, body), encoding="utf-8")
            record = full_note_record(rt, abs_path)
        emit({"success": True, "fixed": issue_id, "record": record}, rt.json_mode)
        return 0
    if kind == "broken-link":
        raise AgentObsidianError(
            "broken-link fixes require an explicit target; use move --update-links or edit the note",
            code=NEEDS_CLARIFICATION,
            finding=finding,
        )
    if kind == "orphan-note":
        raise AgentObsidianError(
            "orphan-note findings require editorial judgment; add related/up links explicitly",
            code=NEEDS_CLARIFICATION,
            finding=finding,
        )
    raise AgentObsidianError(f"no safe automatic fix for finding kind: {kind}", code=NEEDS_CLARIFICATION, finding=finding)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-obsidian-local", add_help=False)
    parser.add_argument("--vault")
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    sub.add_parser("snapshot")
    p = sub.add_parser("refresh")
    p.add_argument("--full", action="store_true")
    p.add_argument("--verbose", action="store_true")

    p = sub.add_parser("read")
    p.add_argument("name", nargs="?")
    p.add_argument("--path")
    p.add_argument("--copy", action="store_true")

    p = sub.add_parser("search")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--folder", default="")
    p.add_argument("--tag", default="")
    p.add_argument("--mode", choices=["keyword", "fts", "exact", "semantic", "hybrid"], default="keyword")
    p.add_argument("--total", action="store_true")

    p = sub.add_parser("embed")
    ep = p.add_subparsers(dest="embed_cmd", required=True)
    es = ep.add_parser("status")
    es.add_argument("--provider")
    es.add_argument("--model")
    es.add_argument("--dimension", type=int)
    er = ep.add_parser("refresh")
    er.add_argument("--full", action="store_true")
    er.add_argument("--provider")
    er.add_argument("--model")
    er.add_argument("--dimension", type=int)

    p = sub.add_parser("context")
    cp = p.add_subparsers(dest="context_cmd", required=True)
    cb = cp.add_parser("build")
    cb.add_argument("query")
    cb.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    cb.add_argument("--limit", type=int, default=12)

    p = sub.add_parser("chat")
    p.add_argument("question")
    p.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    p.add_argument("--limit", type=int, default=12)

    p = sub.add_parser("connections")
    p.add_argument("name")
    p.add_argument("--mode", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("save")
    p.add_argument("--content", required=True)
    p.add_argument("--title")
    p.add_argument("--folder")
    p.add_argument("--up")
    p.add_argument("--related")
    p.add_argument("--tags", nargs="*")
    p.add_argument("--scope", default="local", choices=["local", "team", "public"])
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("save-group")
    p.add_argument("hub_name")
    p.add_argument("--child", action="append")
    p.add_argument("--folder")
    p.add_argument("--tags", nargs="*")
    p.add_argument("--scope", default="local", choices=["local", "team", "public"])
    p.add_argument("--child-scope", action="append")
    p.add_argument("--overwrite", action="store_true")

    p = sub.add_parser("create")
    p.add_argument("name")
    p.add_argument("--content")
    p.add_argument("--template")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--open", action="store_true")

    p = sub.add_parser("append")
    p.add_argument("target")
    p.add_argument("--content", required=True)
    p.add_argument("--path", dest="path_mode", action="store_true")
    p.add_argument("--section")

    p = sub.add_parser("backlinks")
    p.add_argument("name")

    p = sub.add_parser("tags")
    p.add_argument("tags_cmd", nargs="?", default="list", choices=["list", "rename", "merge"])
    p.add_argument("from_tag", nargs="?")
    p.add_argument("to_tag", nargs="?")
    p.add_argument("from_tags", nargs="*")
    p.add_argument("--counts", action="store_true")
    p.add_argument("--total", action="store_true")
    p.add_argument("--sort", choices=["name", "count"], default="name")
    p.add_argument("--prefix")

    p = sub.add_parser("tasks")
    task_sub = p.add_subparsers(dest="task_cmd", required=True)
    for name in ("list", "todo", "done"):
        tp = task_sub.add_parser(name)
        tp.set_defaults(task_cmd="list")
        tp.add_argument("--status", default="open" if name == "todo" else "done" if name == "done" else "")
        tp.add_argument("--priority", default="")
        tp.add_argument("--due-before", default="")
        tp.add_argument("--due-after", default="")
        tp.add_argument("--project", default="")
        tp.add_argument("--tag", default="")
        tp.add_argument("--folder", default="")
        tp.add_argument("--sort", default="due,priority")
        tp.add_argument("--limit", type=int, default=50)
        tp.add_argument("--daily", action="store_true")
    tp = task_sub.add_parser("next")
    tp.add_argument("--context", default="")
    tp.add_argument("--horizon", default="today", choices=["today", "week", "month"])
    tp.add_argument("--limit", type=int, default=10)
    tp.add_argument("--status", default="open")
    tp.add_argument("--priority", default="")
    tp.add_argument("--due-before", default="")
    tp.add_argument("--due-after", default="")
    tp.add_argument("--project", default="")
    tp.add_argument("--tag", default="")
    tp.add_argument("--folder", default="")
    tp.add_argument("--sort", default="due,priority")
    tp = task_sub.add_parser("add")
    tp.add_argument("text")
    tp.add_argument("--priority")
    tp.add_argument("--due")
    tp.add_argument("--scheduled")
    tp.add_argument("--project")
    tp.add_argument("--tags", nargs="*")
    tp.add_argument("--resonance", type=int, default=0)
    tp.add_argument("--into")
    tp.add_argument("--style", choices=["inline", "frontmatter"])
    tp = task_sub.add_parser("complete")
    tp.add_argument("id")
    tp = task_sub.add_parser("update")
    tp.add_argument("id")
    tp.add_argument("--set", dest="set_values", nargs="+", required=True)

    p = sub.add_parser("query")
    p.add_argument("query")
    p.add_argument("--limit", type=int)

    p = sub.add_parser("relate")
    p.add_argument("content_or_name")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--scope", default="vault")

    p = sub.add_parser("summarize")
    p.add_argument("topic")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--style", choices=["brief", "long"], default="brief")

    p = sub.add_parser("daily")
    dp = p.add_subparsers(dest="daily_cmd", required=True)
    d = dp.add_parser("read")
    d.add_argument("--date")
    d = dp.add_parser("append")
    d.add_argument("text", nargs="*")
    d.add_argument("--content")
    d.add_argument("--date")
    d.add_argument("--section")
    d.set_defaults(content=None)
    d = dp.add_parser("list")
    d.add_argument("--since")
    d.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("weekly")
    wp = p.add_subparsers(dest="weekly_cmd", required=True)
    w = wp.add_parser("read")
    w.add_argument("--date")
    w = wp.add_parser("append")
    w.add_argument("text", nargs="*")
    w.add_argument("--content")
    w.add_argument("--date")
    w.add_argument("--section")
    w = wp.add_parser("list")
    w.add_argument("--since")
    w.add_argument("--limit", type=int, default=30)

    p = sub.add_parser("period")
    p.add_argument("period_cmd", choices=["read"])
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)

    p = sub.add_parser("prop")
    pp = p.add_subparsers(dest="prop_cmd", required=True)
    pg = pp.add_parser("get")
    pg.add_argument("name")
    pg.add_argument("--file", required=True)
    ps = pp.add_parser("set")
    ps.add_argument("name")
    ps.add_argument("value")
    ps.add_argument("--file", required=True)
    pl = pp.add_parser("list")
    pl.add_argument("file")
    pb = pp.add_parser("batch")
    pb.add_argument("query")
    pb.add_argument("--set", dest="set_values", nargs="+", required=True)
    pb.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("templates")
    tsp = p.add_subparsers(dest="templates_cmd", required=True)
    tsp.add_parser("list")
    ts = tsp.add_parser("show")
    ts.add_argument("name")
    tr = tsp.add_parser("register")
    tr.add_argument("name")
    tr.add_argument("--from", dest="source", required=True)
    tr.add_argument("--param-schema")
    ta = tsp.add_parser("apply")
    ta.add_argument("name")
    ta.add_argument("--target", required=True)
    ta.add_argument("--param", action="append")

    p = sub.add_parser("move")
    p.add_argument("source")
    p.add_argument("dest")
    p.add_argument("--update-links", action="store_true")

    p = sub.add_parser("delete")
    p.add_argument("name")
    p.add_argument("--confirm", action="store_true")

    p = sub.add_parser("graph")
    gp = p.add_subparsers(dest="graph_cmd", required=True)
    go = gp.add_parser("orphans")
    go.add_argument("--folder")
    gp.add_parser("broken-links")
    gc = gp.add_parser("clusters")
    gc.add_argument("--min-size", type=int, default=2)
    gcl = gp.add_parser("cluster")
    gcl.add_argument("name")
    gcl.add_argument("--depth", type=int, default=2)
    gt = gp.add_parser("tag-usage")
    gt.add_argument("tag")

    p = sub.add_parser("audit")
    p.add_argument("audit_cmd", nargs="?", default="run", choices=["run", "fix"])
    p.add_argument("issue_id", nargs="?")
    p.add_argument("--scope")
    p.add_argument("--dry-run", action="store_true")
    return parser


def normalize_args(args: argparse.Namespace) -> argparse.Namespace:
    if getattr(args, "command", "") == "search":
        args.query = " ".join(args.query)
    if getattr(args, "command", "") == "daily" and getattr(args, "daily_cmd", "") == "append":
        args.content = args.content if args.content is not None else " ".join(args.text)
    if getattr(args, "command", "") == "weekly" and getattr(args, "weekly_cmd", "") == "append":
        args.content = args.content if args.content is not None else " ".join(args.text)
    return args


def run(rt: Runtime, args: argparse.Namespace) -> int:
    cmd = args.command
    if cmd == "doctor":
        return cmd_doctor(rt, args)
    if cmd == "snapshot":
        return cmd_snapshot(rt, args)
    if cmd == "refresh":
        return cmd_refresh(rt, args)
    if cmd == "read":
        return cmd_read(rt, args)
    if cmd == "search":
        return cmd_search(rt, args)
    if cmd == "embed":
        return cmd_embed(rt, args)
    if cmd == "context":
        return cmd_context(rt, args)
    if cmd == "chat":
        return cmd_chat(rt, args)
    if cmd == "connections":
        return cmd_connections(rt, args)
    if cmd == "save":
        return cmd_save(rt, args)
    if cmd == "save-group":
        return cmd_save_group(rt, args)
    if cmd == "create":
        return cmd_create(rt, args)
    if cmd == "append":
        return cmd_append(rt, args)
    if cmd == "backlinks":
        return cmd_backlinks(rt, args)
    if cmd == "tags":
        return cmd_tags(rt, args)
    if cmd == "tasks":
        return cmd_tasks(rt, args)
    if cmd == "query":
        return cmd_query(rt, args)
    if cmd == "relate":
        return cmd_relate(rt, args)
    if cmd == "summarize":
        return cmd_summarize(rt, args)
    if cmd == "daily":
        return cmd_daily(rt, args)
    if cmd == "weekly":
        return cmd_weekly(rt, args)
    if cmd == "period":
        return cmd_period(rt, args)
    if cmd == "prop":
        return cmd_prop(rt, args)
    if cmd == "templates":
        return cmd_templates(rt, args)
    if cmd == "move":
        return cmd_move(rt, args)
    if cmd == "delete":
        return cmd_delete(rt, args)
    if cmd == "graph":
        return cmd_graph(rt, args)
    if cmd == "audit":
        return cmd_audit(rt, args)
    raise AgentObsidianError(f"unknown command: {cmd}", code=NEEDS_CLARIFICATION)


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = normalize_args(parser.parse_args(argv))
    vault = resolve_vault(args.vault)
    if vault is None:
        return NO_LOCAL_VAULT
    repo_root = Path(__file__).resolve().parents[2]
    rt = Runtime(vault=vault, json_mode=args.json, repo_root=repo_root)
    try:
        return run(rt, args)
    except AgentObsidianError as exc:
        return fail(exc.message, code=exc.code, json_mode=rt.json_mode, **exc.payload)
    except KeyboardInterrupt:
        return fail("interrupted", code=1, json_mode=rt.json_mode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
