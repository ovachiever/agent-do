# Managed Integration (`agent-do git integration`)

One repository opts in. Each assignment attempt gets its own worktree and
branch, bound to the exact claimant. A commit saves progress; a submission
requests integration; one integrator per repository builds the candidate
against the current target, validates that exact combined tree with the
repository's own checks, and advances the target only while it still equals
the tested base. `manna done` records closure separately; nothing here closes
an item, lands an unsubmitted commit, or deletes a branch or worktree.

Implementation: `lib/git_integration.py` behind `tools/agent-git`
(`integration` verb). Fixtures: `tests/test_git_integration.py` (run by
`./test.sh`). Item: mn-54fe40.

## Where things live

Everything below is shared by every worktree of one repository, because it
lives with the common git dir, not in a checkout and not in a branch.

| What | Where | Why there |
|---|---|---|
| Policy | `<common git dir>/config`, section `[agent-do "integration"]` | A tracked file is a branch policy: the branch being landed could rewrite it. The private config is per-repository, untracked, read identically from every worktree (verified), and writable only with filesystem access to the primary checkout. |
| Workspaces, queue, landing intent, audit | `<common git dir>/agent-do/integration/` (`workspaces.json`, `queue.json`, `intent.json`, `events.jsonl`, `receipts/<entry>/`) | Durable across every worktree and every session; the same place coord keeps its state (`<git dir>/agent-do/coord`). |
| Pinned refs | `refs/integration/submissions/<entry>` (the exact submitted commit), `refs/integration/candidates/<entry>` (the tested candidate) | A worker may move its branch; recovery and audit need the commits that were actually submitted and tested to stay reachable. |
| Worker branches | `integration/<mn-id>-a<N>` | One per assignment attempt; never deleted by this tool. |
| Workspaces | `<workspace-root>/<repo>-<mn-id>-a<N>` (default: beside the repository) | The same sibling convention `agent-do git worktree add` uses. |
| Candidate tree | `<candidate-path>` (default: `<parent>/<repo>-integration`), a detached worktree | The integrator never builds in the primary checkout or in a worker's tree. |

Policy keys (all under `agent-do.integration.`): `enabled` (true/false),
`target` (a local branch), `check` (multi-valued; the repository's own
validation commands, run with `sh -c` in the candidate tree), `authorized-by`
(required text: who approved integration authority), `authorized-at`,
`enabled-by`, `board-id` (the canonical board's federation id, pinned at enable
time), `workspace-root`, `candidate-path`, `disabled-reason`, `disabled-at`,
`disabled-by`. Any other key makes the policy invalid.

Policy states: `off` (no keys: the existing workflow is unchanged and every
`integration` verb except `config` and `status` says so), `enabled`,
`disabled` (no new dispatch, no landing; status, recovery, pending submissions
and worktrees are retained), `invalid` (every managed operation refuses and
`config` exits 1 naming the problems).

## Commands

```
agent-do git integration enable --target main --check "./test.sh" --authorized-by "Erik, 2026-11-03" [--workspace-root <dir>] [--candidate-path <dir>]
agent-do git integration disable --reason "pause for review"
agent-do git integration config [--json]
agent-do git integration workspace add <mn-id> [--path <dir>]      # the claimant, from anywhere in the repository
agent-do git integration workspace list
agent-do git integration submit <mn-id> [--report <file>] [--evidence <text>...]
agent-do git integration run [--once]                              # the integrator
agent-do git integration recover
agent-do git integration status [<mn-id>] [--json]
```

Exit codes: 0 done; 1 refused (the message says why); 2 contended or
unauthorized (another integrator holds the lock, no Manna identity in this
process, or the caller does not hold the claim). Every verb takes `--json`.

## Lifecycle and status

`status` reports one state per item, with the reason, the receipts, the open
coord drops for the item, and the exact next action.

| State | Meaning | Who acts |
|---|---|---|
| `unregistered` | no workspace yet | the claimant runs `workspace add` |
| `building` | a workspace exists; nothing queued (or the last submission was superseded) | the worker commits and submits |
| `queued` | a submission waits for the integrator | the integrator runs |
| `integrating` | a run is in progress or was interrupted | `recover` settles it |
| `landed` | the target advanced; receipts record submission SHA, candidate, integrated SHA, base, checks | the coordinator reviews and accepts in manna |
| `blocked` | with a reason (below) | named per reason |
| `superseded` | a newer submission for the same attempt replaced it | nothing; history |

Blocked reasons. Worker-owed reasons are routed as **action drops** addressed
to the worker on the item (`coord drop add --for-item --action`) and are not
retried until a new submission supersedes them: `conflict` (the merge onto
the target conflicts; files listed), `checks_failed` (a check exited nonzero;
log path recorded), `board_paths` (the branch changes `.manna/` or
`.handoff/`), `stale_submission` (the managed record's attempt or current
submission moved), `reassigned` (the claim proof changed; a superseded claim's
work is never forwarded), `item_closed` (done on the board). Retryable
reasons are re-attempted by the next `run` and post no obligation:
`target_checkout_busy` (the checkout holding the target has overlapping dirty
files or an operation in progress), `config_disabled`, `config_invalid`,
`config_changed` (the policy's target is no longer the one submitted against).

A landing posts an **info drop** to the worker with the receipt path. A
submission that supersedes a blocked one leaves the old drop as it is: coord
never deletes a drop, and `status` shows the open ones with their stage.

## Design, code-backed

### Canonical board, divergent copies

`manna` roots `.manna/` at the current directory
(`tools/agent-manna/src/store.rs`, `MannaStore::new(".")`), so a worktree
carries its own copy of the tracked board, frozen at the branch's commit. coord
already resolves the canonical board through `git rev-parse --git-common-dir`
(`canonical_board_root` in `tools/agent-coord`). This tool applies the same
rule: every `manna` and `coord` call runs at the checkout that owns the common
git dir, whatever directory the caller is in; `workspace add` from inside a
worktree reports `via_worktree: true` and the canonical root. Worker copies are
never written, and a submission whose diff against the target touches
`.manna/` or `.handoff/` is refused at `submit` and again at landing
(`board_paths`): board edits (claims, seals, handoffs) belong to the canonical
checkout, as today.

### Config trust and integration authority

The policy is read with `git config --file <common>/config` and validated on
every use: `enabled` must be a boolean, `target` a real local branch, at least
one `check`, `authorized-by` non-empty, no unknown keys, and `board-id` equal
to the canonical board's federation id when both exist. `enable` records who
ran it (`enabled-by`, the Manna session label) and when. Before every landing
the integrator re-reads the live policy under its lock: disabled or invalid
refuses (`config_*`, retryable), a changed target refuses (`config_changed`).
Each queue entry records the policy digest it was queued under and the digest
it landed under.

What this does and does not enforce, plainly: this tool guarantees that the
path *it* takes never lands an untested tree, never lands against a base other
than the one it tested, and never lands one submission twice. It does not stop
a local process from running `git update-ref` or editing files directly; local
hooks do not either (`coord guard install` is warn-only, by design). The audit
for this path is `events.jsonl`, the receipts, the pinned refs and the landing
commit message; anything outside it is visible in git history and nowhere
else. Nothing here rewrites a machine-wide runtime policy, and enabling a
repository is a local decision the operator records with `--authorized-by`.

### Main checkout safety (how the ref moves)

Verified in a scratch repository on 2026-11-03 (git 2.56):

- `git update-ref refs/heads/main <new> <old>` is an atomic compare-and-swap
  that refuses a moved ref (exit 128). Moving a ref under a checked-out branch
  that way leaves that working tree showing phantom staged changes, so it is
  never done where the branch is checked out.
- `git merge --ff-only <candidate>` in the checkout that holds the target
  keeps dirty files that the landing does not touch, refuses when a dirty file
  overlaps (`Your local changes ... would be overwritten`) and refuses while a
  merge or rebase is in progress. Nothing is stashed, reset or cleaned there.

So: the candidate is built and checked in the integrator's own detached
worktree; when a worktree holds the target branch, the landing is
`merge --ff-only` run there (`target_checkout_busy` when git refuses);
otherwise it is the compare-and-swap. A target that moved between the test
and the landing is rebuilt and retested, never forced. The candidate is the
source commit itself when it already descends from the base (fast-forward,
integrated SHA = submission SHA), else a merge commit whose message carries
the submission id, source SHA, entry id and `Manna:` trailer; the queue
records both SHAs either way.

### Transaction recovery

Before any ref write the integrator saves `intent.json` (entry, candidate,
base, target, holder) and pins `refs/integration/candidates/<entry>`. On every
`run` and `recover`, a pending intent is settled first:

| Observation | Outcome |
|---|---|
| the target already contains the candidate | the ref moved before the crash: complete the receipt (`recovered: true`), never land again |
| the target still equals the tested base, policy enabled and unchanged | retry the same landing with the same candidate; nothing is rebuilt because nothing changed |
| the target moved, or the policy is no longer enabled | void the intent, requeue the entry; the candidate stays pinned and the next run rebuilds against the new base |

An entry left `integrating` with no intent (killed before the intent) is
requeued. Replaying `run` or `recover` after a completed landing finds
nothing: the fixtures assert the first-parent commit count moves by exactly
one per landing across every interruption. Test seam:
`AGENT_GIT_INTEGRATION_FAULT=after_intent|after_ref_update` exits the process
(code 70) at that point.

### Workspaces, binding, replacement

`workspace add <mn-id>` reads the canonical row (`manna show --json`), requires
`in_progress` with a claimant, and requires the caller's own
`manna identity --json` proof to equal the row's `claim_token_hash` exactly
(a label is never matched). The attempt comes from `.manna/managed.json`
(1 when the item is not managed). The record carries the canonical board path
and id, the base (target tip), the start commit, the worker label and proof,
and the work-order digest. It then runs `coord touch` at the canonical root
in the worker's own process, which binds the worker's coord record to its
proof there (how `drop add --for-item` finds it), and again inside the
workspace.

A later `workspace add` by the same proof is idempotent; by a new claimant on
the same attempt it rebinds the record (history kept); on a new attempt
(after `manna managed release`) it creates `integration/<mn-id>-a<N+1>`
starting from the previous attempt's branch tip, so the replacement inherits
the work, and the previous worktree and branch are retained. A superseded
worker's identity can no longer register or submit (proof mismatch, exit 2).
A recorded workspace whose directory is gone is restored from its branch.

### Submission queue

`submit <mn-id>` requires the live claim (proof equality), the registered
workspace for the current attempt, commits beyond the target, and no
board-owned paths. It pins the branch tip at
`refs/integration/submissions/<entry>`, records base, commits (with which
carry the item's `Manna:` trailer), the evidence lines, and a report (the
`--report` file, or a generated one). For a managed item it runs
`manna submit <id> --report <file> --revision <sha>` at the canonical root and
records the submission id manna minted; otherwise a local id. An earlier open
entry for the same attempt becomes `superseded`. A landing in flight for the
item refuses a new submission until `recover` settles it.

### Routing and the hook boundary

Obligations are coord action drops addressed by item from the canonical root;
coord resolves the recipient by claim proof among live records. coord keeps
its store per git dir (`resolve_project_paths` in `tools/agent-coord`), so a
session whose hooks run with a worktree as cwd reads that worktree's store,
not the canonical one. The obligation is still delivered: `integration status
<mn-id>` lists the item's open drops from the canonical store, and
`coord worker <mn-id>` at the primary shows them. The doorbell reaches a
worker whose hooks read the canonical store. This is stated, not hidden.

## Codex and Claude: the same workflow

Identity comes from the harness hooks either way (`CLAUDE_SESSION_ID` or
`CODEX_THREAD_ID`, derived by manna under the machine key), so the commands
are identical: claim at the canonical root, `workspace add`, work in the
workspace, `agent-do git commit` (secret scan) with a `Manna: <id>` trailer,
`submit`, and leave landing to the integrator. The auto snapshots in
`refs/auto/<branch>` remain recovery material (`agent-do git snap`); the
integrator never reads them and they are never evidence of integration.

## Resource isolation a workspace does not give you

A worktree isolates files under version control and nothing else:

- build caches: `target/` (Rust), `node_modules/`, `.venv/` are per-worktree
  and start empty; the candidate tree keeps its ignored files between runs so
  builds are incremental, which also means a check that depends on an ignored
  file is testing something the repository does not contain (`git clean -fd`,
  not `-fdx`, runs before each build; wipe the candidate tree to reset);
- databases, ports, daemons and installed applications are shared by every
  checkout on the machine; a check that starts a server on a fixed port or
  migrates a shared database collides across lanes, and the pilot's checks
  must be the ones that do not (this repository's `./test.sh` uses an isolated
  `AGENT_DO_HOME` and temp directories);
- `$AGENT_DO_HOME` state (credentials, caches) is shared; coord state is per
  git dir; zpc memory is bound to the primary store by `worktree add`.

## Enabling a pilot (authorization pending)

Creating mn-54fe40 authorized implementation, not activation. Enabling one
repository needs Erik's explicit choice of the repository and of who holds
local integration authority, recorded in the command itself:

```
cd <the chosen repository's primary checkout>
agent-do git integration enable --target main --check "./test.sh" --authorized-by "Erik, <date>, <channel>"
```

Then two real assignments: each worker claims, runs `workspace add`, commits,
submits; the operator runs `agent-do git integration run` (or a scheduler
does); the coordinator accepts in manna against the integrated SHA that
`status` prints. Demonstrating recovery means interrupting one landing with
the fault seam, or killing the process, and running `recover`. Rolling out to
another repository is the same `enable` command there, nothing repository
specific. `disable --reason` stops it without losing anything.

## Verification receipts

`python3 tests/test_git_integration.py` builds eleven isolated estates with
real boards, pinned identities and coord sessions anchored to processes the
fixture kills, and exercises: opt-in off/enabled/invalid/disabled; the
canonical board read from inside a worktree whose own copy predates the
claim; board-owned paths refused; submit, fast-forward landing in the
checkout holding the target, receipts, the info drop, replay as a no-op; two
competing submissions (superseded) and a stale base (merge candidates in
order, provenance of both SHAs); a conflict blocking with the file list, one
action drop, no duplicate on rerun, resubmission landing; failed checks with
the log as the receipt; a dirty target checkout (non-overlapping edits
preserved, overlapping edits block and retry); interruption after the intent
and after the ref update (exactly one landing each), and a moved target
voiding the intent and rebuilding; disabled retaining the queue, a changed
target and a removed `authorized-by` failing closed, reassignment and closure
not forwarded; a managed item whose worker dies (coord verifies, `managed
release`), a replacement inheriting the branch on attempt 2, landing, and the
coordinator accepting at the integrated SHA and closing; one integrator per
repository.

Found while building the fixtures and fixed in the same change: manna's
sidecar files (`managed.json`, `coordinators.json`, `managed-intent.json`)
were written with `"version": 0` by the derived `Default`, while the read
default and coord's assignment targeting expect 1, so no item on a freshly
managed board could receive an item-addressed drop. New files carry version
1 and a 0 on disk is read as 1 and upgraded by the next save
(`tools/agent-manna/src/managed.rs`, regression test included).
