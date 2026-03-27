# JSON Structure

Use the exported JSON blocks like this:

- `history.current_week` = the current incomplete week. It uses the same structure as a normal week, but includes `is_partial = true`.
- `history.weekly_detailed_summary` = recent completed weeks with nested `days`.
- `history.weekly_history_summary` = longer weekly history without nested `days`, but still with weekly notes.
- `history.weekly_detailed_summary` and `history.weekly_history_summary` must not overlap. The history block starts only after the last week included in the detailed block.
- Each week may include:
  - `week_of_year` = ISO week number within the year
  - weekly summary metrics
  - `notes` = weekly notes, each note object contains only `title` and `text`
  - `days` = daily objects for that week
- Each day may include:
  - `day_of_week` = ISO weekday number inside the week, from `1` to `7`
  - `workouts_count` = number of workouts known for that day
  - sleep / weight / HRV / VO2max / RHR / mood / motivation / fitness / fatigue / form / ramp rate / FTP
  - `notes` = day notes, each note object contains only `title` and `text`
  - `workouts` = workouts performed on that date
- Each workout may include:
  - duration / power / NP / IF / FTP reference / HR / cadence
  - `rpe` and `session_rpe_load`
  - execution and cost fields such as `decoupling_pct`, `efficiency_factor`, `variability_index`, `power_load`, `hr_load`
  - session structure fields such as `power_zone_times` and `hr_zone_times`
  - high-intensity cost fields such as `joules_above_ftp` and `max_wbal_depletion`
  - subjective state field `feel`
  - intent/helper fields such as `session_class`, `is_commute_like`, `upper_zone_leakage_pct`, `execution_verdict_precalc`
  - `description` = workout-level free text, typically taken from the Intervals activity description
- `trends_and_baselines.current_trends` = short operational trend blocks grouped by metric, not by time window. Each metric may contain only the windows that are useful for interpretation, for example `3d / 7d / 14d / 28d`.
- Each `trends_and_baselines.current_trends` metric window may include:
  - `avg`
  - `n`
  - `coverage_pct`
  - `sd`
  - precomputed deltas such as `delta_vs_prev_window`, `delta_vs_28d`, `delta_vs_90d`
  - metric-specific helper fields such as `best` for FTP proxies or `zone_majority` for `form`
- Typical metric families in `current_trends` are:
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
  - optional subjective metrics such as `mood_score` and `motivation_score`
- Common current window patterns in this project currently look like:
  - `sleep_hours` -> `3d / 7d / 14d / 28d`
  - `hrv`, `rhr` -> `7d / 14d`
  - `vo2max` -> `7d / 28d`
  - `form` -> `3d / 7d`
  - `fatigue`, `fitness`, `weight_kg`, `ride_eftp_*`, `run_eftp*` -> `7d / 28d`
  - `mood_score`, `motivation_score` -> `7d / 14d`
- `trends_and_baselines.personal_baselines` = personal baseline blocks grouped by metric with only `90d` and `365d` windows.
- Typical metric families in `personal_baselines` are:
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
- Each long-term baseline window may include:
  - `avg`
  - `sd`
  - `typical_low`
  - `typical_high`
  - `n`
  - `coverage_pct`
  - performance-specific fields such as `best_30d`, `best_90d`, `best_365d`
- `snapshot_version` = version tag for the exported interpretation contract
- `decision.inputs` = discrete decision states derived from trends and baselines
- `decision.primary_state_support` = high-priority numeric support for short-term readiness and load decisions
- `decision.recovery_signals` = structured recovery-warning block with boolean inputs and counts
- `decision.contradictions` = grouped disagreement markers between important signals
- `decision.outcome.recommended_load_action` = discrete load decision chosen from a fixed rubric
- `decision.outcome.load_action_detail` = operational detail for how the recommended load change should be applied
- `decision.outcome.confidence_precalc` = backend-calculated decision confidence
- `decision.context.capacity` = slower performance context and the primary capacity metric
- `decision.context.execution` = recent session-cost and execution context
- `decision.context.subjective` = recent mood / motivation context
- `decision.context.weight` = recent body-mass context
- `decision.plan_adherence` = optional explicit process-vs-plan block when a real plan source and adherence logic are available

`decision.inputs` is the main structured state for downstream reasoning. Typical fields:

- `readiness_state`
- `fatigue_state`
- `form_zone`
- `sleep_state`
- `subjective_state`
- `process_state`
- `data_quality_state`

The decision layer should be treated as the preferred interpretation layer above raw metrics:

- `trends_and_baselines.current_trends` and `trends_and_baselines.personal_baselines` remain the numeric source of truth
- `decision.inputs`, `decision.primary_state_support`, and `decision.recovery_signals` are the main decision core
- `decision.context.capacity`, `decision.context.execution`, `decision.context.subjective`, and `decision.context.weight` are supporting context layers
- the final LLM answer should explain this state, not re-derive it freely

If `decision.context.capacity.capacity_metric` is present:

- use it as the primary capacity metric for the main capacity verdict
- use other capacity metrics only as secondary context or for explicit comparison
- do not let secondary capacity metrics override the primary capacity verdict unless the user explicitly asks for that comparison or the metrics clearly describe different domains

If the structure is incomplete:

- do not invent missing fields
- rely on available blocks
- explicitly say what is missing and how it lowers confidence
- `workouts_count` may be greater than the number of detailed workout objects in `workouts`; this is normal when the system knows a workout happened but does not have full session details via API
