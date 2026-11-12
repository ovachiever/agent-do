# Audiobook archives with Libation

`agent-do audiobook` manages account profiles, cached Audible libraries,
explicit book downloads, audio verification, and non-secret archive receipts.
Libation is its first provider. The adapter targets **Libation 14.2.2**; other
versions fail closed. The implementation is tested offline with fake engines;
no live Audible download has been tested.

## Setup

The adapter currently supports POSIX hosts (macOS/Linux), Python 3.10+, and the
Libation CLI. Libation itself also supports Windows; this adapter uses POSIX
locks and a pseudo-terminal and does not yet support native Windows.
Install Libation from its [official release](https://github.com/rmcrackan/Libation/releases/tag/v14.2.2).
Set `AGENT_LIBATION_BIN` if its CLI is not on PATH or in the usual macOS app
bundle. Install ffprobe for archive verification; ffmpeg is needed only for
`verify --deep`. Test hooks `AGENT_FFPROBE_BIN` and `AGENT_FFMPEG_BIN` can also
select explicit executables.

Use the Libation GUI to initialize a **dedicated state directory per account
and marketplace**, including `Settings.json`. Configure at most one Audible
account in it and no additional marketplaces. Close the GUI while running
adapter operations. For another account, use another alias, native directory,
and archive directory. The adapter changes native directory/file permissions
to 0700/0600; do not point it at shared state that other users need to access.

Encrypted native sessions require their existing master key. The adapter
requires a valid Base64-encoded 32-byte `LIBATION_MASTER_KEY` for native
operations. Agent Do resolves this declared credential from its secure store.
To store a native raw master-key export without printing it:

```bash
base64 < /secure/libation-master.key | tr -d '\n' | agent-do creds store LIBATION_MASTER_KEY --stdin
```

Use Libation's GUI or `export-master-key` on the machine holding its encryption
key to produce that raw file. Keep/delete the export according to your own
secret-retention policy. Do not place keys or passwords in profile settings.
Different accounts can share this encryption key, while keeping separate native
state. If native states use different keys, supply the corresponding key through
the supported environment interface for that invocation; the adapter does not
create another secret manager.

Register an already authenticated native account:

```bash
agent-do audiobook connect --account home --marketplace us \
  --libation-files /private/path/libation-home --output /private/path/audiobooks --json
```

Or establish/renew authentication through Libation's supported browser flow:

```bash
agent-do audiobook connect --account home --marketplace us \
  --libation-files /private/path/libation-home --output /private/path/audiobooks \
  --login --email owner@example.com --json
```

`--login` requires a user terminal. It displays the sign-in URL on that terminal;
complete Audible login/MFA in your browser, then paste the final browser URL at
the hidden prompt. The response is passed through a private pseudo-terminal,
never argv, JSON, receipts, or adapter logs. Without a terminal, the command
returns `interactive_terminal_required`. There is no password injection or
browser-cookie extraction. Repeat the same profile arguments when refreshing
it. Profiles cannot be silently repointed at another account/output/format.
Marketplace names must exactly match native `list-accounts --bare` locales;
for example `us`, `uk`, or `germany`.

## Commands

```bash
agent-do audiobook doctor --json
agent-do audiobook accounts --json
agent-do audiobook sync --account home --json
agent-do audiobook snapshot --account home --json
agent-do audiobook download B012345678 --account home --json
agent-do audiobook download B012345678 --account home --resume --json
agent-do audiobook verify B012345678 --account home --json
agent-do audiobook verify B012345678 --account home --deep --save-receipt --json
agent-do audiobook reconcile --account home --json
agent-do audiobook download B012345678 B098765432 --account home --json
```

With exactly one profile, `--account` is optional. `--marketplace` can assert
that the selected profile uses the intended marketplace. `snapshot --export
/path/to/library.json` also reads an existing native JSON export without a
profile or native engine. That mode reports unknown freshness and unverified
archives. `accounts` reports cached readiness with its last check time, never a
claim that a live authentication request has just succeeded.

`sync` is the explicit network refresh. A scan must produce CLI completion,
fresh default-format native library-count logs matching the processed count,
and no error/fatal records. This guards
against the pinned engine swallowing some account failures and returning zero.
Custom logging that cannot provide this evidence fails as `sync_unverifiable`.
Failed or partial scans preserve the last good cache; snapshot/reconcile report
the failed refresh separately. A successful empty scan is an empty library.
Library parsing uses the supported JSON export and whitelists public fields.

`download` requires explicit IDs present in the cached library; there is no
implicit whole-library selector. Batches are serialized and return one result
per ID. Timeouts/interruption preserve earlier results and mark remaining IDs
`not_attempted`. `--timeout <seconds>` supplies a per-subprocess time budget;
otherwise native operations can run until completion or interruption.

M4B is the default. For explicit MP3 transcoding, register a separate profile
with `connect ... --format mp3`. Downloads override native settings to retain
one file, keep the ASIN in filenames, avoid overwrites, avoid audible-brand
stripping, and disable Audiobookshelf upload. No deletion, scheduling, broad
conversion, or Audiobookshelf feature is exposed.

## Archive state and verification

Audio is written under `<output>/.staging/<book-id>`, with source identity saved
alongside it. The native in-progress directory is stable per book. `--resume`
reuses those paths; byte-level transfer recovery is delegated to Libation.
Completed staged audio can be verified/promoted without a new download. Invalid
staged audio fails verification and is left for inspection; it is not silently
overwritten. Final archives live under `<output>/<book-id>/payload/` and are
created exclusively. An existing archive is skipped only when its receipt still
matches its identity, size, source duration, format, and SHA-256 hash. Conflicts
require explicit investigation instead of replacement.

Verification checks nonempty files, parsed container, an audio stream, positive
finite duration, expected format, and chapter presence for M4B. Source duration
uses the export's integer minutes with a one-minute quantization allowance.
Missing source duration is recorded as unavailable. `--allow-no-chapters`
explicitly waives chapter presence and records the unavailable check. Container
inspection does not prove every audio frame decodes; `--deep` uses ffmpeg to
perform a full decode and fails on decode errors.

`verify` is read-only by default. `--save-receipt` writes evidence separately.
Downloads save receipts automatically **after** verification, including account
alias, marketplace, book ID/title, engine version, timestamps, file path/size,
format, duration, chapter count, hash, unavailable checks, and verification
limits. Plugin state writes are atomic. A crash after promotion but before the
receipt can be repaired with `verify <id> --save-receipt`; files are retained.

`snapshot` and `reconcile` use local cache, operation records, and file hashes;
they never invoke native account commands or contact Audible. Hashing a large
library can take time. Reconcile reports
missing, in-progress/interrupted, failed, completed-unverified, and unverifiable
archives. Changed files invalidate prior receipts. A busy state lock returns
`operation_in_progress` instead of starting a second native operation.

All operational success/failure responses are one JSON document. With `--json`,
invalid arguments also produce one document (exit 2); operational failures exit
1 and success exits 0. Raw provider output is classified then discarded,
including probe, scan, download, and decode errors. Only the user-visible browser
sign-in URL is displayed during interactive authentication.

## Discovery and integration decision

Sources were inspected at the exact release above, rather than assuming
current development flags exist in a release. No installed Libation executable
or Audible account was available. Tests use an offline fake executable; this is
a **source-inspected pin, not a live-tested engine integration**.

- [CLI documentation](https://github.com/rmcrackan/Libation/blob/v14.2.2/docs/advanced/command-line-interface.md): Windows, macOS, Linux and Docker CLI; Windows
  installers/ZIPs, macOS DMGs, Linux deb/rpm packages are published. CLI cannot
  perform every upgrade migration; configure/upgrade through the GUI first.
- [Program.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/LibationCli/Program.cs) and
  [Setup.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/LibationCli/Setup.cs): parser help bypasses runtime initialization;
  normal verbs run migrations/logging. Version headings come from HelpVerb.
- [LoginExternalOptions.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/LibationCli/Options/LoginExternalOptions.cs): supported external-browser login handles Audible's
  login/MFA. Redirected stdin requires `--response-url`, which exposes an
  authentication response in argv. `connect --login` uses a private pseudo-terminal, disables echo,
  displays only the trusted browser sign-in URL on the user terminal, and reads
  the final redirect with hidden input. It never uses `--response-url`. Password environment injection is not supported
  by the inspected CLI. Browser-cookie extraction is not part of this design.
- [Docker authentication/storage documentation](https://github.com/rmcrackan/Libation/blob/v14.2.2/docs/installation/docker.md): `LIBATION_MASTER_KEY` is a supported Base64
  encryption-key interface. The dispatcher already resolves declared secret
  environment variables from `agent-do creds`; the audiobook registry declares
  this key optional. Store an existing key using `agent-do creds store
  LIBATION_MASTER_KEY --stdin`. Do not put the key in argv or ordinary settings.
  Libation still owns `AccountsSettings.json` tokens and device identity, using
  its native encryption/OS-store mechanism. The native engine may create a local
  key file or fall back to plaintext on encryption failure. This adapter does
  not claim those sessions are held by Agent Do's secure store. Mutating commands protect the entire native state tree with owner-only
  permissions and umask, reject symlinks, and request encrypted token storage.
  Key presence alone does not prove existing tokens are encrypted. Existing
  plaintext token conversion remains an explicit native GUI operation.
- [ScanOptions.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/LibationCli/Options/ScanOptions.cs): scans all accounts unless account ids/nicknames are
  selected. CLI scan disables interactive login; expired sessions must fail
  explicitly. `list-accounts --bare` exposes local account readiness, not proof
  that a live request will authenticate. Multiple marketplaces can share an
  account. Each profile requires a dedicated native state directory
  with exactly one account and no additional marketplaces, preventing ASIN-only
  native selection from crossing accounts. Native account identity is hashed
  into the profile and checked before network operations.
- [ExportDto.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/ApplicationServices/ExportDto.cs): supported JSON export has stable product ID, native
  account, locale, title, duration in integer minutes, and native download status.
  JSON uses C# property names, unlike CSV headings. Only whitelisted public fields
  are returned. No internal database parsing is used.
- [LiberateOptions.cs](https://github.com/rmcrackan/Libation/blob/v14.2.2/Source/LibationCli/Options/LiberateOptions.cs): naming an ASIN explicitly re-downloads even an already
  liberated book. Native CLI exit zero is insufficient (some failure paths only
  print an error). The adapter checks a verified receipt before calling
  it, isolates staged output, and inspects actual audio afterward. Retries use
  the same native in-progress directory, delegating byte-level resume to the
  engine; no promise of byte-level resume has been live-tested. Engine access
  uses both a global adapter lock and a lock in native state. Plugin locks
  cannot protect against independently running GUI/native CLI commands. A
  native GUI-busy warning fails the adapter operation.
- [Audio format documentation](https://github.com/rmcrackan/Libation/blob/v14.2.2/docs/features/audio-file-formats.md): original audio normally uses M4B and preserves the
  delivered codec; MP3 normally transcodes and must remain opt-in. Container
  verification will not prove full frame decoding.

[Media PR #21](https://github.com/ovachiever/agent-do/pull/21) uses one neutral
family with internal providers, provider-specific readiness, and family-owned
verification. Audiobooks are a separate library/account/archive domain from
that PR's disc/transcoding workflow. This implementation follows the family
principle without importing or depending on its unmerged code. Provider-specific
work stays behind the audiobook surface.


## Validation and remaining limits

Run `python3 tests/test_audiobook.py` with Python 3.10+ for offline workflow,
failure, permission, isolation, batch, redaction, and private-login tests.
The root suite includes it. Contracts, contract drift, generated docs, and health
checks are wired through the repository's existing mechanisms.

Live engine/session/storage behavior has not been exercised against Audible.
The pin is source-inspected and fake-tested, not a claim of live compatibility.
Native token encryption can fall back to plaintext in the upstream engine;
the adapter rejects a fresh logged encryption failure, requests encrypted
storage, and restricts file permissions, but does not certify preexisting
native tokens as encrypted. Native authentication/device secrets remain native
state, not Agent Do-managed secrets; only the supported master-key environment
interface integrates with `creds`.

Manna work tracking could not be initialized: `manna-core` and the Rust toolchain
are absent in this checkout. No board JSONL or handoff pair was fabricated.
