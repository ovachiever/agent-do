<p align="center"><img src="assets/agent-do-logo.png" alt="agent-do" width="360"></p>

agent-do is a command-line toolkit for fleets of AI coding agents. It puts 103 tools behind one command, `agent-do <tool> <command>`, along with the shared systems a fleet needs: a git-backed work board (manna), a sign-in sheet that checks which agents are really running (coord), per-project memory (zpc), and hooks that load all of it into every session. A human installs it once, and agents use it from the shell.

## Why it exists

Picture a workshop where every worker shows up each morning with notes from yesterday and none of yesterday's habits. The notes are good: they say what got done and what went wrong. They don't say how things are done here, so each worker reads them and works out the day's method from scratch. By evening the shop has one more way of doing everything and has kept none of them. There's plenty of memory in that shop, and practice never builds up. Telling the workers how things are done doesn't fix it either, because an instruction gets read in the morning and reinvented by noon.

What fixes it is a shop that holds the practice itself: a job list where every job is claimed before anyone works it, a sign-in sheet that shows who is really in the building, a journal read aloud at the start of every shift, a foreman whose only job is the reading and the filing, and a register of every tool, how it's used, and a receipt for every use. Then the right way is simply what the shop does, whoever is doing it. The old word for a way of acting that holds no matter who is acting is dharma, and that's what the shop needs.

That workshop is a fleet of AI coding agents. Each session is a worker: it arrives with memory files and instruction files, and it still starts the job over. The agents have a second problem, and it shows up the moment one reaches outside the repository. Inside, an agent is capable: it reads files, edits them, runs the tests, and reasons about a diff (and maybe a life; we're working on that too). Outside, it has no standard way to open a web page, no reliable read on a database's current shape, no way to tell whether another agent is working in the same directory, and nowhere safe to keep a key. So every time, it improvises: a `curl` line with a pasted token, a throwaway browser script, a number guessed into a config file, a secret copied into a shell profile. The improvisation works once, nobody checks it, and it's gone by the next shift.

agent-do answers both problems. Every agent picks up the same set of tools at clock-in, and the shop holds the practice, so no agent can skip orientation. A human installs it once. After that only agents use it, and they use it from the shell, because the shell is the one interface every coding agent already has:

```
agent-do <tool> <command> [args...]
```

Behind that command sit 103 tools and 961 commands. The rest of this page walks through the shop as an agent meets it: the tools, the sign-in sheet, the job list, the journal, the foreman, and the owner's window. Then it covers why the parts hold together and where the project is going.

## The tools on the bench

Every tool follows one rhythm: Connect, Snapshot, Interact, Verify, Save. The rhythm is machine-readable. Each of the 961 commands is filed under those beats in `registry.yaml` (6,805 lines), so an agent knows before it acts whether a command looks or changes something.

### Snapshot: state as data

An agent made of text needs the page as text with handles, not a picture. `browse snapshot -i` returns a web page as a numbered list of its interactive elements, each with a reference such as `@e7` that the next command can click or fill. `db snapshot` returns a schema. `macos` returns the desktop as a tree of controls. An agent can't reason about a state it hasn't seen as data, and a screenshot is a picture of data, not data.

### Interact: every command declares what it can do

Every command declares its reach. The registry classifies 543 verbs as read-only, 556 as writes, 60 as destructive, 28 as emitting secret material, and 11 as arbitrary-code escape hatches. A program running several agents at once reads that list once and knows which commands can run side by side and which have to wait.

Three checks keep the declarations honest. No tool enters the registry without a complete declaration, every promised verb is compared against the tool's own help text, and the read-only verbs are actually run and graded on whether they behaved like reads. The checks run in the test suite and on every push, and a tool that promises a verb it lacks fails the build.

### Verify: check the act against the world

`browse wait --stable` blocks until the network is quiet and the page has stopped moving. `namecheap` reads a DNS record back from the provider after writing it and compares the bytes. `manna lint` grades the work board's grammar and exits nonzero on findings.

Design is checked the same way. Two earlier design tools were retired on 2026-09-18, and their results were written down. `dpt` scored live pages 0–100 and turned out to be a floor check, not taste: a ratified design and a banned neon template scored one point apart. `aphrodite` generated pages from relational briefs and lost every blind trial it entered. What replaced them is `agent-do design`, the method that won a controlled trial on the Palingenesis home page. A top image model renders looks from the owner's copy, the owner picks a picture, a builder reproduces the pick in HTML under a copy contract, and a measured polish audit runs in the live page before anything is shown. Every judged round is kept in `corpus/design/`.

### Credentials (creds)

29 tools declare the secrets they need. Each secret is stored once in the operating system's secure store. The dispatcher looks it up at the moment of the call and passes it to the tool as an environment variable, so a token never appears in a command line, a log, a document, or a commit.

`OPENAI_API_KEY` needs explicit access. Ordinary tool calls and intent routing never load it from the secure store, and a stored key being present doesn't authorize its use. On macOS, credential status, source, and check commands read Keychain metadata without reading the secret or opening an unlock prompt. After the user authorizes it, only a named `creds get OPENAI_API_KEY --reveal` or `creds export OPENAI_API_KEY` request can unlock it, and a denied read fails without retrying. Bulk `creds export --tool ...` refuses tools that include this key. Environments that already supply the key explicitly still work.

### The human's desktop (+live)

Agents stop at the edge of the human's desktop. Commands that drive the visible desktop or a real browser window, or send messages in the human's own name, refuse to run unless the command starts with an explicit `+live(...)` modifier naming a scope, an application, and a time limit. Without it, the tool declines.

## Who is in the building (coord)

Several agents routinely work in one repository at once, and none of them can see the others. So the shop keeps a sign-in sheet under the repository's git directory and checks it against the operating system. A session counts as present only if its process still exists and its start time matches the one recorded, so a recycled process id can never pass for a dead session. A session unseen for 48 hours turns idle, and a dead one is marked dead and swept later. Agents declare a role (builder, auditor, researcher, overseer), a goal, and the paths they own. When two builders' paths overlap, both are interrupted with the overlapping paths named, and an auditor stepping onto a builder's paths sends a courtesy notice. Handoffs between live agents are pointers to files on the sheet; there's no mailbox. The sheet also carries a pulse fed by the host program's own events: whether an agent is working, waiting on the human, failed, or finished, and what it last touched.

<p align="center"><a href="assets/manna-serve-coord.png"><img src="assets/manna-serve-coord.png" alt="The coordination sheet: liveness-verified workers with focus and holdings, a selected worker in the inspector, and live path claims" width="900"></a></p>

## The job list on the wall (manna)

`manna` keeps the job list inside the repository, in `.manna/`, so it travels with the code and has git history. Every entry is one of three kinds: a track, which names a program of work; an item, which is a job an agent can claim; or a dream, an idea nobody can build until the owner converts it. This repository's board holds 225 entries: 128 done, 75 open, 19 blocked, and 3 in progress. Five of them are tracks and 12 are dreams.

Claiming is the move that matters, because two agents working from their own notes will happily start the same job. A claim here is proven, not just labeled. When an agent claims an item, the board stores a fingerprint of a secret derived from that session's identity, under a key that lives on the machine outside the repository and is readable only by the owner's account. A restarted process derives the same secret and keeps its claims. Writing another agent's name on the entry gets you nothing, because the name was never the credential. Status changes only through lifecycle verbs (claim, done, abandon, block, unblock). Nobody can set a status by hand, and the tool refuses the attempt.

An agent picking up a job needs the whole job on one page, so every claimable item has exactly one work order under `.handoff/` (175 files). It holds the exact claim command, the paths this agent owns, the neighboring paths to leave alone, the project's memory pasted in verbatim (an agent told to go fetch context usually doesn't), and numbered verification steps. The order is sealed: a hash of its content is stored on the board entry, editing it requires an explicit reseal, and a claim against an order with a broken seal fails with nothing written. Priority is a numbered filename derived from one ordered list. A bare number means "safe to start," and a `b` suffix means "held until that numbered blocker closes."

`done` closes on receipts. A commit carrying the item's trailer that touched real source lets the item close from any status. Without one, the operator can close it from their own terminal, and otherwise the claim-holder has to show proof.

## The journal and the library (zpc, context)

`zpc` is the journal, kept per project in `.zpc/`. This repository's holds 226 lessons, 68 decisions, and 18 positions, where a position is a verdict filed together with the evidence that would change it. Agents write it as they work, and it's read into every new session, sized to a budget looked up from the model's published limits instead of typed in. Two rules keep it honest. Entries arrive as dated claims, and a live observation outranks them. An entry that turns out wrong is retracted by appending a correction with a receipt; nothing is edited or deleted, because the record of having been wrong is worth keeping. And an agent that tries to reverse a filed position without naming new evidence is refused: the tool quotes the agent's own falsifier back and writes nothing. Every read leaves a line in an access log, which in this repository holds 6,329 lines.

`context` is the library next door: reference documentation fetched from the web and indexed for search. It's kept separate from the journal on purpose, because what a manual says and what the shop learned using it are different kinds of knowledge and go stale at different rates. Saved browser sessions and open database connections are short-term memory, so an agent doesn't log in again at every step.

## The foreman (hooks)

None of this asks an agent to remember that it exists, because hooks do the reading and the filing. Hooks are small scripts the agent's host program runs at fixed moments, and the installer ships 14 of them for Claude Code. At session start, the hooks pin the session's identity, read the job list, read the journal, read the previous session's drift report, and name any interrupts other agents have raised. During the session they nudge an agent that reaches for a raw command when a tool exists, or types a number where a published limit should have been looked up. Once per session, they note at turn's end when code changed and nothing was written to the journal. At session end, they retire the agent's presence and run reconcile with only its judgment-free repairs: releasing claims held by verified-dead sessions and clearing blocked flags whose blockers are done. Then they write `.manna/drift.yaml` for the next session's greeting. None of these block anything; they add context and get out of the way. Every step is gated on presence, so a repository with no board sees none of it.

## Receipts the shift leaves behind (trailers, reconcile)

A commit that advances a job carries a trailer line at the end of its message, `Manna: mn-xxxxxx`. 258 of this repository's 732 commits do. That one convention lets the job list be audited against git instead of against itself. `reconcile` looks for jobs whose commits landed while the entry still says open, claims held by sessions the operating system reports dead, blocked flags whose blockers have finished, stale dreams, work orders that point at nothing, and shadow work orders filed outside the canonical root. It reports everything and repairs only what needs no judgment. A trailer says which job a commit worked on, not that the job is finished, so reconcile never closes an item.

## The owner's window

One human owns the shop. The owner converts dreams into items and rules on the questions the machine flags. An agent that tries to claim a dream is refused with exit code 2, which this system uses for "stopped on purpose, needs a human," and nothing is written. The owner looks in through `manna serve`, a page on a loopback port that only this machine can reach. The port is picked on first run and kept, so the address stays stable. Its inbox lists every ask in one shape, who is asking and what for, with the owner's action as a button that runs exactly that one board command. The page and native clients read the same model from `manna state --json` instead of rebuilding the board's meaning in each interface.

<p align="center"><a href="assets/manna-serve-board.png"><img src="assets/manna-serve-board.png" alt="The owner's window: the job list with one-line digests, an item selected, its summary and receipts in the inspector" width="900"></a></p>

## Install

```bash
git clone https://github.com/ovachiever/agent-do.git
cd agent-do
./install.sh
```

It needs GNU Bash 4.4 or newer (macOS ships 3.2, so `brew install bash` first), Python 3.10 or newer, Node 18 or newer for the browser tool, and Rust if you want the work board built locally. The installer symlinks the command, installs the hook scripts, asks before registering them (an unregistered hook never fires), and runs a health check. After that the human types nothing. Agents pick up the tools and run the shop, and the one thing a human might be handed back is a link to the job list, where the work can be watched.

## Why it holds together

Every part of the shop trades in one unit, the receipt, and that's what makes the parts one system. Each tool takes a snapshot before it acts and a check after, so an agent's claim to have done something comes with the thing that shows it. The sign-in sheet is a receipt of presence, checked against the operating system. A claim on the job list is a receipt of ownership, a proof instead of a name. A commit trailer is a receipt in git, where the shop's history can be audited against the board. A journal entry carries the evidence that would overturn it. The hooks move receipts between sessions, reading them in at the start and writing them out at the end, and the owner rules on receipts, never on testimony. Take any one part away and the others still run. Take the receipt away and none of them do. That's what lets an agent vanish mid-session without loss, and lets a new one continue the work as if it were its own.

The shop is also its own first customer. This repository was built inside the systems it describes: 732 commits, 258 with a board trailer, 436 with a co-author line naming a model or an editor, 16 co-author identities in the log, and one person behind 677 of the 732. The board described here is the board that scheduled the work, and the journal is the one the work was learned in. The contracts gate was turned on this catalog first, with a grandfather list ratcheted to empty and then deleted. Nothing here was enforced on anyone else before it was enforced here.

## Built while building

agent-do was built in the middle of real work by one person and a fleet, and each of these projects was built on it. The rules were written where these builds broke: the sign-in sheet was rebuilt around incidents from multi-session builds, the design scorer was demoted to a floor check the week the Palingenesis redesign was about to ship on its say-so, and the policy layer on the board started as a claim-enforcement problem inside a Versova build.

- **Versova Supply.** Someone at an egg farm opens the Supply Catalog, finds a part by name or by clicking its number on the drawing of their own site's equipment, and sees whether it's in stock and how to request it. They can also ask in plain English. The assistant answers only from read-only lookups into the company's business records and machine manuals, cites the PDF page for every manual claim, attaches any SQL it ran, and treats text inside manuals and data rows as evidence, never as instructions. On staging and not yet live: a cart that checks out as a purchase request, and a model-read pass over the parts manuals that grew the drawing index from 672 drawings to 1,720.
- **Versova Research.** Someone at the company types a research question, or uploads their own data such as a trial spreadsheet, and gets back a cited report in hours, from a one-page brief to a fifty-page report. Before the research starts, a review panel reads the request and the files and stops to ask the requester anything that would send the work the wrong way. Eight specialist agents do the research or the number-crunching, and reviewers from different AI labs check the finished report and send it back for fixes before it can publish. One measured test run took about two and a half hours and cost about sixty dollars.
- **Holy Ghostty.** A macOS terminal, forked from Ghostty, that runs AI coding agents the way an operating system runs programs. Claude Code, Codex, OpenCode and shell sessions live in tmux on your Mac or any machine you reach over SSH, so a reboot doesn't end the work, and after a crash each one resumes the exact conversation it was in. Beside the terminals sit the agent-do work board, where one confirmation sends a worker off holding its sealed work order, and an archive that puts five tools' conversation history in one search.
- **Palingenesis.** An R&D engine for egg production. It reads published research claim by claim, breeds candidate innovations in generations where every idea keeps its parents, and sends each one to a three-round AI council: twelve experts scoring six dimensions from technical to ethical, twelve archetypal judges, and a thirteenth seat whose veto no code path can override. A simulator is built but labeled exploratory, and calibrated simulation is still ahead.
- **Aldebaran Group.** An astrology estate rebuilt around one command: a birth event goes in, and a complete, checkable record of that sky comes out, where every fact is either served, refused with a named reason, or left out by a signed scope ruling. A precision ephemeris engine computes the sky, and everything else reaches it only through contracted interfaces. When every source is silent on a number, the estate may invent one, but only after a recorded search, with the derivation committed before the test runs, rederived blind by a second model family, and labeled as the estate's own wherever it's served.
- **The orient.** A research campaign into whether reality shows evidence of orientation: intent, direction, or meaning waiting to be found. Nine blind lanes across two model families each worked a candidate with a steelman, a deflation, and a kill-test stated up front, and a claim counted only by how many independent fields it survived. The red team, from the other model family, was first tested on a decoy with seven planted defects, including a fake citation, and caught all seven. The finding it upheld: no claim pointing toward orientation survives two independent fields. The final report is still unwritten.
- **Scale Mechanics.** An experiment in getting frontier models to build new physical theory and then attack it until it holds or breaks. Three generations are kept in full, from a first draft that a later audit found carried 14 fatal defects to a paper whose every headline number comes from the repository's own code, locked by tests that fail if the paper and the code disagree. Models checking models can't prove nature agrees, so five predictions are registered in advance for reality to grade, among them a neutrino mass sum and a dark-energy sign.
- **The expense pipeline.** It finds the receipt for each company card charge wherever it ended up: a work mailbox, personal mail read straight from disk, a mail filter's quarantine, vendor billing pages, or Stripe invoice links. Then it fills in the expense and attaches the one document that belongs to that charge. Its handoff records the day a lazy fallback attached the alphabetically first of eighty receipts to every charge it couldn't match, which left some expenses holding two to four wrong receipts in a system with no bulk delete. The rule it kept is that no receipt beats a wrong one, and a later check reads every attached document to confirm it belongs to its charge.

## Where this is going

There are three moves, all on the board, in a program the board calls Moon: seven trunks lettered A through G, two of them done.

**The agent operating system.** Today the shop's rules live in the tools. The next layer makes them data: one committed policy file per repository or organization stating which model tiers can take which class of work, how a job can be claimed, and what evidence a commit must carry. The harness stamps every commit with the model, effort, and session that produced it, because models misreport and the harness doesn't. A session checks its own floor before it spends a token, and the merge gate refuses anything under the floor, unclaimed, out of order, or unproven. It's advisory in the session and binding at the gate, so no agent is stopped mid-flight and nothing unproven reaches main. The six questions a team should never have to ask aloud become answers the machine gives all day: what's next, who has it, is my branch current, was the model strong enough, can we prove it, and what is actually live.

**Multiple humans in the loop.** The same loop that serves the agents serves the people. A developer gets the job list at session start, claims with one command that also assigns the GitHub issue, and gets evidence stamps written by installed hooks without thinking about them. The owner's window becomes the team's window, with each ask routed to whoever holds that decision. Boards already work across repositories: since v1.5 every board carries a portable identity (this one is `mb-615bf342bcb87e41e7d54a7c6c0b84ae`) and can cite work on another repository's board, so a program that spans repositories stays one graph. A missing counterpart shows as "unavailable" instead of a broken link.

**The complete outer harness for any inner harness.** The inner harness (Claude Code, Codex, Cursor, whatever ships next) does the thinking. agent-do is everything around it: the tools, the sign-in sheet, the job list, the journal, the hooks, the receipts, the window. Hooks ship for three inner harnesses today: 14 scripts for Claude Code, six for Codex, and four for Cursor. Any inner harness that can run a shell command can use the tools without hooks at all, because the shell is the contract. Swap the inner harness or the model mid-program, and the board, the receipts, the journal, and the rules stay the same. A company can change who sits at the bench without changing the company.

## What it means that this exists

A team running ten agents without something like this pays for the same job twice, starts blocked work because the dependency graph lived in a document nobody read, ships work from a model too weak for it, and can't say a month later which model wrote which commit. The usual fix is to ask people to be careful, and carefulness doesn't scale to five developers and ten agents with the lead asleep. This is the other fix: the practice is held by the machine, so nobody has to remember to be careful. Intelligence is now the cheap part. What's scarce is a place intelligence can work inside of without having to remember that it exists, and that's what was built here, on itself and on real builds first.

The full system map is in [ARCHITECTURE.md](ARCHITECTURE.md), hook wiring is in [docs/INTEGRATION.md](docs/INTEGRATION.md), and the tool catalog is generated into [docs/TOOLS.md](docs/TOOLS.md). MIT license.
