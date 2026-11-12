---
workflow: 2
manna: mn-c2d546
track: mn-b7a0cc
source: wild-hunt.md (2026-09-08 rite); Erik's commission this session
base_commit: 87781bab78067fcd806ee540a094c68cb5183803
scope: 'DPT taste instrument: verify wild-hunt candidates against the ruled corpus'
inputs:
- wild-hunt.md (2026-09-08 rite); Erik's commission this session
binding: sha256:bccbe995966a4ec75c15d237394363547adb15a0a47874c45d788cab7acbe66f
---

# Handoff: DPT taste instrument: verify wild-hunt candidates against the ruled corpus

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-c2d546
```

## Scope

DPT taste instrument: verify wild-hunt candidates against the ruled corpus

## Inputs

- wild-hunt.md (2026-09-08 rite); Erik's commission this session

## Work order

Downstream verification of wild-hunt.md (28 candidate beauty formalisms, generation artifact, zero evidential standing). Consolidate the labeled corpus from the round record, pre-register kill-test thresholds, run the three bets first (TSE complexity, Three Trees, Self-Teaching Index), then the wider file as budget allows. Report-only: no new tools, no new verbs, no dpt src changes.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-c2d546`.
4. Commit with `Manna: mn-c2d546` and run `agent-do manna done mn-c2d546` only after the work is verified.

## Work order

`wild-hunt.md` (repo root) holds 28 candidate beauty formalisms in six houses. It is a
GENERATION ARTIFACT: zero evidential standing. Your job is the colder seat — verify or kill
against ground truth Erik has already ruled. Report-only: no new agent-do tools or verbs, no
registry or contracts changes, no edits to tools/agent-dpt/src. All code under
tools/agent-dpt/research/wildhunt-verify/ (new directory). Every bounding literal cites its
authority or derives (quantity doctrine).

### Step 0 — consolidate the labeled corpus (do this first; it nearly died once already)

Ground truth lives in four places:
1. Fixtures (in repo): tools/agent-dpt/fixtures/ — canon-today, canon-dossier, barf, broken.
2. Pins (in repo): tools/agent-dpt/corpus/pins/ 001–005 + shots/ (every.to has no shot —
   site blocks headless; noted in its pin).
3. Round renders + candidate HTML: extractable from the old session transcript
   /Users/erik/.claude/projects/-Users-erik-Custom-Coding-agent-do/fae1af41-26ba-4c61-9805-d261387c8a4a.jsonl
   Mining recipe (proven 2026-08-31): stream-parse JSONL; map tool_use Read calls (input
   .file_path ends .png) to their tool_result by tool_use_id; decode content[].source.data
   base64 → PNG. Round dirs: moon1/concept/renders (round 1: today-A..E, dossier-A..E),
   moon1/concept2/renders (round 2 TRAP SET: engine-A..E, library-A..E), moon1/lib4/renders,
   moon1/eng5..7. Candidate HTML for eng6/eng7 also appears in later tool calls and gallery
   srcdoc blocks.
4. Reground round (on disk): scratchpad moon1/reground/ A|B|C today+engine + approved/ (the
   ratified pixels: today-C = Paper Broadsheet, dossier-D = Auction Lot [verify D vs B against
   the transcript gallery card order before trusting], askhero, renders-E2-rail).
Consolidate into tools/agent-dpt/corpus/rounds/<round>/ with a labels.yaml per round.

### Erik's verdicts (authoritative labels; quote, never reinterpret)

- Round 5 (eng5, 14 candidates): L1 "maybe" · L2 "way too busy" · L3 kill "word spam x 100" ·
  L4 "boring but the cards do work" · L5 "interesting… word spam again" · T1 "clean… but does
  it really tell us a data story?" · T2 "no" · T3 "trying but not correct" · T4 "junk" · T5
  "don't see the data story" · B1 "getting better… but it's not coherent, it's schizo".
  Overall: "don't try to sound smart, be smart; don't be schizo, be coherent."
- Round 6 (eng6, 8): M1 "this is good" · M4 "compelling because it's unique" (+questions) ·
  MC1 cards fine, tie-lines "meaningless and actually ill" · S1 "interesting, maybe is right" ·
  D1 conditional winner ("if this gives us real operator drilldown, it's the winner; dream
  bigger while keeping it clean") · M2, M3, MC2 unnoted = out of contention.
- Round 7 (eng7): CONFLICT — chat 2026-08-25 "E2 is the winner"; page note 2026-08-31
  "e7-E3: this is the winner, lock it in". Unresolved by Erik. EXCLUDE round 7 from pairwise
  tests until he rules; note the exclusion in results.
- Concept round 1: Today winner = The Paper Broadsheet; Dossier winner = The Auction Lot.
- Concept round 2 = THE TRAP SET: AI judges crowned heavy conceits Erik hated; his favorite
  was "The Null". Judge-refutation evidence — the core calibration asset.
- Library rounds 3/4: winner = askhero composite ("the very obvious winner").
- Pins: register-spanning by design (quiet editorial 001–003; maximalist 004–005).

### Step 1 — pre-register BEFORE computing anything

Write PROTOCOL.md fixing, per candidate: implementation sketch, and the four gates —
(a) fixtures: canon above barf AND broken, stated margin;
(b) rounds: within-round winner-vs-killed pairwise accuracy, pooled, binomial test vs 0.5,
    alpha 0.05;
(c) Round-2 trap: The Null must rank at or above the median heavy conceit (fail = novelty
    bias, instant kill);
(d) register-blindness: all available pins above the fixture barf/broken band.
Banded candidates (Wundt, #27): band parameters fixed from PINS ONLY, never from the round
data under test. No threshold moves after results exist.

### Step 2 — run the bets in order

Wave 1 (the three bets): #17 TSE complexity (region grid ≥24 cells, feature vectors, TSE
proxy) · #18 Three Trees (geometric/style/semantic partitions, pairwise MI; DOM = semantic
tree) · #1 Self-Teaching Index (conditional compression bottom|top, zstd or PPM, on both PNG
strips and HTML).
Wave 2: #10 squint trajectory · #23 emphasis transport · #13 loom rank · #14 size chord.
Wave 3+: remaining candidates as budget allows; Reliquary stays buried.

### Step 3 — deliverables

- tools/agent-dpt/research/wildhunt-verify/RESULTS.md: per candidate KILLED (evidence) /
  SURVIVED SCREENING (effect sizes, all four gates) / BANDED-RETEST. wild-hunt.md stays
  frozen as the generation record.
- zpc position per survivor (with falsifier) and zpc lesson per instructive kill.
- No commits until Erik says commit; when he does, trailer: Manna: mn-c2d546.
- Do NOT wire anything into dpt scoring — survivors are candidates for a future round of
  Erik-gated instrument design (new verbs = taxonomy gate, his explicit approval).


## Verification delivery (2026-09-08)

Research execution is complete; lifecycle closure is pending the explicit commit
instruction required above. Do not rerun or retune this screen as a continuation.

- Claim owner: codex-01a0825b56597a40. No commits or publishing performed.
- Canonical report: `tools/agent-dpt/research/wildhunt-verify/RESULTS.md`.
- Recovered 261 source/asset versions from 141 transcript files and seven saved
  galleries. Indexed 80 specimens, retained 69 for evaluation, with 68 screenshots
  and 64 DOM probes. All labels and exclusions are explicit in per-round
  `tools/agent-dpt/corpus/rounds/*/labels.yaml` and `corpus-measured.json`.
- Corrected bindings: Auction Lot = dossier-D; Library round 3 paneldock preference
  is distinct from round 4 askhero. Round 5 has no declared winner. Round 7 remains
  excluded for its E2/E3 conflict; every.to remains a missing pin image.
- Ran #17, #18, #1 (both channels), then #10, #23, #13, #14, and three pins-only #27
  bands. All eleven score tests KILLED, zero survivors. Three Trees: 8/10 preference
  pairs, raw p=0.0546875, Holm p=0.6015625; fixture margin also fails, pin DOM gate
  incomplete. Banded squint passes A/C/D but only 1/10 preference wins.
- Ten analytic/regression checks pass. All 237 frozen input/code files and
  protected DPT source, registry, and wild-hunt hashes verify. Independent integer
  binomial recomputation confirms all eleven reported p-values and denominators.
- `preregistration.json` fixes the original protocol/config. The first run failed
  only while serializing a NumPy integer before any score was written or inspected.
  Original `freeze.json` is retained; the successful run uses
  `freeze-serialization-fix.json`. `AMENDMENT-serialization.md` and
  `serialization-amendment.json` disclose the exact change; metrics, data, labels,
  and thresholds stayed unchanged. No alternate measurement path or threshold move.
- Scores SHA-256: `1d5b8b8d438c50c7c6c981ebbd614267f2a9be7b2c4610e8b1b8067b6acddfe8`.
- Lessons logged: 11 (new). Decisions logged: 0 (new). Survivor positions: 0.
- Delivery bundle and combined report: `.dev/dpt-wildhunt/deliverables/`, also in
  iCloud `Transfer/`. Combined report/PROTOCOL/amendment/handoff is saved to the
  Erkverse vault's `+/` folder, title `2026-09-08 DPT Wild-Hunt Verification mn-c2d546`.
- Repository-wide `test.sh` was not run: the work is isolated research and no
  production code changed. The root's pre-existing board/handoff dirt, existing
  pins, and frozen generation file remain outside this lane's commit ownership.

Needed next: Erik's explicit commit instruction. At that point review the owned
research/corpus and this handoff, commit with `Manna: mn-c2d546`, then follow the
canonical verified Manna completion path. Do not admit any candidate to DPT.
Optional backlog: the twenty untested generation candidates or a newly registered
operationalization, only if Erik commissions another research wave.
