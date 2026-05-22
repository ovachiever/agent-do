# KAN-8 Green Lantern workflow demo

This file shows the shape of a scheduled job that detects a bad record in MongoDB,
creates a Jira ticket with context, moves it into active work, and then hands off
to GitHub for the code-fix PR.

## Detection

```bash
agent-do mongo query justice_league heroes \
  --where '{"name":"Green Lantern"}' \
  --projection '{"_id": 0, "name": 1, "alterEgo": 1, "powers": 1}' \
  --connection local --json
```

If the scheduled job sees `alterEgo != "Kyle Rayner"`, it opens Jira.

## Jira handoff

```bash
agent-do jira issue create KAN \
  --type Task \
  --priority High \
  --summary "Green Lantern alter ego is Hal Jordan instead of Kyle Rayner" \
  --description "Scheduled job detected a data integrity issue in justice_league.heroes.\n\nDatabase: justice_league\nCollection: heroes\nHero: Green Lantern\nObserved value: alterEgo = Hal Jordan\nExpected value: alterEgo = Kyle Rayner\n\nEngineer should inspect the record, apply the Mongo update, verify the fix, and then move the issue to review."

agent-do jira issue assign KAN-8 --to 712020:3efe562e-7c15-42f4-a2d6-e4281f2dd3ad
agent-do jira issue transition KAN-8 --to "In Progress"
```

## Code-fix handoff

The engineer runs the repo-local Mongo repair script:

```bash
mongosh --host 127.0.0.1 --port 27017 docs/internal/kan-8-green-lantern-fix.js
```

## GitHub handoff

Once the fix lands in a branch, push it and open the PR with the GitHub CLI
or a future `agent-do gh` PR-create extension:

```bash
git push fork fix/kan-8-green-lantern
gh pr create --title "Fix Green Lantern alter ego" --body "KAN-8: update justice_league.heroes Green Lantern alterEgo to Kyle Rayner"
agent-do jira issue transition KAN-8 --to "In Review"
```

The important bit is the handoff order:

1. Detect in Mongo
2. Create Jira ticket with context
3. Assign and move to `In Progress`
4. Create the code-fix branch and PR
5. Move the Jira ticket to `In Review`
