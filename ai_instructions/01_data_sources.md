# Data Sources

Use data sources in this order:

1. JSON sent in the current message.
2. The newest `metrics_YYYY-MM-DD.json` file from Source.
3. The training plan from `training_plan.md`.

If there is no JSON in the message and no metrics file in Source, explicitly say that there is no data for analysis.

Rules:

- Do not mix multiple snapshot files unless the user explicitly asks for comparison.
- If the JSON in the message conflicts with the file in Source, prefer the JSON from the message.
- If you use a file from Source, explicitly say which file was selected.
- Base physiological date = the latest day inside `current_week.days`.
- Use note `local_date` as the content date for notes.
