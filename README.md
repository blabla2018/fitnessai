# Fitness AI

Local app for training and recovery analysis.

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

## Important Notes

- Intervals is used in read-only mode.
- Only `GET` requests are allowed for Intervals.
- Secrets should be passed through environment variables, not stored in code.
- There is one local SQLite database inside this repo.

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

The main output right now is a local JSON snapshot that AI can use for clear analysis of status, training, and recommendations.

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
