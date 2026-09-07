# Set up your private agent-strava dashboard

![Training Local application icon](../assets/training-local-icon.png)

`agent-strava` is personal and local-first: each person creates their own
Strava application, connects only their own account, and keeps their activity
cache on their own machine.

## Before you begin

You need a Strava account and your own Strava API application. Visit
[Strava API Settings](https://www.strava.com/settings/api) while signed in and
create an application if you do not already have one.

For the default local setup, set the application's **Authorization Callback
Domain** to:

```text
localhost
```

Keep the displayed client ID and client secret available. The client secret is
entered directly in the terminal; do not paste it into chat, a shell profile,
or a repository file.

Use the included [Training Local application icon](../assets/training-local-icon.png)
when Strava asks for an API application icon. It is a shared project asset and
contains no personal data or Strava branding.

## Connect your account

From the agent-do checkout, run:

```bash
agent-do strava init
```

The guided prompt stores the client secret in your operating system's secure
credential store and writes non-secret profile metadata under
`~/.agent-do/strava/`. It uses this local callback address by default:

```text
http://localhost:8787/callback
```

Then authorize the account in your browser:

```bash
agent-do strava connect
```

Approve the requested read-only activity access. A successful connection saves
the refresh token to the OS credential store, not to the profile JSON.

### Include private activities

`agent-do strava connect` requests `activity:read_all` in addition to the
standard read scope. This lets the local dashboard read activities whose
visibility is **Only Me**. If you connected before this scope was added, run
the command again and approve Strava's updated authorization screen:

```bash
agent-do strava connect
```

The command uses the same local callback and replaces only the secure local
refresh token. No activity data or credentials are added to the repository.

## Sync and view the dashboard

The first sync retrieves the recent 90 days of activities into the local cache:

```bash
agent-do strava sync
```

Start the responsive dashboard:

```bash
agent-do strava serve --open
```

Starting `serve` also performs one refresh by default. The dashboard then
updates only when you select a date range or click **Sync now**. To view the
existing cache without contacting Strava, use:

```bash
agent-do strava serve --no-sync --open
```

The dashboard displays imperial units (miles and feet) by default. Use the
**Units: Imperial** button to switch to metric; this saves the selected unit in
your local Strava profile configuration and does not alter the activity cache.

Use the **Activity** selector to view totals and recent sessions for an
individual Strava activity type—such as Ride, Run, Walk, Swim, or TrailRun.
The available choices come from your own synced activities.

Choose one of four ranges: **1 week**, **1 month** (the default), **3 months**,
or **1 year**. The header summarizes distance, moving time, elevation,
activity count, and average pace for runs and walks. With a cycling-only
filter, the pace summary instead shows average speed. It is hidden for sport
types that do not have a meaningful pace or speed measurement.

For ranges longer than one week, the dashboard charts distance and moving time
by week. Labels are thinned automatically for longer ranges so they remain
readable. The one-week view has no charts because its distance and moving-time
totals are already in the header. Recent activities are paginated ten at a
time. Drag a recent-activity table header edge to resize that column for the
current browser session. Click a recent activity to open its expanded summary.
That request fetches the selected activity's richer detail, route coordinates,
available analysis streams, splits, laps, efforts, segments, and zones on
demand; it is not bulk-saved into the activity cache. The route is drawn
locally without external map tiles.

## Where data lives

| Data | Location |
| --- | --- |
| Client secret and refresh token | OS secure credential store |
| Profile metadata, activity cache, and optional static dashboard | `~/.agent-do/strava/` |
| Tool code and documentation | the agent-do repository |

`agent-strava` never stages, commits, or pushes personal activity data. Avoid
setting `AGENT_DO_HOME` to a Git worktree; doing so would place the otherwise
local cache inside that directory.

## Troubleshooting

- **“No local Strava profile”**: run `agent-do strava init`.
- **Browser authorization fails**: confirm the Strava app callback domain is
  exactly `localhost`, then run `agent-do strava connect` again.
- **Startup sync is skipped**: run `agent-do strava status --json`; if the
  refresh token was revoked, reconnect with `agent-do strava connect`.
- **Use a different callback port**: pass `--redirect-uri
  http://localhost:PORT/callback` to `agent-do strava init`, and configure the
  same callback domain in Strava.
