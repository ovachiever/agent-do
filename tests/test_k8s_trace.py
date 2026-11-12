#!/usr/bin/env python3
"""Offline contract tests for the incident-safe Kubernetes trace commands."""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
def output(value):
    print(json.dumps(value))
    raise SystemExit(0)

if "logs" in args:
    print(os.environ.get("FAKE_LOG", "started token=top-secret\nfinished"))
    raise SystemExit(0)

if "--raw" in args:
    output({"metadata": {}, "items": [{"type": "Warning", "reason": "BackOff", "message": "secret=top-secret", "count": 5,
                       "lastTimestamp": "2026-10-12T00:00:00Z", "involvedObject": {"uid": "pod-1", "kind": "Pod", "name": "payments-abc-x"}}]})

resource = args[args.index("get") + 1]
if resource == "deployment":
    output({"metadata": {"name": "payments", "uid": "dep-1", "generation": 8,
                         "labels": {"app": "payments"},
                         "annotations": {"deployment.kubernetes.io/revision": "12", "token": "top-secret"}},
            "spec": {"replicas": 3, "selector": {"matchLabels": {"app": "payments"}},
                     "template": {"spec": {"containers": [{"name": "web", "image": "api:12"}]}}},
            "status": {"observedGeneration": 8, "updatedReplicas": 3, "readyReplicas": 2, "availableReplicas": 2}})
if resource == "replicasets":
    output({"items": [{"metadata": {"name": "payments-abc", "uid": "rs-1", "annotations": {"deployment.kubernetes.io/revision": "12"},
                                    "ownerReferences": [{"uid": "dep-1", "controller": True}]},
                       "spec": {"template": {"spec": {"containers": [{"image": "api:12"}]}}}}]})
if resource == "pods":
    output({"items": [{"metadata": {"name": "payments-abc-x", "uid": "pod-1", "ownerReferences": [{"uid": "rs-1", "controller": True}]},
                       "spec": {"nodeName": "node-a"},
                       "status": {"phase": "Running", "conditions": [{"type": "Ready", "status": "False", "message": "token=top-secret"}],
                                  "containerStatuses": [{"name": "web", "ready": False, "restartCount": 4,
                                                         "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "password=hunter2"}},
                                                         "lastState": {"terminated": {"reason": "Error", "exitCode": 1}}}]}}]})
if resource == "events":
    output({"items": [{"type": "Warning", "reason": "BackOff", "message": "secret=top-secret", "count": 5,
                       "lastTimestamp": "2026-10-12T00:00:00Z", "involvedObject": {"uid": "pod-1", "kind": "Pod", "name": "payments-abc-x"}}]})
raise SystemExit("unexpected resource: " + resource)
'''


class K8sTraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        fake = pathlib.Path(self.temp.name) / "kubectl"
        fake.write_text(FAKE_KUBECTL)
        fake.chmod(0o755)
        self.env = os.environ | {"AGENT_DO_KUBECTL_BIN": str(fake)}

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(ROOT / "tools" / "agent-k8s"), *args], text=True, capture_output=True, env=self.env, check=False)

    def json_command(self, *args: str) -> dict:
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_deployment_collects_only_read_facts_and_redacts_messages(self):
        data = self.json_command("deployment", "payments", "--context", "aks-prod", "--namespace", "pay", "--json")
        self.assertTrue(data["success"])
        self.assertEqual(data["context"], "aks-prod")
        self.assertEqual(data["deployment"]["revision"], "12")
        self.assertEqual(data["pods"][0]["containers"][0]["restart_count"], 4)
        self.assertNotIn("top-secret", json.dumps(data))
        self.assertNotIn("hunter2", json.dumps(data))

    def test_events_follow_deployment_ownership(self):
        data = self.json_command("events", "--for-deployment", "payments", "--context", "aks-prod", "--namespace", "pay", "--json")
        self.assertEqual(data["events"][0]["object"]["uid"], "pod-1")
        self.assertIn("[REDACTED]", data["events"][0]["message"])

    def test_logs_are_bounded_redacted_and_can_request_previous_instance(self):
        data = self.json_command("logs", "payments-abc-x", "--container", "web", "--previous", "--context", "aks-prod", "--namespace", "pay", "--tail", "2", "--max-bytes", "64", "--json")
        self.assertTrue(data["previous"])
        self.assertTrue(data["redaction"]["applied"])
        self.assertNotIn("top-secret", data["log"])
        self.assertTrue(data["truncated"]["line_limit_applied"])

    def test_invalid_duration_returns_structured_error(self):
        result = self.run_tool("logs", "pod", "--container", "web", "--context", "aks-prod", "--namespace", "pay", "--since", "forever", "--json")
        self.assertNotEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertFalse(data["success"])
        self.assertIn("--since", data["error"])

    def test_byte_limit_reports_provider_truncation_after_redaction_shrinks_log(self):
        secret = "x" * 80
        self.env["FAKE_LOG"] = "token=" + secret
        size = len((self.env["FAKE_LOG"] + "\n").encode())
        data = self.json_command("logs", "pod", "--container", "web", "--context", "aks-prod", "--namespace", "pay", "--max-bytes", str(size), "--json")
        self.assertTrue(data["truncated"]["bytes"])
        self.assertNotIn(secret, data["log"])


if __name__ == "__main__":
    unittest.main()
