# Contributing to agent-do

Thank you for your interest in contributing. This document covers the essentials.

## Getting Started

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
./test.sh
```

## Project Structure

```
agent-do              # Main entry point (bash)
bin/                  # Core routing and discovery scripts
lib/                  # Shared libraries (Python, bash, Node.js)
tools/agent-*         # Individual tools (standalone or directory-based)
hooks/                # Claude Code integration hooks
registry.yaml         # Master tool catalog
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full routing flow and component map.

## Adding a Tool

1. Create an executable at `tools/agent-<name>` (must support `--help`)
2. Add an entry to `registry.yaml` with `description`, `capabilities`, `commands`, and `examples`
3. Add `routing` metadata if the tool should participate in discovery, nudges, or offline matching
4. Add `credentials` metadata if the tool needs API keys or tokens

Shared helpers reduce boilerplate:

- `lib/snapshot.sh` for structured JSON snapshot output
- `lib/json-output.sh` for `--json` flag support
- `lib/retry.sh` for API error recovery with backoff

## Testing

```bash
./test.sh                                      # Root smoke tests
cd tools/agent-browse && npm test              # Browser tool tests
cd tools/agent-manna && cargo test             # Issue tracker unit tests
bash tools/agent-context/test/integration.sh   # Context tool integration tests
bash tools/agent-manna/test/integration.sh     # Manna integration tests
```

Run the relevant test suite before submitting changes.

## Code Conventions

- **Bash tools**: `set -euo pipefail`, source shared helpers, support `--help` and `--json`
- **Python components**: Python 3.10+, type hints where helpful, no unnecessary dependencies
- **Node.js tools**: ES modules, Playwright for browser work, Vitest for tests
- **Rust components**: Stable Rust, Clippy clean, standard error handling

Follow existing patterns in the codebase. Consistency over novelty.

## Pull Requests

1. Fork the repository and create a feature branch
2. Keep diffs small and focused on a single concern
3. Include test coverage for new functionality
4. Run the relevant test suite and confirm it passes
5. Write a clear commit message that explains the *why*, not just the *what*

## Reporting Issues

Open a GitHub issue with:

- What you expected to happen
- What actually happened
- Steps to reproduce
- Your platform (macOS, Linux, etc.) and relevant tool versions

## Security

If you discover a security vulnerability, please report it privately. See [SECURITY.md](SECURITY.md) for details.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
