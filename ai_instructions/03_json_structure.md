# JSON Structure

Use the JSON blocks like this:

- `current_week` = the current incomplete week. It uses the same structure as a normal week, but includes `is_partial = true`.
- `weekly_detailed_summary` = recent completed weeks with nested `days`.
- `weekly_history_summary` = longer weekly history without nested `days`, but still with weekly notes.
- `weekly_detailed_summary` and `weekly_history_summary` must not overlap. The history block starts only after the last week included in the detailed block.
- Each week may include:
  - `week_of_year` = ISO week number within the year
  - weekly summary metrics
  - `notes` = weekly notes, each note object contains only `title` and `text`
  - `days` = daily objects for that week
- Each day may include:
  - `day_of_week` = ISO weekday number inside the week, from `1` to `7`
  - `workouts_count` = number of workouts known for that day
  - sleep / weight / HRV / RHR / mood / motivation / fitness / fatigue / form / ramp rate / FTP
  - `notes` = day notes, each note object contains only `title` and `text`
  - `workouts` = workouts performed on that date
- Each workout may include:
  - duration / power / NP / IF / FTP reference / HR / cadence / RPE / training load
  - `notes` = workout notes, each note object contains only `title` and `text`
- `trends` = aggregated windows `3d / 7d / 14d / 28d` with averages and coverage.
- `long_term_baselines` = long baseline windows `90d / 365d / 12w / 52w`.

If the structure is incomplete:

- do not invent missing fields
- rely on available blocks
- explicitly say what is missing and how it lowers confidence
- `workouts_count` may be greater than the number of detailed workout objects in `workouts`; this is normal when the system knows a workout happened but does not have full session details via API
