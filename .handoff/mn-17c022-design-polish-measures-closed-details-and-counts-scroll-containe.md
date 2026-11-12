---
workflow: 2
manna: mn-17c022
track: null
source: null
base_commit: 630640e73afe7081ae34b79d7e4f09b90d27f703
scope: design polish measures closed details and counts scroll containers as clips
inputs: []
binding: sha256:ae14bd6324997ad073ca2568c571f43804799e64adc0fdae31d25cacd0aee676
---

# Handoff: design polish measures closed details and counts scroll containers as clips

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-17c022
```

## Scope

design polish measures closed details and counts scroll containers as clips

## Inputs

- None declared.

## Work order

Companion to mn-772f53, measured 2026-09-22 on the Palingenesis Today page. (1) Closed <details> content is measured: in this Chromium, content under a closed details has real client rects (a value 183px wide, a 116px item) while nothing is visible, so polish.js reports orphans and clips nobody can see (45 at 1440). Fix: set open on every details before measuring, or treat el.closest('details:not([open])') && !el.closest('summary') as not visible. (2) overflow:hidden ancestors with a scrolling descendant are counted as clips: the app shell wrapper (overflow hidden) contains #main (scroll), and every word below the fold is reported clipped_by the wrapper (236 to 563 per width). A scroll container makes the text reachable and is not a clip. (3) Accept an intentional clamp marked data-polish-clamp with an aria-expanded control, or open the control before measuring.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-17c022`.
4. Commit with `Manna: mn-17c022` and run `agent-do manna done mn-17c022` only after the work is verified.

## Builder receipt, 2026-09-23

Status: implementation ready; required browser acceptance is pending. Do not mark
this item done from compilation or the adjacent contract tests alone.

- Claimed through `agent-do manna claim mn-17c022` as
  `codex-01a0ce84914a77a0`. Canonical owner, prompt, frontmatter binding, and the
  normalized content binding all matched the supplied intake seal
  `sha256:cc5a1e570bb22a64627ad72148ec5d961d4b87a0365a2b65eb3ee035b68b0f58`.
- Source base: `630640e73afe7081ae34b79d7e4f09b90d27f703`.
- Isolated build checkout: `/Users/erik/Custom-Coding/agent-do-mn-17c022`.
  Manna and Coord lifecycle operations remain in the primary checkout.
- Claimed source paths: `tools/agent-design/polish.js` and
  `tools/agent-design/test/test_polish.py`. The companion `mn-772f53` owns
  readiness changes in `design_browser.py` and separate readiness tests.

### Implementation

1. Closed disclosures contribute only their first summary. Every closed ancestor
   is checked, so a nested summary cannot escape a closed outer disclosure.
   Open disclosures still receive ordinary layout checks. The audit does not
   open or click controls.
2. Scroll reachability is tracked independently for each axis. Text reachable
   through an inner scroll viewport is not reported against a containing shell
   when that viewport fits inside the shell's clipping bounds. Inner clipping,
   inaccessible siblings, cut-off scroll viewports, and text outside the
   reachable scroll area remain eligible findings.
3. Vertical truncation marked `data-polish-clamp` is accepted when a related,
   visible, enabled button has `aria-expanded="false"`. `aria-controls` binds an
   explicit target; without it, the local parent must contain exactly one marked
   clamp and one disclosure control. Expanded, disabled, hidden, inert, unrelated,
   or absent controls do not exempt a clip. The exemption is recorded in
   `coverage.intentional_clamps`, applies only to the marked vertical clip, and
   does not hide horizontal or inner clipping. Hidden tail lines no longer create
   orphan findings; visible orphan lines still do. Full text remains available
   for copy-contract checking.
4. Added 17 browser regression methods, for 32 total. These use the existing real
   `agent-do browse` test path; no DOM simulation substitutes for browser evidence.

The visibility and scroll distinctions follow the
[HTML disclosure definition](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element),
[CSS scrollport definition](https://www.w3.org/TR/css-overflow-3/#scrolling), and
[ARIA disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/).

### Verification receipts

Commands ran in the isolated build checkout unless stated otherwise.

| Command | Actual result | Evidence category |
| --- | --- | --- |
| `node --check tools/agent-design/polish.js` | Exit 0 | JavaScript syntax only |
| `python3 -m py_compile tools/agent-design/test/test_polish.py` | Exit 0; 32 test methods compiled | Compilation, zero browser tests executed |
| `python3 tools/agent-design/test/test_contract.py` | Exit 0; 13 tests passed, 0 failed | Executed contract/state unit tests |
| `git diff --check` | Exit 0 | Whitespace validation |
| `python3 tools/agent-design/test/test_polish.py` | Not executed yet | Required real-browser acceptance remains pending |

Machine-readable receipt: `.dev/mn-17c022/validation.json`.
No app launches, browser sessions, installs, screenshots, pushes, or pull requests
were performed during this build lane. The root suite was not run, per the
focused-only instruction.

### Required closing pass

- The user was asked to authorize the canonical browser test command as the
  coordinated closing pass. No answer has been inferred from elapsed time.
- Coord dependency: `mn-17c022-browser-acceptance`.
- After authorization, coordinate the dedicated headless session with
  `mn-772f53`, execute the 32 real-browser tests using the canonical command above,
  and retain the actual output. Fix failures at their source. Never relabel the
  compiled tests as executed.
- The Palingenesis Today surface was not launched or visually inspected in this
  lane. No live-page finding counts or visual acceptance are claimed.
- Seal updated receipts, commit with the exact `Manna: mn-17c022` trailer, and
  close only after the required acceptance passes.

Lessons logged: 1 (new) | Decisions logged: 0 (new).
