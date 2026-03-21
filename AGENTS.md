# AGENTS.md

## Project rules

- Intervals API access is read-only only.
- Allowed HTTP methods for Intervals integration: `GET`.
- Forbidden HTTP methods for Intervals integration: `POST`, `PUT`, `PATCH`, `DELETE`.
- Never change or write remote Intervals data.
- Never store Intervals credentials in committed source files.
- Use environment variables for local secrets.
- This project has only one local SQLite database, stored inside this repo.
- Do not keep permanent database migration code for backward compatibility.
- If a database migration is needed, write the migration, run it against the local database, and then remove the migration code in the same task.
- If a migration is complex or risky, prefer rebuilding local data from Intervals instead of keeping migration logic.
- Rebuilding local data is cheap here: a `sync-intervals --days 365` backfill uses 3 read-only requests and is fast enough to prefer over long-lived migration code.
