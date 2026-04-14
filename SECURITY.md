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
- **Command injection**: Tools dispatch user-provided arguments to shell commands. Injection vectors through tool arguments or natural language routing are in scope.
- **Hook behavior**: Claude Code hooks intercept tool calls and inject context. Unintended information disclosure through hook output is in scope.

## Out of Scope

- Vulnerabilities in third-party dependencies (report those upstream)
- Issues requiring physical access to the machine
- Social engineering

## Supported Versions

Security fixes are applied to the latest release only.
