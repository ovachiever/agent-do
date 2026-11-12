# GitHub issues and PR creation

`agent-do gh` uses the authenticated GitHub CLI transport. Local repository
operations belong to `agent-do git`. Existing PR inspection and review commands,
including `agent-do gh pr owner/repo#123 --json`, keep their existing syntax.

## Issues

```bash
agent-do gh issue create --repo owner/repo --title "Fix export" --body-file issue.md --label bug
agent-do gh issue list --repo owner/repo --state open --assignee @me --json
agent-do gh issue assign owner/repo#12 --assignee alice --assignee bob
agent-do gh issue unassign owner/repo#12 --assignee bob
agent-do gh issue label owner/repo#12 --add in-progress --remove ready
agent-do gh issue comment owner/repo#12 --body-file comment.md
agent-do gh issue close owner/repo#12 --reason completed
```

- Targets accept `owner/repo#12`, a `https://github.com/owner/repo/issues/12`
  URL, or a positive issue number. Bare numbers use `--repo` or the current
  checkout's GitHub `origin`. An explicit repository conflicting with the
  reference is an error. PR URLs and PR objects are refused by issue mutations.
- `assign` and `unassign` default to `@me`; repeat `--assignee` for other people.
  Assignment is additive. It preserves existing assignees and does not provide
  exclusive ownership or change Manna claims. Claim arbitration and GitHub/Manna
  synchronization belong to the separate Moon trunk B lane.
- `list` follows every page and excludes PRs from GitHub's shared issues
  collection. Filters are `--state open|closed|all`, `--assignee`, `--author`,
  and repeatable `--label`. `--limit N` caps display after collection; JSON
  always carries the exact `count` shown and `total` matching issues fetched.
  Large repositories can take longer because a display limit does not limit
  collection. Totals describe the fetched pages, not an atomic GitHub snapshot.
- Create/comment require exactly one of `--body` or `--body-file`; `-` reads
  stdin. Comments require nonempty text. Bodies go to the transport over stdin,
  preserving their text and avoiding body contents in process arguments.
- All issue commands support `--json`. Writes return the observed issue after
  reading it back. Comments also return the transport's comment URL.
  A failed read-back after a successful write reports that partial success.
  Inspect the existing issue before retrying, especially after create/comment.
- `close --reason` accepts `completed` (default) or `not planned`.

## PR creation and declaration

```bash
agent-do gh pr create --title "Fix export" --base main --head feature/export \
  --body-file pr.md --declare --draft --dry-run --json
```

Review that payload, then remove `--dry-run` when authorized to create the PR.
`--repo` defaults to the checkout's GitHub `origin`; `--head` defaults to the
current branch. `--title`, `--base`, and exactly one body input are required.
Repeatable `--assignee`, `--reviewer`, and `--label` flags are also supported.

The local preview makes no GitHub calls. Actual creation always supplies
`--head`: GitHub CLI documents this as skipping its implicit push/fork behavior.
The branch must already be published. Native `gh pr create --dry-run` can push,
so this tool renders its own preview without invoking that command.
See the [GitHub CLI creation contract](https://cli.github.com/manual/gh_pr_create).

`--declare` appends a versioned JSON block between
`<!-- agent-do:declaration:v1 -->` and `<!-- /agent-do:declaration -->`.
The user's body remains intact. A body already containing either marker is
refused, preventing duplicate or stale declarations.

The declaration records `base_commit`, `head_commit`, and an ordered
`contributions` array for **every** commit in `base..head`. Each contribution
contains its commit SHA and committed `Work-Item`, `Model`, `Effort`, and
`Session` trailers. `Manna` is accepted as the repository's existing alias for
`Work-Item`; conflicting values are refused. Each required field must have
one nonempty value. Missing fields, ambiguous values, no commits, or unavailable
local branch refs stop creation before any GitHub call.

For declarations, `--head` must name a local branch. Fork-qualified heads are
supported only without `--declare`. Base resolution prefers `origin/<base>`
when origin matches the target repository, otherwise the local base branch.
The declaration names the exact base SHA used; refresh the base ref explicitly
when needed. No fetch or push runs implicitly.

Before publishing a declared PR, the tool checks that the published head SHA
matches the local declaration. After creation it reads the PR back and checks
both head SHA and body. A concurrent change or failed read-back reports the
created PR URL and exits with an error; it never creates a replacement PR.

This command preserves committed provenance. It does not infer model or effort
from its current caller, authenticate trailer claims, generate missing stamps,
or enforce model floors. Those functions belong to Moon trunk C (`attest`)
and trunk D (policy). An unstamped branch can use ordinary PR creation, but
`--declare` fails closed until the required commit stamps exist.

## Focused validation

```bash
env PATH="$PWD/.venv/bin:$PATH" python3 tests/test_gh.py
env PATH="$PWD/.venv/bin:$PATH" python3 -m py_compile tools/agent-gh tests/test_gh.py
env PATH="$PWD/.venv/bin:$PATH" ./agent-do harness contracts validate
env PATH="$PWD/.venv/bin:$PATH" ./agent-do harness contracts drift --tool gh --json
env PATH="$PWD/.venv/bin:$PATH" ./bin/gen-tools-doc --check
```

The GitHub suite executes the real dispatcher against a recording transport and
temporary Git repositories. It creates no live GitHub issues or PRs and launches
no apps. Provider writes require separately authorized live acceptance.
