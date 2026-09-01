# agent-do handoffs

This directory is generated workflow state. `.manna/` owns status, tracks,
claims, and blockers. Each actionable Manna item owns exactly one Markdown
work order here, and the two are content-bound.

Rules:

- Create work through `agent-do manna create`; do not hand-build parallel
  prompt roots such as `.handoffs/`, `.dev/session-prompts/`, or
  `<campaign>/handoff-prompts/`.
- The Manna item `prompt` field points to a board-wide fixed-width name,
  `.handoff/<NN...>[b<MM...>]-mn-xxxxxx-<slug>.md`, after synchronization.
  Width is at least two digits and expands when the active plan exceeds 99.
- Frontmatter identifies the item, track, source, base commit, scope, inputs,
  and SHA-256 binding for the complete document.
- Edit a work order, then run `agent-do manna handoff seal mn-xxxxxx` before
  claiming it. A claim fails closed on any unsealed change.
- Board state stays in Manna. The handoff contains scope, authority,
  deliverables, and verification, never a second backlog.
- Priority lives in `.manna/handoff-order.yaml`. Run `agent-do manna sync`
  after board changes; never hand-maintain numbered filenames or this index.
- A bare numbered filename is safe to launch. `bMM...` means the item is held
  until that numbered priority closes. The full dependency truth remains
  `blocked_by`.
- Completed pairs return to unnumbered sealed history on sync, so no numbered
  filename advertises work that is already done.
- Commit `.manna/workflow.yaml`, `.manna/handoff-order.yaml`,
  `.manna/federation.yaml`, `.manna/issues.jsonl`, and `.handoff/`.

## Generated index

| Priority | Manna ID | Status | Full blocker list | Handoff |
| ---: | --- | --- | --- | --- |
| 01 | `mn-90b694` | open | none | `.handoff/01-mn-90b694-moon-trunk-a-gh-issue-verbs-create-assign-label-list-close-comme.md` |
| 02 | `mn-807f18` | open | none | `.handoff/02-mn-807f18-moon-trunk-b-manna-floor-claim-policy-gh-issue-metadata-sync-git.md` |
| 03 | `mn-c3145f` | open | none | `.handoff/03-mn-c3145f-moon-trunk-c-agent-do-attest-stamp-verify-doctor.md` |
| 04 | `mn-404dd7` | blocked | `mn-90b694`, `mn-807f18`, `mn-c3145f` | `.handoff/04b03-mn-404dd7-moon-trunk-d-policy-engine-init-show-check-install-org-scoping.md` |
| 05 | `mn-f1604f` | blocked | `mn-404dd7` | `.handoff/05b04-mn-f1604f-moon-trunk-e-ambient-hooks-board-injection-auto-claim-floor-nudg.md` |
| 06 | `mn-54cec0` | blocked | `mn-404dd7`, `mn-f1604f` | `.handoff/06b05-mn-54cec0-moon-trunk-g-vid-adoption-pass-newco-portable-spec-policy-yaml-1.md` |
| 07 | `mn-a45739` | open | none | `.handoff/07-mn-a45739-companion-agent-do-dictate-the-chair-s-ears-wispr-class-streamin.md` |
| 08 | `mn-b17dc6` | open | none | `.handoff/08-mn-b17dc6-companion-p1-security-voice-speak-replace-eval-d-shell-string-wi.md` |
| 09 | `mn-ec44be` | open | none | `.handoff/09-mn-ec44be-charter-law-5-organ-parked-eval-redraw-fresh-context-agreement-c.md` |
| 10 | `mn-2ac590` | open | none | `.handoff/10-mn-2ac590-charter-law-2-nudge-sessionend-warns-when-substantial-work-dies-u.md` |
| 11 | `mn-e0d107` | open | none | `.handoff/11-mn-e0d107-harness-context-redesign-unify-context-zpc-ledger-the-memory-hem.md` |
| 12 | `mn-c2dc8b` | open | none | `.handoff/12-mn-c2dc8b-harness-undocumented-verbs-promote-help-only-verbs-into-registry.md` |
| 13 | `mn-96415d` | open | none | `.handoff/13-mn-96415d-harness-doc-reference-scan-scope-archive-noise-and-cross-board-r.md` |
| 14 | `mn-194972` | open | none | `.handoff/14-mn-194972-harness-family-re-org-audit-sweep-the-96-bundled-tools-for-famil.md` |
| 15 | `mn-9dbb48` | open | none | `.handoff/15-mn-9dbb48-harness-media-family-surface-agent-do-media-with-makemkv-handbra.md` |
| 16 | `mn-b8359d` | open | none | `.handoff/16-mn-b8359d-install-sh-warn-when-an-installed-wrapper-has-no-settings-regist.md` |
| 17 | `mn-010cd0` | open | none | `.handoff/17-mn-010cd0-zpc-write-nudge-misreads-a-bound-worktree.md` |
| 18 | `mn-6be265` | open | none | `.handoff/18-mn-6be265-zpc-security-a-tracked-zpc-store-injects-a-repo-s-own-text-as-pr.md` |
| 19 | `mn-b7cb18` | open | none | `.handoff/19-mn-b7cb18-quantities-the-authority-does-not-know-the-model-it-runs-on-clau.md` |
| 20 | `mn-a8337a` | open | none | `.handoff/20-mn-a8337a-suggest-project-walks-the-whole-tree-to-answer-one-yes-no.md` |
| 21 | `mn-43932b` | open | none | `.handoff/21-mn-43932b-brief-contract-v2-verb-labels-scope-state-sentence-adopted-panel.md` |
| 22 | `mn-f12284` | open | none | `.handoff/22-mn-f12284-harness-zpc-write-nudge-attributes-shared-checkout-drift-to-a-re.md` |
| 23 | `mn-9668e9` | open | none | `.handoff/23-mn-9668e9-ci-triage-anchor-the-429-transient-hint-changelog-notes-the-gate.md` |
| 24 | `mn-8b4a1c` | open | none | `.handoff/24-mn-8b4a1c-tests-suite-can-hang-forever-on-the-bootstrap-gui-dialog-pin-age.md` |
| 25 | `mn-ee7d1e` | open | none | `.handoff/25-mn-ee7d1e-tests-record-ages-fails-in-a-worktree-when-the-primary-zpc-store.md` |
| 26 | `mn-d2d67b` | open | none | `.handoff/26-mn-d2d67b-manna-done-handoffs-retire-to-handoff-archive-root-is-the-live-p.md` |
| 27 | `mn-040aae` | blocked | `mn-d2d67b` | `.handoff/27b26-mn-040aae-manna-estate-wide-handoff-debris-cleanup-pre-structure-work-orde.md` |
| 28 | `mn-cbaf37` | in_progress | none | `.handoff/mn-cbaf37-research-audit-landed-stage-0-and-adjudicate-the-missing-provena.md` (held under live claim; expected `.handoff/28-mn-cbaf37-research-audit-landed-stage-0-and-adjudicate-the-missing-provena.md`) |
| 29 | `mn-7ec6dc` | open | none | `.handoff/29-mn-7ec6dc-design-rounds-bake-the-taste-elicitation-loop-into-agent-do.md` |
| 30 | `mn-15fed0` | open | none | `.handoff/30-mn-15fed0-manna-typed-decision-state-replaces-the-erik-title-convention.md` |
| 31 | `mn-8f9ef3` | blocked | `mn-404dd7` | `.handoff/31b04-mn-8f9ef3-board-view-policy-floor-layer-and-notify-rules-trunk-f-remainder.md` |
| 32 | `mn-8f0319` | open | none | `.handoff/32-mn-8f0319-zpc-triggers-honest-delivery-receipts-in-process-matching.md` |
| 33 | `mn-62acb6` | open | none | `.handoff/33-mn-62acb6-security-keep-agent-psql-keychain-secrets-off-argv.md` |
| 34 | `mn-4f6f2b` | open | none | `.handoff/34-mn-4f6f2b-security-audit-remaining-macos-keychain-writers-for-argv-exposur.md` |
| 35 | `mn-9605b0` | open | none | `.handoff/35-mn-9605b0-security-remove-remaining-agent-psql-secret-subprocess-propagati.md` |
| 36 | `mn-a7fd91` | blocked | `mn-5d7c5a` | `.handoff/36b37-mn-a7fd91-zpc-intuitions-estate-recurrence-graduates-into-agent-do-improve.md` |
| 37 | `mn-5d7c5a` | open | none | `.handoff/37-mn-5d7c5a-zpc-fascia-one-shared-judgment-layer-both-organs-ride.md` |
| 38 | `mn-fc5028` | blocked | `mn-5d7c5a` | `.handoff/38b37-mn-fc5028-zpc-gardener-the-per-repo-top-50-that-strengthens-as-it-shrinks.md` |
| 39 | `mn-c7e91b` | in_progress | none | `.handoff/mn-c7e91b-manna-state-json-expose-the-derived-board-model-from-the-core.md` (held under live claim; expected `.handoff/39-mn-c7e91b-manna-state-json-expose-the-derived-board-model-from-the-core.md`) |
| 40 | `mn-7ef12d` | in_progress | none | `.handoff/mn-7ef12d-manna-estate-json-registered-boards-with-per-board-counts.md` (held under live claim; expected `.handoff/40-mn-7ef12d-manna-estate-json-registered-boards-with-per-board-counts.md`) |
| 41 | `mn-86a41b` | in_progress | none | `.handoff/mn-86a41b-coord-pulse-accept-an-explicit-verdict-write-from-a-non-hook-cal.md` (held under live claim; expected `.handoff/41-mn-86a41b-coord-pulse-accept-an-explicit-verdict-write-from-a-non-hook-cal.md`) |
