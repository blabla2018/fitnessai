# AGENTS.md

## Project rules

- Intervals API access is read-only only.
- Allowed HTTP methods for Intervals integration: `GET`.
- Forbidden HTTP methods for Intervals integration: `POST`, `PUT`, `PATCH`, `DELETE`.
- Never change or write remote Intervals data.
- Never store Intervals credentials in committed source files.
- Use environment variables for local secrets.
