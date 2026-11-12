---
workflow: 2
manna: mn-58c9ea
track: mn-455a88
source: 'travel-bank-automation session 2026-10-22: another agent missed a 2026-10-21 SutiProcure email that Graph found'
base_commit: 4010d8a1842224a890298514ba5f84626dc6e580
scope: 'Harness: email searches live mailboxes — the local Mail index silently misses everything after May for versova.com'
inputs:
- 'travel-bank-automation session 2026-10-22: another agent missed a 2026-10-21 SutiProcure email that Graph found'
binding: sha256:3055ff3e99a7969dc6647656a43deb574287665d73c782795f063f38c2fa89f8
---

# Handoff: Harness: email searches live mailboxes — the local Mail index silently misses everything after May for versova.com

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-58c9ea
```

## Scope

Harness: email searches live mailboxes — the local Mail index silently misses everything after May for versova.com

## Inputs

- travel-bank-automation session 2026-10-22: another agent missed a 2026-10-21 SutiProcure email that Graph found

## Work order

## Why

On 2026-10-22, another agent searched for a SutiProcure sandbox password email
that arrived on 2026-10-21. It used `agent-do email search`, found nothing, and
told Erik the mail could not be reached. The email was there. A travel-bank
session found it in seconds through Microsoft Graph.

The cause is measured, not guessed:

- `agent-do email` reads Apple Mail's Envelope Index
  (`agent-do email status` -> `"platform": "macOS Mail Envelope Index"`).
- Mail.app's copy of the work account (the EWS account) stopped syncing after May 2026. That was measured 2026-10-16
  from the Envelope Index: 25,153 messages indexed for May, then one message
  total for June through October. The three IMAP accounts (two Gmail, one custom domain) kept
  syncing.
- Nothing reports the gap. A search of the stale account returns zero rows,
  and the agent reads that as "the email does not exist".
- The existing "remote hydration" path is IMAP-only and only fetches bodies
  for rows the local index already holds (`lib/email_query.py`,
  `remote_provider_config` / `hydrate_remote_message`).
  `status` reports `remote_body_search: false`. It cannot find a message the
  local index never saw.

## What already works (reuse it, do not re-derive it)

`~/Custom-Coding/travel-bank-automation/travel-bank-automation`:

- `lib/graph_auth.py`: python-o365 `Account`, client-credentials flow,
  env `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID`, target
  mailbox `GRAPH_TARGET_MAILBOX`, token cached to a file.
- `scripts/mailsearch.py`: `search`, `find`, `body <id>`, `atts`, `save`,
  `savebody`. It uses Graph `$search` (`mb.new_query().search(term)`), then
  re-filters locally because Graph also matches inside attachments.
  Confirmed live on 2026-10-22: it returned that day's messages.

Those values live in that project's git-ignored `config/.env`. Move them into
`agent-do creds` (Erik runs `agent-do creds store <KEY> --stdin`). Never
read them out of another project's .env, and never print them.

## The work

1. **Live search for the work account.** `agent-do email search / latest /
   get / export / wait / code / link` reach the work account live through
   Microsoft Graph. This is a new provider beside the Envelope Index, not a
   replacement for it. Results carry the same JSON shape plus a `source`
   field (`graph` | `envelope_index` | `imap`).
2. **Coverage guard: never answer from a stale account silently.** Before
   answering from the local index, measure each account's freshness: the
   newest `date_received` per account. Do it with the coverage query below,
   run on a copy of the index plus its `-wal`/`-shm`, since Mail holds the
   live file open. If an account in scope is stale and has a live provider,
   route that account to the live provider. If it has no live provider, say
   so in the output (`"stale_accounts": [...]` in JSON, and a stderr line in
   text). A clean zero must never be the answer for an account the tool knows
   is gapped. The staleness threshold must come from a named authority or a
   measured cadence, never a bare literal (global CLAUDE.md quantity rule).
3. **`status` tells the truth.** Report per-account newest message date, the
   live provider (if any), and whether live search is ready.
4. **Gmail (optional, second).** The Gmail accounts currently sync locally
   and are fine. Live Gmail search (Gmail API or IMAP `X-GM-RAW`) is in scope
   only if it costs little after the Graph provider lands. If it is skipped,
   file it as its own item.

Coverage query (from the 2026-10-16 measurement):

    SELECT strftime('%Y-%m', m.date_received, 'unixepoch') AS mon,
           substr(mb.url, 9, 8) AS acct, COUNT(*)
    FROM messages m JOIN mailboxes mb ON mb.ROWID = m.mailbox
    GROUP BY mon, acct ORDER BY mon, acct;

## Constraints

- Prefer extending the existing verbs (`search`, `status`, ...) with a
  provider. A new verb or new tool needs Erik's go-ahead first (taxonomy
  gate).
- Update `registry.yaml` and contracts for anything added. `./test.sh` stays
  green, and `agent-do harness contracts validate` stays at zero warnings.
- No bare bounding literals for result counts, page sizes, timeouts or
  staleness. Page through Graph to the end, or take the provider default.
- Read-only. Sending mail through Graph is out of scope.
- Unverified, so check before relying on it: the Azure app's Graph
  permission scope (application `Mail.Read` may be tenant-wide). Read it
  from the token's `roles` claim or the Azure portal, and record what it is.
  Do not assume.

## Verification

1. `agent-do email search "sutiprocure" --account <versova> --json` returns
   the 2026-10-21 and 2026-10-22 messages from the vendor sender with
   `"source": "graph"`. Before the change it returns none.
2. With the Graph creds removed, the same search prints the stale-account
   warning instead of a clean empty result.
3. `agent-do email status` lists every account with its newest date and its
   provider readiness.
4. `./test.sh` passes. The new tests use fixtures, not Erik's live mailbox.
5. Commit with a `Manna: mn-58c9ea` trailer, then `agent-do manna done mn-58c9ea`.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-58c9ea`.
4. Commit with `Manna: mn-58c9ea` and run `agent-do manna done mn-58c9ea` only after the work is verified.


## Worker return: 2026-10-22

Status: PARTIAL, implementation and fixture verification complete; required live Graph acceptance is not verified. Keep mn-58c9ea in progress and claimed by codex-01a16419b40d7490. Do not run `manna done` yet.

Initial authorization was verified against canonical Manna ownership and the normalized binding `sha256:68f5cd8a23fff8ae61c8634730121f300ef77f52116d533bd60dc82b73613722`, at base commit `4010d8a1842224a890298514ba5f84626dc6e580`.

Implemented:

- `lib/email_graph.py` adapts the named travel-bank O365 client-credentials flow and search plus local filtering. It reads only credentials resolved by agent-do, keeps tokens in memory, follows every search nextLink, scopes exact IDs to the configured mailbox, fetches MIME for export, and records the token roles when available. It exposes no send operation.
- `lib/email_query.py` copies the Envelope Index, WAL and SHM before reading, measures per-account freshness from the median interval between distinct UTC receiving days, and routes the Graph account through the existing search/latest/get/export/wait/code/link verbs. An explicit local account mapping wins; otherwise the unique Exchange account is bound, or Graph remains a separate account when ambiguous.
- Stale or unmeasurable local coverage appears in `stale_accounts`; text mode writes a warning. An empty answer with incomplete coverage fails with `incomplete_coverage`. A failed configured Graph read cannot silently fall back to local rows. Partial results retain `coverage_complete: false`.
- Results carry `source: graph | envelope_index | imap`. Exact get/JSON export retain RFC822 content under `raw_source`, since `source` now identifies provenance. Status reports every account, newest local date, measured cadence, Graph configuration, SDK availability, actual read readiness, and observed roles.
- Graph's published 1,000-result search ceiling is disclosed when reached, even after following every available page. Authority: https://learn.microsoft.com/en-us/graph/search-query-parameter . No client page-size cap is introduced; unbounded search is the default and singular verbs select one match after filtering.
- Registry credentials/capabilities and generated `docs/TOOLS.md` were updated. Gmail live search was deferred to optional item `mn-882c9e`.

Executed verification (2026-10-22):

- `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_email.py`: PASS, existing email regressions plus 32 new Graph/coverage tests executed, zero failures/skips. Final log: `.dev/mn-58c9ea/email-tests.log`.
- `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_auth_email_challenge.py`: PASS (`auth email challenge tests passed`).
- `PATH="$PWD/.venv/bin:$PATH" python3 tests/test_creds.py`: PASS (`credential tests passed`).
- `PATH="$PWD/.venv/bin:$PATH" agent-do harness contracts validate`: PASS, 103 tools declared, 0 errors, 0 warnings; bounds gate 0 errors. Existing ungated inventory remains disclosed (156 ceilings owed, 11 shared-code sites without a declaration home). Log: `.dev/mn-58c9ea/contracts.log`.
- `PATH="$PWD/.venv/bin:$PATH" bin/gen-tools-doc --check`, `bash -n tools/agent-email`, and `git diff --check`: PASS.
- `.venv/bin/python -m py_compile lib/email_graph.py lib/email_query.py tests/test_email_graph.py`: PASS. This is syntax compilation, distinct from the executed suites above.
- `./test.sh` was not run, following the dispatch instruction to run focused suites only. This Python/Bash lane has no Xcode test target; no `xcodebuild test` or `build-for-testing` receipt is claimed.
- One intermediate email-suite run failed because the fixture source limited before filtering. It was corrected to filter before limiting; the final canonical run above passed.

Live local acceptance at close (read-only, no app launch):

- `agent-do email status --json`: PASS, 5 accounts reported (one EWS, three IMAP, one local). The EWS account `ews://<work-account-id>` has newest indexed receipt `2026-05-14T20:47:34+00:00`; its measured receiving-day cadence is 86,400 seconds from 378 samples. It is reported stale. Graph readiness is false, not inferred from configuration.
- `agent-do email search sutiprocure --account ews://<work-account-id> --json`: PASS for the missing-provider guard, with `coverage_complete: false`, an explicit stale account, and `served_live: false`. Existing historical hits were not printed or persisted in the receipt.
- The same search without `--json`: PASS for the stderr stale-account warning. No message body or secret was included in these receipts.

Needed next, before completion:

1. Four keys are absent from agent-do creds: `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `GRAPH_TARGET_MAILBOX`. Erik must store them with `agent-do creds store <KEY> --stdin`. No other project's .env or token cache was read.
2. The runtime and repository venv do not contain O365. Approval to add `O365>=2.1,<3` to requirements.txt is pending under AGENTS.md's new-dependency rule. The manifest has not been changed, and no package or app was installed. Runtime provisioning also remains subject to the dispatch's no-installs boundary.
3. Once those prerequisites are authorized and ready, coordinate the live CLI pass through Coord need `mn-58c9ea-live-acceptance`: the SutiProcure search must return the 2026-10-21 and 2026-10-22 messages from the vendor sender with `source: graph`; record the real token's roles. Those two checks have not run. Application roles alone do not establish Exchange mailbox-access-policy restrictions.
4. There is no visual UI acceptance for this CLI change. No installed app launches, installs, screenshots, live session spawning, pushes, or PR creation occurred.

Lessons logged: 3 (new), les-fb049b, les-b9a76b, les-1af24f. Decisions logged: 0 (new). ZPC harvest ran after the lessons.
