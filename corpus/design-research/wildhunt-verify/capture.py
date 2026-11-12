#!/usr/bin/env python3
"""Capture through the existing agent-do browse production surface only."""
import datetime
import hashlib
import json
import os
import subprocess
from pathlib import Path
from PIL import Image
from recover import HERE, ROOT
from catalog import write_json


def parse_reply(verb, stdout):
    # The existing CLI deliberately emits text for this lifecycle verb.
    if verb == "close" and stdout.strip() == "Browser closed":
        return {"success": True, "data": {"closed": True}}
    return json.loads(stdout)


def main():
    config = json.loads((HERE / "config.json").read_text())
    corpus = json.loads((HERE / "corpus.json").read_text())
    env = dict(os.environ, AGENT_BROWSER_SESSION="wildhunt-c2d546-01a0825b")
    receipts = []
    def browse(*args):
        command = [str(ROOT / "agent-do"), "browse", *map(str, args)]
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=config["browser_timeout_seconds"])
        value = parse_reply(args[0], proc.stdout)
        receipts.append({"verb": args[0], "success": value.get("success"), "returncode": proc.returncode, "stderr": proc.stderr})
        if proc.returncode or not value.get("success"):
            raise RuntimeError(f"browse {args[0]} failed: {proc.stderr} {proc.stdout}")
        return value.get("data", {})
    # Existing session is ours; launch is idempotent. Never restart a failed path.
    browse("launch")
    for row in corpus["specimens"]:
        if row.get("exclude_reason") or not row.get("html"):
            continue
        historical = row.get("image") and (ROOT / row["image"]).exists()
        width, extent = Image.open(ROOT / row["image"]).size if historical else config["fixture_viewport"]
        # Full-page image height is not the viewport height. Source galleries use
        # 1440x900 or 1920x1080; the larger viewport is the browser's observed default.
        viewport_height = config["fixture_viewport"][1] if width == config["fixture_viewport"][0] else 1080
        browse("viewport", width, viewport_height)
        browse("open", (ROOT / row["html"]).resolve().as_uri())
        probe = browse("eval", (HERE / "probe.js").read_text())["result"]
        if probe["url"] != (ROOT / row["html"]).resolve().as_uri():
            raise RuntimeError("Probe navigated away from intended specimen")
        if row["kind"] == "fixture":
            target = ROOT / row["image"]
            target.parent.mkdir(parents=True, exist_ok=True)
            browse("screenshot", target, "--full")
            width, extent = Image.open(target).size
            row["image_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        probe["historical_extent"] = [width, extent]
        probe["all_node_count"] = len(probe["nodes"])
        probe["nodes"] = [n for n in probe["nodes"] if n["x"] < width and n["x"] + n["width"] > 0 and n["y"] < extent and n["y"] + n["height"] > 0]
        probe["node_count"] = len(probe["nodes"])
        probe["captured_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        probe["source_html_sha256"] = hashlib.sha256((ROOT / row["html"]).read_bytes()).hexdigest()
        target = ROOT / ".dev/dpt-wildhunt/probes" / (row["id"] + ".json")
        write_json(target, probe)
        row["probe"] = str(target.relative_to(ROOT))
        row["probe_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(row["id"], "nodes", probe["node_count"], "extent", width, extent, flush=True)
    write_json(HERE / "corpus-measured.json", corpus)
    browse("close")
    write_json(HERE / "capture-receipts.json", {"session": env["AGENT_BROWSER_SESSION"], "operations": receipts})


if __name__ == "__main__":
    main()
