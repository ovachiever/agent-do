---
workflow: 2
manna: mn-86b4e7
track: mn-455a88
source: null
base_commit: ff0b766b4a505b665701807e84206c29f5aebcb3
scope: 'Harness: browse import-browser (arc) dies on ''Can''t resolve blob if blob dir is not set'' and re-exports a stale signed-out session'
inputs: []
binding: sha256:379bac0d89f8b67b0d9676cd8079782ceb859a3f209057042ced8201105161c7
---

# Handoff: Harness: browse import-browser (arc) dies on 'Can't resolve blob if blob dir is not set' and re-exports a stale signed-out session

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-86b4e7
```

## Scope

Harness: browse import-browser (arc) dies on 'Can't resolve blob if blob dir is not set' and re-exports a stale signed-out session

## Inputs

- None declared.

## Work order

The Arc cookie import in agent-browse has failed since ~2026-09-24 with a dependency ValueError about a missing blob dir; the wrapper then exports the old ytmember session, whose cookie names look authenticated but YouTube treats as signed out. Fix the import (blob-store Chromium profiles), make failure loud (typed refusal, nonzero exit), stop stale re-exports, and add a headless signed-in verification. Full work order appended to the handoff.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-86b4e7`.
4. Commit with `Manna: mn-86b4e7` and run `agent-do manna done mn-86b4e7` only after the work is verified.


---

# Work order: `agent-do browse session import-browser --browser arc` fails with "Can't resolve blob if blob dir is not set" and silently hands back a stale, signed-out session

## Observed (measured 2026-09-24 to 2026-09-26, Erik's Mac Studio)

- `agent-do browse session import-browser ytmember --browser arc --domain .youtube.com` exits with a Python traceback ending `ValueError: Can't resolve blob if blob dir is not set`.
- `~/.local/bin/refresh_yt_cookies.py` wraps that call with `capture_output=True` and does not check the return code, then runs `agent-do browse session export ytmember`, which exports whatever `ytmember` already held. The exported file carried cookie NAMES that look authenticated (LOGIN_INFO, SID, SAPISID, __Secure-3PSID) but YouTube rejects them: loading the session headless and opening `https://www.youtube.com/account` renders the "Sign in" page; `yt-dlp --cookies` on a members-only video returns "This video is available to this channel's members," and on an age-gated video "Sign in to confirm your age."
- Arc IS running and signed in on the Studio (Erik, 2026-09-26: "I'm logged in on Arc on the Studio, it's always been logged into"). The import is the broken link, not the login.
- The same import worked on 2026-09-20/21 (it unlocked DIVINATION_ARCHIVE #471 in the-point-revision). Something changed between then and 2026-09-24: candidates are an Arc update that moved cookie values into a blob store, or a dependency change in the cookie reader. Do not guess: run the import under `-v`/a debugger and read where `blob dir` is expected to come from.
- The string "blob dir is not set" is NOT in agent-do's own source (grep of `tools/agent-browse/import_browser.py` and the tree found nothing); it comes from a dependency the importer calls. Find which one, and whether it needs a blob/`Local State` directory argument for Chromium profiles that store cookie values out-of-line.

## Acceptance

1. `agent-do browse session import-browser <name> --browser arc --domain .youtube.com` succeeds on the Studio against the running Arc, with a nonzero exit AND a typed refusal message when it cannot read the store (never a silent success over a stale session).
2. `agent-do browse session export <name> <file>` after a failed import must refuse or mark the export stale, not re-export the previous session as if fresh.
3. A verification lane in the tool: after import, load the session headless, open `https://www.youtube.com/account`, and report signed-in vs "Sign in" (the cookie names being present is NOT authentication; that was the misdiagnosis for two days).
4. `refresh_yt_cookies.py` (Erik's, in `~/.local/bin`) is outside this repo; note in the ticket close-out what it should check (the import's return code) so the wrapper can be fixed separately.
5. Tests: cover the blob-dir path (a Chromium profile whose cookie values live in a blob store) and the refusal path.

## Why it matters

The divination lane in the-point-revision pulls members-only and age-gated YouTube readings through this import; when it fails silently, the lane either falls back to asking Erik to paste transcripts or to hand-decrypting a browser cookie store, which was stopped by a safety layer and is not a route to keep. Fixing the importer is the sustainable path.

## Receipts

- the-point-revision zpc lessons les-4c9cdf, les-fe33cb, les-b55e8c (2026-09-24).
- the-point-revision memory `reference_transcribe_pipeline.md` (members-only routes 1 and 2).

## Verified implementation and close-out, 2026-09-26

Outcome: all five scoped acceptance requirements passed on Erik's Mac Studio. The final fresh headless check reached `https://www.youtube.com/account` and returned `signed_in`, exit 0, at `2026-09-26T06:45:59.696Z`. Evidence was `LOGGED_IN=true`, a visible account avatar, and no visible sign-in control. Cookie names were never treated as authentication evidence.

Ownership and delivery:

- The required first command, `agent-do manna claim mn-86b4e7`, succeeded for `codex-01a0dc3b23ab7b91`. The initial canonical binding was verified as `sha256:73bb6af2c82a64fc44de2dbfdef31b7e490177c21f43ca3a938dddcacdb682a1` before implementation.
- Source work is isolated in `/Users/erik/Custom-Coding/agent-do-mn-86b4e7`, branch `fix/mn-86b4e7-browser-import`, based on `ff0b766b4a505b665701807e84206c29f5aebcb3`. The enclosing implementation commit carries `Manna: mn-86b4e7`.
- Canonical Manna and Coord operations stayed in `/Users/erik/Custom-Coding/agent-do`. Focus and path claims covered `tools/agent-browse`, `tests/test_browser_import.py`, and this handoff.
- Primary-checkout foreign changes were preserved, including the pre-existing importer patch that catches and skips storage-reader failures. The verified branch is the delivered source; it has not been installed or integrated over that conflicting patch. No dependency installs, pushes, or pull requests were performed.

### Diagnosis and changes

1. The reported blob exception came from the pinned `ccl_chromium_reader` IndexedDB reader, not from cookie decryption. Its constructor had no sibling `.indexeddb.blob` directory. The importer now supplies that path, decodes Chromium's compressed Blink/V8 envelopes with the existing Snappy dependency, and refuses missing or malformed live blobs.
2. The forensic LevelDB reader returned historical versions and tombstones. Current-key snapshots now prevent obsolete namespace collisions and deleted IndexedDB/sessionStorage values from being resurrected. The typed-array adapter retains binary values instead of expanding them into millions of integers and changing their JavaScript types.
3. `browser-cookie3`'s CookieJar identity omitted Chromium cookie partitions. Arc contained 229 YouTube rows, but the old jar collapsed them to 24. Direct serialization through the same dependency's database/keychain/decryption path now retains 79 live cookies with partition identity, cross-site ancestry, expiry, HttpOnly and SameSite. Expired cookies and lookalike domains are excluded. No new crypto or dependencies were introduced.
4. Every browser-import attempt writes a durable `importing` receipt before reading. Completed private files are atomically published with SHA-256 bindings. Failed or interrupted attempts remain unusable; load and export reject stale or modified generations with `BROWSER_IMPORT_STALE`. Import refusals are typed, sanitized JSON and exit 2, including a missing required storage reader. The regression exercises the actual shell-to-Node export command and verifies that refusal leaves an existing destination untouched.
5. `session verify <name> --site youtube` restores the saved state in a dedicated headless browser and evaluates the actual account page. Signed-out and indeterminate states exit 2. Large IndexedDB state is restored in bounded batches with the installed Playwright decoder. The normal session loader shares that restoration path and no longer falls back to silently dropping storage or bad cookies. Verification owns a loopback BrowserServer with bounded cleanup and process-tree termination on a stuck close.
6. `session export` now reads saved state directly without launching or disturbing a browser daemon. Imported metadata explicitly says authentication is unverified until the account check succeeds.

### Executed focused validation

Commands below ran from the isolated worktree unless another directory is stated. Existing primary-checkout dependencies were reused; nothing was installed.

| Command | Actual result |
| --- | --- |
| `/Users/erik/Custom-Coding/agent-do/.venv/bin/python3 tests/test_browser_import.py` | PASS, 26 executed tests. Real synthetic Chromium LevelDB WAL/blob/V8/Snappy fixtures reproduce the original exception and cover missing/corrupt blobs, missing dependencies, current snapshots, binary types, cookie partitions, typed refusals, stale export, publication failure and recovery. |
| `python3 tests/test_browse_session_defaults.py` | PASS, executed. |
| `python3 tests/test_tool_regressions.py` | PASS, executed. |
| In `tools/agent-browse`: `npm test -- session.test.js session-verify.test.js storage-codec.test.js storage-restore.test.js protocol.test.js wait.test.js` | PASS, 64 executed tests across six files. These focused unit tests launch no browser. Three existing missing-source-map warnings are non-failing. |
| `env PATH="/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH" ./agent-do harness contracts validate --tool browse` | PASS, zero errors, zero warnings. |
| Same environment: `./agent-do harness contracts drift --tool browse` | PASS, zero declared-but-unimplemented verbs; 24 advisory undocumented verbs, identical to primary baseline. An earlier invocation without the repo venv failed to import YAML; the canonical venv invocation passed. |
| `bash -n tools/agent-browse/agent-browse`; `node --check` on changed/new production JS; `python3 -m py_compile` on importer and its test; `git diff --check` | PASS. Syntax/bytecode checks only, separate from executed tests. |

No full root suite or app-hosted browser suite was run. There are no compiled-only test results being presented as executed tests.

### Coordinated closing live acceptance

Source edits paused for each closing probe; Coord's `mn-86b4e7-closing-acceptance` publication recorded the live gate. The probes used a dedicated headless browser, with no visible app launch, screenshots, installation, or attachment to another session's daemon.

```text
env PATH="/Users/erik/Custom-Coding/agent-do/.venv/bin:$PATH" ./agent-do browse session import-browser mn86b4e7-acceptance --browser arc --domain .youtube.com
exit 0: 79 cookies, 3 storage origins, 1 sessionStorage origin, 2 IndexedDB databases
import receipt: ready; storage.json: 410598638 bytes

./agent-do browse session verify mn86b4e7-acceptance --site youtube
exit 0: signed_in
host=www.youtube.com pathname=/account loggedIn=true avatar=true signIn=false
checkedAt=2026-09-26T06:45:59.696Z
```

Earlier probes correctly exposed transport-size failures and then a signed-out redirect. Those failed results were retained, diagnosed and not called acceptance. The two initial stuck browser probes were contained by terminating only their verified parent/child processes; the final verifier completed and left zero owned verifier processes. The signed-in result followed the cookie partition fix.

The importer still reports 13 existing best-effort warnings for unsupported IndexedDB key paths or non-serializable values. This is an explicit format limitation, not a claim of a lossless clone of every Arc store. The required live YouTube authentication check passed with those warnings. No members-only download or account mutation was attempted.

Private session credentials remain under `~/.agent-browse/sessions/mn86b4e7-acceptance/`. Diagnostic receipts are under the worktree's ignored `.dev/mn-86b4e7/receipts/`. Credential payloads are excluded from Git, iCloud, the vault and this handoff.

### External wrapper follow-up

`~/.local/bin/refresh_yt_cookies.py` was not edited because the work order excludes it. It must stop on a nonzero import return code, require `session verify <name> --site youtube` to exit 0 with `signedIn=true`, and only then export/use the resulting cookies. It must also check the export return code and must not consume a pre-existing export after any failed step. The fail-closed exporter protects the known ignored-import-error path, but changing this external wrapper is a separate task.

Scoped acceptance remaining: none. Primary-checkout integration must preserve or resolve the pre-existing foreign importer patch; the verified local branch and its worktree are the delivered implementation. External wrapper changes and members-only downstream downloads are outside this item.

Lessons logged: 11 (new) | Decisions logged: 0 (new). The lessons cover blob/compression diagnosis, stale session refusal, current-state reconstruction, dependency diagnostics, fixture mutation, command discovery, binary preservation, decoder test setup, bounded restoration/cleanup, and cookie partition identity. `agent-do zpc harvest --auto --since last` passed with zero format issues and zero consolidation gaps.
