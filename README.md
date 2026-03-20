# Fitness AI

Single-user training analytics app that pulls recovery, fitness-state, and note context from Intervals, stores it locally, and builds compact AI-ready snapshots for daily decision support.

Designed for:

- local-first development with SQLite
- read-only Intervals sync
- compact JSON + prompt export for LLM analysis
- a later path to GitHub + Google Cloud deployment

## What it does

- syncs daily wellness and fitness-state data from Intervals
- imports weekly notes and day notes
- stores the data in a local SQLite database
- builds compact snapshots for AI analysis
- exports a ready-to-paste prompt for manual LLM use

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
- single-athlete app config
- database initialization command
- sync run bookkeeping
- read-only Intervals wellness sync

Intervals is currently used for daily metrics and fitness-state data only.

- We ingest recovery, sleep, HR/HRV, readiness, CTL/ATL, ramp rate, steps, and eFTP-style fields.
- We also ingest Intervals `NOTES`, including weekly notes and day-specific notes.
- We do not rely on Intervals activities as workout truth because many workouts are Strava-sourced and incomplete via the Intervals API.

For manual AI experiments without an API key, export a compact snapshot and a ready-to-paste prompt:

```bash
python3 -m app.main export-snapshot
```

Recommended daily workflow:

```bash
python3 -m app.main daily-sync
python3 -m app.main export-snapshot
```

`daily-sync` re-syncs the last 3 days, which is safer than syncing only 1 day because Intervals values and notes can settle or update slightly after the first import.

Under the hood the incremental sync currently does:

- wellness sync for the last `N` days
- notes sync for the last `21` days
- weekly summary sync for the last `63` days

This keeps the daily sync small while still giving enough room for late updates and rolling trend calculations.

This writes:

- `data/current_snapshot.json`
- `data/current_prompt.txt`

Edit the prompt template here:

- `prompts/manual_analysis_prompt_template.txt`

Next step:

- connect the primary workout source separately
