---
workflow: 2
manna: mn-0197a9
track: mn-455a88
source: session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19 post-purge ./test.sh run; evidence dir $TMPDIR/tmp.2my38sr08B
base_commit: b06aa56690735e526752bed3eb90cb427a42ade3
scope: 'Manna: init recovery refuses its own abandoned temp file — a crash mid-README write leaves .handoff/.README.md.<pid>.<nonce>.tmp, every later init fails, identity lands without federation.yaml'
inputs:
- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19 post-purge ./test.sh run; evidence dir $TMPDIR/tmp.2my38sr08B
binding: sha256:8a2bc7d866d1f93a265be0e836c9e52334213546e0438dd91b56d5b8971b2f97
---

# Handoff: Manna: init recovery refuses its own abandoned temp file — a crash mid-README write leaves .handoff/.README.md.<pid>.<nonce>.tmp, every later init fails, identity lands without federation.yaml

Board state is canonical in `.manna/`. This file is the work order for one item only.

## Claim

```bash
agent-do manna claim mn-0197a9
```

## Scope

Manna: init recovery refuses its own abandoned temp file — a crash mid-README write leaves .handoff/.README.md.<pid>.<nonce>.tmp, every later init fails, identity lands without federation.yaml

## Inputs

- session 5f72481f-37de-413c-bb85-42206d5d14f5, 2026-10-19 post-purge ./test.sh run; evidence dir $TMPDIR/tmp.2my38sr08B

## Work order

Found 2026-10-19 by the post-purge full ./test.sh run (128 passed, 1 failed: manna integration, Test 1b kill-mid-init recovery). Unrelated to the temp-dir incident; a standalone re-run of tools/agent-manna/test/integration.sh passes, so the failure is a timing race the test can hit under load.

Evidence (failed board kept at $TMPDIR/tmp.2my38sr08B, sub-second mtimes 10:00:16): the killed init (pid 80725) wrote issues .797, sessions .807, workflow .818, handoff-order .827, then began .handoff/README.md through atomic_write (workflow.rs 505-532: temp `.README.md.<pid>.<nonce>.tmp` born .837); the test saw the journaled pre-identity state and SIGKILLed it mid-write, so the temp stayed. The rerun replayed the journal (recover_board_init, workflow.rs 3161): README.md .855, board.yaml .952, journal consumed .963. Then build_board_init called validate_new_handoff_root (workflow.rs 2849 -> 765-793), which accepts only an empty dir or README.md alone, saw the abandoned temp as a second entry, and returned ".handoff already contains non-workflow files; migrate or archive them before initializing a strict board". initialize_workflow errored after identity was already published, and main.rs 1010-1015 runs federation::initialize only on success, so .manna/federation.yaml was never written. A third init on that board (run by hand) fails identically: the refusal is permanent until a human deletes a hidden temp file. workflow_markers_present (workflow.rs 570) is false on an empty board, so every init of a fresh strict board takes this path.

Defects: (1) recovery treats the writer's own abandoned atomic_write temp as a foreign file instead of sweeping `.<name>.<pid>.<nonce>.tmp` whose pid is dead (or any such temp when holding board.lock); (2) the recovery path reports failure after publishing identity and consuming the journal, leaving a board with board.yaml and no federation.yaml, the half-fired shape mn-65fae2 closed; (3) the integration test only hits the race by timing, so it is flaky rather than a fixed receipt; a MANNA_TEST pause before the README write (like pause_init_before_identity_for_test, workflow.rs 3022) would make the crash point deterministic.

Verification: with the pause, kill-mid-README-write then rerun init -> success: true, recovered_transactions: 1, .handoff holds README.md only, federation.yaml present; the hand-built board above (or a copy of its .handoff and .manna) initializes cleanly; cargo test in tools/agent-manna and bash tools/agent-manna/test/integration.sh green; ./test.sh green; harness contracts validate 0 warnings.

## Completion

1. Produce the scoped deliverables and verification receipts.
2. Update this handoff only when continuation context changed.
3. Seal changes with `agent-do manna handoff seal mn-0197a9`.
4. Commit with `Manna: mn-0197a9` and run `agent-do manna done mn-0197a9` only after the work is verified.
