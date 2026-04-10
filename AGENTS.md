# agent-do Engineering Guide

This file is the current as-is operating guide for agents working in this project.

## Scope
- Applies to `agent-do/`.

## Source Of Truth
1. Running code and checked-in files in this project
2. Local manifests and lockfiles
3. Local README, deployment files, and nearest scoped `AGENTS.md` files
4. Historic notes only when they still match the code

## Current Repo Signals
- Root manifests: `requirements.txt`.
- Inferred stack signals: Python.
- Allowed external helper reference here: `agent-do` when browser, mobile, desktop, or GUI automation is actually required.

## Top-Level Layout
- `lib/` - shared library code
- `bin/` - checked-in subtree
- `hooks/` - hooks or automation
- `tools/` - checked-in subtree
- `agent-do` - checked-in root file
- `ARCHITECTURE.md` - checked-in root file
- `CHANGELOG.md` - checked-in root file
- `context7` - checked-in root file
- `IMPROVEMENTS.md` - checked-in root file
- `install.sh` - checked-in root file
- `INTEGRATION.md` - checked-in root file
- `PLAN.md` - checked-in root file
- `README.md` - checked-in root file
- `registry.yaml` - checked-in root file

## Working Rules
- Keep this file factual and current-state. Do not turn it into a roadmap or target architecture document.
- Keep unrelated non-engineering language out of this file.
- Use the nearest scoped `AGENTS.md` before changing a deeper package, app, or subsystem.
- Prefer small, local changes and validate through the manifest that owns the touched code.

## Validation
- Use the commands defined in `pyproject.toml`, `requirements.txt`, or the local README before validating changes.
