#!/usr/bin/env python3
"""Focused credential storage and resolution tests for agent-do."""

from __future__ import annotations

import json
import os
import shutil
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


# Realistic dump-keychain genp records: acct is ~12 lines *before* svce.
# Neighbor items exist to catch sliding-window greps (-A after svce, -B before).
MACOS_KEYCHAIN_DUMP_FIXTURE = textwrap.dedent(
    """\
    keychain: "/Users/test/Library/Keychains/login.keychain-db"
    version: 512
    class: "genp"
    attributes:
        0x00000007 <blob>="other-service"
        0x00000008 <blob>=<NULL>
        "acct"<blob>="OTHER_SECRET"
        "cdat"<timedate>=0x00  "Z\\000"
        "crtr"<uint32>=<NULL>
        "cusi"<sint32>=<NULL>
        "desc"<blob>=<NULL>
        "gena"<blob>=<NULL>
        "icmt"<blob>=<NULL>
        "invi"<sint32>=<NULL>
        "mdat"<timedate>=0x00  "Z\\000"
        "nega"<sint32>=<NULL>
        "prot"<blob>=<NULL>
        "scrp"<sint32>=<NULL>
        "svce"<blob>="other-service"
        "type"<uint32>=<NULL>
    keychain: "/Users/test/Library/Keychains/login.keychain-db"
    version: 512
    class: "genp"
    attributes:
        0x00000007 <blob>="agent-do-test"
        0x00000008 <blob>=<NULL>
        "acct"<blob>="TEST_API_KEY"
        "cdat"<timedate>=0x00  "Z\\000"
        "crtr"<uint32>=<NULL>
        "cusi"<sint32>=<NULL>
        "desc"<blob>=<NULL>
        "gena"<blob>=<NULL>
        "icmt"<blob>=<NULL>
        "invi"<sint32>=<NULL>
        "mdat"<timedate>=0x00  "Z\\000"
        "nega"<sint32>=<NULL>
        "prot"<blob>=<NULL>
        "scrp"<sint32>=<NULL>
        "svce"<blob>="agent-do-test"
        "type"<uint32>=<NULL>
    keychain: "/Users/test/Library/Keychains/login.keychain-db"
    version: 512
    class: "genp"
    attributes:
        0x00000007 <blob>="unrelated"
        0x00000008 <blob>=<NULL>
        "acct"<blob>="NEXT_ITEM_ACCT"
        "cdat"<timedate>=0x00  "Z\\000"
        "crtr"<uint32>=<NULL>
        "cusi"<sint32>=<NULL>
        "desc"<blob>=<NULL>
        "gena"<blob>=<NULL>
        "icmt"<blob>=<NULL>
        "invi"<sint32>=<NULL>
        "mdat"<timedate>=0x00  "Z\\000"
        "nega"<sint32>=<NULL>
        "prot"<blob>=<NULL>
        "scrp"<sint32>=<NULL>
        "svce"<blob>="unrelated"
        "type"<uint32>=<NULL>
    """
)


def configure_fake_security(tmpdir: Path, dump_text: str, dump_exit: int = 0) -> dict[str, str]:
    fake_bin = tmpdir / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    dump_path = tmpdir / "keychain.dump"
    dump_path.write_text(dump_text, encoding="utf-8")

    security = fake_bin / "security"
    write_executable(
        security,
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import sys
            from pathlib import Path

            if len(sys.argv) >= 2 and sys.argv[1] == "dump-keychain":
                sys.stdout.write(Path({str(dump_path)!r}).read_text(encoding="utf-8"))
                raise SystemExit({dump_exit})
            if len(sys.argv) >= 2 and sys.argv[1] == "find-generic-password" and "-w" in sys.argv:
                # Real `security -w` ends the password with a newline.
                account = sys.argv[sys.argv.index("-a") + 1]
                if account == "MAC_SECRET":
                    sys.stdout.write("macsecret\\n")
                    raise SystemExit(0)
                raise SystemExit(44)
            if len(sys.argv) >= 2 and sys.argv[1] == "find-generic-password":
                # Attribute-only probe (no -w): existence without revealing the value.
                account = sys.argv[sys.argv.index("-a") + 1]
                raise SystemExit(0 if account == "MAC_SECRET" else 44)
            print("unexpected security argv:", sys.argv, file=sys.stderr)
            raise SystemExit(2)
            """
        ),
    )

    return {
        "AGENT_DO_CREDS_PLATFORM": "macos",
        "AGENT_DO_CREDS_SERVICE": "agent-do-test",
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
    }


def test_explicit_openai_keychain_reads() -> None:
    """Count real CLI lookup attempts against a synthetic Keychain boundary."""
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        fake_bin = tmpdir / "bin"
        fake_bin.mkdir()
        log = tmpdir / "keychain-calls.jsonl"
        home = tmpdir / "agent-home"
        home.mkdir()
        (home / "registry.yaml").write_text(textwrap.dedent("""\
            tools:
              promptdemo:
                description: synthetic local tool with an optional OpenAI feature
                credentials:
                  required: [OTHER_API_KEY]
                  optional: [OPENAI_API_KEY]
            """), encoding="utf-8")
        write_executable(fake_bin / "agent-promptdemo", textwrap.dedent("""\
            #!/usr/bin/env bash
            set -euo pipefail
            [[ -z "${OPENAI_API_KEY:-}" ]]
            [[ "${OTHER_API_KEY:-}" == "synthetic-other-value" ]]
            printf 'local-tool-ok\\n'
            """))
        write_executable(fake_bin / "security", textwrap.dedent("""\
            #!/usr/bin/env python3
            import json, os, sys
            from pathlib import Path
            args = sys.argv[1:]
            key = args[args.index('-a') + 1] if '-a' in args else ''
            reveal = '-w' in args or '-g' in args
            with Path(os.environ['FAKE_KEYCHAIN_LOG']).open('a') as out:
                out.write(json.dumps({'key': key, 'reveal': reveal, 'command': args[0]}) + '\\n')
            if not args or args[0] != 'find-generic-password':
                raise SystemExit(90)
            values = {'OPENAI_API_KEY': 'synthetic-openai-value', 'OTHER_API_KEY': 'synthetic-other-value'}
            if key not in values:
                raise SystemExit(44)
            if reveal:
                if os.environ.get('FAKE_KEYCHAIN_DENY') == '1':
                    raise SystemExit(51)
                print(values[key])
            else:
                print('attributes-only')
            """))
        env = {
            key: value for key, value in os.environ.items()
            if not any(word in key.upper() for word in ('API_KEY', 'SECRET', 'TOKEN', 'PASSWORD'))
        }
        env.update({
            "AGENT_DO_HOME": str(home),
            "AGENT_DO_CREDS_PLATFORM": "macos",
            "AGENT_DO_CREDS_SERVICE": "agent-do-test",
            "AGENT_DO_TELEMETRY_SUPPRESS": "1",
            "FAKE_KEYCHAIN_LOG": str(log),
            "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
        })

        def calls() -> list[dict]:
            return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

        def openai_reads() -> list[dict]:
            return [row for row in calls() if row['key'] == 'OPENAI_API_KEY' and row['reveal']]

        for args in (('--help',), ('state', '--json'), ()):
            result = run('./agent-do', 'promptdemo', *args, env=env)
            require(result.returncode == 0, f"local dispatch failed: {result.stderr}")
            require(result.stdout.strip() == 'local-tool-ok', f"unexpected local output: {result.stdout}")
        require(not any(row['key'] == 'OPENAI_API_KEY' for row in calls()),
                f"general tools must not look up OpenAI at all: {calls()}")
        require(any(row['key'] == 'OTHER_API_KEY' and row['reveal'] for row in calls()),
                'other credential preloading must remain available')

        # Exercise the installed commands reported in the incident, through
        # the production dispatcher but with an entirely synthetic Keychain.
        log.write_text('')
        for tool in ('manna', 'obsidian'):
            result = run('./agent-do', tool, '--help', env=env)
            require(result.returncode == 0, f"{tool} help failed: {result.stderr}")
        require(not any(row['key'] == 'OPENAI_API_KEY' for row in calls()),
                f"Manna/Obsidian help must not look up OpenAI: {calls()}")

        log.write_text('')
        for args in (('get', 'OPENAI_API_KEY'), ('get', 'OPENAI_API_KEY', '--source'),
                     ('get', 'OPENAI_API_KEY', '--json'), ('check', '--json', 'OPENAI_API_KEY'),
                     ('check', '--tool', 'models', '--json')):
            result = run('./agent-do', 'creds', *args, env=env)
            require(result.returncode == 0, f"metadata check failed: {args}: {result.stderr}")
            require('synthetic-openai-value' not in result.stdout, 'status exposed a secret')
        require(not openai_reads(), f"metadata checks must not unlock the key: {calls()}")

        log.write_text('')
        implicit = run('bash', '-c', 'source lib/creds-helper.sh; creds_get OPENAI_API_KEY', env=env)
        require(implicit.returncode == 2, f"implicit shared-helper read must refuse: {implicit.stderr}")
        require(not calls(), 'implicit shared-helper read reached Keychain')

        for args in (('get', 'openai_api_key', '--reveal'), ('export', 'OPENAI_API_KEY')):
            log.write_text('')
            result = run('./agent-do', 'creds', *args, env=env)
            require(result.returncode == 0, f"explicit read failed: {args}: {result.stderr}")
            require('synthetic-openai-value' in result.stdout, 'explicit read did not return its synthetic value')
            require(len(openai_reads()) == 1, f"explicit read must unlock exactly once: {calls()}")

            log.write_text('')
            denied = run('./agent-do', 'creds', *args, env={**env, 'FAKE_KEYCHAIN_DENY': '1'})
            require(denied.returncode == 51, f"denial must propagate: {args}: {denied.returncode}")
            require(not denied.stdout, f"denial must not produce a value: {denied.stdout}")
            require(len(openai_reads()) == 1, f"denial must not retry: {calls()}")

        log.write_text('')
        bulk = run('./agent-do', 'creds', 'export', '--tool', 'models', env=env)
        require(bulk.returncode == 2 and not bulk.stdout, 'bulk export must require the OpenAI key to be named')
        require(not calls(), f"bulk refusal must precede all credential reads: {calls()}")

        log.write_text('')
        routed = run('python3', '-c', textwrap.dedent("""\
            import importlib.machinery, importlib.util
            loader = importlib.machinery.SourceFileLoader('intent_router', 'bin/intent-router')
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            env = module.load_tool_credentials_env('promptdemo')
            assert 'OPENAI_API_KEY' not in env
            assert env.get('OTHER_API_KEY') == 'synthetic-other-value'
            """), env=env)
        require(routed.returncode == 0, f"intent-router credential regression: {routed.stderr}")
        require(not any(row['key'] == 'OPENAI_API_KEY' for row in calls()),
                f"intent routing must not request OpenAI implicitly: {calls()}")


def main() -> int:
    test_explicit_openai_keychain_reads()
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

    obsidian_info = get_tool_info(registry, "obsidian")
    obsidian_creds = get_tool_credentials(obsidian_info or {})
    require("VOYAGE_API_KEY" in obsidian_creds["optional"], f"unexpected obsidian credentials: {obsidian_creds}")
    require(
        obsidian_creds.get("features", {}).get("VOYAGE_API_KEY", {}).get("recommended") is True,
        f"obsidian credentials should describe recommended Voyage semantic setup: {obsidian_creds}",
    )

    models_info = get_tool_info(registry, "models")
    models_creds = get_tool_credentials(models_info or {})
    require(
        models_creds["optional"] == ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"],
        f"internal model credentials must remain optional: {models_creds}",
    )

    notion_info = get_tool_info(registry, "notion")
    notion_creds = get_tool_credentials(notion_info or {})
    require(notion_creds["required"] == ["NOTION_TOKEN"], f"unexpected notion credentials: {notion_creds}")
    require(
        notion_creds.get("features", {}).get("NOTION_TOKEN", {}).get("recommended") is True,
        f"notion credentials should describe required token setup: {notion_creds}",
    )

    required = run("./agent-do", "creds", "required", "render", "--json")
    require(required.returncode == 0, f"render required failed: {required.stderr}")
    required_payload = json.loads(required.stdout)
    require(required_payload["required"] == ["RENDER_API_KEY"], f"unexpected render required output: {required_payload}")

    obsidian_required = run("./agent-do", "creds", "required", "obsidian")
    require(obsidian_required.returncode == 0, f"obsidian required failed: {obsidian_required.stderr}")
    require("VOYAGE_API_KEY: default voyage-4-large semantic embeddings" in obsidian_required.stdout,
            f"obsidian required output should explain Voyage use: {obsidian_required.stdout}")
    require("read, save, keyword search" in obsidian_required.stdout,
            f"obsidian required output should explain no-key baseline: {obsidian_required.stdout}")

    notion_required = run("./agent-do", "creds", "required", "notion")
    require(notion_required.returncode == 0, f"notion required failed: {notion_required.stderr}")
    require("NOTION_TOKEN: Notion workspace read/write" in notion_required.stdout,
            f"notion required output should explain token use: {notion_required.stdout}")
    require("pages/data sources shared with that integration" in notion_required.stdout,
            f"notion required output should explain sharing requirement: {notion_required.stdout}")

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
        require(get_value.stdout == "supersecret\n", f"--reveal must print the value and one newline: {get_value.stdout!r}")

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
        store_models = run("./agent-do", "creds", "store", "ANTHROPIC_API_KEY", "--stdin", input_text="anthropic-from-store", env=fake_env)
        require(store_models.returncode == 0, f"model secret store failed: {store_models.stderr}")

        demo_tool = run("./agent-do", "credsdemo", env=fake_env)
        require(demo_tool.returncode == 0, f"dispatcher did not run demo tool: {demo_tool.stderr}")
        require(demo_tool.stdout.strip() == "from-store", f"dispatcher did not preload secret: {demo_tool.stdout}")

        (tmpdir / "anthropic.py").write_text(
            textwrap.dedent(
                """\
                import json
                import os

                class _Chunk:
                    def __init__(self, text): self.text = text

                class _Response:
                    def __init__(self, payload): self.content = [_Chunk(json.dumps(payload))]

                class _Messages:
                    def create(self, **kwargs):
                        assert os.environ.get("ANTHROPIC_API_KEY") == "anthropic-from-store"
                        return _Response({
                            "tool": "vercel",
                            "primary": "agent-do vercel deploy <project>",
                            "entrypoints": ["agent-do vercel deploy <project>"],
                            "confidence": 0.9,
                            "reason": "store credential reached suggest",
                        })

                class Anthropic:
                    def __init__(self, **kwargs): self.messages = _Messages()
                """
            ),
            encoding="utf-8",
        )
        suggest_env = fake_env.copy()
        suggest_env.pop("ANTHROPIC_API_KEY", None)
        suggest_env["PYTHONPATH"] = f"{tmpdir}{os.pathsep}{suggest_env.get('PYTHONPATH', '')}"
        suggest_env["AGENT_DO_SUGGEST_AI"] = "1"
        store_backed_suggest = run(
            "./agent-do",
            "suggest",
            "deploy this on vercel",
            "--json",
            env=suggest_env,
        )
        require(
            store_backed_suggest.returncode == 0,
            f"store-backed suggest failed: {store_backed_suggest.stderr}\n{store_backed_suggest.stdout}",
        )
        suggest_payload = json.loads(store_backed_suggest.stdout)
        require(
            suggest_payload["results"][0]["source"] == "ai",
            f"suggest did not use store-resolved credential: {suggest_payload}",
        )

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

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        macos_env = os.environ.copy()
        macos_env.update(configure_fake_security(tmpdir, MACOS_KEYCHAIN_DUMP_FIXTURE))

        list_macos = run("./agent-do", "creds", "list", "--json", env=macos_env)
        require(list_macos.returncode == 0, f"macos list --json failed: {list_macos.stderr}\n{list_macos.stdout}")
        macos_payload = json.loads(list_macos.stdout)
        require(
            macos_payload["keys"] == ["TEST_API_KEY"],
            f"macos list must parse acct-before-svce without neighbor leakage: {macos_payload}",
        )

        list_macos_text = run("./agent-do", "creds", "list", env=macos_env)
        require(list_macos_text.returncode == 0, f"macos list failed: {list_macos_text.stderr}")
        require(
            list_macos_text.stdout.strip() == "TEST_API_KEY",
            f"unexpected macos list text: {list_macos_text.stdout!r}",
        )

        # D28: the Keychain value already ends in a newline; --reveal must not
        # add a second (blank) line, or `$(… | tail -1)` captures nothing.
        macos_env.pop("MAC_SECRET", None)
        reveal_macos = run("./agent-do", "creds", "get", "MAC_SECRET", "--reveal", env=macos_env)
        require(reveal_macos.returncode == 0, f"macos get --reveal failed: {reveal_macos.stderr}")
        require(
            reveal_macos.stdout == "macsecret\n",
            f"macos --reveal must print the value and exactly one newline: {reveal_macos.stdout!r}",
        )

    # Env-sourced values carry no newline of their own; same single-line contract.
    env_reveal_env = os.environ.copy()
    env_reveal_env["ENV_ONLY_SECRET"] = "fromenv"
    env_reveal = run("./agent-do", "creds", "get", "ENV_ONLY_SECRET", "--reveal", env=env_reveal_env)
    require(env_reveal.returncode == 0, f"env get --reveal failed: {env_reveal.stderr}")
    require(env_reveal.stdout == "fromenv\n", f"env --reveal must print value + one newline: {env_reveal.stdout!r}")

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        fail_env = os.environ.copy()
        fail_env.update(configure_fake_security(tmpdir, MACOS_KEYCHAIN_DUMP_FIXTURE, dump_exit=45))

        list_fail = run("./agent-do", "creds", "list", env=fail_env)
        require(list_fail.returncode != 0, f"macos list must fail loud on dump-keychain error, got: {list_fail.stdout!r}")
        require(
            "No stored secrets." not in list_fail.stdout,
            f"dump-keychain failure must not look like an empty store: {list_fail.stdout!r}",
        )
        require(
            "dump-keychain exited 45" in list_fail.stderr,
            f"expected dump-keychain failure on stderr: {list_fail.stderr!r}",
        )

    # Review 2026-08-31 (HIGH): an EMPTY linux store must be a valid outcome,
    # not a silent exit 1 — under pipefail, grep's zero-match exit killed the
    # pipeline before the fix.
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        empty_env = os.environ.copy()
        empty_env.update(configure_fake_secret_tool(tmpdir))  # store starts empty

        list_empty = run("./agent-do", "creds", "list", env=empty_env)
        require(
            list_empty.returncode == 0,
            f"empty linux store must exit 0, got {list_empty.returncode}: {list_empty.stderr!r}",
        )
        require(
            "No stored secrets." in list_empty.stdout,
            f"empty linux store must report 'No stored secrets.': {list_empty.stdout!r}",
        )

    # Review 2026-08-31 (HIGH): an unsupported platform must refuse loudly.
    unknown_env = os.environ.copy()
    unknown_env["AGENT_DO_CREDS_PLATFORM"] = "unknown"
    list_unknown = run("./agent-do", "creds", "list", env=unknown_env)
    require(list_unknown.returncode != 0, "unknown platform must fail")
    require(
        "unsupported platform" in list_unknown.stderr,
        f"unknown platform must explain itself on stderr: {list_unknown.stderr!r}",
    )
    require(
        "No stored secrets." not in list_unknown.stdout,
        f"unknown-platform failure must not look like an empty store: {list_unknown.stdout!r}",
    )

    # Review 2026-08-31: windows without powershell.exe must refuse loudly.
    # Only meaningful where powershell.exe is genuinely absent (macOS/Linux CI).
    if shutil.which("powershell.exe") is None:
        win_env = os.environ.copy()
        win_env["AGENT_DO_CREDS_PLATFORM"] = "windows"
        list_win = run("./agent-do", "creds", "list", env=win_env)
        require(list_win.returncode != 0, "windows without powershell must fail")
        require(
            "powershell.exe not found" in list_win.stderr,
            f"missing powershell must explain itself on stderr: {list_win.stderr!r}",
        )

    print("credential tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
