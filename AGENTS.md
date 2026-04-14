# agent-do Engineering Guide

This file is the operating guide for agents working in this repository.

## Scope

Applies to `agent-do/`.

## Source Of Truth

1. Running code and checked-in files in this project
2. Local manifests and lockfiles
3. Local README, deployment files, and nearest scoped `AGENTS.md` files
4. Historic notes only when they still match the code

## Current Repo Signals

- Root manifests: `requirements.txt`.
- Inferred stack signals: Python, Bash, Node.js, Rust.
- Allowed external helper reference: `agent-do` when browser, mobile, desktop, or GUI automation is actually required.

## Top-Level Layout

- `assets/`: images and visual assets
- `bin/`: core routing, discovery, and bootstrap scripts
- `hooks/`: Claude Code integration hooks
- `lib/`: shared library code (Python, Bash, Node.js)
- `tests/`: test scripts
- `tools/`: 84 tools (standalone scripts + directory-based tools)
- `agent-do`: main entry point (bash)
- `registry.yaml`: master tool catalog
- `install.sh`: idempotent installer
- `ARCHITECTURE.md`: routing flow and component map
- `CHANGELOG.md`: release history
- `CLAUDE.md`: Claude Code project instructions
- `CONTRIBUTING.md`: contribution guidelines
- `INTEGRATION.md`: Claude Code hook wiring
- `LICENSE`: MIT license
- `README.md`: public-facing documentation
- `SECURITY.md`: vulnerability reporting policy

## Working Rules

- Keep this file factual and current-state. Do not turn it into a roadmap or target architecture document.
- Keep unrelated non-engineering language out of this file.
- Use the nearest scoped `AGENTS.md` before changing a deeper package, app, or subsystem.
- Prefer small, local changes and validate through the manifest that owns the touched code.

## Validation

```bash
./test.sh                                      # Root smoke tests
cd tools/agent-browse && npm test              # Browser tool tests
cd tools/agent-manna && cargo test             # Issue tracker unit tests
bash tools/agent-context/test/integration.sh   # Context tool integration tests
bash tools/agent-manna/test/integration.sh     # Manna integration tests
```
