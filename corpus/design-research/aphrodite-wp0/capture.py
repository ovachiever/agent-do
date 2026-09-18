#!/usr/bin/env python3
"""Capture only through the existing agent-do browse CLI and an isolated session."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from bench import DEFAULT, HERE, ROOT, read, sha, stamp, verify, write
from model import bind, chord, score, separation
from render import render

PINS = [
    ("001", "https://recognitionoracle.com"), ("002", "https://every.to"),
    ("003", "https://www.pangram.com"), ("004", "https://petespasta.com"),
    ("005", "https://us.sneakenergy.com"), ("006", "https://teenage.engineering"),
    ("007", "https://attio.com"), ("008", "https://daylightcomputer.com"),
    ("009", "https://tally.so"), ("010", "https://culturedcode.com/things/"),
    ("011", "https://kagi.com"), ("012", "https://readwise.io")]

PRIME = """(async()=>{let steps=0, reached=false;
for(;steps<40;steps++){const height=document.documentElement.scrollHeight;
window.scrollTo(0, Math.min((steps+1)*innerHeight*.8,height));
await new Promise(r=>setTimeout(r,180));
if(scrollY+innerHeight>=document.documentElement.scrollHeight-2){reached=true;steps++;break;}}
window.scrollTo(0,0);await new Promise(r=>setTimeout(r,600));
return {steps,max_steps:40,reached_bottom:reached,height:document.documentElement.scrollHeight,full_visual_coverage_verified:false};})()"""


class Browser:
    def __init__(self, purpose):
        self.session = "aphrodite-wp0-75f010-" + purpose
        self.receipts = []

    def call(self, verb, *args):
        result = subprocess.run([str(ROOT / "agent-do"), "browse", verb, *map(str,args)],
                                cwd=ROOT, env=dict(os.environ, AGENT_BROWSER_SESSION=self.session),
                                capture_output=True, text=True, timeout=55)
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError:
            if verb == "close" and result.stdout.strip() == "Browser closed":
                value = {"success": True, "data": {"closed": True}}
            else:
                raise RuntimeError(f"Invalid browse {verb} response: {result.stdout[:500]}")
        self.receipts.append({"at": stamp(), "verb": verb, "returncode": result.returncode,
                              "success": value.get("success"), "stderr": result.stderr[:1500],
                              "error": value.get("error")})
        if result.returncode or not value.get("success"):
            raise RuntimeError(f"browse {verb}: {json.dumps(value)[:1200]}")
        return value.get("data", {})


def compare(out):
    verify(out)
    render(out)
    spec, model = read(out / "source/comparison.json"), read(out / "source/model.json")
    browser = Browser("comparison")
    rows = {}
    try:
        browser.call("launch")
        browser.call("viewport", *spec["viewport"])
        for label, expected in spec["variants"].items():
            path = out / "comparison" / (label + ".html")
            browser.call("open", path.resolve().as_uri())
            probe = browser.call("eval", (HERE / "probe.js").read_text())["result"]
            if probe["url"] != path.resolve().as_uri():
                raise ValueError("Unexpected comparison navigation")
            h, b = probe["measure"]["heading"], probe["measure"]["support"]
            gap = separation(h,b)
            if abs(gap-expected["gap"]) > .01 or h["font_size"] != expected["heading_size"]:
                raise ValueError("Rendered intervention does not match frozen factors")
            if probe["viewport"] != spec["viewport"] or probe["document"][0] > probe["viewport"][0]:
                raise ValueError("Viewport or horizontal overflow failure")
            if h["text"] != spec["copy"]["title"] or b["text"] != spec["copy"]["description"]:
                raise ValueError("Required comparison copy changed")
            probe["captured_at"] = stamp()
            shot = out / "captures" / (label + ".png")
            shot.parent.mkdir(parents=True, exist_ok=True)
            browser.call("screenshot", shot, "--full")
            write(out / "comparison" / (label + ".probe.json"), probe)
            rows[label] = {"observed_heading_size": h["font_size"], "observed_support_size": b["font_size"], "observed_gap": gap,
                           "F03_pair": chord(gap,h["font_size"],b["font_size"],model["parameters"]),
                           "whole_page": score(bind(probe,model),model), "html_sha256": sha(path), "shot_sha256": sha(shot)}
            print("captured comparison",label,flush=True)
    finally:
        browser.call("close")
        write(out / "comparison/capture-receipts.json", {"session": browser.session, "operations": browser.receipts})
    write(out / "comparison/predictions.json", {"recorded_at": stamp(), "source_spec_sha256": sha(out / "source/comparison.json"),
                                                "rows": rows, "human_response": spec["human_response"]})
    return {"captured": list(rows), "human_response": "pending"}


def pins(out):
    verify(out)
    browser = Browser("pins")
    model = read(out / "source/model.json")
    results = []
    try:
        browser.call("launch")
        browser.call("viewport", 1440, 1000)
        for number, url in PINS:
            row = {"id": "live-pins-2026-09-14/"+number, "original_pin": number,
                   "requested_url": url, "new_human_approval": False, "status": "attempting"}
            try:
                browser.call("open", url)
                row["scroll"] = browser.call("eval", PRIME)["result"]
                probe = browser.call("eval", (HERE / "probe.js").read_text())["result"]
                probe["captured_at"] = stamp()
                probe["new_observation_not_historic_match"] = True
                dest = out / "pins" / number
                dest.mkdir(parents=True, exist_ok=True)
                write(dest / "probe.json", probe)
                browser.call("screenshot", dest / "page.png", "--full")
                row.update(status="captured", captured_at=probe["captured_at"], actual_url=probe["url"], title=probe["title"],
                           body_text_length=probe["body_text_length"], nodes=probe["node_count"], extent=probe["document"],
                           unloaded_images=sum(not i["complete"] or i["width"]==0 for i in probe["images"]),
                           probe_sha256=sha(dest / "probe.json"), shot_sha256=sha(dest / "page.png"),
                           full_visual_coverage_verified=False)
                if not probe["body_text_length"]:
                    row["status"] = "empty_capture"
                try:
                    graph = bind(probe,model)
                    write(dest / "graph.json", graph)
                    computed = score(graph,model)
                    write(dest / "score.json", computed)
                    row["score_status"], row["B"] = computed["status"], computed["B"]
                except ValueError as error:
                    row["score_status"], row["score_error"] = "invalid_observation", str(error)
            except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
                row.update(status="capture_failed", error=str(error))
            results.append(row)
            write(out / "pins/INDEX.json", {"session": browser.session, "rows": results, "attempts_planned": len(PINS)})
            write(out / "pins/capture-receipts.json", {"session": browser.session, "operations": browser.receipts})
            print(number,row["status"],row.get("nodes"),flush=True)
    finally:
        browser.call("close")
        write(out / "pins/capture-receipts.json", {"session": browser.session, "operations": browser.receipts})
    return {"attempts": len(results), "captured": sum(r["status"]=="captured" for r in results)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["comparison","pins"])
    parser.add_argument("--out",type=Path,default=DEFAULT)
    args=parser.parse_args()
    print(json.dumps({"comparison":compare,"pins":pins}[args.command](args.out),indent=2))


if __name__ == "__main__":
    main()
