# AGENTS.md

Role of this file:

- define Codex operational behavior in this repo
- interpret user intent
- choose local commands and workflows
- keep analysis setup separate from `README.md`
- keep analysis reasoning separate from `ai_instructions/`

## Project rules

- The Python application code in this repo is read-only against Intervals and should only be used for reading, syncing, and exporting.
- Allowed HTTP methods for Intervals integration inside the repo code: `GET`.
- Do not add local CLI wrappers or Python app commands for writing workout notes, weekly notes, or activity descriptions.
- Remote writes are allowed only when the user explicitly asks to save their own workout note or week note.
- Treat note-saving requests as natural-language commands from the user.
- When the user explicitly asks to save a note, use the agreed final text, find the correct remote target, write it through the official Intervals API outside the Python app code in this repo, and then run a read-only sync so the local cache matches remote state.
- For workout notes, write to the activity `description`.
- For weekly notes, create or update a Sunday `Daily Note` for that week.
- Never store Intervals credentials in committed source files.
- Use environment variables for local secrets.
- This project has only one local SQLite database, stored inside this repo.
- Do not keep permanent database migration code for backward compatibility.
- If a database migration is needed, write the migration, run it against the local database, and then remove the migration code in the same task.
- If a migration is complex or risky, prefer rebuilding local data from Intervals instead of keeping migration logic.
- Rebuilding local data is cheap here: a `sync-intervals --days 365` backfill uses 3 read-only requests and is fast enough to prefer over long-lived migration code.

## Working modes

This repository is used in two different modes. Choose the mode from the user's request.

### 1. Development mode

Use this mode when the user asks to:

- change code
- change export logic
- change analysis prompts or instruction files
- change schema or database behavior
- fix bugs
- run tests
- review code

In this mode:

- focus on implementation, validation, and code review
- do not perform athlete analysis unless the user also asks for it
- do not treat the repo primarily as an end-user tool

### 2. Analysis mode

Use this mode when the user asks to:

- give status
- analyze current state
- analyze a workout
- review a week or block
- explain metrics
- suggest next training step
- forecast recovery or readiness

In this mode:

- treat the repository as a local analysis tool used by an end user
- do not modify source code unless the user explicitly asks
- use the local generated metrics snapshot plus the user-specific plan in `data/athlete/training_plan.md`
- follow `ai_instructions/INSTRUCTIONS.md` and the related files for the analysis format
- always answer analysis in Russian

## Training plan source priority

There are two different training plan files in this repository and they have different roles:

- `data/athlete/training_plan.md` = the real user-specific training plan for local analysis in Codex
- `ai_instructions/templates/training_plan_template.md` = a generic template and guidance file for prompt packaging

When running local analysis in Codex:

- always prefer `data/athlete/training_plan.md` as the athlete's actual plan when it contains user-specific content
- treat `ai_instructions/templates/training_plan_template.md` as a template only
- never replace a real athlete-specific plan with the template during analysis

## Metrics refresh rule for analysis mode

When the user asks for status, workout analysis, week review, forecast, prescription, or general training analysis:

1. Check `data/` for the newest file matching `metrics_YYYY-MM-DD.json`.
2. Use the user's local date when deciding whether a file is "today's" file.
3. If today's metrics file already exists, use it as-is and do not run a new export.
4. If today's metrics file does not exist:
   - run the standard read-only Intervals refresh flow
   - refresh recent data first
   - then export metrics
   - then use the newly created metrics file
5. Prefer today's file over older files, even if an older file is newer by modification timestamp.
6. If refresh fails, say so clearly and then use the newest available local metrics file only if the user still wants analysis from stale data.
7. Never write to remote Intervals data while doing this flow.

## Default interpretation of common user requests

- `дай статус`:
  - in analysis mode
  - first check whether today's `metrics_YYYY-MM-DD.json` already exists
  - if yes, use it without sync/export
  - if no, run read-only refresh and export, then analyze

- `дай статус без обновления`:
  - in analysis mode
  - do not run Intervals sync
  - do not export a new file unless no metrics file exists at all
  - use the newest available local metrics file

- `оцени тренировку сегодня`:
  - in analysis mode
  - prefer today's metrics file if it exists
  - otherwise refresh and export first
  - then do a single-workout review for today's workout

- `обнови данные и дай статус`:
  - in analysis mode
  - always run read-only refresh first
  - then export a fresh metrics file for today
  - then analyze it

- `почини ...`, `добавь ...`, `измени ...`, `сделай review`:
  - in development mode

## Suggested thread structure for the user

Prefer keeping separate conversation threads for:

- `Development`
- `Status and analysis`
- `Mixed fix + use` only when both are needed in the same task

In the `Status and analysis` thread, default to the metrics refresh rule above.
