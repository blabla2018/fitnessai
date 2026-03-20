# Intervals Ingestion Plan

## Goal

Build the first project stage: regularly ingest training and recovery data from Intervals into a local database that is easy to analyze and pass to an AI recommendation layer.

## What To Collect

Collect data in four groups.

### 1. Athlete daily state

One row per day.

- date
- body weight
- sleep duration
- sleep score if available
- resting heart rate
- HRV if available
- mood / subjective readiness
- perceived fatigue
- muscle soreness
- stress / motivation if you track it manually

This table is the backbone for recovery analysis and daily recommendations.

Also collect Intervals-specific readiness and fitness state fields when present:

- readiness score
- average sleeping HR
- HRV SDNN
- SpO2
- respiration
- steps
- CTL
- ATL
- ramp rate
- CTL load
- ATL load
- ride eFTP
- run eFTP
- swim eFTP

### 2. Notes

Import Intervals calendar notes through the events API with `category=NOTE`.

Store both:

- weekly notes (`for_week=true`)
- day-specific notes (`for_week=false` or omitted)

Notes are valuable because they capture context not present in metrics:

- subjective response to workouts
- illness / travel / recovery context
- comments on motivation and fatigue
- weekly summaries in your own words
### 3. Intervals fitness state

Intervals is the source of daily recovery and fitness state, not the source of workout truth.

Reason:

- many workouts are synced from Strava
- Intervals API may not expose full activity details for Strava-sourced sessions
- workout truth should come from the original source system later

So for the Intervals integration we prioritize:

- daily readiness and recovery markers
- fitness / fatigue model outputs
- trend metrics like CTL, ATL, ramp rate, and eFTP

### 4. Daily aggregates for analysis

One row per day.

- total load proxy from Intervals wellness
- CTL / ATL trend
- readiness trend
- sleep trend
- HR / HRV trend

These values can be materialized after ingestion and make downstream analytics much simpler.

## Sync Strategy

Use two sync modes.

### Initial backfill

Backfill at least the last 365 days.

Why:

- enough history for seasonality and baseline calculations
- enough context for recovery vs load trends
- enough training examples for future recommendation logic

If API limits are easy to handle, backfill 730 days.

### Incremental sync

Run once per day as the default schedule.

Recommended schedule:

- daily sync at 05:00-06:00 local time

Why daily is enough for MVP:

- sleep, resting metrics, and subjective wellbeing mostly update once per day
- recommendations are usually made once per day or before the next session
- simpler, cheaper, and more robust than near-real-time ingestion

Optional future improvement:

- second sync at 13:00 or 14:00 for same-day workout updates

### Sync window

For each daily run:

- re-fetch the last 14 days of daily metrics
- re-fetch the last 30 days of notes

Why:

- wearable platforms may revise sleep or body metrics late
- this avoids complicated change-tracking in MVP

Use upsert semantics rather than append-only ingestion.

## Recommended Time Horizons For Analysis

Use these windows from the start.

- `7 days`: short-term fatigue / freshness
- `28 days`: current training block
- `42 days`: rolling load baseline
- `90 days`: medium-term progress
- `365 days`: seasonality and long-term trend

These windows are enough for the first recommendation engine.

## Storage Format

Use a relational database plus raw JSON snapshots.

### Canonical storage

Preferred for MVP:

- SQLite if this stays local and single-user
- PostgreSQL if you already expect a web app or remote deployment

### Why relational first

- easy filtering by date ranges
- easy joins between workouts and recovery markers
- easy feature generation for AI prompts or ML
- much cleaner than storing everything as nested JSON

### Also store raw payloads

For every imported entity, keep the original API payload in a `raw_json` column.

Why:

- easier debugging
- safe schema evolution
- ability to expose new metrics later without re-importing everything

## Data Model Principles

- Keep one source of truth per concept.
- Intervals is the source of daily state and fitness-state metrics.
- Workouts should come from the original workout source later, not from Intervals.
- Store timestamps in UTC.
- Store local date separately for daily metrics.
- Use source ids from Intervals as external ids.
- Use upserts on `(source, external_id)` or `(athlete_id, metric_date)`.
- Keep units explicit when values may vary.

## What AI Will Need Later

Prepare data so it can be turned into features like:

- acute load
- chronic load
- load ramp rate
- sleep trend
- resting HR deviation from baseline
- HRV deviation from baseline
- readiness trend
- workout compliance
- discipline mix
- hard days in the last 7 days

This is why normalized relational storage matters more than “AI-friendly JSON”.

## MVP Recommendation

Start with these tables only:

- `athlete_metrics_daily`
- `intervals_notes`
- `sync_runs`

That is enough to build:

- ingestion
- basic dashboard
- first recovery/load heuristics
- first AI summary prompt
