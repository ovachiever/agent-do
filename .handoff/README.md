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
| 01 | `mn-807f18` | open | none | `.handoff/01-mn-807f18-moon-trunk-b-manna-floor-claim-policy-gh-issue-metadata-sync-git.md` |
| 02 | `mn-c3145f` | open | none | `.handoff/02-mn-c3145f-moon-trunk-c-agent-do-attest-stamp-verify-doctor.md` |
| 03 | `mn-404dd7` | blocked | `mn-807f18`, `mn-c3145f` | `.handoff/03b02-mn-404dd7-moon-trunk-d-policy-engine-init-show-check-install-org-scoping.md` |
| 04 | `mn-f1604f` | blocked | `mn-404dd7` | `.handoff/04b03-mn-f1604f-moon-trunk-e-ambient-hooks-board-injection-auto-claim-floor-nudg.md` |
| 05 | `mn-54cec0` | blocked | `mn-404dd7`, `mn-f1604f` | `.handoff/05b04-mn-54cec0-moon-trunk-g-vid-adoption-pass-newco-portable-spec-policy-yaml-1.md` |
| 06 | `mn-a45739` | open | none | `.handoff/06-mn-a45739-companion-agent-do-dictate-the-chair-s-ears-wispr-class-streamin.md` |
| 07 | `mn-b17dc6` | open | none | `.handoff/07-mn-b17dc6-companion-p1-security-voice-speak-replace-eval-d-shell-string-wi.md` |
| 08 | `mn-ec44be` | open | none | `.handoff/08-mn-ec44be-charter-law-5-organ-parked-eval-redraw-fresh-context-agreement-c.md` |
| 09 | `mn-2ac590` | open | none | `.handoff/09-mn-2ac590-charter-law-2-nudge-sessionend-warns-when-substantial-work-dies-u.md` |
| 10 | `mn-e0d107` | open | none | `.handoff/10-mn-e0d107-harness-context-redesign-unify-context-zpc-ledger-the-memory-hem.md` |
| 11 | `mn-c2dc8b` | open | none | `.handoff/11-mn-c2dc8b-harness-undocumented-verbs-promote-help-only-verbs-into-registry.md` |
| 12 | `mn-96415d` | open | none | `.handoff/12-mn-96415d-harness-doc-reference-scan-scope-archive-noise-and-cross-board-r.md` |
| 13 | `mn-194972` | open | none | `.handoff/13-mn-194972-harness-family-re-org-audit-sweep-the-96-bundled-tools-for-famil.md` |
| 14 | `mn-9dbb48` | open | none | `.handoff/14-mn-9dbb48-harness-media-family-surface-agent-do-media-with-makemkv-handbra.md` |
| 15 | `mn-b8359d` | open | none | `.handoff/15-mn-b8359d-install-sh-warn-when-an-installed-wrapper-has-no-settings-regist.md` |
| 16 | `mn-010cd0` | open | none | `.handoff/16-mn-010cd0-zpc-write-nudge-misreads-a-bound-worktree.md` |
| 17 | `mn-6be265` | open | none | `.handoff/17-mn-6be265-zpc-security-a-tracked-zpc-store-injects-a-repo-s-own-text-as-pr.md` |
| 18 | `mn-b7cb18` | open | none | `.handoff/18-mn-b7cb18-quantities-the-authority-does-not-know-the-model-it-runs-on-clau.md` |
| 19 | `mn-a8337a` | open | none | `.handoff/19-mn-a8337a-suggest-project-walks-the-whole-tree-to-answer-one-yes-no.md` |
| 20 | `mn-43932b` | open | none | `.handoff/20-mn-43932b-brief-contract-v2-verb-labels-scope-state-sentence-adopted-panel.md` |
| 21 | `mn-f12284` | open | none | `.handoff/21-mn-f12284-harness-zpc-write-nudge-attributes-shared-checkout-drift-to-a-re.md` |
| 22 | `mn-9668e9` | open | none | `.handoff/22-mn-9668e9-ci-triage-anchor-the-429-transient-hint-changelog-notes-the-gate.md` |
| 23 | `mn-8b4a1c` | open | none | `.handoff/23-mn-8b4a1c-tests-suite-can-hang-forever-on-the-bootstrap-gui-dialog-pin-age.md` |
| 24 | `mn-ee7d1e` | open | none | `.handoff/24-mn-ee7d1e-tests-record-ages-fails-in-a-worktree-when-the-primary-zpc-store.md` |
| 25 | `mn-d2d67b` | open | none | `.handoff/25-mn-d2d67b-manna-done-handoffs-retire-to-handoff-archive-root-is-the-live-p.md` |
| 26 | `mn-040aae` | blocked | `mn-d2d67b` | `.handoff/26b25-mn-040aae-manna-estate-wide-handoff-debris-cleanup-pre-structure-work-orde.md` |
| 27 | `mn-cbaf37` | in_progress | none | `.handoff/mn-cbaf37-research-audit-landed-stage-0-and-adjudicate-the-missing-provena.md` (held under live claim; expected `.handoff/27-mn-cbaf37-research-audit-landed-stage-0-and-adjudicate-the-missing-provena.md`) |
| 28 | `mn-15fed0` | open | none | `.handoff/28-mn-15fed0-manna-typed-decision-state-replaces-the-erik-title-convention.md` |
| 29 | `mn-8f9ef3` | blocked | `mn-404dd7` | `.handoff/29b03-mn-8f9ef3-board-view-policy-floor-layer-and-notify-rules-trunk-f-remainder.md` |
| 30 | `mn-8f0319` | open | none | `.handoff/30-mn-8f0319-zpc-triggers-honest-delivery-receipts-in-process-matching.md` |
| 31 | `mn-62acb6` | open | none | `.handoff/31-mn-62acb6-security-keep-agent-psql-keychain-secrets-off-argv.md` |
| 32 | `mn-4f6f2b` | open | none | `.handoff/32-mn-4f6f2b-security-audit-remaining-macos-keychain-writers-for-argv-exposur.md` |
| 33 | `mn-9605b0` | open | none | `.handoff/33-mn-9605b0-security-remove-remaining-agent-psql-secret-subprocess-propagati.md` |
| 34 | `mn-a7fd91` | blocked | `mn-5d7c5a` | `.handoff/34b35-mn-a7fd91-zpc-intuitions-estate-recurrence-graduates-into-agent-do-improve.md` |
| 35 | `mn-5d7c5a` | open | none | `.handoff/35-mn-5d7c5a-zpc-fascia-one-shared-judgment-layer-both-organs-ride.md` |
| 36 | `mn-fc5028` | blocked | `mn-5d7c5a` | `.handoff/36b35-mn-fc5028-zpc-gardener-the-per-repo-top-50-that-strengthens-as-it-shrinks.md` |
| 37 | `mn-fa0e85` | open | none | `.handoff/37-mn-fa0e85-bootstrap-dialog-nested-package-json-beats-the-git-root-dialog-d.md` |
| 38 | `mn-a44b72` | open | none | `.handoff/38-mn-a44b72-agent-substack-verbs-tags-delete-schedule-scan.md` |
| 39 | `mn-d4b0fd` | open | none | `.handoff/39-mn-d4b0fd-agent-pangram-paid-pangram-api-tool.md` |
| 40 | `mn-fa98a3` | open | none | `.handoff/40-mn-fa98a3-manna-handoff-the-completion-section-states-the-closing-rule.md` |
| 41 | `mn-00160d` | open | none | `.handoff/41-mn-00160d-manna-reconcile-stale-claim-finding-for-claims-whose-liveness-ca.md` |
| 42 | `mn-c2d546` | in_progress | none | `.handoff/42-mn-c2d546-dpt-taste-instrument-verify-wild-hunt-candidates-against-the-rul.md` |
| 43 | `mn-9517e0` | open | none | `.handoff/43-mn-9517e0-manna-reconcile-doc-reference-findings-flooded-200x-scope-the-sc.md` |
| 44 | `mn-481318` | open | none | `.handoff/44-mn-481318-git-commit-help-is-taken-as-the-commit-message-and-commits-whate.md` |
| 45 | `mn-0eff4d` | open | none | `.handoff/45-mn-0eff4d-field-check-combined-polish-on-palingenesis-today.md` |
| 46 | `mn-febe8f` | open | none | `.handoff/46-mn-febe8f-design-polish-a-framework-s-empty-open-shadow-root-makes-every-a.md` |
| 47 | `mn-42501b` | open | none | `.handoff/47-mn-42501b-p1-manna-full-report-lands-on-the-ledger-at-done-the-drop-note-c.md` |
| 48 | `mn-13d14f` | open | none | `.handoff/48-mn-13d14f-p1-manna-reconcile-walks-dev-and-floods-drift-yaml-with-doc-refe.md` |
| 49 | `mn-e24d9f` | open | none | `.handoff/49-mn-e24d9f-p3-docs-mid-claim-coordination-is-not-reopening.md` |
| 50 | `mn-d06a8f` | open | none | `.handoff/50-mn-d06a8f-deai-performed-humility-rule-family-measured.md` |
| 51 | `mn-368b25` | open | none | `.handoff/51-mn-368b25-deai-deictic-time-and-negation-run-rule-families-measured.md` |
| 52 | `mn-e593a1` | open | none | `.handoff/52-mn-e593a1-review-fable-s-unauthorized-manna-change-159261d-reconcile-fix-o.md` |
| 53 | `mn-9d54e7` | open | none | `.handoff/53-mn-9d54e7-deai-work-message-register-ceremony-shell-family-measured.md` |
| 54 | `mn-82488c` | open | none | `.handoff/54-mn-82488c-deai-os-m1-vault-copy-with-hash-receipts-and-drift-check.md` |
| 55 | `mn-5e92f9` | blocked | `mn-82488c` | `.handoff/55b54-mn-5e92f9-deai-os-m2-deai-voice-register-contract-plus-exemplar-retrieval.md` |
| 56 | `mn-bdbc10` | blocked | `mn-82488c`, `mn-5e92f9` | `.handoff/56b55-mn-bdbc10-deai-os-m3-registers-yaml-plus-deai-yaml-resolution.md` |
| 57 | `mn-2d4702` | blocked | `mn-82488c` | `.handoff/57b54-mn-2d4702-deai-os-m4-deai-catch-catches-pairs-typed-intake.md` |
| 58 | `mn-98e013` | blocked | `mn-82488c` | `.handoff/58b54-mn-98e013-deai-os-m5-deai-claims-the-receipts-pass.md` |
| 59 | `mn-d86eae` | blocked | `mn-82488c` | `.handoff/59b54-mn-d86eae-deai-os-m6-deai-gate-one-command-bundle.md` |
| 60 | `mn-29f3b6` | blocked | `mn-82488c` | `.handoff/60b54-mn-29f3b6-deai-os-m7-meters-v2-in-stats.md` |
| 61 | `mn-4af2e6` | blocked | `mn-2d4702` | `.handoff/61b57-mn-4af2e6-deai-os-m8-first-pairs-export-plus-receipted-lora-dpo-run.md` |
| 62 | `mn-ebde91` | blocked | `mn-2d4702` | `.handoff/62b57-mn-ebde91-deai-os-m9-ratify-lifecycle-end-to-end.md` |
| 63 | `mn-27f9fd` | blocked | `mn-d86eae` | `.handoff/63b59-mn-27f9fd-deai-os-m10-runtime-net-reference-in-versova-supply-intelligence.md` |
| 64 | `mn-91c878` | open | none | `.handoff/64-mn-91c878-agent-sessions-search-cli-handoff-cannot-deliver-5-s-literal-wai.md` |
| 65 | `mn-652a9e` | open | none | `.handoff/65-mn-652a9e-upstream-security-guidance-plugin-lists-the-whole-shared-temp-di.md` |
| 66 | `mn-0197a9` | open | none | `.handoff/66-mn-0197a9-manna-init-recovery-refuses-its-own-abandoned-temp-file-a-crash-m.md` |
| 67 | `mn-fefa01` | open | none | `.handoff/67-mn-fefa01-git-commit-the-staged-secret-scan-report-crashes-f-string-with-b.md` |
| 68 | `mn-882c9e` | open | none | `.handoff/68-mn-882c9e-harness-optional-live-gmail-search-provider-for-email.md` |
| 69 | `mn-7cac30` | open | none | `.handoff/69-mn-7cac30-harness-build-agent-do-superhuman-for-split-inboxes-auto-labels-a.md` |
