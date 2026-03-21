# JSON Structure

Use the JSON blocks like this:

- `current_snapshot` = current state on the analysis date. Main source for current values.
- `daily_series` = recent daily series for sleep, HRV, RHR, weight, form, and FTP. Use for short-term trends and stability.
- `fitness_model_series` = daily series for `fitness`, `fatigue`, `form`, `ramp_rate`.
- `subjective_series.series` = actually populated manual subjective scales, currently mainly `mood_score` and `motivation_score`.
- `subjective_series.missing_in_source` = subjective fields missing in the source.
- `weekly_series` = main weekly series: workouts count, distance, elevation, calories, training load, weekly fitness/fatigue/form, weight, FTP, session RPE load.
- `weekly_derived` = precomputed comparison of current week vs previous week and vs 4-week baseline.
- `trends` = aggregated windows `3d / 7d / 14d / 28d` with averages and coverage.
- `long_term_baselines` = long baseline windows `90d / 365d / 12w / 52w`.
- `notes_context` = short context from the latest relevant notes.
- `interpretation_hints` = helper computed features. Use only as support, not as a replacement for main data.

If the structure is incomplete:

- do not invent missing fields
- rely on available blocks
- explicitly say what is missing and how it lowers confidence
