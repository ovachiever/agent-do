from __future__ import annotations

import json
from typing import Any

def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))

def print_table(rows: list[dict[str, Any]], fields: list[str]) -> None:
    if not rows:
        print("No results.")
        return
    widths = {field: len(field.upper()) for field in fields}
    for row in rows:
        for field in fields:
            widths[field] = max(widths[field], len(str(row.get(field, "") or "")))
    print("  ".join(field.upper().ljust(widths[field]) for field in fields))
    for row in rows:
        print("  ".join(str(row.get(field, "") or "").ljust(widths[field]) for field in fields))

def output(payload: Any, *, json_mode: bool, table_fields: list[str] | None = None) -> None:
    if json_mode:
        print_json(payload)
        return
    if isinstance(payload, list) and table_fields:
        print_table(payload, table_fields)
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}: {json.dumps(value)}")
            else:
                print(f"{key}: {value}")
        return
    print(payload)
