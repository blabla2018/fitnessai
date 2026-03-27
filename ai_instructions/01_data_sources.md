# Data Sources

Use data sources in this order:

1. JSON sent in the current message.
2. The newest available `metrics_YYYY-MM-DD.json` file accessible in the current environment.
3. The athlete training plan, but only when it contains real user-specific content rather than a generic template.

Exception for direct database lookup requests:

- when the user asks to find, list, count, filter, or rank workouts from history, prefer the local SQLite database first
- in this repository, the default local database is `data/fitnessai.sqlite3`

Accessible files may come from an attached chat file, project/workspace files, or local repository files, depending on the environment.

If there is no JSON in the message and no accessible metrics file, explicitly say that there is no data for analysis.

Rules:

- Do not mix multiple snapshot files unless the user explicitly asks for comparison.
- If the JSON in the message conflicts with a metrics file, prefer the JSON from the message.
- Base physiological date = the latest day inside `history.current_week.days`.
- Use note `local_date` as the content date for notes.
