# Approved implementation amendments

Erik approved the verb proposal on 2026-09-18 with the following binding changes. The original proposal and trial prompts remain preserved.

- `design brief`, `imagine`, `ballot images|pages`, `measure`, `reproduce`, and `polish` all live under `agent-do design`. Commit `8525d95` retired DPT and Aphrodite. Only the node-tagged brief format and browse-based measurement technique carry forward.
- Budget is unlimited. No price inputs, preflights, price prerequisites, dollar ceilings, generation-count caps, repair caps, or invented token/timeout limits. Record provider usage when returned, otherwise record `usage not returned` and proceed.
- Recheck official provider model pages at run time. Use the strongest current image model, initially `gpt-image-2.5-sunburst`, at its highest supported quality. Only a genuine model-availability error permits fallback to `gpt-image-2`. Text uses the strongest current model at its maximum supported reasoning effort. Published hard maxima are read from their authority, never guessed.
- Polish tolerances must cite a source or derive from the page's measured type scale. The trial's 24px and 60-character guesses are not shipped.
- Ballots stop pending and hand off through `agent-do coord drop add` to Claude Code. Claude's `/ballot` publishes and reads the actual self-saving Artifact. No alternate host or invented receipt.
- Owner copy stays verbatim in all prompts and pages. Every figure binds to a fact ID. Unknown image measurements are null. Rounds preserve every attempt with resumable stages and a mutation lock.
- Build tests and polish first, then brief, imagine, measure, reproduce, ballot. Required gates: contracts with zero errors and warnings, then green `./test.sh` before rehearsal.
- Rehearsal waits for a new surface Erik names and copy/facts he approves. Home is regression evidence. No-spend dry run precedes live generation; both human ballot rulings remain explicit stop points.

Build item: `mn-7de24f`, claimed in the primary checkout. Implementation lane: `/Users/erik/Custom-Coding/agent-do-design-mn-7de24f`, branch `design/mn-7de24f-image-first`. Stage commits carry `Manna: mn-7de24f`. No push is authorized.

**TL;DR (12th grade):** Build the image-first method under six design verbs, with unlimited work, current strongest models, exact owner text and facts, mechanical checks, and Claude-hosted human ballots.
