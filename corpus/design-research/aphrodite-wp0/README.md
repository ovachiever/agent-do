# Aphrodite WP-0

The first executable candidate **failed** its predeclared readiness checks. The
bounded experiment is implemented; no autonomous design selector was admitted.
See the [report](../../../../.handoff/aphrodite-wp0/REPORT.md).

This directory owns only the research implementation. Production DPT and the old
wild-hunt study are unchanged. Python's standard library is sufficient. Captures
use the existing `agent-do browse` CLI, with named isolated browser sessions.

## Reproduce the delivered experiment

From the repository root:

```bash
python3 -m unittest discover -s corpus/design-research/aphrodite-wp0 -p 'test_*.py' -v
python3 -m compileall -q corpus/design-research/aphrodite-wp0
python3 corpus/design-research/aphrodite-wp0/bench.py verify --out .dev/aphrodite-wp0/run-02
python3 corpus/design-research/aphrodite-wp0/bench.py evaluate --out .dev/aphrodite-wp0/run-02
```

The existing freeze cannot be overwritten. The initial run remains in
`.dev/aphrodite-wp0/`; `run-02` corrects one capture-renderer syntax error with
identical model, inputs and raw scores. [Amendment](../../../../.handoff/aphrodite-wp0/AMENDMENT-001.md).

The iCloud bundle contains a portable copy of the complete amended run. From its
`run/` folder, recompute without requiring the original checkout:

```bash
python3 source/bench.py verify --out . --frozen-only
python3 source/bench.py evaluate --out . --frozen-only
```

That verifies every frozen input and the frozen evaluator, but explicitly does
not verify the original checkout's files. Output timestamps may differ; raw scores
must remain identical. Replaying captures requires the repository and `agent-do`
on this machine. The capture commands are documented for reproducibility, not an
instruction to overwrite the delivered captures:

```bash
python3 corpus/design-research/aphrodite-wp0/capture.py comparison --out <fresh-frozen-run>
python3 corpus/design-research/aphrodite-wp0/capture.py pins --out <fresh-frozen-run>
```

## Inspect the evidence

- `model.json`: eleven proposed kernel constants, four fixed weights, all binding choices.
- `PROTOCOL.md`: questions, hypotheses, denominators, stop rules and scope limits.
- `model.py`: pure graph binding and scoring; it never reads human labels.
- `bench.py`: freeze, hash verification and exact diagnostics.
- `capture.py`, `probe.js`: browser transport and actual rendered observations.
- `render.py`, `comparison.json`: one fixed two-by-two intervention, no score-based selection.
- `.dev/aphrodite-wp0/run-02/FREEZE.json`: input and executable hashes.
- `.dev/aphrodite-wp0/run-02/graphs/`: all inferred graph nodes and edges, both binding variants.
- `.dev/aphrodite-wp0/run-02/scores.json`: all 64 observations with per-edge factors.
- `.dev/aphrodite-wp0/run-02/diagnostics.json`: all four requested diagnostics and failures.
- `.dev/aphrodite-wp0/run-02/comparison/index.html`: neutral visual comparison.
- `.dev/aphrodite-wp0/run-02/pins/`: twelve NEW page observations, including incomplete evidence.

Human responses belong to field check **mn-03e95e**. The choice sheet starts empty.
The model does not infer human approval from its predictions, our visual inspection,
or absence of an answer. The four pages are a controlled experiment, not examples
of designs certified beautiful by Aphrodite.
