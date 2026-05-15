#!/usr/bin/env bash

# HTML capture and extraction helpers for agent-context.

_context_is_html_response() {
  local headers_file="$1"
  local content_file="$2"

  if [[ -f "$headers_file" ]] && grep -qiE '^content-type:.*text/html|^content-type:.*application/xhtml\+xml' "$headers_file"; then
    return 0
  fi

  if [[ -f "$content_file" ]] && LC_ALL=C head -c 1024 "$content_file" | grep -qiE '<!doctype html|<html[[:space:]>]'; then
    return 0
  fi

  return 1
}

_context_store_html_file() {
  local source_url="$1"
  local html_file="$2"
  local headers_file="$3"
  local dest_dir="$4"

  python3 - "$source_url" "$html_file" "$headers_file" "$dest_dir" <<'PY'
import datetime as _dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import re
import shutil
import sys
from urllib.parse import urljoin


source_url, html_file, headers_file, dest_dir = sys.argv[1:5]


class Extractor(HTMLParser):
    skip_tags = {"script", "style", "noscript", "svg", "canvas", "iframe"}
    block_tags = {"p", "li", "blockquote", "pre", "code", "td", "th", "caption"}
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.skip_depth = 0
        self.title_mode = False
        self.title_parts = []
        self.meta_description = ""
        self.canonical_url = ""
        self.headings = []
        self.links = []
        self.blocks = []
        self.current_tag = None
        self.current_parts = []
        self.current_heading = None
        self.current_href = None
        self.current_link_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if tag == "title":
            self.title_mode = True
        elif tag == "meta" and attrs.get("name", "").lower() == "description":
            self.meta_description = _clean(attrs.get("content", ""))
        elif tag == "link" and attrs.get("rel", "").lower() == "canonical" and attrs.get("href"):
            self.canonical_url = urljoin(self.base_url, attrs["href"])
        elif tag == "a" and attrs.get("href"):
            self.current_href = urljoin(self.base_url, attrs["href"])
            self.current_link_text = []
        elif tag in self.heading_tags:
            self.current_tag = tag
            self.current_parts = []
            self.current_heading = tag
        elif tag in self.block_tags:
            self.current_tag = tag
            self.current_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return

        if tag == "title":
            self.title_mode = False
        elif tag == "a" and self.current_href:
            text = _clean(" ".join(self.current_link_text))
            if text:
                self.links.append({"text": text[:180], "url": self.current_href})
            self.current_href = None
            self.current_link_text = []
        elif tag == self.current_tag:
            text = _clean(" ".join(self.current_parts))
            if text:
                if self.current_heading:
                    self.headings.append({"level": int(self.current_heading[1]), "text": text})
                    self.blocks.append({"kind": "heading", "level": int(self.current_heading[1]), "text": text})
                elif tag in {"pre", "code"}:
                    self.blocks.append({"kind": "code", "text": text})
                else:
                    self.blocks.append({"kind": "text", "text": text})
            self.current_tag = None
            self.current_parts = []
            self.current_heading = None

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.title_mode:
            self.title_parts.append(data)
        if self.current_tag:
            self.current_parts.append(data)
        if self.current_href:
            self.current_link_text.append(data)


def _clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _render_text(page):
    lines = []
    title = page.get("title") or page.get("url")
    lines.append(f"# {title}")
    lines.append(f"Source: {page.get('url')}")
    if page.get("canonical_url") and page.get("canonical_url") != page.get("url"):
        lines.append(f"Canonical: {page.get('canonical_url')}")
    if page.get("description"):
        lines.append("")
        lines.append(page["description"])

    for block in page.get("blocks", []):
        text = block.get("text", "")
        if not text:
            continue
        lines.append("")
        if block.get("kind") == "heading":
            level = max(1, min(6, int(block.get("level", 2))))
            lines.append(f"{'#' * level} {text}")
        elif block.get("kind") == "code":
            lines.extend(["```", text, "```"])
        else:
            lines.append(text)
    return "\n".join(lines).strip() + "\n"


with open(html_file, "rb") as fh:
    raw_bytes = fh.read()

raw_text = raw_bytes.decode("utf-8", errors="replace")
parser = Extractor(source_url)
parser.feed(raw_text)
title = _clean(" ".join(parser.title_parts)) or source_url
page = {
    "url": source_url,
    "canonical_url": parser.canonical_url or source_url,
    "title": title,
    "description": parser.meta_description,
    "headings": parser.headings,
    "links": parser.links,
    "blocks": parser.blocks,
    "content_hash": hashlib.sha256(raw_bytes).hexdigest(),
    "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
}

os.makedirs(dest_dir, exist_ok=True)
raw_dir = os.path.join(dest_dir, "raw")
os.makedirs(raw_dir, exist_ok=True)
shutil.copyfile(html_file, os.path.join(raw_dir, "raw.html"))
if os.path.exists(headers_file) and os.path.abspath(headers_file) != os.path.abspath(os.path.join(dest_dir, "headers.txt")):
    shutil.copyfile(headers_file, os.path.join(dest_dir, "headers.txt"))

with open(os.path.join(dest_dir, "content.md"), "w", encoding="utf-8") as fh:
    fh.write(_render_text(page))
with open(os.path.join(dest_dir, "extracted.json"), "w", encoding="utf-8") as fh:
    json.dump(page, fh, indent=2, sort_keys=True)
with open(os.path.join(dest_dir, "metadata.json"), "w", encoding="utf-8") as fh:
    json.dump(
        {
            "source_url": source_url,
            "canonical_url": page["canonical_url"],
            "title": title,
            "description": parser.meta_description,
            "content_hash": page["content_hash"],
            "format": "html",
            "fetched_at": page["fetched_at"],
        },
        fh,
        indent=2,
        sort_keys=True,
    )
PY
}

_context_crawl_html_site() {
  local start_url="$1"
  local dest_dir="$2"
  local limit="${3:-20}"

  python3 - "$start_url" "$dest_dir" "$limit" <<'PY'
import datetime as _dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen


start_url, dest_dir, limit_raw = sys.argv[1:4]
limit = max(1, int(limit_raw or 20))
USER_AGENT = "agent-do-context/1.0 (+https://github.com/ovachiever/agent-do)"


class Extractor(HTMLParser):
    skip_tags = {"script", "style", "noscript", "svg", "canvas", "iframe"}
    block_tags = {"p", "li", "blockquote", "pre", "code", "td", "th", "caption"}
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.skip_depth = 0
        self.title_mode = False
        self.title_parts = []
        self.meta_description = ""
        self.canonical_url = ""
        self.headings = []
        self.links = []
        self.blocks = []
        self.current_tag = None
        self.current_parts = []
        self.current_heading = None
        self.current_href = None
        self.current_link_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in self.skip_tags:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.title_mode = True
        elif tag == "meta" and attrs.get("name", "").lower() == "description":
            self.meta_description = clean(attrs.get("content", ""))
        elif tag == "link" and attrs.get("rel", "").lower() == "canonical" and attrs.get("href"):
            self.canonical_url = normalize_url(urljoin(self.base_url, attrs["href"]))
        elif tag == "a" and attrs.get("href"):
            self.current_href = normalize_url(urljoin(self.base_url, attrs["href"]))
            self.current_link_text = []
        elif tag in self.heading_tags:
            self.current_tag = tag
            self.current_parts = []
            self.current_heading = tag
        elif tag in self.block_tags:
            self.current_tag = tag
            self.current_parts = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.title_mode = False
        elif tag == "a" and self.current_href:
            text = clean(" ".join(self.current_link_text))
            if text:
                self.links.append({"text": text[:180], "url": self.current_href})
            self.current_href = None
            self.current_link_text = []
        elif tag == self.current_tag:
            text = clean(" ".join(self.current_parts))
            if text:
                if self.current_heading:
                    level = int(self.current_heading[1])
                    self.headings.append({"level": level, "text": text})
                    self.blocks.append({"kind": "heading", "level": level, "text": text})
                elif tag in {"pre", "code"}:
                    self.blocks.append({"kind": "code", "text": text})
                else:
                    self.blocks.append({"kind": "text", "text": text})
            self.current_tag = None
            self.current_parts = []
            self.current_heading = None

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.title_mode:
            self.title_parts.append(data)
        if self.current_tag:
            self.current_parts.append(data)
        if self.current_href:
            self.current_link_text.append(data)


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_url(url):
    url = urldefrag(url)[0]
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.path == "":
        parsed = parsed._replace(path="/")
    return parsed.geturl()


def same_origin(url):
    a = urlparse(start_url)
    b = urlparse(url)
    return a.scheme == b.scheme and a.netloc == b.netloc


def crawl_worthy(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    if not same_origin(url):
        return False
    if any(path.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".zip", ".tar.gz", ".pdf"]):
        return False
    start_path = urlparse(start_url).path.rstrip("/")
    if start_path and path.startswith(start_path.lower().rstrip("/") + "/"):
        return True
    docs_terms = ("/docs", "/guide", "/learn", "/api", "/reference", "/manual", "/tutorial", "/getting-started")
    return not path or path == "/" or any(term in path for term in docs_terms)


def fetch(url):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.5"})
    with urlopen(req, timeout=15) as response:
        status = getattr(response, "status", 200)
        headers = dict(response.headers.items())
        content_type = headers.get("Content-Type", headers.get("content-type", ""))
        raw = response.read(2_500_000)
    text = raw.decode("utf-8", errors="replace")
    is_html = "html" in content_type.lower() or bool(re.search(r"<(?:!doctype html|html)[\s>]", text[:2048], re.I))
    if not is_html:
        raise ValueError(f"not html: {content_type}")
    parser = Extractor(url)
    parser.feed(text)
    title = clean(" ".join(parser.title_parts)) or url
    page = {
        "url": url,
        "status": status,
        "content_type": content_type,
        "headers": headers,
        "canonical_url": parser.canonical_url or url,
        "title": title,
        "description": parser.meta_description,
        "headings": parser.headings,
        "links": [link for link in parser.links if link.get("url")],
        "blocks": parser.blocks,
        "content_hash": hashlib.sha256(raw).hexdigest(),
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "raw_html": text,
    }
    return page


def page_text(page):
    lines = [f"# {page.get('title') or page['url']}", f"Source: {page['url']}"]
    if page.get("canonical_url") and page["canonical_url"] != page["url"]:
        lines.append(f"Canonical: {page['canonical_url']}")
    if page.get("description"):
        lines += ["", page["description"]]
    for block in page.get("blocks", []):
        text = block.get("text", "")
        if not text:
            continue
        lines.append("")
        if block.get("kind") == "heading":
            level = max(1, min(6, int(block.get("level", 2))))
            lines.append(f"{'#' * level} {text}")
        elif block.get("kind") == "code":
            lines += ["```", text, "```"]
        else:
            lines.append(text)
    return "\n".join(lines).strip() + "\n"


os.makedirs(dest_dir, exist_ok=True)
pages_dir = os.path.join(dest_dir, "pages")
raw_dir = os.path.join(dest_dir, "raw")
os.makedirs(pages_dir, exist_ok=True)
os.makedirs(raw_dir, exist_ok=True)

queue = [normalize_url(start_url)]
seen = set()
pages = []
errors = []

while queue and len(seen) < limit:
    batch = []
    while queue and len(seen) + len(batch) < limit and len(batch) < 6:
        url = normalize_url(queue.pop(0))
        if not url or url in seen or not crawl_worthy(url):
            continue
        seen.add(url)
        batch.append(url)
    if not batch:
        continue

    with ThreadPoolExecutor(max_workers=min(4, len(batch))) as executor:
        futures = {executor.submit(fetch, url): url for url in batch}
        for future in as_completed(futures):
            url = futures[future]
            try:
                page = future.result()
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
                errors.append({"url": url, "error": str(exc)})
                continue
            pages.append(page)
            for link in page.get("links", []):
                linked = normalize_url(link.get("url", ""))
                if linked and linked not in seen and linked not in queue and crawl_worthy(linked):
                    queue.append(linked)
    time.sleep(0.05)

if not pages:
    raise SystemExit("no html pages fetched")

pages.sort(key=lambda page: (0 if page["url"] == normalize_url(start_url) else 1, page["url"]))

aggregate = []
safe_pages = []
for index, page in enumerate(pages, start=1):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", urlparse(page["url"]).path.strip("/") or "index").strip("-") or "index"
    page_dir = os.path.join(pages_dir, f"{index:03d}-{slug[:80]}")
    os.makedirs(page_dir, exist_ok=True)
    with open(os.path.join(page_dir, "raw.html"), "w", encoding="utf-8") as fh:
        fh.write(page.pop("raw_html"))
    text = page_text(page)
    with open(os.path.join(page_dir, "content.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(os.path.join(page_dir, "metadata.json"), "w", encoding="utf-8") as fh:
        json.dump(page, fh, indent=2, sort_keys=True)
    aggregate.append(text)
    safe_pages.append(page)

with open(os.path.join(dest_dir, "content.md"), "w", encoding="utf-8") as fh:
    fh.write("\n\n---\n\n".join(aggregate))
with open(os.path.join(dest_dir, "extracted.json"), "w", encoding="utf-8") as fh:
    json.dump({"start_url": normalize_url(start_url), "pages": safe_pages}, fh, indent=2, sort_keys=True)
with open(os.path.join(dest_dir, "crawl.json"), "w", encoding="utf-8") as fh:
    json.dump(
        {
            "start_url": normalize_url(start_url),
            "page_count": len(safe_pages),
            "errors": errors,
            "limit": limit,
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        },
        fh,
        indent=2,
        sort_keys=True,
    )
with open(os.path.join(dest_dir, "metadata.json"), "w", encoding="utf-8") as fh:
    first = safe_pages[0]
    json.dump(
        {
            "source_url": normalize_url(start_url),
            "canonical_url": first.get("canonical_url", normalize_url(start_url)),
            "title": first.get("title") or normalize_url(start_url),
            "description": first.get("description", ""),
            "content_hash": hashlib.sha256("\n".join(p.get("content_hash", "") for p in safe_pages).encode()).hexdigest(),
            "format": "html-site",
            "page_count": len(safe_pages),
            "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        },
        fh,
        indent=2,
        sort_keys=True,
    )
PY
}

cmd_crawl() {
  local url="${1:-}"
  if [[ -z "$url" || "$url" == "-h" || "$url" == "--help" ]]; then
    cat <<'EOF'
Usage: agent-context crawl <url> [--source-name NAME] [--limit N] [--trust N] [--tags csv]

Crawl a bounded same-origin HTML documentation site, preserve raw HTML, extract
readable text/metadata, and index the extracted content.
EOF
    return 0
  fi
  shift || true

  local source_name=""
  local limit="${CONTEXT_DEFAULT_CRAWL_LIMIT:-20}"
  local trust="0.85"
  local tags=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source-name)
        source_name="${2:-}"
        shift 2
        ;;
      --limit)
        limit="${2:-20}"
        shift 2
        ;;
      --trust)
        trust="${2:-0.85}"
        shift 2
        ;;
      --tags)
        tags="${2:-}"
        shift 2
        ;;
      *)
        echo "Unknown option: $1" >&2
        return 2
        ;;
    esac
  done

  ensure_init

  local identity="$url"
  local name="$url"
  if [[ -n "$source_name" ]]; then
    identity="$source_name"
    name="$source_name"
  fi

  local id pkg_dir title="" description="" canonical="" content_hash="" token_count
  id="$(make_id "$identity")"
  pkg_dir="$CONTEXT_CACHE_DIR/fetched/$id"
  mkdir -p "$pkg_dir"
  rm -rf "$pkg_dir/pages" "$pkg_dir/raw" "$pkg_dir/content.md" "$pkg_dir/extracted.json" "$pkg_dir/crawl.json" "$pkg_dir/metadata.json"

  if ! _context_crawl_html_site "$url" "$pkg_dir" "$limit"; then
    return 1
  fi

  if [[ -f "$pkg_dir/metadata.json" ]]; then
    title="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("title",""))' "$pkg_dir/metadata.json")"
    description="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("description",""))' "$pkg_dir/metadata.json")"
    canonical="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("canonical_url",""))' "$pkg_dir/metadata.json")"
    content_hash="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("content_hash",""))' "$pkg_dir/metadata.json")"
  fi

  [[ -n "${title:-}" ]] && name="${source_name:-$title}"
  token_count="$(_context_count_tree_tokens "$pkg_dir")"
  write_meta "$pkg_dir" "$name" "html-site" "$description" "$url" "$token_count" "$trust" "$tags"
  _index_package "$id" "$name" "html-site" "$description" "$tags" "$trust" "$token_count" "$pkg_dir" "$url"
  python3 - "$CONTEXT_INDEX_DB" "$id" "$limit" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect(sys.argv[1])
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute("UPDATE package_meta SET crawl_limit = ? WHERE id = ?", (int(sys.argv[3]), sys.argv[2]))
conn.commit()
conn.close()
PY

  cat <<EOF
Fetched HTML site:
  ID: $id
  Name: $name
  URL: $url
  Limit: $limit
  Cache: $pkg_dir
EOF
}
