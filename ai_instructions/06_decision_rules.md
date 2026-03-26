# Decision Rules

This file defines the discrete decision layer that sits between raw metrics and the final natural-language explanation.

The goal is to reduce free-form interpretation and make the final answer depend on explicit states, flags, and reason codes.

These rules are app-level interpretation heuristics layered on top of Intervals data. They are not official Intervals thresholds unless explicitly stated.

## Main Principle

- Prefer backend-derived states over open-ended interpretation.
- The AI should explain and prioritize the decision state, not recompute it from scratch.
- When multiple signals disagree, keep the contradiction explicit and lower confidence.
- Match the level of structure to the user's intent: status, review, explanation, source-trace, prescription, forecast, or direct answer.

## Required Decision Outputs

Use the precomputed decision layer when available:

- `decision_inputs`
- `decision_flags`
- `reason_codes`
- `contradictions`
- `decision_support`
- `recovery_signals`
- `decision_debug`
- `recommended_load_action`
- `confidence_precalc`

If one of these blocks is missing, fall back to the lower-level metrics and say that the decision layer is incomplete.

Reporting rule:

- `decision_flags`, `reason_codes`, and `recommended_load_action` are internal interpretation handles, not user-facing phrasing by default.
- In a normal report, translate them into plain language rather than echoing the raw code.
- Only expose the raw technical code when the user explicitly asks for internals, debugging, or the exact field value.

## State Definitions

### Readiness State

Allowed values:

- `ready`
- `stable`
- `reduced`
- `poor`
- `insufficient_data`

Interpretation:

- `ready` = recovery signals are supportive, load is manageable, no major contradiction
- `stable` = no clear problem, but no strong positive support either
- `reduced` = training is still possible, but caution is justified
- `poor` = strong recovery warning, recovery-first decision is more appropriate

### Fatigue State

Allowed values:

- `low`
- `normal`
- `elevated`
- `high`
- `insufficient_data`

Interpretation:

- `elevated` = fatigue is meaningfully above the athlete's recent norm
- `high` = fatigue is clearly elevated and usually aligned with negative short-term recovery signs

### Fitness State

Allowed values:

- `rising`
- `stable`
- `falling`
- `insufficient_data`

### Capacity State

Allowed values:

- `improving`
- `stable`
- `drifting_down`
- `clearly_down`
- `insufficient_data`

`capacity_state` refers to the performance proxy layer such as `ride_eftp_*` or `run_eftp_*`, not to today's readiness.

### Sleep State

Allowed values:

- `above_baseline`
- `near_baseline`
- `below_baseline`
- `well_below_baseline`
- `insufficient_data`

Suggested thresholds:

- `well_below_baseline` only when `7d` sleep is below `90d typical_low`, or when `delta_vs_90d <= -0.8 h`
- `below_baseline` when sleep is below `90d avg` or clearly below recent `28d` context
- do not use `well_below_baseline` only because sleep is modestly below `90d avg`

### Weight State

Allowed values:

- `stable`
- `drifting_up`
- `drifting_down`
- `insufficient_data`

### Subjective State

Allowed values:

- `supportive`
- `mixed`
- `strained`
- `insufficient_data`

Suggested thresholds:

- `insufficient_data` when recent subjective coverage is below about `50%`
- `mixed` when coverage is usable and `mood` / `motivation` conflict is visible
- `strained` when both recent subjective signals are clearly poor

### Process State

Allowed values:

- `process_working_well`
- `process_working_but_constrained`
- `process_mixed_unstable`
- `process_showing_overload`
- `insufficient_data`

## Load Decision Rubric

Choose exactly one:

- `keep`
- `keep_but_simplify`
- `reduce_20_30`
- `recovery_day`
- `deload_week`

Decision guidance:

- `recovery_day` when 2 or more strong recovery warnings align on the current day or in the immediate short window
- `recovery_day` is also reasonable when `fatigue_state = high` and total recovery warnings are already clustered
- `reduce_20_30` when fatigue is elevated or high and readiness is reduced, even if capacity is still stable
- `keep_but_simplify` when physiology is mostly neutral but subjective cost or contradiction risk is meaningful
- `keep` when recovery, form, and execution context are aligned and no major warning is present
- `deload_week` when repeated overload signs persist at the weekly-process level rather than only in today's state
- repeated expensive sessions support `keep_but_simplify`, `reduce_20_30`, or `deload_week` depending on how persistent and how aligned the overload signals are

User-facing translation principle:

- translate a load action code into practical advice, not into the raw code string
- example:
  - not `recommended_load_action = reduce_20_30`
  - but `it is reasonable to reduce load by about 20-30% now to absorb the accumulated cost and restore higher-quality recovery`

## Signal Priority

For short-term load decisions, trust signals in this order:

1. sleep + HRV/RHR + immediate subjective state
2. form + fatigue balance
3. recent execution context and notes
4. fitness trend
5. capacity / FTP trend
6. weight trend

Priority rules:

- Readiness can be reduced even when capacity is stable.
- Stable or improving capacity must not override poor recovery.
- Weight trend is supporting context, not a primary load signal.
- VO2max is slow context, not a same-day decision driver.
- Expensive execution can reduce confidence in an apparently neutral or positive capacity read.

## Explanation and Provenance Rules

For metric explanation questions:

- define the metric first, interpret second
- distinguish session-level metrics from state-level metrics and from long-term capacity metrics
- if two metrics look similar, explain the difference in role, timescale, and source rather than saying they are simply duplicates

For source-trace questions:

- identify the exact block and field when possible
- state whether the value is raw, aggregated, baseline-derived, or backend-derived
- if the answer used a trend average instead of a daily raw point, say that explicitly
- if the value comes from a proxy or derived layer, do not describe it as a directly measured fact

## Prescription Rules

When the user asks what to do next:

- prefer the training plan context and current state over a generic motivational answer
- prefer target ranges over false precision
- prefer `% FTP` framing when the plan is written that way, and translate to watts as a convenience layer when a practical reference is available
- if short-term readiness is reduced, simplify before you increase
- if the basis is uncertain, say so and give a conservative range

## Forecast Rules

When the user asks for recovery time or near-term outlook:

- provide a bounded estimate, not a promise
- state the confidence and the main uncertainty
- base the estimate on aligned short-term signals first: sleep, HRV/RHR, fatigue, form, recent session cost
- do not imply day-level precision that the data cannot support
- when evidence is weak, answer with scenarios rather than a single timeline

## Note-Derived Pattern Rules

Workout notes may be aggregated into reusable athlete-specific rules, but only cautiously.

Human-in-the-loop policy:

- Treat `workout notes` as free-form raw observations, not as a stored rules database.
- Treat note-derived patterns from workout notes as provisional candidate rules.
- Treat `week notes` as the curated memory layer because the athlete manually decides what to carry forward there.
- Do not behave as if a candidate rule is saved or persistent unless it is actually present in `week notes` or strongly repeated again across later workouts with objective support.

Extraction rules:

- treat workout notes as free text, not as a reliable structured form
- only when the text clearly states them, use soft note-level elements such as:
  - state or recovery context
  - intended work
  - observed response
  - outcome
  - explicit insight
- treat these elements as supportive interpretation, not as parsed raw truth

Pattern-building rules:

- if similar patterns appear `>= 2-3` times, they may be generalized
- generalize narrow numeric points into practical ranges
- prefer rule format: `condition -> outcome -> recommendation`
- do not generate a rule from a single outlier workout unless objective metrics strongly support it
- when such a rule is not already present in `week notes`, label it as a candidate for manual carry-over rather than as established athlete memory

Conflict handling:

- if note-derived patterns contradict each other, keep both
- mark them as `unstable` or `needs more data`
- lower confidence in the resulting recommendation
- if `week notes` disagree with fresh workout-note candidates, keep both visible and prefer `week notes` as the memory layer unless objective metrics clearly argue otherwise

Confidence guide:

- `1` occurrence = `low`
- `2-3` occurrences = `medium`
- `4+` occurrences = `high`

Use note-derived rules mainly for:

- athlete-specific power guidance under different fatigue states
- identifying what work is controllable vs too costly
- strengthening recommendations with repeated personal evidence

Use curated week-note rules for:

- carrying athlete-specific learning across weeks
- stabilizing recommendations when the same pattern keeps reappearing
- explaining why a similar recommendation is being repeated again

## Expensive Session Rules

A workout may be treated as `expensive` when 2 or more of the following align:

- high `decoupling_pct` for an intended steady / endurance session
- `hr_load` materially above `power_load`
- high effective exertion at only moderate / easy `if`
  Use direct `rpe` when present, or estimate it from `session_rpe_load / duration_min` when direct `rpe` is missing.
- high `variability_index` for an intended steady / controlled session
- poor or weak `feel` as supporting context together with another cost signal
- notes indicating unusual struggle, unusually high heart rate, or inability to hold target structure

Guidance:

- treat `materially above` as both `>= 10 load units` and `>= 15%` higher
- do not treat `session_rpe_load` as a standalone absolute trigger without duration context
- do not treat poor or weak `feel` alone as enough to call a session expensive
- one expensive session is a caution signal, not automatic overload
- repeated expensive sessions support `process_working_but_constrained` or `process_showing_overload`
- an expensive long ride or expensive key workout can justify simplifying the next key session
- if execution cost is repeatedly high while capacity is only stable, do not describe the process as clearly working well

## Workout Review Verdicts

When the user asks about training usefulness, block quality, or one workout, produce explicit review verdicts in natural language.

Use these categories:

- `useful`
- `useful_but_costly`
- `neutral`
- `mistimed`
- `missed_target`

Interpret them this way:

- `useful` = likely delivered the intended stimulus at acceptable cost for the current state
- `useful_but_costly` = likely delivered the intended stimulus, but cost was materially high
- `neutral` = added some context or maintenance value, but not a strong targeted stimulus
- `mistimed` = the session may have been good in itself, but the athlete's short-term state suggests it came at the wrong time
- `missed_target` = the session execution or structure did not match the likely intended purpose

Practical rules:

- Do not treat `execution_verdict_precalc` as identical to usefulness. Execution quality and usefulness are related, but not the same.
- A workout can be well executed yet still be `mistimed`.
- A workout can be `useful_but_costly` when the stimulus was achieved but cost was clearly elevated.
- A commute-like or incidental session is usually `neutral` unless the user explicitly asks to treat it as a meaningful training stimulus.
- For strength sessions, judge usefulness from `rpe`, `session_rpe_load`, `feel`, notes, and next-day interaction, not from cycling execution metrics.

Timeliness guidance:

- `timely` when readiness is at least stable enough for the session type and the cost is controlled
- `borderline_timed` when readiness is reduced but the session remained manageable
- `mistimed` when readiness was reduced or poor and the session also looked expensive, overly stochastic, or unusually costly

## Workout-Type-Specific Decision Use

Use execution signals in context:

- for steady / endurance sessions, prioritize `decoupling_pct`, `efficiency_factor`, `variability_index`, `hr_load` vs `power_load`, and zone leakage above intended intensity
- for threshold / sweet-spot sessions, prioritize target-zone time, `rpe`, `feel`, and whether output matched intended structure at acceptable cost
- for VO2 / HIIT sessions, prioritize `z5+` time, `joules_above_ftp`, `max_wbal_depletion`, `variability_index`, `rpe`, and `feel`

Do not use `joules_above_ftp`, `max_wbal_depletion`, or `decoupling_pct` in isolation without considering session type.

## Contradiction Handling

Treat these as important contradictions:

- `poor_sleep_but_hrv_neutral`
- `poor_sleep_but_rhr_neutral`
- `good_mood_but_low_motivation`
- `high_motivation_but_low_mood`
- `stable_capacity_but_reduced_readiness`
- `good_subjective_but_elevated_load_signals`
- `good_subjective_but_high_rpe_for_moderate_if`

Use the mood / motivation contradiction codes only when the 7-day averages show a clear split, not when one side is merely average.

When contradictions exist:

- keep both signals visible
- prefer the more decision-relevant short-term signal
- lower confidence by at least one level when the contradiction is meaningful and unresolved

## Confidence Rubric

Allowed values:

- `high`
- `medium`
- `low`

Suggested interpretation:

- `high` = strong coverage and multiple aligned signals
- `medium` = usable state with some contradiction, partial coverage, or limited evidence
- `low` = weak coverage, insufficient recent points, or unresolved disagreement among important signals

## Reason Codes

Use compact, reusable fact codes rather than narrative explanations.

Typical examples:

- `sleep_7d_below_28d`
- `sleep_7d_below_90d_typical_low`
- `hrv_7d_suppressed_vs_90d`
- `rhr_7d_elevated_vs_90d`
- `fatigue_7d_above_28d`
- `fatigue_gt_fitness`
- `form_in_high_risk_zone`
- `form_in_optimal_zone`
- `ride_eftp_7d_stable_vs_28d`
- `ride_eftp_7d_down_vs_90d`
- `weight_7d_up_vs_28d`
- `subjective_state_strained`
- `expensive_execution_14d_present`
- `repeated_expensive_execution`
- `high_rpe_at_moderate_if`
- `hr_load_above_power_load`
- `session_cost_high_for_output`

Rules:

- prefer codes tied to an explicit metric and comparison window
- keep reason codes categorical and reusable across snapshots
- keep exact numeric payload in `decision_support`, not inside the code string
- do not emit vague codes like `recovery_bad`
- use reason codes as the primary evidence layer for the final explanation
