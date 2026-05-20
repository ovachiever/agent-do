# agent-gh

GitHub repository, pull request, issue, and release work-state plugin for agent-do. Wraps the GitHub CLI (`gh`) with structured output, a concurrency-safe repo cache, and an expanded command surface designed for autonomous agents running across multiple repositories.

## Requirements

- Python 3.10+
- [`gh` CLI](https://cli.github.com/) authenticated (`gh auth login`)

## PR reference format

Most commands accept a PR (or issue) reference in any of these forms:

| Form | Example | Notes |
|------|---------|-------|
| `owner/repo#N` | `ovachiever/agent-do#5` | Fully qualified — works from any directory |
| Full URL | `https://github.com/owner/repo/pull/5` | Parsed from clipboard-style URLs |
| Bare number | `5` | Inferred from current directory's git remote |

---

## Commands

### Identity & inventory

```bash
agent-do gh whoami [--json] [--refresh]
agent-do gh repos [sync] [--json] [--refresh] [--limit N]
```

`repos` caches your accessible repository list under `~/.agent-do/gh/` for fast subsequent lookups. `repos sync` forces a fresh fetch.

---

### PR discovery

```bash
agent-do gh inbox [--json] [--limit N]
agent-do gh awaiting [query] [--json] [--limit N] [--repo owner/repo] [--owner org] [--author name]
                     [--include-bots] [--include-drafts] [--include-reviewed]
                     [--audit] [--replies] [--probe-deploys]
agent-do gh prs [query] [--json] [--limit N] [--state open|closed|all]
                [--repo owner/repo] [--owner org] [--author name]
                [--review-requested [me]] [--review none|required|approved|changes_requested]
                [--checks pending|success|failure]
```

`inbox` shows PRs where action is needed (review requested, changes requested, failing checks). `awaiting` filters to PRs likely waiting on your review specifically.

---

### PR detail

```bash
agent-do gh pr <ref> [--json]
agent-do gh diff <ref>
agent-do gh threads <ref> [--all] [--json]
agent-do gh checks <ref> [--json]
agent-do gh review <ref> [--json]
agent-do gh audit <ref> [--reply] [--probe-deploys] [--json]
```

`audit` produces a structured risk analysis of a PR — security, correctness, test coverage, API contract changes. `--reply` formats the output as a ready-to-post review comment. `--probe-deploys` checks whether the PR's target branch has active deployments.

---

### PR actions

```bash
agent-do gh approve <ref> [--body <text>] [--body-file <path>]
agent-do gh request-changes <ref> [--body <text>] [--body-file <path>]
agent-do gh comment <ref> [--body <text>] [--body-file <path>]
agent-do gh merge <ref> [--squash|--merge|--rebase] [--auto] [--delete-branch]
                  [--match-head-commit <sha>] [--subject <text>] [--body <text>]
agent-do gh ready <ref>
agent-do gh draft <ref>
```

---

### PR lifecycle (v1.2)

```bash
agent-do gh close <ref> [--delete-branch] [--comment <text>] [--comment-file <path>] [--dry-run]
agent-do gh reopen <ref> [--comment <text>] [--comment-file <path>] [--dry-run]
agent-do gh checkout <ref> [--branch <name>] [--detach] [--force] [--recurse-submodules] [--dry-run]
agent-do gh co <ref> ...        # alias for checkout
agent-do gh edit <ref> [--title <text>] [--body <text>] [--body-file <path>] [--base <branch>]
                 [--milestone <name>] [--remove-milestone]
                 [--add-label <label>] [--remove-label <label>]
                 [--add-assignee <user>] [--remove-assignee <user>]
                 [--add-reviewer <user>] [--remove-reviewer <user>]
                 [--add-project <project>] [--remove-project <project>]
                 [--dry-run]
agent-do gh update-branch <ref> [--rebase] [--dry-run]
```

All five lifecycle commands support `--dry-run`: prints the `gh` command that would be run and exits with code `2` without touching GitHub.

---

### Issues

```bash
agent-do gh issue list <owner/repo> [--state open|closed|all] [--label <label>]
                       [--assignee <user>] [--author <user>] [--milestone <name>]
                       [--limit N] [--json]

agent-do gh issue view <owner/repo#N> [--comments] [--json]

agent-do gh issue create <owner/repo> --title <text> [--body <text>] [--body-file <path>]
                         [--label <label>] [--assignee <user>] [--milestone <name>]
                         [--project <name>] [--dry-run] [--json]

agent-do gh issue comment <owner/repo#N> [--body <text>] [--body-file <path>] [--dry-run] [--json]

agent-do gh issue close <owner/repo#N> [--reason completed|not_planned] [--comment <text>] [--dry-run] [--json]
agent-do gh issue reopen <owner/repo#N> [--comment <text>] [--dry-run] [--json]

agent-do gh issue label <owner/repo#N> [--add <label>] [--remove <label>] [--dry-run] [--json]
agent-do gh issue assign <owner/repo#N> [--add <user>] [--remove <user>] [--dry-run] [--json]

agent-do gh issue snapshot <owner/repo> [--state open|closed|all] [--limit N] [--json]
agent-do gh issue triage <owner/repo#N> [--json]
```

`issue snapshot` returns a bulk structured view of all open issues — useful for agents that need to reason over the full issue backlog. `issue triage` runs deterministic classification (bug/feature/question/chore) and suggests labels based on title + body patterns.

---

### Releases

```bash
agent-do gh release list <owner/repo> [--limit N] [--json]
agent-do gh release view <owner/repo> <tag> [--json]
agent-do gh release latest <owner/repo> [--json]

agent-do gh release create <owner/repo> <tag> [--title <text>] [--notes <text>] [--notes-file <path>]
                           [--target <branch-or-sha>] [--draft] [--prerelease]
                           [--generate-notes] [--asset <file>] [--dry-run] [--json]

agent-do gh release edit <owner/repo> <tag> [--title <text>] [--notes <text>]
                         [--draft|--no-draft] [--prerelease|--no-prerelease] [--dry-run] [--json]

agent-do gh release publish <owner/repo> <tag> [--dry-run] [--json]
agent-do gh release delete <owner/repo> <tag> [--cleanup-tag] [--confirm] [--dry-run] [--json]

agent-do gh release upload <owner/repo> <tag> <file> [<file>...] [--dry-run] [--json]
agent-do gh release download <owner/repo> <tag> [--pattern <glob>] [--output-dir <dir>] [--dry-run] [--json]

agent-do gh release notes <owner/repo> --since <previous-tag> [--target <branch-or-sha>] [--json]
```

`release notes` generates categorized release notes (features, fixes, chores, uncategorized) for all PRs merged since `--since`. Uses the GitHub API to resolve tag timestamps — supports both annotated and lightweight tags — so the fallback PR list is correctly bounded even when `--generate-notes` isn't available.

`release delete` requires `--confirm` to execute; `--dry-run` prints the would-be command and exits 2.

---

### Raw API access

```bash
agent-do gh api GET /rate_limit [--paginate] [--jq <expr>] [--json]
agent-do gh api POST /repos/owner/repo/issues --field title="Bug" --field body="..."
agent-do gh api PATCH /repos/owner/repo/pulls/5 --field title="New title"
agent-do gh api PUT /repos/owner/repo/topics --raw-field names='["go","api"]'
agent-do gh api DELETE /repos/owner/repo/releases/123

agent-do gh graphql '<query>' [--field K=V] [--paginate] [--jq <expr>] [--json]
agent-do gh graphql @query.graphql [--field owner=ovachiever --field repo=agent-do]
```

Pass `@file` to `graphql` to read the query from a file. `--paginate` follows GitHub's cursor-based pagination automatically.

---

## Dry-run behavior

Commands that write to GitHub accept `--dry-run`:

- Prints the `gh` command that would be executed
- Exits with code `2` (the agent-do "needs clarification" exit — orchestrators treat this as "preview shown, awaiting confirmation")
- Nothing is sent to GitHub

Supported on: `close`, `reopen`, `checkout`, `edit`, `update-branch`, `issue create`, `issue comment`, `issue close`, `issue reopen`, `issue label`, `issue assign`, `release create`, `release edit`, `release publish`, `release delete`, `release upload`, `release download`.

---

## JSON output

All commands support `--json`. Output follows the agent-do snapshot envelope:

```json
{
  "tool": "pr",
  "ref": "ovachiever/agent-do#5",
  "timestamp": "2026-05-20T14:00:00Z",
  "data": { ... }
}
```

Error conditions return structured `{"error": "..."}` to stderr with a non-zero exit code.

---

## Error handling

All subprocess failures (including a missing or unauthenticated `gh` binary) raise a `GhError` and print a structured error — no Python tracebacks leak to the caller. `OSError` (missing `git` or `gh`) is caught at both the transport layer and the git-remote resolution layer.

---

## Regression test coverage

Test suite: `tests/test_gh_pr_compat.py` (56 assertions, all passing). Run via:

```bash
python3 tests/test_gh_pr_compat.py
# or via the full test suite:
./test.sh
```

Unit tests also live in `tools/agent-gh/test/unit/` covering ref parsing and triage logic.

**Covered scenarios:**

| Area | What's tested |
|------|---------------|
| Ref parsing | `owner/repo#N`, URL, bare number, infer from git remote |
| `git` binary missing | `repo_from_git` returns `None`, no exception |
| `gh` binary missing | `run_gh` raises `GhError`, no traceback |
| `gh` timeout | `run_gh` raises `GhError` with timeout message |
| PR `--dry-run` | All 5 lifecycle commands: close, reopen, checkout, edit, update-branch |
| Multi-label `--add-label` | Multiple labels passed and forwarded correctly |
| Release notes | Tag date resolution (annotated + lightweight tags), mergedAt filtering |
| Issue triage | Classification rules, label suggestions |
| Fixture-backed | issue list, view, release list, release view all parse real API shapes |
