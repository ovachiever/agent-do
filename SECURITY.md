# Security Policy

## Reporting Vulnerabilities

If you discover a security vulnerability in agent-do, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email the maintainer directly or use GitHub's private vulnerability reporting feature on the repository's Security tab.

Include:

- A description of the vulnerability
- Steps to reproduce
- The potential impact
- Any suggested fixes, if you have them

You should receive a response within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Scope

Security concerns for this project include:

- **Credential handling**: `agent-do creds` stores secrets in OS-level secure storage (macOS Keychain, Linux Secret Service). Bugs in credential resolution, storage, or export are in scope.
- **Auth session data**: `agent-do auth` manages encrypted auth bundles under `~/.agent-do/auth/`. Leaks or improper encryption are in scope.
- **Reference fetching**: `agent-do context` fetches public docs and source files for local retrieval. Leaks through source URLs, provenance metadata, refresh logs, or cached reference material are in scope.
- **Command injection**: Tools dispatch user-provided arguments to shell commands. Injection vectors through tool arguments or natural language routing are in scope.
- **Hook behavior**: Claude Code hooks intercept tool calls and inject context. Unintended information disclosure through hook output is in scope.

## Reference Fetching Boundaries

`agent-do context` is designed for public reference material, not private data ingestion.
For HTML sources it preserves raw downloaded HTML in the local cache for
provenance and indexes extracted readable text for retrieval. Do not register
private authenticated pages as context sources.

- WAN fetches use plain `curl` with curl config disabled, no browser cookies, no saved auth state, and bounded connection/request timeouts.
- GitHub directory fetches are bounded by crawl limits and text-file allowlists.
- Refresh failures preserve the last good cache entry and mark freshness metadata as failed instead of silently replacing content.
- Agent-facing output redacts common secret-bearing URL query parameters such as token, key, secret, signature, password, auth, and credential values.
- `--require-fresh` and `--require-official` are fail-closed retrieval controls for workflows that need current or trusted reference material.
- Background maintenance is opt-in. `agent-do context maintain schedule print` shows the launchd job before installation.

## Out of Scope

- Vulnerabilities in third-party dependencies (report those upstream)
- Issues requiring physical access to the machine
- Social engineering

## Supported Versions

Security fixes are applied to the latest release only.
