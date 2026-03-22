# Analysis Logic

Analyze in this order:

1. Recovery / state today
2. Load / fatigue
3. Capacity / FTP
4. Weight trend
5. Weekly process
6. Notes context inside weeks / days / workouts

Key derived comparisons to use when data is available:

- sleep vs `3d / 7d / 28d / 90d`
- HRV vs `7d / 14d`
- VO2max vs `28d / 90d / 365d` when available
- RHR vs `7d / 14d`
- form vs `3d / 7d`
- fatigue vs `7d`
- weight vs `7d / 28d / 90d`
- FTP vs `7d / 28d / 90d / 365d`
- current week vs previous week
- current week vs 4-week baseline

Use the `current_trends` block as the main short-term interpretation layer:

- prefer precomputed `delta_vs_*` fields over recomputing them mentally
- always read `n` and `coverage_pct` before trusting an average
- use `sd` to distinguish a likely real shift from normal noise
- use `zone_majority` for `form` when present

Use `personal_baselines` as the athlete's personal norm:

- prefer `90d` and `365d` for long-horizon comparisons
- use `typical_low` / `typical_high` as a normal corridor, not as a medical threshold
- for FTP proxies, use both `avg` and the available `best_*` fields
- interpret both cycling and running performance proxies the same way:
  - absolute proxy (`*_watts` / `run_eftp`)
  - relative proxy per kg (`*_wkg`)

Interpretation guidance:

- Treat `current_week` as incomplete. Do not compare it directly to completed weeks as if it were a full week.
- Use `week_of_year` and `day_of_week` for temporal orientation when they help connect the JSON to the training plan.
- Poor sleep can lower readiness even with neutral HRV/RHR.
- Treat `VO2max` as a slow capacity signal. Do not let it override short-term recovery markers.
- If `fatigue > fitness`, short-term fatigue is present.
- If current balance is still negative but better than `3d` or `7d` average, say that fatigue remains but may be easing.
- For `form`, always state both:
  - the numeric value
  - the current Intervals zone: `high risk`, `optimal`, `grey`, `fresh`, or `transition`
- If FTP is stable but recovery is worse, separate `capacity` from `readiness`.
- For FTP, prefer verdict labels such as: `improving`, `stable`, `drifting down`, `clearly down`, `insufficient data`.
- For the weekly process, prefer labels such as: `process is working well`, `mostly working but constrained`, `mixed / unstable`, `signs of overload`, `insufficient data`.
- If notes and metrics disagree, mention both signals and lower confidence.
- Explicitly call out contradictions when they matter.
- Use weekly notes, day notes, and workout notes to detect patterns such as overreaching goals, failed intervals, unusually high heart rate, cadence drop, or unusually easy execution.
- Interpret `mood` and `motivation` mainly at the day level, then connect them to workout `RPE`, `IF`, and power / HR execution on that same day.
- Treat `mood` and `motivation` as different signals:
  - `mood` = emotional state / stress tone
  - `motivation` = willingness to train / act
- Use these practical patterns when relevant:
  - low `mood` + high `motivation` = athlete may still want to train, but emotional or life stress may be elevated
  - good `mood` + low `motivation` = possible physical fatigue, monotony, or emerging burnout despite acceptable emotional state
  - low `mood` + low `motivation` = stronger caution signal for overload, under-recovery, or broad stress
  - good `mood` + high `motivation` = supportive readiness signal, but still confirm with sleep, HRV/RHR, and load
- Recommendations based on `mood` / `motivation` should be conservative:
  - if both are low, lean toward reduced load, easier execution, or recovery
  - if motivation is low but physiology is neutral, consider keeping the session but reducing psychological cost or complexity
  - if mood is low but motivation is high, avoid framing the athlete as lazy or uncommitted; acknowledge likely stress load and support a controlled session choice
- If workout notes are absent, say that post-session context is limited.
- If `workouts_count` is greater than the number of workout objects in `workouts`, treat that as a normal API coverage limitation rather than a contradiction by default.
- If weight is absent or too sparse, say that the weight conclusion is limited.
- If data quality is weak, say so explicitly.

Always answer:

1. Is the process moving in the right direction?
2. What is happening with fatigue?
3. What is happening with form, including its current Intervals zone?
4. What is happening with FTP?
5. What is happening with weight, if available?
6. What is happening with sleep?
7. Should load be changed?
