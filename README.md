# Fitness AI

Single-user training analytics app that pulls recovery, fitness-state, and note context from Intervals, stores it locally, and builds compact AI-ready snapshots for daily decision support.

Designed for:

- local-first development with SQLite
- read-only Intervals sync
- compact dated metrics JSON export for LLM analysis
- a later path to GitHub + Google Cloud deployment

## What it does

- syncs daily wellness and fitness-state data from Intervals
- imports weekly notes and day notes
- stores the data in a local SQLite database
- builds compact metrics snapshots for AI analysis
- exports a dated `metrics_YYYY-MM-DD.json` file for AI analysis use

## Safety rule for Intervals

Intervals access is strictly read-only.

- Only `GET` requests are allowed when talking to the Intervals API.
- Never send `POST`, `PUT`, `PATCH`, or `DELETE` requests.
- Never modify workouts, athlete settings, notes, or any remote data in Intervals.
- Keep credentials out of committed source code and out of git history.
- Pass secrets through local environment variables only.

## Local setup

1. Create a virtual environment if you want:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Initialize the local SQLite database:

```bash
python3 -m app.main init-db
```

3. Show configured paths:

```bash
python3 -m app.main show-config
```

4. Export local Intervals credentials before running sync commands:

```bash
export INTERVALS_ATHLETE_ID="..."
export INTERVALS_API_KEY="..."
```

## Current status

Implemented:

- SQLite schema
- single-user local data model
- database initialization command
- sync run bookkeeping
- read-only Intervals wellness sync

Intervals is currently used for daily metrics and fitness-state data only.

- We ingest recovery, sleep, HR/HRV, readiness, CTL/ATL, ramp rate, steps, and eFTP-style fields.
- We also ingest Intervals `NOTES`, including weekly notes and day-specific notes.
- We do not rely on Intervals activities as workout truth because many workouts are Strava-sourced and incomplete via the Intervals API.

Export a dated metrics JSON for AI analysis use:

```bash
python3 -m app.main export-metrics
```

Recommended weekly workflow:

```bash
python3 -m app.main sync-last-week
python3 -m app.main export-metrics
```

`sync-last-week` re-syncs the last 7 days. This matches the weekly training cycle better than a 3-day window and is still small enough to keep incremental syncs fast and focused on recent changes.

Under the hood the incremental sync currently does:

- wellness sync for the last `N` days
- notes sync for the last `max(N, 7)` days
- weekly summary sync for the last `N` days
- activities sync for the last `N` days

This keeps the recurring sync focused on genuinely fresh data, while the long history stays in the local database after the initial backfill.

First-time setup for a new user:

```bash
python3 -m app.main sync-intervals --days 365
python3 -m app.main export-metrics
```

Why `365` on the first run:

- it backfills daily wellness data for one year
- it also backfills notes, weekly summaries, and activities for the same one-year range
- this gives enough history for `90d / 365d` daily baselines and long weekly trend context

After the initial backfill, switch to the normal recurring workflow with `sync-last-week`.

This writes:

- `data/metrics_YYYY-MM-DD.json`

Next step:

- connect the primary workout source separately
