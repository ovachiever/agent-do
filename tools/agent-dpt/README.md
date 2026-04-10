# Design Perception Tensor

> **DPT does not measure taste. It measures whether the unconscious will flinch.**

Browser-injectable design quality scanner. 72 rules across 5 perception layers — chromatic field, typographic skeleton, spatial rhythm, attention architecture, coherence — fused into a single 0-100 score via synthesis.

Runs inside a live page via `page.evaluate()`. Returns structured JSON describing design quality from measured signals: computed styles, bounding rects, DOM structure, font APIs. No network requests, no server-side data, no subjectivity.

## Install

```bash
git clone <repo-url> dpt
cd dpt
./install.sh        # Sets up agent-do tool + Claude Code hook + catalog
```

Inside `agent-do`, the repo-local path is:

```bash
cd tools/agent-dpt
./install.sh
```

The install script:
1. Builds the engine (`dist/dpt-engine.js`)
2. Symlinks `bin/agent-dpt` into your agent-do tools directory
3. Installs a PostToolUse hook for automatic design scoring after CSS/HTML/JSX edits
4. Adds catalog and index entries for agent-do tool discovery

Options:
```bash
./install.sh --tool-only   # Just the agent-do symlink, no hook
./install.sh --uninstall   # Remove all installed files
```

### Requirements

- [agent-do](https://github.com/...) with agent-browser daemon
- Python 3.8+
- A running browser session: `agent-do browse open <url>`

## Usage

### As an agent-do tool

```bash
agent-do dpt score                     # Score current page
agent-do dpt score https://stripe.com  # Score a URL
agent-do dpt violations                # Violations sorted by fix impact
agent-do dpt report                    # Full narrative critique
agent-do dpt scan --json > out.json    # Export structured JSON
agent-do dpt baseline                  # Save comparison point
agent-do dpt diff                      # Show delta after changes
agent-do dpt build                     # Rebuild engine from source
```

### Directly

```bash
bin/agent-dpt score          # Same commands, no agent-do wrapper
bin/build                    # Assemble engine from src/ into dist/
bin/dpt-report result.json   # Narrative report from raw JSON
```

### Autonomous Fix Loop (via Claude Code hook)

When the PostToolUse hook is installed, editing any CSS/HTML/JSX/TSX file automatically triggers a DPT score. The score feeds back into the AI agent's context:

```
Agent edits style.css
  → Hook fires: "DPT: 67 C+ (chr75 typ60 spa75 att74 coh76)"
    → Agent sees the score, reads violations
      → Agent fixes the top violation
        → Hook fires again with updated score
          → Loop continues until score stabilizes
```

No explicit loop code. The hook is the loop.

## Architecture

```
agent-dpt                           Repo-local wrapper entry point
bin/agent-dpt                       Main CLI implementation
src/utils.js                        Color math, DOM traversal, statistics
src/layers/chromatic-field.js       Color perception, palette, contrast, harmony
src/layers/typographic-skeleton.js  Type scale, weight, measure, craft
src/layers/spatial-rhythm.js        Spacing grid, touch targets, shadows, alignment
src/layers/attention-architecture.js  Hierarchy, affordance, navigation, forms
src/layers/coherence.js             Token consistency, component drift, animation bounds
src/synthesis.js                    Weighted fusion → 0-100 score

bin/agent-dpt                       agent-do tool entry point (self-resolving)
bin/build                           Engine assembler
bin/dpt-scan                        Socket-based scanner
bin/dpt-quick                       Eval-based scanner
bin/dpt-report                      Narrative report generator

install.sh                          Sets up agent-do tool + hook + catalog
```

## Scoring

Four mechanical dimensions weighted (chromatic 20%, typography 30%, spatial 25%, attention 25%) then scaled by coherence as a multiplier — not a peer dimension.

- **Coherence multiplier**: Above 70 coherence, a design system exists (factor 0.95-1.0). Below 50, no real system (factor 0.55-0.75). The research basis: recognition over recall (Johnson Ch.9) — coherent systems enable pattern recognition; incoherent systems force effortful recall.
- **Floor anchoring**: Overall score can't outrun the weakest dimension. Per-dimension authority: chromatic and typography anchor hard (1.0), spatial softer (0.8), attention softest (0.6).
- **Variance penalty**: High standard deviation across dimensions = scattered passes among failures = no design intent.

## Calibration

```
Site             Score  Grade   Dimensions
───────────     ─────  ─────   ──────────
IAMTHESTAR         74    B-    chr76 typ78 spa74 att74 coh85
Stripe             67    C+    chr60 typ81 spa75 att75 coh66
Linear             60     C    chr74 typ74 spa60 att72 coh60
blinkee            51    D+    chr88 typ65 spa57 att74 coh52
mrbottles          45     D    chr60 typ76 spa56 att50 coh54
```

## Research

The `research/` directory contains deep extractions from foundational texts mapped to DPT's dimensional architecture:

- **Refactoring UI** (Schoger): 252 pages, 17 new rules, 8 threshold refinements
- **Designing with the Mind in Mind** (Johnson): 320 pages, architecture validation across 109 research citations
- **100 Things Every Designer Needs to Know About People** (Weinschenk): 100 findings, scoring weight validation

Key finding (Sillence, 2004): 83% of trust rejection is design-based. Bechara (1997): the unconscious evaluates 30 decisions before consciousness catches up. DPT's five layers map to the temporal cascade of the 500ms trust judgment.

Source material: 48 books across UX, perceptual science, color theory, and typography.
