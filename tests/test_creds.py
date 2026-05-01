#!/usr/bin/env python3
"""Focused credential storage and resolution tests for agent-do."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from registry import load_registry, get_tool_info, get_tool_credentials  # noqa: E402


def run(*args: str, input_text: str | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def configure_fake_secret_tool(tmpdir: Path) -> dict[str, str]:
    fake_bin = tmpdir / "bin"
    store_dir = tmpdir / "secret-store"
    fake_bin.mkdir(parents=True, exist_ok=True)
    store_dir.mkdir(parents=True, exist_ok=True)

    secret_tool = fake_bin / "secret-tool"
    write_executable(
        secret_tool,
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import sys
            from pathlib import Path

            store_root = Path(os.environ["FAKE_SECRET_TOOL_STORE"])
            store_root.mkdir(parents=True, exist_ok=True)

            def parse_pairs(argv):
                attrs = {}
                i = 0
                while i < len(argv):
                    arg = argv[i]
                    if arg == "--all":
                        i += 1
                        continue
                    if arg.startswith("--label="):
                        i += 1
                        continue
                    if i + 1 >= len(argv):
                        break
                    attrs[arg] = argv[i + 1]
                    i += 2
                return attrs

            command = sys.argv[1]
            attrs = parse_pairs(sys.argv[2:])
            service = attrs.get("service", "default")
            account = attrs.get("account", "default")
            path = store_root / f"{service}__{account}"

            if command == "store":
                path.write_text(sys.stdin.read(), encoding="utf-8")
                raise SystemExit(0)

            if command == "lookup":
                if not path.exists():
                    raise SystemExit(1)
                sys.stdout.write(path.read_text(encoding="utf-8"))
                raise SystemExit(0)

            if command == "clear":
                path.unlink(missing_ok=True)
                raise SystemExit(0)

            if command == "search":
                prefix = f"{service}__"
                for entry in sorted(store_root.glob(f"{service}__*")):
                    account = entry.name[len(prefix):]
                    print(f"attribute.account = {account}")
                raise SystemExit(0)

            raise SystemExit(1)
            """
        ),
    )

    return {
        "AGENT_DO_CREDS_PLATFORM": "linux",
        "AGENT_DO_CREDS_SERVICE": "agent-do-test",
        "FAKE_SECRET_TOOL_STORE": str(store_dir),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }


def main() -> int:
    registry = load_registry()

    render_info = get_tool_info(registry, "render")
    render_creds = get_tool_credentials(render_info or {})
    require(render_creds["required"] == ["RENDER_API_KEY"], f"unexpected render credentials: {render_creds}")

    namecheap_info = get_tool_info(registry, "namecheap")
    namecheap_creds = get_tool_credentials(namecheap_info or {})
    require(
        namecheap_creds["required"] == ["NAMECHEAP_API_USER", "NAMECHEAP_API_KEY"],
        f"unexpected namecheap credentials: {namecheap_creds}",
    )

    cloudflare_info = get_tool_info(registry, "cloudflare")
    cloudflare_creds = get_tool_credentials(cloudflare_info or {})
    require(
        cloudflare_creds["one_of"] == [["CLOUDFLARE_API_TOKEN"], ["CLOUDFLARE_EMAIL", "CLOUDFLARE_API_KEY"]],
        f"unexpected cloudflare credentials: {cloudflare_creds}",
    )

    resend_info = get_tool_info(registry, "resend")
    resend_creds = get_tool_credentials(resend_info or {})
    require(resend_creds["required"] == ["RESEND_API_KEY"], f"unexpected resend credentials: {resend_creds}")

    email_info = get_tool_info(registry, "email")
    email_creds = get_tool_credentials(email_info or {})
    require("AGENT_EMAIL_IMAP_PASS" in email_creds["optional"], f"unexpected email credentials: {email_creds}")

    required = run("./agent-do", "creds", "required", "render", "--json")
    require(required.returncode == 0, f"render required failed: {required.stderr}")
    required_payload = json.loads(required.stdout)
    require(required_payload["required"] == ["RENDER_API_KEY"], f"unexpected render required output: {required_payload}")

    env = os.environ.copy()
    env["RENDER_API_KEY"] = "render-test-token"

    check_env = run("./agent-do", "creds", "check", "--tool", "render", "--json", env=env)
    require(check_env.returncode == 0, f"render env check failed: {check_env.stderr}")
    check_env_payload = json.loads(check_env.stdout)
    require(check_env_payload["ok"] is True, f"expected ok render env check: {check_env_payload}")
    require(check_env_payload["items"][0]["source"] == "env", f"expected env source: {check_env_payload}")

    export_env = run("./agent-do", "creds", "export", "--tool", "render", env=env)
    require(export_env.returncode == 0, f"render export failed: {export_env.stderr}")
    require(
        "export RENDER_API_KEY='render-test-token'" in export_env.stdout or "export RENDER_API_KEY=render-test-token" in export_env.stdout,
        f"unexpected export output: {export_env.stdout}",
    )

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        fake_env = os.environ.copy()
        fake_env.update(configure_fake_secret_tool(tmpdir))
        fake_env.pop("TEST_API_KEY", None)

        store = run("./agent-do", "creds", "store", "TEST_API_KEY", "--stdin", input_text="supersecret", env=fake_env)
        require(store.returncode == 0, f"store via fake secret-tool failed: {store.stderr}")

        get_source = run("./agent-do", "creds", "get", "TEST_API_KEY", "--source", env=fake_env)
        require(get_source.returncode == 0, f"get --source failed: {get_source.stderr}")
        require(get_source.stdout.strip() == "store", f"expected store source, got: {get_source.stdout}")

        get_value = run("./agent-do", "creds", "get", "TEST_API_KEY", "--reveal", env=fake_env)
        require(get_value.returncode == 0, f"get --reveal failed: {get_value.stderr}")
        require(get_value.stdout.strip() == "supersecret", f"unexpected revealed value: {get_value.stdout}")

        list_keys = run("./agent-do", "creds", "list", "--json", env=fake_env)
        require(list_keys.returncode == 0, f"list --json failed: {list_keys.stderr}")
        list_payload = json.loads(list_keys.stdout)
        require("TEST_API_KEY" in list_payload["keys"], f"expected stored key in list: {list_payload}")

        delete = run("./agent-do", "creds", "delete", "TEST_API_KEY", env=fake_env)
        require(delete.returncode == 0, f"delete failed: {delete.stderr}")
        missing = run("./agent-do", "creds", "get", "TEST_API_KEY", env=fake_env)
        require(missing.returncode != 0, "expected deleted key to be missing")

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        fake_env = os.environ.copy()
        fake_env.update(configure_fake_secret_tool(tmpdir))
        fake_env.pop("RENDER_API_KEY", None)
        fake_env.pop("DEMO_SECRET", None)

        home = tmpdir / "home"
        tool_bin = tmpdir / "tool-bin"
        home.mkdir(parents=True, exist_ok=True)
        tool_bin.mkdir(parents=True, exist_ok=True)
        fake_env["AGENT_DO_HOME"] = str(home)
        fake_env["PATH"] = f"{tool_bin}{os.pathsep}{fake_env['PATH']}"

        (home / "registry.yaml").write_text(
            textwrap.dedent(
                """\
                tools:
                  credsdemo:
                    description: test-only credential resolution tool
                    credentials:
                      required:
                      - DEMO_SECRET
                """
            ),
            encoding="utf-8",
        )

        write_executable(
            tool_bin / "agent-credsdemo",
            "#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"${DEMO_SECRET:-missing}\"\n",
        )

        store_demo = run("./agent-do", "creds", "store", "DEMO_SECRET", "--stdin", input_text="from-store", env=fake_env)
        require(store_demo.returncode == 0, f"demo secret store failed: {store_demo.stderr}")
        store_render = run("./agent-do", "creds", "store", "RENDER_API_KEY", "--stdin", input_text="render-from-store", env=fake_env)
        require(store_render.returncode == 0, f"render secret store failed: {store_render.stderr}")

        demo_tool = run("./agent-do", "credsdemo", env=fake_env)
        require(demo_tool.returncode == 0, f"dispatcher did not run demo tool: {demo_tool.stderr}")
        require(demo_tool.stdout.strip() == "from-store", f"dispatcher did not preload secret: {demo_tool.stdout}")

        intent_router_check = run(
            "python3",
            "-c",
            textwrap.dedent(
                """\
                import importlib.machinery
                import importlib.util
                import json
                from pathlib import Path

                path = Path("bin/intent-router")
                loader = importlib.machinery.SourceFileLoader("intent_router", str(path))
                spec = importlib.util.spec_from_loader(loader.name, loader)
                module = importlib.util.module_from_spec(spec)
                loader.exec_module(module)
                env = module.load_tool_credentials_env("render")
                print(json.dumps({"render": env.get("RENDER_API_KEY", "")}))
                """
            ),
            env=fake_env,
        )
        require(intent_router_check.returncode == 0, f"intent-router env preload failed: {intent_router_check.stderr}")
        intent_router_payload = json.loads(intent_router_check.stdout)
        require(
            intent_router_payload["render"] == "render-from-store",
            f"intent-router did not preload render secret: {intent_router_payload}",
        )

        health_store = run("./agent-do", "--health", "render", env=fake_env)
        require(health_store.returncode == 0, f"health render via store failed: {health_store.stderr}")
        require("credentials from store" in health_store.stdout, f"expected store-backed health note: {health_store.stdout}")

    health_env = run("./agent-do", "--health", "render", env=env)
    require(health_env.returncode == 0, f"health render via env failed: {health_env.stderr}")
    require("credentials from env" in health_env.stdout, f"expected env-backed health note: {health_env.stdout}")

    print("credential tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
