# JSON Field Contract

This file defines the technical JSON contract used by the AI.

Rules:

- Unless stated otherwise, missing fields mean `not available` and must not be invented.
- Numbers are JSON numbers, not strings.
- Dates use ISO format `YYYY-MM-DD`.
- `coverage_pct` is always `0..100`.
- `n` is always the number of valid non-null observations actually used in that aggregation.
- Unless stated otherwise, `delta_vs_*` fields are absolute differences, not percentages.
- `typical_low` / `typical_high` are currently defined as `avg ± sd`.

## Top-Level Blocks

- `current_week`: object, required
- `weekly_detailed_summary`: array of week objects, required
- `weekly_history_summary`: array of week summary objects, required
- `current_trends`: object, required
- `personal_baselines`: object, required

## Week Object

Used in:
- `current_week`
- `weekly_detailed_summary[]`
- `weekly_history_summary[]` (without `days`)

Fields:

- `week_start_date`: string, required, ISO date, Monday of the week
- `week_of_year`: integer, required, range `1..53`, ISO week number
- `workouts_count`: integer | null, optional, count of workouts known for that week
- `distance_km`: number | null, optional, kilometers
- `elevation_gain_m`: number | null, optional, meters
- `calories_kcal`: number | null, optional, kilocalories
- `training_load`: number | null, optional, modeled load units from Intervals
- `session_rpe_load`: number | null, optional, subjective load units
- `fitness`: number | null, optional, modeled signal from Intervals
- `fatigue`: number | null, optional, modeled signal from Intervals
- `form`: number | null, optional, modeled signal from Intervals
- `ramp_rate`: number | null, optional
- `weight_kg_end`: number | null, optional, kilograms
- `ride_eftp_watts`: number | null, optional, watts
- `ride_eftp_wkg`: number | null, optional, watts per kilogram
- `run_eftp`: number | null, optional, running performance proxy
- `run_eftp_wkg`: number | null, optional, running performance proxy per kilogram
- `notes`: array of note objects, required, may be empty
- `days`: array of day objects, required only in `current_week` and `weekly_detailed_summary[]`
- `is_partial`: boolean, required only in `current_week`

Semantics:

- `current_week.is_partial = true` means the week is incomplete and must not be compared directly to completed weeks as if it were a full week.
- `weekly_detailed_summary` and `weekly_history_summary` must not overlap.

## Day Object

Used in:
- `current_week.days[]`
- `weekly_detailed_summary[].days[]`

Fields:

- `date`: string, required, ISO date
- `day_of_week`: integer, required, range `1..7`, ISO weekday inside the week
- `workouts_count`: integer, required, count of workouts known for that day
- `sleep_hours`: number | null, optional, hours
- `sleep_score`: number | null, optional
- `sleep_quality_score`: number | null, optional
- `weight_kg`: number | null, optional, kilograms
- `hrv_ms`: number | null, optional, milliseconds
- `vo2max`: number | null, optional
- `resting_hr_bpm`: number | null, optional, bpm
- `mood_score`: number | null, optional, expected range `1..4`
- `motivation_score`: number | null, optional, expected range `1..4`
- `fitness`: number | null, optional
- `fatigue`: number | null, optional
- `form`: number | null, optional
- `ramp_rate`: number | null, optional
- `ride_eftp_watts`: number | null, optional, watts
- `ride_eftp_wkg`: number | null, optional, watts/kg
- `run_eftp`: number | null, optional
- `run_eftp_wkg`: number | null, optional
- `notes`: array of note objects, required, may be empty
- `workouts`: array of workout objects, required, may be empty

Semantics:

- `workouts_count` may be greater than `len(workouts)`. This means the system knows workouts happened on that date, but does not have full workout details via API.
- Missing daily fields mean the source did not provide a usable value for that date.

## Workout Object

Used in:
- `day.workouts[]`

Fields:

- `type`: string | null, optional
- `name`: string | null, optional
- `duration_min`: number | null, optional, minutes
- `power_avg`: number | null, optional, watts
- `power_np`: number | null, optional, watts
- `if`: number | null, optional, ratio
- `ftp_reference`: number | null, optional, watts
- `hr_avg`: number | null, optional, bpm
- `hr_max`: number | null, optional, bpm
- `cadence_avg`: number | null, optional, rpm
- `rpe`: number | null, optional
- `training_load`: number | null, optional
- `notes`: array of note objects, required, may be empty
- `sport_type_raw`: string | null, optional
- `source_device`: string | null, optional

Semantics:

- `if` is relative intensity, not load by itself.
- `ftp_reference` is the FTP value that the session-level intensity context was based on.
- Workout `notes` are post-session notes or extracted activity messages.

## Note Object

Used in:
- `week.notes[]`
- `day.notes[]`
- `workout.notes[]`

Fields:

- `title`: string | null, optional
- `text`: string | null, optional

## Current Trends

`current_trends` is grouped by metric name.

Typical metric keys:

- `sleep_hours`
- `hrv`
- `vo2max`
- `rhr`
- `form`
- `fatigue`
- `fitness`
- `weight_kg`
- `ride_eftp_watts`
- `ride_eftp_wkg`
- `run_eftp`
- `run_eftp_wkg`
- `mood_score`
- `motivation_score`

Each metric contains one or more window objects such as:

- `3d`
- `7d`
- `14d`
- `28d`

### Trend Window Object

Fields:

- `avg`: number | null, optional
- `n`: integer, required
- `coverage_pct`: integer, required, range `0..100`
- `sd`: number | null, optional
- `delta_vs_prev_window`: number | null, optional, absolute delta
- `delta_vs_7d`: number | null, optional, absolute delta
- `delta_vs_14d`: number | null, optional, absolute delta
- `delta_vs_28d`: number | null, optional, absolute delta
- `delta_vs_90d`: number | null, optional, absolute delta
- `zone_majority`: string | null, optional, only meaningful for `form`
- `best`: number | null, optional, only meaningful for performance proxies

Aggregation rules:

- `avg` uses all valid non-null values within the window.
- `sd` is standard deviation over valid non-null values.
- `best` is the maximum valid value within that same window.
- `coverage_pct = round(100 * n / window_size_days)`.
- Windows are calendar lookback windows ending on the current metric date and include the current day.

## Personal Baselines

`personal_baselines` is grouped by metric name.

Typical metric keys:

- `sleep_hours`
- `hrv`
- `vo2max`
- `rhr`
- `form`
- `fatigue`
- `fitness`
- `weight_kg`
- `ride_eftp_watts`
- `ride_eftp_wkg`
- `run_eftp`
- `run_eftp_wkg`

Each metric contains one or more baseline windows:

- `90d`
- `365d`

### Baseline Window Object

Fields:

- `avg`: number | null, optional
- `sd`: number | null, optional
- `typical_low`: number | null, optional
- `typical_high`: number | null, optional
- `n`: integer, required
- `coverage_pct`: integer, required, range `0..100`
- `best_30d`: number | null, optional, performance proxies only
- `best_90d`: number | null, optional, performance proxies only
- `best_365d`: number | null, optional, performance proxies only

Aggregation rules:

- `avg` uses all valid non-null values within that baseline window.
- `sd` is standard deviation over valid non-null values.
- `typical_low = avg - sd`
- `typical_high = avg + sd`
- `coverage_pct = round(100 * n / window_size_days)`
- `best_*` fields are maximum valid values over the named lookback window.

## Source Semantics

- `sleep_hours`, `hrv_ms`, `vo2max`, `resting_hr_bpm`, `weight_kg`, `mood_score`, `motivation_score`:
  - imported from Intervals wellness data
  - mostly raw or directly reported by source integrations
- `fitness`, `fatigue`, `form`, `ramp_rate`:
  - modeled signals from Intervals
- `ride_eftp_watts`, `run_eftp`, `*_wkg`:
  - derived or modeled performance proxies from Intervals plus pipeline normalization
- `current_trends`:
  - computed by this pipeline from daily stored data
- `personal_baselines`:
  - computed by this pipeline from daily stored data
