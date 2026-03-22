# JSON Structure

Use the JSON blocks like this:

- `current_snapshot` = current state on the analysis date. Main source for current values.
- `daily_records` = recent daily records with sleep, weight, HRV, RHR, subjective scores, fitness/fatigue/form, ramp rate, and FTP fields combined per date. Use this as the main short-term daily context block.
- `individual_sessions_recent` = individual activity sessions from Intervals for the last 6 weeks. Use them for session-level context such as duration, power, NP, IF, HR, cadence, RPE, session note, and same-day `mood` / `motivation` when available.
- `weekly_series` = main weekly series: workouts count, distance, elevation, calories, training load, weekly fitness/fatigue/form, weight, FTP, session RPE load.
- `weekly_series_extended` = extended weekly history for medium-term trend and historical questions.
- `weekly_derived` = precomputed comparison of current week vs previous week and vs 4-week baseline.
- `trends` = aggregated windows `3d / 7d / 14d / 28d` with averages and coverage.
- `long_term_baselines` = long baseline windows `90d / 365d / 12w / 52w`.
- `notes_context` = short context from the latest relevant notes.

If the structure is incomplete:

- do not invent missing fields
- rely on available blocks
- explicitly say what is missing and how it lowers confidence
