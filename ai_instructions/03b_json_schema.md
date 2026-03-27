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

- `snapshot_version`: string, required
- `history`: object, required
- `trends_and_baselines`: object, required
- `decision`: object, required

## History Block

Fields:

- `current_week`: object, required
- `weekly_detailed_summary`: array of week objects, required
- `weekly_history_summary`: array of week summary objects, required

## Week Object

Used in:
- `history.current_week`
- `history.weekly_detailed_summary[]`
- `history.weekly_history_summary[]` (without `days`)

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
- `days`: array of day objects, required only in `history.current_week` and `history.weekly_detailed_summary[]`
- `is_partial`: boolean, required only in `history.current_week`

Semantics:

- `history.current_week.is_partial = true` means the week is incomplete and must not be compared directly to completed weeks as if it were a full week.
- `history.weekly_detailed_summary` and `history.weekly_history_summary` must not overlap.

## Day Object

Used in:
- `history.current_week.days[]`
- `history.weekly_detailed_summary[].days[]`

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
- `mood_score`: number | null, optional, expected range `1..4`, lower is better; canonical labels `1 = Extreme`, `2 = Good`, `3 = Avg`, `4 = Low`
- `motivation_score`: number | null, optional, expected range `1..4`, lower is better; canonical labels `1 = Extreme`, `2 = Good`, `3 = Avg`, `4 = Low`
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
- `session_rpe_load`: number | null, optional, subjective load units for that workout, usually `RPE × duration_min`
- `training_load`: number | null, optional
- `feel`: number | null, optional, same-session subjective state / feel score from Intervals, expected range `1..5`, lower is better; canonical labels `1 = Strong`, `2 = Good`, `3 = Normal`, `4 = Poor`, `5 = Weak`
- `power_load`: number | null, optional, power-derived load units for that workout
- `hr_load`: number | null, optional, heart-rate-derived load units for that workout
- `decoupling_pct`: number | null, optional, Pw:HR drift percent for the session
- `efficiency_factor`: number | null, optional, power-to-HR efficiency proxy for the session
- `variability_index`: number | null, optional, pacing variability proxy for the session
- `joules_above_ftp`: number | null, optional, work above FTP in joules
- `max_wbal_depletion`: number | null, optional, maximum modeled W'bal depletion value reported by Intervals
- `power_zone_times`: object | null, optional, seconds spent in power zones keyed like `z1..z7` and optionally `ss`
- `hr_zone_times`: object | null, optional, seconds spent in heart-rate zones keyed like `z1..z7`
- `session_class`: string | null, optional, backend-derived workout intent / class such as `endurance`, `sweet_spot`, `threshold`, `vo2`, `hiit`, `strength_lower`, `strength_upper`, `commute`, or `mixed`
- `is_commute_like`: boolean | null, optional, marks transport-like or incidental riding context
- `upper_zone_leakage_pct`: number | null, optional, percent of session time above easy-zone intent, mainly meaningful for endurance sessions
- `execution_verdict_precalc`: string | null, optional, backend-derived summary such as `controlled`, `expensive`, `failed`, or `strong_but_costly`
- `notes`: array of note objects, required, may be empty
- `sport_type_raw`: string | null, optional
- `source_device`: string | null, optional

Semantics:

- `if` is relative intensity, not load by itself.
- `ftp_reference` is the FTP value that the session-level intensity context was based on.
- `rpe` and `session_rpe_load` are different:
  - `rpe` = how hard the session felt
  - `session_rpe_load` = total subjective cost of the session
- `decoupling_pct` and `efficiency_factor` are most meaningful when compared across similar steady sessions, not as universal standalone thresholds.
- `power_zone_times` and `hr_zone_times` are session-structure fields. Use them to understand where the load came from, not just how large the total load was.
- `session_class` is the preferred primary workout-intent hint when present.
- `is_commute_like = true` means the workout should usually be treated as supporting load context, not as a key adaptation session by default.
- `upper_zone_leakage_pct` is mainly for endurance sessions and helps detect whether an `easy` ride drifted too high.
- `execution_verdict_precalc` is a backend summary of session execution quality. Prefer it over inventing a completely new session verdict from scratch when the field is present.
- Workout `notes` are post-session notes or extracted activity messages.

## Note Object

Used in:
- `week.notes[]`
- `day.notes[]`
- `workout.notes[]`

Fields:

- `title`: string | null, optional
- `text`: string | null, optional

Semantics:

- Notes at week, day, and workout level must always be read during analysis when present.
- Notes are contextual and explanatory signals, not primary objective measurements.
- Notes must not override objective metrics such as power, heart rate, fatigue, form, or modeled load by themselves.
- `workout.description` is usually free-form raw text about one session.
- `week.notes[]` may contain manually curated summaries, rules, or reminders that the athlete chose to preserve.
- Notes are especially useful for:
  - explaining anomalies in metrics or execution
  - identifying subjective strain, discomfort, failure, or unusual circumstances
  - extracting repeated patterns across multiple entries
- Prefer structured notes when available, especially sequences like `state -> work -> response -> result -> insight`.
- Repeated workout-description patterns may be generalized into temporary week-level or review-level rules during analysis, but these derived rules are not raw schema fields unless explicitly added elsewhere.
- Candidate rules inferred from `workout.description` are provisional until they are manually reflected in `week.notes[]` or repeatedly supported again by later notes plus metrics.
- `week.notes[]` should usually be treated as the higher-trust memory layer than one-off workout notes, but even curated notes still must not override clear objective metrics by themselves.

## Trends And Baselines Block

Fields:

- `current_trends`
- `personal_baselines`

## Current Trends

`trends_and_baselines.current_trends` is grouped by metric name.

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

`trends_and_baselines.personal_baselines` is grouped by metric name.

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

Not every metric uses every window.

Current practical examples in this project:

- `sleep_hours` commonly uses `3d / 7d / 14d / 28d`
- `hrv` and `rhr` commonly use `7d / 14d`
- `vo2max` commonly uses `7d / 28d`
- `form` commonly uses `3d / 7d`
- `fatigue`, `fitness`, `weight_kg`, `ride_eftp_*`, `run_eftp*` commonly use `7d / 28d`
- `mood_score` and `motivation_score` commonly use `7d / 14d`
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

## Data Provenance

- `sleep_hours`, `hrv_ms`, `vo2max`, `resting_hr_bpm`, `weight_kg`, `mood_score`, `motivation_score`:
  - imported from Intervals wellness data
  - mostly raw or directly reported by source integrations
- `fitness`, `fatigue`, `form`, `ramp_rate`:
  - modeled signals from Intervals
- `ride_eftp_watts`, `run_eftp`, `*_wkg`:
  - derived or modeled performance proxies from Intervals plus pipeline normalization
- `trends_and_baselines.current_trends`:
  - computed by this pipeline from daily stored data
- `trends_and_baselines.personal_baselines`:
  - computed by this pipeline from daily stored data
- `decision.inputs`, `decision.primary_state_support`, `decision.recovery_signals`, `decision.contradictions`, `decision.outcome.recommended_load_action`, `decision.outcome.confidence_precalc`:
  - computed by this pipeline from `trends_and_baselines.current_trends`, `trends_and_baselines.personal_baselines`, and current week context

## Decision Block

Fields:

- `inputs`
- `primary_state_support`
- `recovery_signals`
- `contradictions`
- `outcome`
- `context`
- `plan_adherence` optional

## Decision Inputs

`decision.inputs` is a discrete interpretation block.

Fields:

- `readiness_state`: string, required
- `fatigue_state`: string, required
- `form_zone`: string | null, optional
- `sleep_state`: string, required
- `subjective_state`: string, required
- `process_state`: string, required
- `data_quality_state`: string, required

### Allowed Values

`readiness_state`:

- `ready`
- `stable`
- `reduced`
- `poor`
- `insufficient_data`

`fatigue_state`:

- `low`
- `normal`
- `elevated`
- `high`
- `insufficient_data`

`form_zone`:

- `high risk`
- `optimal`
- `grey`
- `fresh`
- `transition`

`sleep_state`:

- `above_baseline`
- `near_baseline`
- `below_baseline`
- `well_below_baseline`
- `insufficient_data`

`subjective_state`:

- `supportive`
- `mixed`
- `strained`
- `insufficient_data`

`process_state`:

- `process_working_well`
- `process_working_but_constrained`
- `process_mixed_unstable`
- `process_showing_overload`
- `insufficient_data`

`data_quality_state`:

- `strong`
- `limited`
- `weak`

`confidence_precalc`:

- `high`
- `medium`
- `low`

## Contradictions

- `contradictions` is a grouped object with:
  - `physiology_conflicts`
  - `subjective_conflicts`
  - `performance_conflicts`
- each field is an array of string codes and may be empty
- typical codes include:
  - `poor_sleep_but_hrv_neutral`
  - `poor_sleep_but_rhr_neutral`
  - `good_mood_but_low_motivation`
  - `high_motivation_but_low_mood`
  - `good_subjective_but_elevated_load_signals`
  - `good_subjective_but_high_rpe_for_moderate_if`
  - `stable_capacity_but_reduced_readiness`
  - `stable_capacity_but_expensive_execution`

## Primary State Support

`decision.primary_state_support` is the highest-priority numeric support block for short-term readiness and load decisions.

It is grouped into:

- `sleep`
- `autonomic`
- `load_balance`
- `form`

Typical fields:

- `sleep.avg_7d`
- `sleep.delta_vs_28d`
- `sleep.delta_vs_90d`
- `sleep.coverage_pct_7d`
- `autonomic.hrv_avg_7d`
- `autonomic.hrv_delta_vs_14d`
- `autonomic.hrv_delta_vs_90d`
- `autonomic.hrv_coverage_pct_7d`
- `autonomic.rhr_avg_7d`
- `autonomic.rhr_delta_vs_14d`
- `autonomic.rhr_delta_vs_90d`
- `autonomic.rhr_coverage_pct_7d`
- `load_balance.fatigue_current`
- `load_balance.fitness_current`
- `load_balance.fatigue_gt_fitness`
- `load_balance.fatigue_avg_7d`
- `load_balance.fatigue_delta_vs_28d`
- `load_balance.fitness_avg_7d`
- `load_balance.fitness_delta_vs_28d`
- `form.current`
- `form.avg_3d`
- `form.avg_7d`
- `form.zone`

## Recovery Signals

`decision.recovery_signals` contains structured recovery-warning inputs.

It is grouped into:

- `primary`
- `amplifiers`

Typical fields:

- `primary.sleep_below_baseline`: boolean
- `primary.sleep_well_below_baseline`: boolean
- `primary.hrv_suppressed`: boolean
- `primary.rhr_elevated`: boolean
- `primary.fatigue_gt_fitness`: boolean
- `primary.fatigue_above_recent_norm`: boolean
- `primary.subjective_low`: boolean | null
- `primary.form_deeply_negative`: boolean | null
- `amplifiers.high_rpe_at_moderate_if`: boolean | null
- `amplifiers.recent_expensive_execution`: boolean | null
- `amplifiers.repeated_expensive_execution`: boolean | null
- `count_total`: integer
- `count_strong`: integer

## Capacity Context

`decision.context.capacity` is slower performance context and must not override short-term recovery by itself.

Fields:

- `capacity_metric`
- `avg_7d`
- `delta_vs_28d`
- `delta_vs_90d`
- `best_7d`

## Execution Context

`decision.context.execution` contains recent session-cost context and last-session execution summary.

Fields:

- `recent_workouts_with_execution_metrics`
- `expensive_sessions_14d`
- `steady_sessions_high_decoupling_14d`
- `hr_load_above_power_load_sessions_14d`
- `high_cost_sessions_14d`
- `expensive_sessions_current_week`
- `last_execution_session`
- `key_workout`

`last_execution_session` typical fields:

- `type`
- `expensive`
- `decoupling_pct`
- `if`
- `rpe`
- `feel`

`key_workout` typical fields:

- `date`
- `name`
- `type`
- `session_class`
- `execution_verdict`

## Subjective Context

`decision.context.subjective`

Fields:

- `mood_avg_7d`
- `motivation_avg_7d`
- `coverage_pct_7d`

## Weight Context

`decision.context.weight`

Fields:

- `avg_7d`
- `delta_vs_28d`
- `delta_vs_90d`
- `coverage_pct_7d`

## Plan Adherence

`decision.plan_adherence` describes how actual training matched the intended weekly template.

This block is optional and should be omitted unless the backend has an explicit plan source and real adherence logic. Do not infer adherence from a missing block.

Current fields:

- `week_type_expected`
- `expected_key_sessions`
- `completed_key_sessions`
- `missed_key_sessions`
- `substituted_key_sessions`
- `bike_sessions_completed`
- `strength_sessions_completed`
- `long_z2_completed`
- `adherence_score`
- `adherence_state`

`adherence_state`:

- `high`
- `acceptable`
- `low`
- `insufficient_data`

## Load Action Detail

`load_action_detail` provides operational detail for the discrete load decision.

Fields:

- `reduce_volume_pct`
- `reduce_intensity_pct`
- `avoid_session_types`
- `prefer_session_types`
- `lift_restriction`
- `session_complexity`
- `action_rationale_short`

`lift_restriction`:

- `none`
- `keep_submaximal`
- `avoid_heavy_lower`
- `skip_strength`

`session_complexity`:

- `normal`
- `simplify`
- `recovery_only`

## Recommended Load Action

`decision.outcome.recommended_load_action` must be exactly one of:

- `keep`
- `keep_but_simplify`
- `reduce_20_30`
- `recovery_day`
- `deload_week`
