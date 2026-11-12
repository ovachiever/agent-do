---
workflow: 2
manna: mn-7ec6dc
track: mn-b7a0cc
source: null
base_commit: 29e816eff57e1c18259782bc372ad06f4b691432
scope: 'Design rounds: bake the taste-elicitation loop into agent-do'
inputs: []
binding: sha256:d4cbaccf5100b73c44c9e5bbdcf0fa09c286bab6425988a15d1b933c81e24992
---

# Handoff: Design rounds: bake the taste-elicitation loop into agent-do

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-7ec6dc
```

## Scope

Design rounds: bake the taste-elicitation loop into agent-do

## Inputs

- None declared.

## Work order

Proven across Palingenesis concept rounds 1-3 (2026-08-22..24): the iterative method for taste-driven design work - the user's feedback compiles into binding constraints; N blind builders span a deliberate range within them (shared truth + one emphasis each, mutually blind); dpt floors annotate, never gate; all renders publish to ONE self-saving feedback gallery (per-design note fields + overall + submit; artifact republish pings the orchestrating session); notes drive the next round; loop ends when the user advances a design; ruling + winning grammar recorded; winner becomes the build handoff. Hard rules learned: AI judges are annotation at most, never authority (refuted twice by Erik); conceits demote to components on the user's word; word-ration and craft-floor clauses live in builder prompts.

BUILD (pending Erik's taxonomy-gate go, per-piece):
1. Skill 'design-rounds' (name renamable) carrying the full protocol + gallery feedback runtime template (artifact capability, fb-state pattern proven in this session).
2. dpt verbs: 'dpt gallery <renders-dir> --out page.html' (deterministic feedback-page assembly) and 'dpt round' (per-project round state: constraints, feedback, rulings) - registry entries + contracts + routing metadata required.
3. DISCOVERY WIRING (the 'how does AI know months later' answer): (a) registry routing.prompt_patterns for design/mockup/concept/redesign/'what should X look like' so the UserPromptSubmit router injects the method at ask-time; (b) skill description written as a trigger condition ('user wants to see options and react - I'll-know-it-when-I-see-it - rather than specify'); (c) zpc lesson promoted global: taste-driven deliverables -> design-rounds, never single-shot.

Evidence and templates: this session's galleries (concept-2 artifact fadf33fa..., lib3 artifact 99658e09...), moon1/ protocols + results.json files in the session scratchpad, museum entries in tools/agent-dpt/fixtures/museum/. Generalization note: the loop is preference elicitation for anything renderable (logos, layouts, naming slates, copy voice) - v2 scope.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-7ec6dc`.
4. Commit with `Manna: mn-7ec6dc` and run `agent-do manna done mn-7ec6dc` only after the work is verified.
