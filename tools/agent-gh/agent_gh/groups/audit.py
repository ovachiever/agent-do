from __future__ import annotations

import argparse
import re
from typing import Any

from ..refs import PrRef, parse_pr_ref
from ..render import print_json, print_table
from ..transport import command_available, run_optional
from .pr import pr_checks, pr_detail, pr_diff_text, pr_threads

ENV_VAR_RE = re.compile(r"\b([A-Z][A-Z0-9_]*[A-Z0-9])\b")
INTERESTING_ENV_PREFIXES = (
    "SENTRY",
    "NEXT_PUBLIC",
    "RENDER",
    "VERCEL",
    "SUPABASE",
    "DATABASE",
    "REDIS",
    "AUTH",
    "NEXTAUTH",
    "OKTA",
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
    "RESEND",
    "SLACK",
)
OPTIONAL_PROVIDER_ENV_NAMES = {
    "CI",
    "NODE_ENV",
    "RENDER",
    "RENDER_SERVICE_NAME",
    "VERCEL",
    "VERCEL_ENV",
}

def add_finding(
    findings: list[dict[str, Any]],
    *,
    severity: str,
    title: str,
    evidence: str,
    fix: str,
    category: str = "review",
) -> None:
    findings.append({"severity": severity, "category": category, "title": title, "evidence": evidence, "fix": fix})

def changed_file(detail: dict[str, Any], suffix: str) -> dict[str, Any] | None:
    for file in detail.get("files") or []:
        if str(file.get("path") or "").endswith(suffix):
            return file
    return None

def changed_paths(detail: dict[str, Any]) -> list[str]:
    return [str(file.get("path") or "") for file in detail.get("files") or [] if file.get("path")]

def extract_interesting_env_vars(text: str) -> list[str]:
    envs: set[str] = set()
    for value in ENV_VAR_RE.findall(text):
        if value in OPTIONAL_PROVIDER_ENV_NAMES or value in {"SENTRY", "NEXT_PUBLIC", "RENDER", "VERCEL"}:
            continue
        if value.startswith(INTERESTING_ENV_PREFIXES):
            envs.add(value)
    if ("SENTRY_ORG" in envs or "SENTRY_PROJECT" in envs) and "SENTRY_AUTH_TOKEN" not in envs:
        envs.add("SENTRY_AUTH_TOKEN")
    return sorted(envs)

def parse_env_keys(output_text: str) -> set[str]:
    keys: set[str] = set()
    for line in output_text.splitlines():
        match = re.search(r"\b([A-Z][A-Z0-9_]{2,})=", line)
        if match:
            keys.add(match.group(1))
    return keys

def repo_slug(repo: str | None) -> str | None:
    if not repo or "/" not in repo:
        return None
    return repo.split("/", 1)[1].lower()

def deployment_target_kind(paths: list[str]) -> str:
    web = any(p.startswith("presentation/") or p == "Dockerfile.web" or p.endswith("Dockerfile.web") for p in paths)
    worker = any(p.startswith("orchestrator/") or p == "Dockerfile.worker" or p.endswith("Dockerfile.worker") for p in paths)
    if web and not worker:
        return "web"
    if worker and not web:
        return "worker"
    return "mixed"

def service_matches_target(service_name: str, target_kind: str) -> bool:
    lower = service_name.lower()
    if target_kind == "web":
        return "worker" not in lower
    if target_kind == "worker":
        return "worker" in lower
    return True

def probe_deployment_env(detail: dict[str, Any], env_vars: list[str], *, target_kind: str = "mixed") -> dict[str, Any]:
    slug = repo_slug(detail.get("repo"))
    result: dict[str, Any] = {
        "enabled": True,
        "env_vars": env_vars,
        "render": {"services": []},
        "vercel": {"projects": []},
        "notes": [],
    }
    if not slug or not env_vars:
        return result

    if command_available("agent-do"):
        render_services = run_optional(["agent-do", "render", "services"])
        if render_services and render_services.returncode == 0:
            for line in render_services.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                service_id, service_name = parts[0], parts[1]
                if slug not in service_name.lower() or not service_matches_target(service_name, target_kind):
                    continue
                env_out = run_optional(["agent-do", "render", "env", service_id])
                keys = parse_env_keys(env_out.stdout if env_out and env_out.returncode == 0 else "")
                result["render"]["services"].append(
                    {
                        "id": service_id,
                        "name": service_name,
                        "present": sorted(set(env_vars) & keys),
                        "missing": sorted(set(env_vars) - keys),
                    }
                )
        elif render_services:
            result["notes"].append(f"render probe failed: {(render_services.stderr or render_services.stdout).strip()[:200]}")

        vercel_projects = None if target_kind == "worker" else run_optional(["agent-do", "vercel", "projects"])
        if vercel_projects and vercel_projects.returncode == 0:
            for line in vercel_projects.stdout.splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                project_id, project_name = parts[0], parts[1]
                if slug != project_name.lower():
                    continue
                env_out = run_optional(["agent-do", "vercel", "env", project_name])
                keys = parse_env_keys(env_out.stdout if env_out and env_out.returncode == 0 else "")
                result["vercel"]["projects"].append(
                    {
                        "id": project_id,
                        "name": project_name,
                        "present": sorted(set(env_vars) & keys),
                        "missing": sorted(set(env_vars) - keys),
                    }
                )
        elif vercel_projects:
            result["notes"].append(f"vercel probe failed: {(vercel_projects.stderr or vercel_projects.stdout).strip()[:200]}")
    else:
        result["notes"].append("agent-do not found; provider env probe skipped")
    return result

def audit_pr(ref: PrRef, *, probe_deploys: bool = False) -> dict[str, Any]:
    detail = pr_detail(ref)
    checks = pr_checks(ref)
    threads = pr_threads(ref)
    diff = pr_diff_text(ref)
    paths = changed_paths(detail)
    findings: list[dict[str, Any]] = []

    failed_checks = [c for c in checks if str(c.get("bucket") or "").lower() in {"fail", "failed", "failure"}]
    pending_checks = [c for c in checks if str(c.get("bucket") or "").lower() in {"pending", "queued", "in_progress", "waiting"}]
    if failed_checks:
        add_finding(findings, severity="high", category="checks", title="Required checks are failing",
                    evidence=", ".join(str(c.get("name") or "unnamed") for c in failed_checks[:5]),
                    fix="Fix the failing checks before review approval. If a check is irrelevant, document why and remove or reconfigure it instead of ignoring the failure.")
    if pending_checks:
        add_finding(findings, severity="medium", category="checks", title="Required signal is still pending",
                    evidence=", ".join(str(c.get("name") or "unnamed") for c in pending_checks[:5]),
                    fix="Wait for the pending checks to settle before merge, or rerun/debug stuck checks so review is based on final CI state.")
    if threads:
        add_finding(findings, severity="medium", category="review", title="Unresolved review threads exist",
                    evidence=f"{len(threads)} unresolved thread(s)",
                    fix="Resolve the review threads in code or reply with a concrete reason they are intentionally left open.")
    if detail.get("merge_state") and str(detail.get("merge_state")).upper() not in {"CLEAN", "UNKNOWN"}:
        add_finding(findings, severity="high", category="merge", title="PR is not cleanly mergeable",
                    evidence=f"merge_state={detail.get('merge_state')} mergeable={detail.get('mergeable')}",
                    fix="Rebase or merge the base branch, resolve conflicts, and rerun checks before review approval.")

    lock_files = [f for f in detail.get("files") or [] if str(f.get("path") or "").endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock"))]
    package_files = [f for f in detail.get("files") or [] if str(f.get("path") or "").endswith("package.json")]
    for file in lock_files:
        churn = int(file.get("additions") or 0) + int(file.get("deletions") or 0)
        if churn >= 1000:
            add_finding(findings, severity="medium", category="dependencies", title="Lockfile blast radius is large",
                        evidence=f"{file.get('path')} changed by +{file.get('additions')} -{file.get('deletions')}",
                        fix="Regenerate the lockfile with only the intended dependency change. If the broad dependency refresh is intentional, split it into a separate PR with its own validation notes.")
        elif churn >= 250 and package_files:
            add_finding(findings, severity="low", category="dependencies", title="Lockfile churn needs review",
                        evidence=f"{file.get('path')} changed by +{file.get('additions')} -{file.get('deletions')}",
                        fix="Confirm the lockfile changes correspond to the manifest change and do not silently upgrade unrelated runtime packages.")

    if re.search(r"tracesSampleRate\s*:\s*1(?:\.0)?", diff):
        add_finding(findings, severity="medium", category="observability", title="Production trace sampling appears too high",
                    evidence="Diff contains tracesSampleRate: 1.0",
                    fix='Make sampling env-driven or lower the production default, for example `Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? "0.1")`, and use it consistently across runtime configs.')
    if "SENTRY_ORG" in diff or "SENTRY_PROJECT" in diff:
        if "SENTRY_AUTH_TOKEN" not in diff:
            add_finding(findings, severity="medium", category="observability", title="Source-map upload looks partially wired",
                        evidence="Diff references SENTRY_ORG/SENTRY_PROJECT without SENTRY_AUTH_TOKEN",
                        fix="Either fully wire build-time source-map upload env, including SENTRY_AUTH_TOKEN, or remove/disable source-map upload config until that path is ready.")
    if "captureException" in diff and "process.exit" in diff and "Sentry.flush" not in diff and "Sentry.close" not in diff:
        add_finding(findings, severity="medium", category="observability", title="Fatal telemetry may be dropped before process exit",
                    evidence="Diff captures exceptions and exits without Sentry.flush()/Sentry.close()",
                    fix="Await `Sentry.flush(2000)` or `Sentry.close(2000)` before fatal `process.exit` paths. Do not let telemetry failure block shutdown indefinitely.")
    if re.search(r"tags\s*:\s*\{[^}]*\bjobId\b", diff, re.DOTALL) or re.search(r"tags\s*:\s*\{[^}]*\bjobName\b", diff, re.DOTALL):
        add_finding(findings, severity="medium", category="observability", title="High-cardinality values are used as Sentry tags",
                    evidence="Diff places jobId/jobName in tags",
                    fix="Keep tags low-cardinality. Move jobId/jobName to `extra` or structured context while keeping only stable dimensions, such as worker name, in tags.")

    if "vitest" in diff.lower():
        package_json = changed_file(detail, "package.json")
        if package_json and '"test"' not in diff and "vitest" not in re.sub(r"^\+.*vitest.*$", "", diff, flags=re.MULTILINE).lower():
            add_finding(findings, severity="medium", category="tests", title="Added Vitest test may not be runnable",
                        evidence="Diff imports/mentions Vitest but does not add an obvious test script or Vitest dependency",
                        fix="Add Vitest to devDependencies and a real test script, rewrite the test for the existing runner, or remove the dead test from this PR.")
        elif package_json and '"test"' not in diff:
            add_finding(findings, severity="medium", category="tests", title="New test runner wiring is unclear",
                        evidence="Diff mentions Vitest but no package.json test script addition was detected",
                        fix="Make the test executable through the package's normal test command so CI and reviewers can run it.")

    if any(p.endswith((".env.example", "render.yaml", "vercel.json")) or "Dockerfile" in p for p in paths):
        add_finding(findings, severity="medium", category="deploy", title="Deployment or environment contract changed",
                    evidence=", ".join(p for p in paths if p.endswith((".env.example", "render.yaml", "vercel.json")) or "Dockerfile" in p)[:300],
                    fix="Verify the live deployment provider has the same required env keys and build/runtime semantics as the checked-in config. Keep blueprint state aligned with production or explicitly mark it non-authoritative.")

    env_vars = extract_interesting_env_vars(diff)
    target_kind = deployment_target_kind(paths)
    deploy_probe = probe_deployment_env(detail, env_vars, target_kind=target_kind) if probe_deploys else {"enabled": False, "env_vars": env_vars}
    deploy_probe["target_kind"] = target_kind
    if probe_deploys:
        for service in deploy_probe.get("render", {}).get("services", []):
            if missing := service.get("missing") or []:
                add_finding(findings, severity="medium", category="deploy",
                            title=f"Render env may be missing keys on {service.get('name')}",
                            evidence=", ".join(missing[:12]),
                            fix="Add the missing keys to the Render service or document why this service should not receive them. Verify build-time NEXT_PUBLIC_* keys separately for Docker builds.")
        for project in deploy_probe.get("vercel", {}).get("projects", []):
            if missing := project.get("missing") or []:
                add_finding(findings, severity="low", category="deploy",
                            title=f"Vercel env may be missing keys on {project.get('name')}",
                            evidence=", ".join(missing[:12]),
                            fix="If Vercel is still an active target, add the missing keys. If it is intentionally disabled/stale, document that so Vercel previews are not treated as production validation.")

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda item: (severity_order.get(item.get("severity"), 9), item.get("category") or "", item.get("title") or ""))
    return {
        "pr": detail,
        "checks": {"count": len(checks), "items": checks},
        "unresolved_threads": {"count": len(threads), "items": threads},
        "changed_paths": paths,
        "env_vars_in_diff": env_vars,
        "deployment_probe": deploy_probe,
        "findings": findings,
        "verdict": "request_changes" if any(item.get("severity") in {"high", "medium"} for item in findings) else "no_blockers_found",
    }

def format_audit_reply(audit: dict[str, Any]) -> str:
    pr = audit.get("pr") or {}
    findings = audit.get("findings") or []
    blockers = [f for f in findings if f.get("severity") in {"high", "medium"}]
    notes = [f for f in findings if f.get("severity") not in {"high", "medium"}]
    if blockers:
        lines = ["Do not merge as-is.", "", "Required fixes:", ""]
        for f in blockers:
            lines.append(f"- {f.get('title')}. {f.get('evidence')}.")
            lines.append(f"  How to address: {f.get('fix')}")
        if notes:
            lines.extend(["", "Lower-priority notes:", ""])
            for f in notes:
                lines.append(f"- {f.get('title')}. {f.get('evidence')}.")
                lines.append(f"  How to address: {f.get('fix')}")
        lines.extend([
            "", "Current verified signals:",
            f"- Checks inspected: {(audit.get('checks') or {}).get('count', 0)}",
            f"- Unresolved review threads: {(audit.get('unresolved_threads') or {}).get('count', 0)}",
            f"- Files changed: {pr.get('changed_files')}  +{pr.get('additions')} -{pr.get('deletions')}",
            "", "Requesting changes.",
        ])
        return "\n".join(lines)

    lines = ["No blocking issues found from the automated review audit."]
    if notes:
        lines.extend(["", "Lower-priority notes:", ""])
        for f in notes:
            lines.append(f"- {f.get('title')}. {f.get('evidence')}.")
            lines.append(f"  How to address: {f.get('fix')}")
    lines.extend([
        "", "Current verified signals:",
        f"- Checks inspected: {(audit.get('checks') or {}).get('count', 0)}",
        f"- Unresolved review threads: {(audit.get('unresolved_threads') or {}).get('count', 0)}",
        f"- Files changed: {pr.get('changed_files')}  +{pr.get('additions')} -{pr.get('deletions')}",
        "", "This is not a substitute for reading the code diff, but there are no automated blockers from the audited signals.",
    ])
    return "\n".join(lines)

def cmd_audit(args: argparse.Namespace) -> None:
    ref = parse_pr_ref(args.pr)
    audit = audit_pr(ref, probe_deploys=args.probe_deploys)
    if args.reply:
        audit["reply"] = format_audit_reply(audit)
    if args.json:
        print_json(audit)
    elif args.reply:
        print(audit["reply"])
    else:
        findings = audit.get("findings") or []
        pr = audit.get("pr") or {}
        print(f"{pr.get('ref')}: {pr.get('title')}")
        print(f"Verdict: {audit.get('verdict')}")
        print(f"Checks: {(audit.get('checks') or {}).get('count', 0)}  Unresolved threads: {(audit.get('unresolved_threads') or {}).get('count', 0)}")
        print(f"Files changed: {pr.get('changed_files')}  +{pr.get('additions')} -{pr.get('deletions')}")
        if findings:
            print()
            print_table(findings, ["severity", "category", "title"])
        else:
            print("No automated blockers found.")
