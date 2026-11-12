#!/usr/bin/env python3
"""Claude/Codex turn-boundary doorbell. Fixed context only; advisory on failure.

Installed on UserPromptSubmit and Stop by the normal hook bundle. The shared
coord implementation verifies the hook's session/cwd, consumes one pending bit,
and emits the runtime's documented JSON shape. No ledger content crosses here.
"""

from __future__ import annotations

import runpy
import signal
from pathlib import Path


def deadline(_signum, _frame) -> None:
    raise TimeoutError("doorbell hook budget exhausted")


def main() -> None:
    previous = None
    try:
        # Bound local git/ps/filesystem work too, not just lock contention.
        # Expiry is caught here, before the harness's five-second timeout.
        previous = signal.signal(signal.SIGALRM, deadline)
        signal.setitimer(signal.ITIMER_REAL, 2.0)
        tool = Path(__file__).resolve().parents[2] / "tools" / "agent-coord"
        runpy.run_path(str(tool))["bell_from_hook"]()
    except Exception:
        # Missing tool, old Python, corrupt/unavailable store: normal polling.
        pass
    finally:
        if previous is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    main()
