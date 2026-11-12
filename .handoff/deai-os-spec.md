# DEAI OS: engineering spec (v0.2, 2026-09-25)

SPEC ONLY. No code before Erik's go, per the taxonomy gate.

v0.2 supersedes v0.1's center of gravity per Erik's rulings of 2026-09-25:
the system is a writer, not a warden. Formation first, receipts second,
gates last and only where no human is present. In interactive surfaces
there is no blocking, ever: the muck stays visible, false positives are a
defect of the highest class, and the voice arrives by influence, not
enforcement.

## 0. Goal

AI on this machine writes like Erik, drops its AI tics, and does not make
things up. Three organs, in priority order:

1. FORMATION: hand the writer Erik's actual voice at write time; turn every
   correction into training material; end state is a local model that
   carries the voice in weights.
2. RECEIPTS: every specific claim traces to a named source or gets cut.
   This is the anti-fabrication organ; it is process, not filtering.
3. NET: deterministic gates only on unattended surfaces (production bots,
   scheduled pipelines). Advisory visibility elsewhere. Gates refuse, never
   rewrite, and never run where a human is in the middle.

## 1. Surface doctrine

| Surface | Mode | Blocking | Rationale |
|---|---|---|---|
| Terminal / interactive sessions | Formation + advisory notes | NEVER | Erik sees the muck; muck is teaching signal; one false block is failure mode |
| Essays (substack pipeline) | Formation + full gate run by the writer pre-review | Gate flags require revision before Erik review, per the standing DRAFT GATE | Pre-publication artifact; Erik arbitrates final |
| Production / unattended (deployed bots, scheduled pours) | Formation at build + gate at runtime | One bounded regeneration, then ship with logged receipt | Nobody present to catch a tic at 2 AM |

## 2. Components

- Vault (data): corpus, calibration, register packs, exemplar index, pairs
  log, catches log. COPIED from substack-writings/voice, never moved
  (Erik's ruling): substack's working set and gate stay untouched in the
  interim; a drift check compares homes; cutover is a later Erik-gated item.
- Engines: voice emitter (new), lint (exists), ensemble (copied), stats +
  meters (copied, extended), claims pass (new).
- Verbs: voice, gate, catch, catches, pairs, ratify, calibrate, registers.
- Hooks: existing PostToolUse prose-lint stays advisory (it already is);
  no Stop-hook blocking exists in this design.

## 3. Interfaces

### deai voice --register R [--topic T] [--json]

The formation organ. Emits, assembled fresh from the vault: the register's
distilled contract and matched exemplars retrieved from the certified
corpus (topic-matched when T is given). Injected at write time by whoever
is about to write: a session, a pipeline, a deployed service's prompt
assembly. This command is why CLAUDE.md files shrink: voice is fetched
when writing happens instead of recited in every context.

### deai catch --text T --fix F --register R --surface S [--why W]

Typed intake for a human correction. Refuses with exit 2 when T or F is
missing. On accept, atomic writes: pairs log (the before/after pair, dated,
hashed), candidate on this repo's board, catches log. The pair is the
primary product; a lint rule is a byproduct some catches also earn.

### deai pairs [--since D] [--export dpo|jsonl]

The training-data ledger: every catch as a preference pair, exportable for
local fine-tuning runs on the Studio. This is the pipeline to voice in
weights; runs happen under Erik's go per run.

### deai gate <path|-> --register R [--json]

Unchanged from v0.1 mechanically (lint + ensemble + stats, one pass, typed
exits: 0 clean, 2 flags, 3 out of zone, 4 usage), but scoped by §1: it is
invoked by pipelines and unattended surfaces, and by the essay flow as
writer discipline. Nothing wires it to block interactive output.

### deai claims <path> [--json]

The receipts pass. Extracts specific factual assertions (names, numbers,
titles, origins, quotes) and reports each with its annotation state:
sourced (a named receipt in the working notes) or naked. Exit 0 all
sourced, exit 2 naked claims listed. Advisory in interactive use, gating
in pipelines. It does not judge truth; it enforces that a source is named,
which is the mechanical part of "don't make shit up."

### deai catches / deai ratify / deai calibrate

As v0.1: lifecycle listing; Erik-only ratification enforced by refusal;
deterministic recalibration with receipts. Ratified rules reach gates and
advisories on next invocation.

## 4. Registers

default, essay, terminal, product-answer, email, x-post, site-copy,
commit-message. Terminal register exists for ADVISORY annotation and voice
emission only; it never blocks. Pack contents come from the measured-rule
workflow with a false-positive ceiling per register recorded at measure
time; a rule that cannot demonstrate a near-zero false-positive rate on
the corpus stays a candidate forever.

## 5. The love path (formation detail)

1. Write time: `deai voice` exemplars ride in the writing context, quietly.
   No rule recitation. The model imitates cadence it was just shown.
2. Catch time: Erik corrects anywhere; the correction becomes a pair.
3. Distill time: pairs export to DPO/LoRA runs on local models (LM Studio);
   each run receipted; Pangram and the local ensemble referee per the
   standing co-evolution rulings (dec-26e51e, dec-12a740).
4. Arrival: a local writer that drafts in Erik's voice by default; gates go
   quiet because there is nothing to catch.

## 6. Determinism requirements

- No network and no vendor-model calls in gate, claims, voice, or hook
  paths; ensemble runs pinned local models recorded in calibration.
- Same input + same VERSION = same output for every verb.
- Zones and ceilings from calibration.json only; bare numeric bounds in
  tool code are defects; `harness bounds scan` covers the tool.
- Advisory surfaces emit notes; they never mutate, delay, or suppress the
  text they annotate.

## 7. Migration (each row one manna item)

| id | work | blocked by |
|---|---|---|
| M1 | Vault COPY with hash receipts both sides; drift check; substack untouched | none |
| M2 | `deai voice`: contract + exemplar retrieval from the vault | M1 |
| M3 | registers.yaml + `.deai.yaml`; CLAUDE.md voice prose across repos collapses to the pointer once M2 serves the content | M1, M2 |
| M4 | `deai catch` / `catches` / `pairs`; correction-keys hook files catches | M1 |
| M5 | `deai claims`: extraction + annotation states, wired into the essay flow as a gate step and everywhere else as advisory | M1 |
| M6 | `deai gate` single-command bundle; substack DRAFT GATE delegates; byte-identical flags on archived drafts | M1 |
| M7 | meters v2 into stats (verbless-spine share, appositive runs, catalog fragments, verdict rhythm, deictic, negation) as advisory columns (absorbs mn-ecdc33) | M1 |
| M8 | first pairs export + one receipted LoRA/DPO run on a local model, Erik-gated | M4 |
| M9 | ratify lifecycle end to end with the queued families (mn-368b25, mn-d06a8f), measured against the false-positive ceiling | M4 |
| M10 | runtime net reference in versova-supply-intelligence (gate at send, one bounded regen) | M6 |

## 8. Acceptance receipts

- M2: for each register, emitted exemplars verifiably originate in the
  certified corpus (hash trace); a seeded topic returns topic-matched
  exemplars.
- M4: refusal matrix executed; atomicity verified by induced mid-write
  failure; a catch filed from a second repo lands identically.
- M5: a draft seeded with three naked claims lists exactly those three;
  the same draft with receipts added exits 0.
- M6: flag set byte-identical to the legacy three-command gate across all
  archived substack drafts.
- M8: run receipt includes dataset hash, base model, method, and
  before/after ensemble readings on a held-out sample.
- M9: candidate walked to live only after its measured false-positive rate
  on the corpus is recorded; the same tell then flags in a fresh repo.

## 9. Non-goals

Blocking any interactive surface. Rewriting inside gates. Auto-
ratification. Cloud calls in enforcement. Typed refusals in terminal
replies. Pangram integration (separate lane: mn-739746, mn-d4b0fd).

## 10. Open questions (Erik rules)

1. ratify authentication: interactive confirm, flag file, or other.
2. Corpus placement: contains sent email; confirm this repo as home or
   name a private vault path.
3. Advisory visibility in terminal: notes appear inline to Erik, or only
   accumulate in the catches/receipts logs.
4. Vault cutover timing: dual-home interim stands until Erik names the
   moment.
5. Local base model for M8's first run: Erik picks from the Studio's
   current stable.
