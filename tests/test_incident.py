#!/usr/bin/env python3
"""Offline coordinator contracts for incident packets."""
from __future__ import annotations
import importlib.util, json, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("incident_tracker",ROOT/"lib"/"incident_tracker.py")
tracker=importlib.util.module_from_spec(spec); sys.modules["incident_tracker"]=tracker; spec.loader.exec_module(tracker)
def ok(argv,data): return {"ok":True,"argv":argv,"data":data}
def fake(argv):
 if argv[:2]==["ci","runs"]: return ok(argv,[{"databaseId":42,"createdAt":datetime.now(timezone.utc).isoformat()}])
 if argv[:2]==["ci","details"]: return ok(argv,{"run":{"id":42,"head_sha":"a"*40,"conclusion":"failure","timestamps":{"updated_at":"2026-10-13T00:00:00Z"}}})
 if argv[:2]==["gh","commit"]: return ok(argv,{"commit":{"sha":"a"*40}})
 if argv[:2]==["k8s","deployment"]: return ok(argv,{"deployment":{"images":["app@sha256:x"],"replicas":{"ready":0}},"pods":[{"name":"p1","containers":[{"name":"app","ready":False,"restart_count":2,"waiting_reason":"CrashLoopBackOff"}]}]})
 if argv[:2]==["k8s","events"]: return ok(argv,{"events":[]})
 if argv[:2]==["render","trace"]: return ok(argv,{"deploys":[{"id":"d1","commit_sha":"a"*40,"status":"live"}]})
 if argv[:2] in (["ci","logs"],["k8s","logs"]): return ok(argv,{"log":"safe"})
 raise AssertionError(argv)
def test_trace_calls_only_allowlist_and_writes_packet():
 config={"services":{"payments":{"github":{"repository":"o/r","workflow":"deploy.yml"},"kubernetes":{"context":"prod","namespace":"pay","deployment":"payments","container":"app"},"render":{"service":"srv"}}}}
 with tempfile.TemporaryDirectory() as d,patch.object(tracker,"dispatch",side_effect=fake) as call:
  base=Path(d); (base/"traces").mkdir(); result=tracker.trace(base,config,"payments",None,"30m",None)
  packet=json.loads((Path(result["path"])/"trace.json").read_text())
  assert packet["summary"]["correlations"][0]["strength"]=="exact"
  assert (Path(result["path"])/"k8s-logs-previous.json").is_file()
  assert all(argv[0] in {"ci","gh","k8s","render"} and "--json" in argv for argv in (x.args[0] for x in call.call_args_list))
def test_config_rejects_spacelift(tmp_path:Path):
 root=tmp_path/".agent-do-incident"; root.mkdir(); (root/"config.yaml").write_text("version: 1\nservices:\n  x:\n    spacelift: {}\n")
 try: tracker.load_config(tmp_path)
 except tracker.IncidentError: return
 raise AssertionError("accepted unsupported source")
def test_config_rejects_alias(tmp_path:Path):
 root=tmp_path/".agent-do-incident"; root.mkdir(); (root/"config.yaml").write_text("version: 1\nservices: &x {}\n")
 try: tracker.load_config(tmp_path)
 except tracker.IncidentError: return
 raise AssertionError("accepted YAML alias")
def test_redacts_nested_credential_fields():
 value={"access_token":"example-token", "nested":[{"authorization":"Bearer private", "api_key":"private", "status":"ok"}], "message":"password=private", "log":"Authorization: Bearer private"}
 assert tracker.redact(value)=={"access_token":"[REDACTED]", "nested":[{"authorization":"[REDACTED]", "api_key":"[REDACTED]", "status":"ok"}], "message":"password=[REDACTED]", "log":"Authorization: [REDACTED]"}
if __name__=="__main__":
 test_trace_calls_only_allowlist_and_writes_packet(); test_config_rejects_spacelift(Path(tempfile.mkdtemp())); test_config_rejects_alias(Path(tempfile.mkdtemp())); test_redacts_nested_credential_fields(); print("incident tests passed")
