---
workflow: 2
manna: mn-7cac30
track: mn-455a88
source: 'Erik 2026-10-22: create manna to build this; Superhuman feasibility review .dev/2026-10-22-superhuman-feasibility.md'
base_commit: c664a81c024fb9a46bc3957528f614679cb0a16c
scope: 'Harness: build agent-do superhuman for Split Inboxes, Auto Labels, and Auto Archive'
inputs:
- 'Erik 2026-10-22: create manna to build this; Superhuman feasibility review .dev/2026-10-22-superhuman-feasibility.md'
binding: sha256:b8939d66fe0508d9cede4ccba5b2af749f73095cebaf563de48fde3d9ab19ad4
---

# Handoff: Harness: build agent-do superhuman for Split Inboxes, Auto Labels, and Auto Archive

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7cac30
```

## Scope

Harness: build agent-do superhuman for Split Inboxes, Auto Labels, and Auto Archive

## Inputs

- Erik 2026-10-22: create manna to build this; Superhuman feasibility review .dev/2026-10-22-superhuman-feasibility.md

## Work order

## Goal

Build `agent-do superhuman` to manage the persistent organization settings in Superhuman itself: Split Inboxes, Auto Labels, and Auto Archive rules. Erik wants substantial control over filters and inboxes. Message search or one-time bulk triage alone does not satisfy this item.

## Required behavior

- Account discovery and explicit account selection; doctor and snapshot distinguish documented capability, available capability, authenticated access, and verified readiness.
- Split Inboxes: list/show definitions, preview matching conversations, create/update, reorder, disable, hide when empty, and control whether matches also appear in Important/Other.
- Auto Labels: list/show, create/update deterministic conditions and AI prompts where the account supports them, AND/OR composition, exclusions, and product-native previews. Report plan limits and retrospective application honestly.
- Auto Archive: inspect and change label-based archiving, Always Archive, and Never Archive for senders/domains. Preserve Superhuman precedence and identify any provider-native rule interaction.
- Configuration plans show before/after changes, affected account and objects, and supported verification. Apply only against the expected current state, serialize mutations, read back after reload, and record receipts. Repeating a request must not create duplicates. A stale plan, wrong account, expired login, absent control, or failed prerequisite stops the write.
- Keep `agent-do email` as the general mailbox surface. Superhuman owns its rules and classification; do not create a competing local routing engine or substitute Gmail/Outlook rules for Superhuman settings.

## Transport and implementation

1. Discover the authenticated official MCP tool surface at https://mcp.mail.superhuman.com/mcp before freezing capability claims. The October 22 review found documented split/label reads and thread updates, but no documented configuration writes. Published examples are not an exhaustive live schema.
2. Use official supported operations where present. For required settings absent from the official interface, implement and test the actual Superhuman settings UI through existing `agent-do browse` or `agent-do macos`. Prove that path early. A chat connector alone is not a standalone CLI implementation.
3. Reuse `creds`, appropriate `auth` infrastructure, browser/session control, JSON output conventions, and existing verification patterns. Browser login state and MCP authorization are distinct. Never log credentials, cookies, or unnecessary message bodies. Do not edit private app storage, invent undocumented endpoints, or bypass a broken production path.
4. Suggested command families: doctor, accounts, snapshot, splits, autolabels, archive-rules, plan, apply, verify. Final names should follow current repository patterns. All mutations are account-scoped and carry read-back results.
5. Register the tool, help, routing/discovery metadata, readiness requirements, and complete five-beat contracts with correct destructive/sensitive/own-state attributes. Add focused tests, root runner coverage, and user documentation. Follow repository approval rules for any genuinely new dependency.

## Acceptance and validation

- Fixture/contract coverage proves account isolation, pagination/completeness reporting, capability differences, duplicate prevention, stale-plan rejection, expired-auth failure, partial-write reporting, split ordering, exclusions, and archive precedence.
- On an authorized account, demonstrate configuration inventory, native preview, a controlled change through the intended transport, reload/read-back, and restoration of the original configuration. Record exact scope and outcomes without exporting private mailbox content. Distinguish restoring configuration from reversing any labels already applied to historical mail.
- Verify the required settings families, not just email search and thread edits. A failed or unavailable settings transport is an explicit unfinished requirement; no connector-only completion claim.
- Run the new focused suite, relevant existing email/auth/browser checks, formatting/lint/type checks applicable to the touched code, `agent-do harness contracts validate` with zero warnings, contracts drift checks for the new tool, and the canonical root gate required by the repo.
- Close under the repository receipt/commit rule. If an acceptance step can only be performed by Erik, track that exact field check separately; report unverified product behavior accurately.

## Starting evidence and prerequisites

Review pin: c664a81c024fb9a46bc3957528f614679cb0a16c. `agent-do email` includes Graph and local Mail index coverage; the review shell had no configured Graph access. The existing email fixture suite and 32 Graph/coverage tests passed. There is no registered `agent-do mail` tool.

Superhuman is installed as /Applications/Superhuman.app (com.superhuman.electron), but AppleEvents probing found no scripting dictionary. The default Python lacked AppKit, built-in computer-use surfaces were disabled, and restored browser state reached only the public website. These are recorded review limitations, not proof of present failure; recheck live readiness before implementation. The official Superhuman plugin was available but uninstalled at review time. Business/Enterprise and Ask AI were documented MCP prerequisites; verify account eligibility and permissions rather than assuming access.

## Sources

- Full assessment: .dev/2026-10-22-superhuman-feasibility.md (also copied to iCloud Transfer and the Erkverse Obsidian vault). This work order carries the build requirements so it does not depend on an ignored local report.
- Official MCP: https://help.superhuman.com/hc/en-us/articles/46005696690317-Superhuman-Mail-MCP-Server
- Setup: https://help.superhuman.com/hc/en-us/articles/47980509830157-Set-Up-the-Superhuman-Mail-MCP
- Split Inboxes: https://help.superhuman.com/hc/en-us/articles/46005636204941-Custom-Split-Inbox
- Auto Labels: https://help.superhuman.com/hc/en-us/articles/46005657758861-Auto-Labels
- Auto Archive: https://help.superhuman.com/hc/en-us/articles/46005662460813-Auto-Archive

Authority: Erik requested creation of this Manna build item on 2026-10-22 following the feasibility review. This filing leaves the item open and unclaimed; it does not start implementation or authorize unrelated publishing or mail sending.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7cac30`.
4. Commit with `Manna: mn-7cac30` and run `agent-do manna done mn-7cac30` only after the work is verified.
