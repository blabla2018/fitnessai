# Decision Rules

This file defines the discrete decision layer that sits between raw metrics and the final natural-language explanation.

The goal is to reduce free-form interpretation and make the final answer depend on explicit states, flags, and reason codes.

## Main Principle

- Prefer backend-derived states over open-ended interpretation.
- The AI should explain and prioritize the decision state, not recompute it from scratch.
- When multiple signals disagree, keep the contradiction explicit and lower confidence.

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
- `strained` when both recent subjective signals are clearly low

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

## Contradiction Handling

Treat these as important contradictions:

- `poor_sleep_but_hrv_neutral`
- `poor_sleep_but_rhr_neutral`
- `good_mood_but_low_motivation`
- `high_motivation_but_low_mood`
- `stable_capacity_but_reduced_readiness`
- `good_subjective_but_high_rpe_for_moderate_if`

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

Rules:

- prefer codes tied to an explicit metric and comparison window
- keep reason codes categorical and reusable across snapshots
- keep exact numeric payload in `decision_support`, not inside the code string
- do not emit vague codes like `recovery_bad`
- use reason codes as the primary evidence layer for the final explanation
