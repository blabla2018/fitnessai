# Fitness AI

Local app for training and recovery analysis.

File roles:
- `README.md` = setup and human-facing usage
- `AGENTS.md` = Codex operational behavior in this repo
- `ai_instructions/` = analysis rules and output logic

What it does:
- pulls data from Intervals
- stores it locally in SQLite
- builds a compact `metrics_YYYY-MM-DD.json` snapshot for AI analysis

## Getting Started

1. Prepare the environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
export INTERVALS_ATHLETE_ID="..."
export INTERVALS_API_KEY="..."
```

2. Initialize the database:

```bash
python3 -m app.main init-db
```

3. Run the first sync and export:

```bash
python3 -m app.main sync-intervals --days 365
python3 -m app.main export-metrics
```

After that, a file like `metrics_YYYY-MM-DD.json` will appear in `data/`.

## Normal Workflow

For regular updates, use:

```bash
python3 -m app.main sync-last-week
python3 -m app.main export-metrics
```

This refreshes recent data and rebuilds the latest AI-ready snapshot.

## Useful Commands

Show config:

```bash
python3 -m app.main show-config
```

Re-export the snapshot without a new sync:

```bash
python3 -m app.main export-metrics
```

## Current Scope

The project brings together:
- recovery and wellness
- fitness / fatigue / form
- weekly / day / workout notes
- weekly summaries and activity-level context

The main output right now is a local JSON snapshot that AI can use for clear analysis of status, training, and recommendations. That JSON snapshot is organized into a few practical layers:
- `current_week` and weekly history for recent training context
- `current_trends` and `personal_baselines` for short-term change vs personal norm
- workout-level details for execution, cost, and notes
- a decision layer with readiness, fatigue, confidence, and load-action support

In practice, this lets AI answer not only `what the numbers are`, but also `what is changing`, `why it matters`, and `what to do next`.

## Using It With ChatGPT

The AI prompt package lives in `ai_instructions/`.

It contains:
- the project-level instruction file
- the supporting `.md` files that describe metrics, JSON structure, logic, confidence rules, and output format

For ChatGPT Projects, the recommended setup is:

1. Create a new project.
2. Put the contents of `ai_instructions/INSTRUCTIONS.md` into the project instructions.
3. Add the other `.md` files from `ai_instructions/` as project sources.
4. In the chat itself, attach the exported `metrics_YYYY-MM-DD.json` file for analysis.

In short:
- `INSTRUCTIONS.md` -> Project Instructions
- other `ai_instructions/*.md` files -> Sources
- `metrics_YYYY-MM-DD.json` -> attached in chat

## Using It With Codex

In Codex, the recommended setup is to keep two separate threads:

1. `Development`
2. `Status and analysis`

Typical requests for `Status and analysis`:

- `дай статус`
- `дай статус без обновления`
- `обнови данные и дай статус`
- `оцени тренировку сегодня`
- `разбери текущую неделю`
- `что делать завтра`

Codex behavior for these requests is defined in `AGENTS.md`.

### Training plan files in Codex

There are two training plan files with different purposes:

- `data/athlete/training_plan.md` = your real athlete-specific plan for local Codex analysis
- `ai_instructions/templates/training_plan_template.md` = a generic template used for prompt packaging and guidance

When using Codex for actual status and training analysis, prefer `data/athlete/training_plan.md`.
