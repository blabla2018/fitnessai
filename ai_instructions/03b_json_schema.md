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
- `current_week`: object, required
- `weekly_detailed_summary`: array of week objects, required
- `weekly_history_summary`: array of week summary objects, required
- `current_trends`: object, required
- `personal_baselines`: object, required
- `decision_inputs`: object, required
- `decision_flags`: array of strings, required, may be empty
- `reason_codes`: array of strings, required, may be empty
- `contradictions`: array of strings, required, may be empty
- `decision_support`: object, required
- `recovery_signals`: object, required
- `plan_adherence`: object, optional
- `load_action_detail`: object, required
- `decision_debug`: object, required
- `recommended_load_action`: string, required
- `confidence_precalc`: string, required

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
- `session_rpe_load`: number | null, optional, subjective load units for that workout, usually `RPE × duration_min`
- `training_load`: number | null, optional
- `feel`: number | null, optional, same-session subjective state / feel score from Intervals
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
- `workout.notes[]` are usually free-form raw observations about one session.
- `week.notes[]` may contain manually curated summaries, rules, or reminders that the athlete chose to preserve.
- Notes are especially useful for:
  - explaining anomalies in metrics or execution
  - identifying subjective strain, discomfort, failure, or unusual circumstances
  - extracting repeated patterns across multiple entries
- Prefer structured notes when available, especially sequences like `state -> work -> response -> result -> insight`.
- Repeated workout-note patterns may be generalized into temporary week-level or review-level rules during analysis, but these derived rules are not raw schema fields unless explicitly added elsewhere.
- Candidate rules inferred from `workout.notes[]` are provisional until they are manually reflected in `week.notes[]` or repeatedly supported again by later notes plus metrics.
- `week.notes[]` should usually be treated as the higher-trust memory layer than one-off workout notes, but even curated notes still must not override clear objective metrics by themselves.

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
- `decision_inputs`, `decision_flags`, `reason_codes`, `contradictions`, `recommended_load_action`, `confidence_precalc`:
  - computed by this pipeline from `current_trends`, `personal_baselines`, and current week context

## Decision Inputs

`decision_inputs` is a discrete interpretation block.

Fields:

- `readiness_state`: string, required
- `fatigue_state`: string, required
- `fitness_state`: string, required
- `capacity_state`: string, required
- `form_zone`: string | null, optional
- `sleep_state`: string, required
- `weight_state`: string, required
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

`fitness_state`:

- `rising`
- `stable`
- `falling`
- `insufficient_data`

`capacity_state`:

- `improving`
- `stable`
- `drifting_down`
- `clearly_down`
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

`weight_state`:

- `stable`
- `drifting_up`
- `drifting_down`
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

## Decision Flags, Reason Codes, Contradictions

- `decision_flags`: discrete fact flags interpreted by backend rules
- `reason_codes`: compact evidence codes intended for explanation and evaluation
- `contradictions`: important disagreement markers between signals

Each item is a string code such as:

- `sleep_7d_below_28d`
- `fatigue_gt_fitness`
- `form_in_optimal_zone`
- `expensive_execution_14d_present`
- `repeated_expensive_execution`
- `stable_capacity_with_reduced_readiness`
- `good_subjective_but_elevated_load_signals`
- `good_subjective_but_high_rpe_for_moderate_if`
- `poor_sleep_but_hrv_neutral`

## Decision Support

`decision_support` is the numeric support block for the decision layer.

Typical fields:

- `sleep_7d_avg`
- `sleep_delta_vs_28d`
- `sleep_delta_vs_90d`
- `sleep_7d_coverage_pct`
- `hrv_7d_avg`
- `hrv_delta_vs_14d`
- `hrv_delta_vs_90d`
- `rhr_7d_avg`
- `rhr_delta_vs_14d`
- `rhr_delta_vs_90d`
- `fatigue_7d_avg`
- `fatigue_delta_vs_28d`
- `fitness_7d_avg`
- `fitness_delta_vs_28d`
- `fatigue_current`
- `fitness_current`
- `form_current`
- `form_3d_avg`
- `form_7d_avg`
- `form_zone`
- `capacity_metric`
- `capacity_metric_group`
- `capacity_source_priority`
- `capacity_7d_avg`
- `capacity_delta_vs_28d`
- `capacity_delta_vs_90d`
- `capacity_7d_best`
- `weight_7d_avg`
- `weight_delta_vs_28d`
- `weight_delta_vs_90d`
- `weight_7d_coverage_pct`
- `mood_7d_avg`
- `motivation_7d_avg`
- `subjective_7d_coverage_pct`
- `last_execution_session_expensive`
- `last_execution_session_type`
- `last_execution_session_decoupling_pct`
- `last_execution_session_if`
- `last_execution_session_rpe`
- `last_execution_session_feel`

## Recovery Signals

`recovery_signals` contains structured recovery-warning inputs.

Typical fields:

- `sleep_below_baseline`: boolean
- `sleep_well_below_baseline`: boolean
- `hrv_suppressed`: boolean
- `rhr_elevated`: boolean
- `fatigue_gt_fitness`: boolean
- `fatigue_above_recent_norm`: boolean
- `subjective_low`: boolean | null
- `form_deeply_negative`: boolean | null
- `high_rpe_at_moderate_if`: boolean | null
- `count_total`: integer
- `count_strong`: integer

## Plan Adherence

`plan_adherence` describes how actual training matched the intended weekly template.

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

- `primary`
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

## Decision Debug

`decision_debug` is a compact debug block for tracing the engine decision.

Fields:

- `load_decision_trigger`
- `load_decision_overridden_by`
- `confidence_downgraded_by_contradictions`
- `sleep_state_rule`
- `subjective_state_rule`
- `recovery_day_rule`

## Recommended Load Action

`recommended_load_action` must be exactly one of:

- `keep`
- `keep_but_simplify`
- `reduce_20_30`
- `recovery_day`
- `deload_week`
