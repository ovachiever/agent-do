---
workflow: 2
manna: mn-bf448b
track: mn-b7a0cc
source: independent review of mn-cf4d8d pass 2, 2026-10-30; .dev/mn-59f1e4-review/pass2-init-fixture-evidence.json
base_commit: eb27c67aade8d9a1e5522099f72fce305e918428
scope: 'manna init: kill-mid-init leaves a hidden README temp in .handoff and the rerun refuses to initialize'
inputs:
- independent review of mn-cf4d8d pass 2, 2026-10-30; .dev/mn-59f1e4-review/pass2-init-fixture-evidence.json
binding: sha256:d089b5f3a5eba7d874ab1022575982c5d2183c0767990dd4ad122b1391d7525e
---

# Handoff: manna init: kill-mid-init leaves a hidden README temp in .handoff and the rerun refuses to initialize

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-bf448b
```

## Scope

manna init: kill-mid-init leaves a hidden README temp in .handoff and the rerun refuses to initialize

## Inputs

- independent review of mn-cf4d8d pass 2, 2026-10-30; .dev/mn-59f1e4-review/pass2-init-fixture-evidence.json

## Work order

Independent review of mn-cf4d8d (2026-10-30) reran the Manna integration suite and Test 1b (kill-mid-init recovery) failed: the rerun init refused with '.handoff already contains non-workflow files', then federation.yaml was missing and the suite aborted. The reviewer's fixture listing (.dev/mn-59f1e4-review/pass2-init-fixture-evidence.json) shows two entries in the fresh .handoff: .README.md.87331.1793384159562101000.tmp (1708 bytes) beside README.md (1708 bytes). That name is exactly the temp workflow::atomic_write (tools/agent-manna/src/workflow.rs, pattern .{name}.{pid}.{nanos}.tmp) creates before its rename or hard-link install, so a process killed between creating the temp and installing it leaves the temp behind. workflow::validate_new_handoff_root accepts an empty .handoff or exactly one entry, README.md, so the leftover temp makes the rerun refuse and init recovery never completes. Fix: on init and init recovery, remove .handoff temps that atomic_write itself named (its own pattern only, never arbitrary hidden files) before validating the root, or have validate_new_handoff_root ignore them; add a regression test that plants .README.md.<pid>.<nanos>.tmp beside README.md and reruns init, and a kill-mid-init test that lands in that window. Out of scope for mn-cf4d8d (pass 3 touched nothing in init). Baseline frequency unknown: four full runs and three standalone kill-mid-init reproductions on the implementing machine passed; the reviewer's machine hit the window once. Reproduced on the implementing machine on 2026-11-02: two of seven runs of the suite against the committed 36a3cb6 source (a scratch copy, then a detached worktree) failed Test 1b the same way; the first one's fixture /var/folders/g5/064rmz495k1_pvw9x6wn00wm0000gn/T/tmp.E0yiX19Rln/.handoff holds .README.md.67328.1793648521760467000.tmp beside README.md (three such leftover fixtures exist under that TMPDIR now). The same day's four runs on the primary checkout all passed Test 1b.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-bf448b`.
4. Commit with `Manna: mn-bf448b` and run `agent-do manna done mn-bf448b` only after the work is verified.
