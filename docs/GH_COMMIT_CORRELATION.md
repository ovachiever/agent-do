# Finding the pull request behind a deployed commit

Use this command when you know a deployed Git commit SHA and need GitHub's
declared links to the pull request and issue that introduced it:

```bash
agent-do gh commit <commit-sha> --repo owner/repository --json
```

It reads three kinds of evidence:

1. The commit itself: its full SHA, URL, message, author time, and commit time.
2. Pull requests GitHub associates with that exact commit, including each PR's
   number, URL, state, head SHA, and merge time.
3. Issues that an associated PR explicitly declares it closes.

This is deliberately narrower than a search. A matching branch name, a commit
message that mentions a ticket, or a rollout that happened soon after a PR does
not prove a relationship. The command reports only links GitHub supplies.

An empty `pull_requests.items` list is a real result: GitHub did not associate
a PR with that commit. It does not mean the commit is safe, unrelated to a
deployment, or unimportant. If GitHub lets the command read the PR but not its
closing-issue references, `issues.status` is `degraded`; callers should report
that limit instead of inventing an issue link.

The command is read-only. It does not create, update, merge, label, comment on,
or otherwise change any GitHub object.
