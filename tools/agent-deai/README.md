# deai

Offline prose lint with explicit register policies. No dependencies beyond
Python 3.10+, no network calls, and no input rewrites.

```bash
agent-do deai lint draft.md --register essay
agent-do deai lint README.md --json
agent-do deai lint - --register product-answer --json < answer.md
agent-do deai packs --register email --json
agent-do deai validate
```

Exit codes: **0** clean, **1** prose findings, **2** input or rule-data error.
`--json` emits `deai-result-v1`, including every file and every occurrence's
original line, column, and text. `success` says whether the command ran;
`clean` says whether lint passed. Errors never report a clean result.

## Register policies

| Pack | Policy |
| --- | --- |
| `essay` | All house bans and measured rate rules, including structural and architecture from the existing essay voice law. |
| `default` | Keeps high-signal words and phrases; exempts ambiguous technical words and functional list/range/role constructions. |
| `email` | Permits technical vocabulary, scheduling ranges, and alternatives; retains prose constructions and house tells. |
| `product-answer` | Permits the same technical vocabulary and instructional formatting as default. Separate pack so future measured changes remain explicit. |

The default cannot infer whether "robust" is literal or promotional from one
word. Its whitelist exempts that ambiguous word rule. It still catches
phrases such as "it is worth noting" and "let me explain". Code fences
(backticks and tildes), inline code, YAML frontmatter, HTML comments, URLs,
and Substack button markers are excluded. Source offsets stay intact; removed
code cannot join a phrase. Curly apostrophes match straight apostrophes.
This is a prose linter, not a parser for arbitrary source-code files.

Each pack carries a complete ceiling table and an attributed whitelist.
**Email, default, and product-answer inherit the source measurements; no
independent calibration for those registers is claimed.** Whitelists are
editorial policy, not corpus statistics. A clean result is not an authorship
verdict. Poisson p-values are per-rule editing signals, not document-wide
false-positive guarantees.

## Provenance

`rules.json` pins the source repository commit and SHA-256 hashes for
`substack-writings/scripts/lint-ai-speak.py` and
`voice/ai-speak-lexicon.md`. The local `ai-speak-lexicon.md` is an unchanged
historical evidence snapshot; its relative links refer to that source repo.
The executable rules now live here. The Substack entry point delegates to
`agent-do deai lint --register essay` and keeps its optional word-hunt review
advisory. That feed does not become automatic bans.

The migration retains 47 source bans, 46 word-rate rules, and 12 construction
rules. It also enforces the two existing essay house bans named above, which
the old script omitted. Original ceilings use 110,977 words (60,129 certified
Erik session words plus 50,848 pre-2022 Paul Graham essay words). Tour-guide,
personified-labor, and knowing-wink ceilings use the later 120,102-word
certified corpus. Their reported counts are 1, 1, and 0.

Reported ceilings retain their original rounding. The effective minimum is
one occurrence per **that rule's** measured corpus. Raw original per-rule
counts were not retained for the older study; this migration imports its
reported measurements and does not claim to have rerun that study.

## Adding a measured tell

Measure the proposed pattern on a corpus whose provenance you can attest:

```bash
agent-do deai measure corpus.txt --rule-id new-tell \
  --pattern '\bnew tell\b' --source 'Certified corpus, approval and location' --json
```

The returned `measurement` is ready to insert into `rules.json.measurements`
under a descriptive key. It includes counts, word denominator, exact pattern,
UTC measurement date, and file hashes. It does not certify authorship for you.
Repeated identical files and empty prose corpora are refused.

1. Add a rule with a stable `id`, `label`, regex `pattern`, `tier` (2 for words,
   3 for constructions), and evidence citation to `rules.json.rules`.
2. Add its `{per_10k, measurement}` reference to each pack's `ceilings`.
   Copy the measured rate exactly. Exempt a register only through an attributed
   whitelist entry with a reason.
3. Run `agent-do deai validate` and `python3 tests/test_deai.py` from the repo.

No engine edit is needed. Validation rejects bare rates, missing denominators,
unknown measurements, rates that differ from the evidence, and changed
patterns without a matching measurement. Tier 1 is the imported never-use
policy, not an escape hatch for new unmeasured tells. New tells use the
measurement workflow above.

The engine uses a stable Poisson tail calculation, including long inputs where
the old summation underflowed. It reports all findings without a result cap.
