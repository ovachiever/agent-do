#!/usr/bin/env python3
"""Focused coverage for the root notify contract."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DO = ROOT / "agent-do"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def make_exec(path: Path, contents: str) -> None:
    path.write_text(contents)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(cmd: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        stub = tmp_path / "agent-do-provider-stub"
        log_path = tmp_path / "notify-calls.jsonl"

        make_exec(
            stub,
            """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

log_path = Path(os.environ["NOTIFY_TEST_LOG"])
entry = {"argv": sys.argv[1:]}
with log_path.open("a") as f:
    f.write(json.dumps(entry) + "\\n")

provider = sys.argv[1]
fail = {item for item in os.environ.get("NOTIFY_TEST_FAIL", "").split(",") if item}
if provider in fail:
    print(f"{provider} failed", file=sys.stderr)
    raise SystemExit(1)

print(f"{provider} sent")
""",
        )

        env = dict(os.environ)
        env["AGENT_DO_HOME"] = str(fake_home)
        env["AGENT_DO_NOTIFY_AGENT_DO"] = str(stub)
        env["NOTIFY_TEST_LOG"] = str(log_path)

        help_result = run([str(AGENT_DO), "notify", "--help"], env=env)
        require(help_result.returncode == 0, f"notify help failed: {help_result.stderr}")
        require("Cross-provider notification contract" in help_result.stdout, f"unexpected notify help: {help_result.stdout}")

        providers = run([str(AGENT_DO), "notify", "providers", "--json"], env=env)
        require(providers.returncode == 0, f"notify providers failed: {providers.stderr}")
        providers_payload = json.loads(providers.stdout)
        require(
            [item["provider"] for item in providers_payload["providers"]] == ["email", "messenger", "pipe", "slack", "sms"],
            f"unexpected providers payload: {providers_payload}",
        )

        templates = run([str(AGENT_DO), "notify", "templates", "--json"], env=env)
        require(templates.returncode == 0, f"notify templates failed: {templates.stderr}")
        templates_payload = json.loads(templates.stdout)
        template_names = [item["name"] for item in templates_payload["templates"]]
        require(
            template_names == ["approval_needed", "build_failed", "deploy_done", "deploy_failed", "job_stalled"],
            f"unexpected template payload: {templates_payload}",
        )

        show_template = run([str(AGENT_DO), "notify", "show-template", "build_failed", "--json"], env=env)
        require(show_template.returncode == 0, f"show-template failed: {show_template.stderr}")
        show_template_payload = json.loads(show_template.stdout)
        require(show_template_payload["template"]["event"] == "build", f"unexpected show-template payload: {show_template_payload}")
        require(
            show_template_payload["template"]["required_facts"] == ["service", "branch", "status"],
            f"unexpected show-template payload: {show_template_payload}",
        )

        save = run(
            [
                str(AGENT_DO),
                "notify",
                "set-recipient",
                "me",
                "--sms",
                "+15551234567",
                "--email",
                "me@example.com",
                "--slack",
                "@erik",
                "--messenger",
                "https://www.messenger.com/t/example-thread",
                "--pipe",
                "cat >/tmp/notify.out",
                "--prefer",
                "sms,email,slack",
                "--subject",
                "Ops alert",
                "--json",
            ],
            env=env,
        )
        require(save.returncode == 0, f"set-recipient failed: {save.stderr}")
        save_payload = json.loads(save.stdout)
        require(save_payload["recipient"]["sms"] == "+15551234567", f"unexpected save payload: {save_payload}")
        require(save_payload["recipient"]["messenger"] == "https://www.messenger.com/t/example-thread", f"unexpected save payload: {save_payload}")

        backup_save = run(
            [
                str(AGENT_DO),
                "notify",
                "set-recipient",
                "backup",
                "--email",
                "backup@example.com",
                "--prefer",
                "email",
                "--subject",
                "Backup alert",
                "--json",
            ],
            env=env,
        )
        require(backup_save.returncode == 0, f"backup set-recipient failed: {backup_save.stderr}")
        backup_save_payload = json.loads(backup_save.stdout)
        require(backup_save_payload["recipient"]["email"] == "backup@example.com", f"unexpected backup recipient payload: {backup_save_payload}")

        recipients = run([str(AGENT_DO), "notify", "recipients", "--json"], env=env)
        require(recipients.returncode == 0, f"notify recipients failed: {recipients.stderr}")
        recipients_payload = json.loads(recipients.stdout)
        recipient_aliases = [item["alias"] for item in recipients_payload["recipients"]]
        require(recipient_aliases == ["backup", "me"], f"unexpected recipients payload: {recipients_payload}")

        set_group = run(
            [
                str(AGENT_DO),
                "notify",
                "set-group",
                "ops",
                "me",
                "backup",
                "--json",
            ],
            env=env,
        )
        require(set_group.returncode == 0, f"set-group failed: {set_group.stderr}")
        set_group_payload = json.loads(set_group.stdout)
        require(set_group_payload["group"]["members"] == ["me", "backup"], f"unexpected set-group payload: {set_group_payload}")

        groups = run([str(AGENT_DO), "notify", "groups", "--json"], env=env)
        require(groups.returncode == 0, f"notify groups failed: {groups.stderr}")
        groups_payload = json.loads(groups.stdout)
        require(groups_payload["groups"][0]["alias"] == "ops", f"unexpected groups payload: {groups_payload}")
        require(groups_payload["groups"][0]["members"] == ["me", "backup"], f"unexpected groups payload: {groups_payload}")

        show_group = run([str(AGENT_DO), "notify", "show-group", "ops", "--json"], env=env)
        require(show_group.returncode == 0, f"show-group failed: {show_group.stderr}")
        show_group_payload = json.loads(show_group.stdout)
        require(show_group_payload["group"]["members"] == ["me", "backup"], f"unexpected show-group payload: {show_group_payload}")

        apply_template = run(
            [
                str(AGENT_DO),
                "notify",
                "apply-template",
                "deploy_failed",
                "--name",
                "deploy_failed_prod",
                "--recipient",
                "me",
                "--via",
                "sms",
                "--match",
                "environment=prod",
                "--cooldown",
                "45m",
                "--json",
            ],
            env=env,
        )
        require(apply_template.returncode == 0, f"apply-template failed: {apply_template.stderr}")
        apply_template_payload = json.loads(apply_template.stdout)
        require(apply_template_payload["rule"]["event"] == "deploy", f"unexpected apply-template payload: {apply_template_payload}")
        require(apply_template_payload["rule"]["via"] == ["sms"], f"unexpected apply-template payload: {apply_template_payload}")
        require(apply_template_payload["rule"]["match"]["status"] == "failed", f"unexpected apply-template payload: {apply_template_payload}")
        require(apply_template_payload["rule"]["match"]["environment"] == "prod", f"unexpected apply-template payload: {apply_template_payload}")
        require(apply_template_payload["rule"]["cooldown_seconds"] == 2700, f"unexpected apply-template payload: {apply_template_payload}")

        set_rule = run(
            [
                str(AGENT_DO),
                "notify",
                "set-rule",
                "build_failed",
                "--recipient",
                "me",
                "--event",
                "build",
                "--message",
                "Build failed for {service} on {branch}",
                "--subject",
                "Build failed: {service}",
                "--via",
                "sms,email",
                "--match",
                "status=failed",
                "--match",
                "env=prod",
                "--fingerprint",
                "{service}:{branch}:{status}",
                "--cooldown",
                "1h",
                "--json",
            ],
            env=env,
        )
        require(set_rule.returncode == 0, f"set-rule failed: {set_rule.stderr}")
        set_rule_payload = json.loads(set_rule.stdout)
        require(set_rule_payload["rule"]["event"] == "build", f"unexpected set-rule payload: {set_rule_payload}")
        require(set_rule_payload["rule"]["cooldown_seconds"] == 3600, f"unexpected cooldown payload: {set_rule_payload}")

        group_rule = run(
            [
                str(AGENT_DO),
                "notify",
                "set-rule",
                "approval_group",
                "--recipient",
                "ops",
                "--event",
                "approval",
                "--message",
                "Approval needed for {item}",
                "--via",
                "sms,email",
                "--match",
                "status=needed",
                "--cooldown",
                "10m",
                "--json",
            ],
            env=env,
        )
        require(group_rule.returncode == 0, f"group rule failed: {group_rule.stderr}")

        rules = run([str(AGENT_DO), "notify", "rules", "--json"], env=env)
        require(rules.returncode == 0, f"notify rules failed: {rules.stderr}")
        rules_payload = json.loads(rules.stdout)
        rule_names = [item["name"] for item in rules_payload["rules"]]
        require(rule_names == ["approval_group", "build_failed", "deploy_failed_prod"], f"unexpected rules payload: {rules_payload}")

        show_rule = run([str(AGENT_DO), "notify", "show-rule", "build_failed", "--json"], env=env)
        require(show_rule.returncode == 0, f"show-rule failed: {show_rule.stderr}")
        show_rule_payload = json.loads(show_rule.stdout)
        require(show_rule_payload["rule"]["match"]["status"] == "failed", f"unexpected show-rule payload: {show_rule_payload}")

        dry_run = run([str(AGENT_DO), "notify", "me", "Build complete", "--dry-run", "--json"], env=env)
        require(dry_run.returncode == 0, f"notify dry-run failed: {dry_run.stderr}")
        dry_run_payload = json.loads(dry_run.stdout)
        require(dry_run_payload["dry_run"] is True, f"unexpected dry-run payload: {dry_run_payload}")
        require(dry_run_payload["attempts"][0]["provider"] == "sms", f"unexpected dry-run attempt order: {dry_run_payload}")

        sent = run([str(AGENT_DO), "notify", "me", "Build complete", "--json"], env=env)
        require(sent.returncode == 0, f"notify send failed: {sent.stderr}")
        sent_payload = json.loads(sent.stdout)
        require(sent_payload["success"] is True, f"unexpected notify send payload: {sent_payload}")
        require(sent_payload["attempts"][0]["provider"] == "sms", f"unexpected notify send attempt: {sent_payload}")

        group_send = run([str(AGENT_DO), "notify", "ops", "Team update", "--json"], env=env)
        require(group_send.returncode == 0, f"group send failed: {group_send.stderr}")
        group_send_payload = json.loads(group_send.stdout)
        require(group_send_payload["group"] == "ops", f"unexpected group send payload: {group_send_payload}")
        require(group_send_payload["success"] is True, f"unexpected group send payload: {group_send_payload}")
        require([item["recipient"] for item in group_send_payload["deliveries"]] == ["me", "backup"], f"unexpected group deliveries: {group_send_payload}")

        env["NOTIFY_TEST_FAIL"] = "sms"
        fallback = run([str(AGENT_DO), "notify", "me", "Need backup", "--json"], env=env)
        require(fallback.returncode == 0, f"notify fallback failed: {fallback.stderr}")
        fallback_payload = json.loads(fallback.stdout)
        require(len(fallback_payload["attempts"]) == 2, f"expected fallback attempts: {fallback_payload}")
        require(
            [attempt["provider"] for attempt in fallback_payload["attempts"]] == ["sms", "email"],
            f"unexpected fallback order: {fallback_payload}",
        )
        require(fallback_payload["attempts"][1]["success"] is True, f"expected email fallback success: {fallback_payload}")

        emit_nonmatch = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "build",
                "--fact",
                "service=api",
                "--fact",
                "branch=main",
                "--fact",
                "status=passed",
                "--fact",
                "env=prod",
                "--json",
            ],
            env=env,
        )
        require(emit_nonmatch.returncode == 0, f"emit nonmatch failed: {emit_nonmatch.stderr}")
        emit_nonmatch_payload = json.loads(emit_nonmatch.stdout)
        require(emit_nonmatch_payload["matched_rules"] == [], f"expected no matched rules: {emit_nonmatch_payload}")

        emit_dry_run = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "build",
                "--fact",
                "service=api",
                "--fact",
                "branch=main",
                "--fact",
                "status=failed",
                "--fact",
                "env=prod",
                "--dry-run",
                "--json",
            ],
            env=env,
        )
        require(emit_dry_run.returncode == 0, f"emit dry-run failed: {emit_dry_run.stderr}")
        emit_dry_run_payload = json.loads(emit_dry_run.stdout)
        require(len(emit_dry_run_payload["matched_rules"]) == 1, f"expected matched rule: {emit_dry_run_payload}")
        require(emit_dry_run_payload["results"][0]["planned"] is True, f"expected planned emit result: {emit_dry_run_payload}")
        require(
            emit_dry_run_payload["results"][0]["notification"]["attempts"][0]["provider"] == "sms",
            f"unexpected emit attempt order: {emit_dry_run_payload}",
        )

        del env["NOTIFY_TEST_FAIL"]
        group_emit = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "approval",
                "--fact",
                "item=database migration",
                "--fact",
                "status=needed",
                "--json",
            ],
            env=env,
        )
        require(group_emit.returncode == 0, f"group emit failed: {group_emit.stderr}")
        group_emit_payload = json.loads(group_emit.stdout)
        require(group_emit_payload["results"][0]["notification"]["group"] == "ops", f"unexpected group emit payload: {group_emit_payload}")
        require(len(group_emit_payload["results"][0]["notification"]["deliveries"]) == 2, f"unexpected group emit deliveries: {group_emit_payload}")

        history = run([str(AGENT_DO), "notify", "history", "--json", "--limit", "5"], env=env)
        require(history.returncode == 0, f"notify history failed: {history.stderr}")
        history_payload = json.loads(history.stdout)
        require(len(history_payload["history"]) >= 1, f"expected history entries: {history_payload}")
        require(history_payload["history"][0]["provider"] in {"sms", "email"}, f"unexpected history payload: {history_payload}")
        require("timestamp" in history_payload["history"][0], f"missing timestamp in history payload: {history_payload}")

        history_rule = run([str(AGENT_DO), "notify", "history", "--json", "--rule", "approval_group", "--limit", "5"], env=env)
        require(history_rule.returncode == 0, f"notify history rule filter failed: {history_rule.stderr}")
        history_rule_payload = json.loads(history_rule.stdout)
        require(len(history_rule_payload["history"]) == 2, f"expected two group rule history entries: {history_rule_payload}")
        require(all(item["rule"] == "approval_group" for item in history_rule_payload["history"]), f"unexpected rule-filtered history payload: {history_rule_payload}")
        require(all(item.get("group") == "ops" for item in history_rule_payload["history"]), f"unexpected group history payload: {history_rule_payload}")

        history_provider = run([str(AGENT_DO), "notify", "history", "--json", "--provider", "sms", "--success", "true", "--limit", "3"], env=env)
        require(history_provider.returncode == 0, f"notify history provider filter failed: {history_provider.stderr}")
        history_provider_payload = json.loads(history_provider.stdout)
        require(len(history_provider_payload["history"]) >= 1, f"expected sms history entries: {history_provider_payload}")
        require(all(item["provider"] == "sms" and item["success"] is True for item in history_provider_payload["history"]), f"unexpected provider-filtered history payload: {history_provider_payload}")

        emit_sent = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "build",
                "--fact",
                "service=api",
                "--fact",
                "branch=main",
                "--fact",
                "status=failed",
                "--fact",
                "env=prod",
                "--json",
            ],
            env=env,
        )
        require(emit_sent.returncode == 0, f"emit send failed: {emit_sent.stderr}")
        emit_sent_payload = json.loads(emit_sent.stdout)
        require(emit_sent_payload["results"][0]["success"] is True, f"expected successful emit send: {emit_sent_payload}")
        require(
            emit_sent_payload["results"][0]["notification"]["attempts"][0]["provider"] == "sms",
            f"unexpected emit notification payload: {emit_sent_payload}",
        )

        emit_cooldown = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "build",
                "--fact",
                "service=api",
                "--fact",
                "branch=main",
                "--fact",
                "status=failed",
                "--fact",
                "env=prod",
                "--json",
            ],
            env=env,
        )
        require(emit_cooldown.returncode == 0, f"emit cooldown failed: {emit_cooldown.stderr}")
        emit_cooldown_payload = json.loads(emit_cooldown.stdout)
        require(emit_cooldown_payload["results"][0]["skipped"] == "cooldown", f"expected cooldown skip: {emit_cooldown_payload}")

        reset_rule_state = run([str(AGENT_DO), "notify", "reset-state", "build_failed", "--json"], env=env)
        require(reset_rule_state.returncode == 0, f"reset-state rule failed: {reset_rule_state.stderr}")
        reset_rule_state_payload = json.loads(reset_rule_state.stdout)
        require(reset_rule_state_payload["scope"] == "rule", f"unexpected reset-state payload: {reset_rule_state_payload}")
        require(reset_rule_state_payload["rule"] == "build_failed", f"unexpected reset-state payload: {reset_rule_state_payload}")
        require(reset_rule_state_payload["cleared_count"] == 1, f"expected one cleared fingerprint: {reset_rule_state_payload}")

        emit_after_reset = run(
            [
                str(AGENT_DO),
                "notify",
                "emit",
                "build",
                "--fact",
                "service=api",
                "--fact",
                "branch=main",
                "--fact",
                "status=failed",
                "--fact",
                "env=prod",
                "--json",
            ],
            env=env,
        )
        require(emit_after_reset.returncode == 0, f"emit after reset failed: {emit_after_reset.stderr}")
        emit_after_reset_payload = json.loads(emit_after_reset.stdout)
        require(emit_after_reset_payload["results"][0]["success"] is True, f"expected send after reset: {emit_after_reset_payload}")

        reset_all_state = run([str(AGENT_DO), "notify", "reset-state", "--json"], env=env)
        require(reset_all_state.returncode == 0, f"reset-state all failed: {reset_all_state.stderr}")
        reset_all_state_payload = json.loads(reset_all_state.stdout)
        require(reset_all_state_payload["scope"] == "all", f"unexpected global reset payload: {reset_all_state_payload}")
        require("build_failed" in reset_all_state_payload["cleared_rules"], f"expected build_failed in cleared rules: {reset_all_state_payload}")

        delete_rule = run([str(AGENT_DO), "notify", "delete-rule", "build_failed", "--json"], env=env)
        require(delete_rule.returncode == 0, f"delete-rule failed: {delete_rule.stderr}")
        delete_rule_payload = json.loads(delete_rule.stdout)
        require(delete_rule_payload["name"] == "build_failed", f"unexpected delete-rule payload: {delete_rule_payload}")

        show_deleted_rule = run([str(AGENT_DO), "notify", "show-rule", "build_failed", "--json"], env=env)
        require(show_deleted_rule.returncode == 1, f"expected deleted rule lookup failure: {show_deleted_rule.stdout} {show_deleted_rule.stderr}")
        show_deleted_rule_payload = json.loads(show_deleted_rule.stdout)
        require("Unknown rule" in show_deleted_rule_payload["error"], f"unexpected deleted rule payload: {show_deleted_rule_payload}")

        delete_group = run([str(AGENT_DO), "notify", "delete-group", "ops", "--json"], env=env)
        require(delete_group.returncode == 0, f"delete-group failed: {delete_group.stderr}")
        delete_group_payload = json.loads(delete_group.stdout)
        require(delete_group_payload["alias"] == "ops", f"unexpected delete-group payload: {delete_group_payload}")

        show_deleted_group = run([str(AGENT_DO), "notify", "show-group", "ops", "--json"], env=env)
        require(show_deleted_group.returncode == 1, f"expected deleted group lookup failure: {show_deleted_group.stdout} {show_deleted_group.stderr}")
        show_deleted_group_payload = json.loads(show_deleted_group.stdout)
        require("Unknown group alias" in show_deleted_group_payload["error"], f"unexpected deleted group payload: {show_deleted_group_payload}")

        messenger_denied = run([str(AGENT_DO), "notify", "me", "Ping", "--via", "messenger", "--json"], env=env)
        require(messenger_denied.returncode == 1, f"expected messenger live approval failure: {messenger_denied.stdout} {messenger_denied.stderr}")
        messenger_denied_payload = json.loads(messenger_denied.stdout)
        require(messenger_denied_payload["action_required"] == "LIVE_APPROVAL_REQUIRED", f"unexpected messenger denied payload: {messenger_denied_payload}")
        require("notify" in messenger_denied_payload["rerun"], f"expected notify rerun hint: {messenger_denied_payload}")

        env["AGENT_DO_NOTIFY_MESSENGER_TEST_MODE"] = "1"
        messenger_live = run(
            [
                str(AGENT_DO),
                '+live(scope=desktop,app=Messenger,ttl=15m,reason="notify:messenger")',
                "notify",
                "me",
                "Ping",
                "--via",
                "messenger",
                "--json",
            ],
            env=env,
        )
        require(messenger_live.returncode == 0, f"messenger live send failed: {messenger_live.stderr}")
        messenger_live_payload = json.loads(messenger_live.stdout)
        require(messenger_live_payload["success"] is True, f"unexpected messenger live payload: {messenger_live_payload}")
        require(messenger_live_payload["attempts"][0]["provider"] == "messenger", f"unexpected messenger attempt payload: {messenger_live_payload}")

    print("notify tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
