"""Raw GitHub REST and GraphQL API escape hatch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..render import print_json
from ..snapshot import envelope, now_iso
from ..transport import GhError, gh_json, run_gh


def call_api(method: str, path: str, *, fields: list[str] | None = None,
             raw_fields: list[str] | None = None, headers: list[str] | None = None,
             paginate: bool = False, jq: str | None = None) -> dict[str, Any]:
    """Make a raw GitHub REST API call and return the response in an envelope."""
    args = ["api", "--method", method, path]
    for f in fields or []:
        args += ["--field", f]
    for f in raw_fields or []:
        args += ["--raw-field", f]
    for h in headers or []:
        args += ["--header", h]
    if paginate:
        args.extend(["--paginate", "--slurp"])
    if jq:
        args += ["--jq", jq]
    data = gh_json(args)
    return envelope(f"api {method} {path}", data=data)


def call_graphql(query: str, *, fields: list[str] | None = None,
                 paginate: bool = False, jq: str | None = None) -> dict[str, Any]:
    """Make a raw GitHub GraphQL call; query may be a string or @filepath."""
    # Allow @file syntax for reading query from disk
    if query.startswith("@"):
        path = Path(query[1:])
        try:
            query = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise GhError(f"failed to read GraphQL query file '{path}': {exc}") from exc
    args = ["api", "graphql", "-f", f"query={query}"]
    for f in fields or []:
        k, _, v = f.partition("=")
        args += ["-f", f"{k}={v}"]
    if paginate:
        args.extend(["--paginate", "--slurp"])
    if jq:
        args += ["--jq", jq]
    data = gh_json(args)
    return envelope("graphql", data=data)


# ── command handlers ───────────────────────────────────────────────────────────

def cmd_api(args: argparse.Namespace) -> None:
    result = call_api(
        args.method,
        args.path,
        fields=args.fields,
        raw_fields=args.raw_fields,
        headers=args.headers,
        paginate=args.paginate,
        jq=args.jq,
    )
    if args.json:
        print_json(result)
    else:
        data = result.get("data")
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2))
        else:
            print(data)


def cmd_graphql(args: argparse.Namespace) -> None:
    result = call_graphql(
        args.query,
        fields=args.fields,
        paginate=args.paginate,
        jq=args.jq,
    )
    if args.json:
        print_json(result)
    else:
        data = result.get("data")
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2))
        else:
            print(data)
