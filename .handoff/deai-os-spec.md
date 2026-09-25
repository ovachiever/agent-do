# DEAI OS: engineering spec (v0, 2026-09-25)

SPEC ONLY. No code before Erik's go, per the taxonomy gate.

## 0. Definition

One rule source. Deterministic gates. Typed feedback intake. Gates refuse named
tells after generation; they impose no constraint on what gets written. Every
verb exits typed, emits JSON under --json, counts exactly, and takes every
threshold from calibration, never from a literal.

## 1. Components

- Vault (data): corpus, calibration, register packs, lexicon, catch log. One
  versioned home in this repo.
- Engines (code): lint (exists), ensemble (ported), fingerprint stats (ported),
  meters (new columns in stats).
- Verbs (new): gate, catch, catches, ratify, calibrate, registers. Existing:
  lint, packs, validate, measure, guard.
- Hooks: existing PostToolUse prose-lint (unchanged, reads vault packs); new
  Stop reply gate.
- Runtime pattern: deployed services vendor agent-do and pipe replies through
  gate before send.

## 2. Data layout

```
voice/
  corpus/            # certified text; RECEIPTS.jsonl: sha256, source, date per file
  calibration.json   # zones + provenance (model versions, batch receipts)
  packs/             # default.json, essay.json, terminal.json, product-answer.json, ...
  registers.yaml     # surface -> pack
  catches.jsonl      # append-only intake log
  VERSION
  CHANGELOG.md
```

Per-repo override: `.deai.yaml`, one field, `register: <name>`. This file
replaces CLAUDE.md voice prose everywhere.

## 3. Interfaces

### deai gate <path|-> --register R [--json]

Runs lint + ensemble + stats against the vault in one pass.

- exit 0: clean
- exit 2: rule flags
- exit 3: ensemble or fingerprint outside calibration zone
- exit 4: unknown register / usage error

JSON: `{register, words, flags[], ensemble: {score, zone}, stats: {metric:
{value, corpus, zone}}}`. Reads stdin when path is `-`, for pipelines and
servers.

### deai catch --text T --fix F --register R --surface S [--why W]

Typed intake for a human correction.

- Missing T or F: exit 2, message names the missing field. Nothing written.
- On accept, three writes, atomic as a unit: corpus append (dated, hashed),
  candidate item on this repo's manna board, catches.jsonl entry.

### deai catches [--status candidate|measured|ratified|live]

Lifecycle listing. Nothing is ever deleted; a rejected candidate keeps its
measurement attached.

### deai ratify <candidate-id>

Agents get exit 2, always; the enforcement mechanism mirrors manna dream
conversion (refusal, not convention). On Erik's invocation: pack write,
VERSION bump, CHANGELOG line. Open question 10.1 covers how Erik's invocation
is distinguished.

### deai calibrate

Re-derives calibration.json from vault corpus plus declared AI batches (batch
spec lives in config with provenance, never as a CLI literal). Identical
inputs must reproduce identical output. Writes receipts beside the result.

### Stop reply gate (hook)

Reads the turn's final assistant message from the transcript, runs
`gate - --register terminal`. On exit 2 or 3, blocks the stop and returns the
findings so the model revises. At most one block per turn, enforced by a
turn-keyed marker. Ships only after the terminal pack's false-positive rate is
measured against a recorded transcript sample (sample size and source in the
receipt).

## 4. Registers (initial set)

default, essay, terminal, product-answer, email, x-post, site-copy,
commit-message. Terminal permits technical vocabulary; tells stay banned.
Pack contents come from the measured-rule workflow only.

## 5. Catch lifecycle

candidate -> measured (`deai measure`, false-positive rate recorded) ->
ratified (Erik only) -> live (VERSION+1, enforced by every gate and hook on
the machine on next invocation). Queued first cargo: deictic-time and
negation-run (mn-368b25), performed-humility (mn-d06a8f).

## 6. Determinism requirements

- No network and no vendor-model calls anywhere in the enforcement path;
  ensemble runs pinned local models, versions recorded in calibration.
- Same input + same VERSION = same output, every verb.
- All zones from calibration.json; a bare numeric bound in tool code is a
  defect and `harness bounds scan` covers the tool.
- Loop guards: reply gate blocks once per turn; runtime regeneration bounded
  at one attempt, then ship with a logged receipt.
- Gates refuse; they never rewrite.

## 7. Migration (each row one manna item)

| id | work | blocked by |
|---|---|---|
| M1 | Vault COPY from substack-writings/voice (Erik's ruling 2026-09-25: copy, never move; the substack working set stays untouched and its gate keeps running as-is in the interim). Hash receipts on both sides; a drift check compares the homes; lint output on the archived drafts must diff empty between homes; cutover to a single home is its own later item, Erik-gated | none |
| M2 | gate verb; substack DRAFT GATE becomes `deai gate --register essay` | M1 |
| M3 | registers.yaml + `.deai.yaml` resolution | M1 |
| M4 | terminal pack, measured; Stop reply gate registered | M3 |
| M5 | catch / catches / ratify; correction-keys hook files catches | M1 |
| M6 | meters v2: verbless-spine share, appositive run length, catalog-fragment runs, verdict-rhythm, deictic and negation counters, with corpus baselines (absorbs mn-ecdc33) | M1 |
| M7 | runtime pattern reference in versova-supply-intelligence | M2 |
| M8 | CLAUDE.md shrink: substack repo now; a proposed diff for the global file, applied by Erik's hand | M3, M9 |
| M9 | first cargo through measure/ratify end to end | M5 |

## 8. Acceptance receipts

- M2: flag set byte-identical to the legacy three-command gate across every
  archived draft in substack-writings.
- M4: a seeded tell in a scripted reply blocks exactly once and passes after
  revision; false-positive rate on the recorded transcript sample logged in
  the item.
- M5: refusal matrix executed (each missing field); atomicity verified by an
  induced mid-write failure.
- M9: one candidate walked candidate->live; VERSION incremented; the same
  tell then flags in a fresh repo with no local config.

## 9. Non-goals

Generative rewriting inside gates. Cloud calls in enforcement. Auto-
ratification. Pangram integration (separate lane: mn-739746, mn-d4b0fd).

## 10. Open questions (Erik rules)

1. ratify authentication: interactive confirm, flag file, or other.
2. Corpus placement: it contains sent email; confirm this repo is an
   acceptable home or name a separate private vault path.
3. Terminal register strictness: full essay tell-set in replies, or a named
   subset.
4. Vault cutover timing: the interim runs dual-home (substack authoritative
   for its own gate, this repo canonical for everything new) with the drift
   check standing; Erik names the cutover moment.
