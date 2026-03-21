# Metric Definitions

- `HRV` = heart rate variability. Interpret it relative to the athlete's own baseline, not in isolation.
- `RHR` = resting heart rate, baseline resting pulse.
- `Fitness` = long-term modeled fitness from Intervals.
- `Fatigue` = short-term modeled accumulated load / fatigue from Intervals.
- `Form` = `Fitness - Fatigue`. A more negative value usually means higher short-term accumulated fatigue.
- Intervals `Form` zones:
  - `< -30` = `high risk`
  - `-30 ... -10` = `optimal`
  - `-10 ... 5` = `grey`
  - `5 ... 20` = `fresh`
  - `> 20` = `transition`
- `Ramp rate` = speed of change of modeled load / form over time. Interpret it in the context of recent weeks.
- `ride_eftp_watts` and `run_eftp` = performance proxies for cycling and running.
- `ride_eftp_wkg` and `run_eftp_wkg` = the same performance proxies normalized by body weight.
- `training_load` = weekly modeled load from Intervals.
- `session_rpe_load` = subjective session load, usually something like `duration × RPE`.
- `power_np` = normalized power or weighted average power proxy for a session.
- `if` = intensity factor for a session. Interpret it as relative intensity, not as load by itself.
- `rpe` = session rating of perceived exertion.
- `cadence_avg` = average cadence for the session.

Interpretation rules:

- Evaluate HRV and RHR primarily against the athlete's personal baseline.
- Poor sleep can reduce readiness even if HRV and RHR are near baseline.
- If `fatigue > fitness`, treat it as accumulated short-term fatigue, but compare it with recent baseline.
- If current balance is still negative but better than recent `3d` or `7d` context, it is valid to say that fatigue remains but may be easing.
- Stable FTP does not imply high readiness. A valid conclusion may be: `capacity stable, readiness reduced`.
- Always interpret `form` both as a number and as an Intervals zone label.
- When discussing `form`, explicitly say which zone it is currently in: `high risk`, `optimal`, `grey`, `fresh`, or `transition`.
- Analyze weight only as a trend and context signal, without medical conclusions.
- If weight is missing or too sparse, explicitly say that the weight conclusion is limited.
- Do not treat `ramp rate` as a standalone signal.
- Do not reduce the entire conclusion to one metric. Base conclusions on at least 2-3 aligned signals or clearly lower confidence.
