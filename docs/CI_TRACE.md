# Reading a GitHub Actions deployment with `agent-do ci`

This guide explains the read-only GitHub Actions features that an operator, a
support engineer, or a future incident tracker can use to answer a basic
deployment question: which commit did this workflow run use, when did it run,
which parts passed or failed, and what is the smallest safe slice of its log?

These commands do **not** deploy code, retry a workflow, cancel a run, alter
GitHub, or change the checked-out repository. They only ask GitHub Actions for
information that already exists. They require the [GitHub CLI](https://cli.github.com/)
(`gh`) to be installed and authenticated with permission to read the target
repository's Actions runs.

## The two commands

Use `details` first. It is the receipt for a single workflow run.

```bash
agent-do ci details 48201933 --repo acme/payments-api --json
```

Use `logs` only when the run or a job needs closer attention. Ask for failed
output when investigating a failure; this produces less noise and is normally
the right evidence for an incident report.

```bash
agent-do ci logs 48201933 --failed --tail 200 --max-bytes 65536 \
  --repo acme/payments-api --json
```

`--repo owner/repository` makes the target explicit. This matters when running
the command from a fork, from a different checkout, or from no checkout at all.
If it is omitted, `agent-do ci` uses the current checkout's `origin` GitHub
remote.

## What `details` means

`details` returns one normalized JSON document. The important fields are:

| Field | Plain-language meaning | Why a deployment investigation needs it |
| --- | --- | --- |
| `run.head_sha` | The exact Git commit GitHub checked out for the run | It is the strongest link between a deployment workflow and a code change. |
| `run.workflow.name` and `run.workflow.id` | The human workflow name and GitHub's stable workflow identifier | They distinguish a production deploy from a test or scheduled workflow. |
| `run.status` / `run.conclusion` | Whether the run is still active and its final result, if known | A run can be queued, running, successful, failed, cancelled, or incomplete. |
| `run.timestamps` | When GitHub created, started, and last updated the run | These timestamps support careful correlation; timing alone never proves causation. |
| `jobs` and `jobs[].steps` | Every job and step GitHub reported, plus their results and timing | They show whether the build, infrastructure, or deployment stage actually failed. |
| `deployment_evidence` | GitHub deployment records whose SHA matches the run's commit | These are explicit GitHub deployment objects, distinct from guessing from names or nearby timestamps. |
| `run.url` and job URLs | GitHub's durable links | A human can review the primary record without reconstructing a web address. |

For example, a successful run with `head_sha` equal to the commit in an
application image label is **exact** commit evidence. A successful run that
started shortly before a rollout but has no matching version label is only
**timing correlation**. The command intentionally reports facts, not a claim
that a workflow caused an outage.

When the authenticated GitHub account can read deployment records, `details`
also returns matching GitHub deployment objects and marks
`deployment_evidence.status` as `available`. An empty deployment list means
GitHub has no matching deployment object; it does not mean no deployment took
place. If that API is unavailable to the credential, the status is `degraded`
with a reason while the rest of the workflow evidence remains usable.

## What `logs` returns—and why it is bounded

Workflow logs often contain huge volumes of build output. They can also contain
values that should not be copied into a ticket, chat, evidence bundle, or model
prompt. `logs` therefore returns an excerpt rather than claiming to be the
entire log.

By default it returns the last 200 lines and at most 65,536 bytes. You may make
the excerpt smaller or larger, within these hard safety limits:

- `--tail` must be between 1 and 1,000 lines.
- `--max-bytes` must be between 1 and 262,144 bytes.
- `--failed` uses GitHub's failed-step log view; without it, `logs` asks for the
  workflow's ordinary log view.

The JSON response includes its `limits` and a `truncated` object. Treat
`truncated.any: true` as “there may be important material outside this excerpt,”
not as an error and not as proof that the missing material is harmless.

Before returning an excerpt, `agent-do` removes common credential shapes,
including GitHub tokens, JWTs, AWS access-key IDs, bearer/basic authorization
values, and values assigned to names such as `token`, `secret`, `api_key`, and
`password`. It also strips terminal control characters. This is a guardrail,
not a guarantee that arbitrary sensitive text is safe to publish: review an
excerpt before sharing it outside the authorized investigation.

## A practical investigation sequence

1. Find the likely run ID in GitHub's Actions page, or list recent runs with
   `agent-do ci runs --repo acme/payments-api --json`.
2. Fetch `details` and record its run URL, commit SHA, conclusion, timestamps,
   and failed jobs.
3. If a job failed, fetch `logs` with `--failed`; start with the defaults
   rather than downloading a large log.
4. Compare the exact SHA against other evidence sources such as the commit
   deployed to a workload. Record whether the comparison is exact, likely, or
   unknown.
5. Preserve the structured JSON as evidence. Do not infer a causal chain only
   because two timestamps are close together.

## Expected failures and how to interpret them

The JSON form always uses a structured error document when the command itself
cannot retrieve data. Common examples are a missing run ID, an invalid log
limit, a run that does not exist, missing GitHub authentication, or missing
permission to view the target repository.

An unavailable source is evidence about the investigation's limits, not proof
that the workflow succeeded or failed. A future incident tracker should report
that source as degraded and continue gathering evidence from other configured
providers.

## Scope and non-goals

This feature is intentionally a GitHub Actions read surface. It does not try to
discover whether a workflow performed an Azure, Kubernetes, Terraform, or
Spacelift deployment. Those systems require their own explicit, read-only
provider evidence. It also does not parse arbitrary workflow logs as deployment
truth. The command gives a caller reliable, bounded facts from GitHub;
correlating those facts with a running workload remains a separate, explicit
step.
