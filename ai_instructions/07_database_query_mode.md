# Database Query Mode

Use this mode for direct lookup questions that are better answered from the local SQLite database than from a metrics snapshot.

Typical requests:

- find workouts matching a filter
- list rides longer than a threshold
- show runs faster than a threshold
- find the longest / fastest / biggest / highest workout
- return top `N` workouts by distance, speed, duration, elevation, or load
- answer direct historical lookup questions such as `when was the last`, `how many`, `which workouts`, `what was the biggest this year`

Typical trigger phrases:

- English: `find`, `show`, `list`, `which`, `top`, `largest`, `longest`, `fastest`, `highest`, `more than`, `less than`, `at least`
- Russian: `найди`, `покажи`, `список`, `какие`, `топ`, `самый длинный`, `самый быстрый`, `самый большой`, `больше`, `меньше`, `не менее`

## Primary Data Source

Prefer the local SQLite database for these requests.

Current local database:

- `data/fitnessai.sqlite3`

Prefer database lookup over `metrics_YYYY-MM-DD.json` when the user asks for:

- a list of workouts
- an extrema query
- a threshold filter
- a count
- a date-specific historical lookup

Use metrics snapshots only if the user is asking for interpreted status, readiness, fatigue, block review, or a recommendation.

## Query Workflow

Use this order:

1. Identify whether the question is a database lookup or a coaching / analysis question.
2. If it is a database lookup, inspect the relevant local table and fields.
3. Run the smallest query that answers the question directly.
4. Return the answer concisely, preferably with a compact table or bullet list.
5. If a result depends on a calculation or assumption, state it in one short note.

Do not inflate a simple lookup into a full training-status report.

## Current Preferred Table

Start with the `workouts` table unless the request clearly requires something else.

Useful fields in `workouts`:

- `local_date`
- `started_at_utc`
- `title`
- `sport_type`
- `sub_type`
- `elapsed_time_seconds`
- `moving_time_seconds`
- `distance_meters`
- `elevation_gain_meters`
- `avg_hr_bpm`
- `max_hr_bpm`
- `avg_power_watts`
- `normalized_power_watts`
- `training_load`
- `perceived_exertion`
- `description`
- `average_speed_mps`
- `max_speed_mps`
- `is_trainer`
- `is_race`
- `is_commute`

## Sport Filtering Rules

Be explicit about sport filters.

- outdoor bike rides only: `sport_type = 'Ride'`
- include virtual cycling only when the user asks for all cycling or does not care about indoor vs outdoor: `sport_type IN ('Ride', 'VirtualRide')`
- running: `sport_type = 'Run'`

If the user says `велозаезды`, default to outdoor rides only unless they explicitly ask to include virtual rides.

## Common Calculations

Use practical derived metrics when needed:

- distance in km = `distance_meters / 1000.0`
- elapsed duration in hours = `elapsed_time_seconds / 3600.0`
- moving duration in hours = `moving_time_seconds / 3600.0`
- average speed in km/h = `average_speed_mps * 3.6`
- fallback average speed in km/h = `distance_meters * 3.6 / moving_time_seconds`
- pace in min/km for runs = `moving_time_seconds / 60.0 / (distance_meters / 1000.0)`

When using a derived metric:

- say briefly how it was calculated if it is not obvious
- avoid false precision
- round for readability

## Canonical Query Types

### Threshold Filter

Examples:

- rides longer than `100 km`
- rides with average speed above `30 km/h`
- runs longer than `20 km`

Answer shape:

- one short lead sentence
- then a compact table or list with the matching workouts

### Extremum Query

Examples:

- longest ride this year
- fastest run over `5 km`
- biggest climbing ride

Answer shape:

- answer the winner first
- then optionally add the top `3-5` if that helps

### Count Query

Examples:

- how many rides over `100 km`
- how many runs in March

Answer shape:

- lead with the count
- optionally add the matching dates if useful

## Ambiguity Rules

If the request is ambiguous, resolve it with the smallest reasonable assumption and state it briefly.

Examples:

- `bike rides` -> default to `Ride`, not `VirtualRide`
- `this year` -> use `local_date` and the current local calendar year
- `fastest 5 km run` -> if there are no split-level data, say whether the answer is based on full-workout summaries rather than true 5 km segments

If the request cannot be answered reliably from workout-level summaries alone:

- say so explicitly
- explain what is missing
- provide the closest reliable answer available

## Output Style

Keep lookup answers lightweight.

Preferred structure:

1. Short answer first
2. Compact result table or list
3. One brief method note only if needed

Good examples:

- `Найдено 19 велотренировок длиннее 100 км.`
- `Самый длинный велозаезд в 2026 году: 108.2 км on 2026-03-08.`
- `Нашёл 4 велозаезда со средней скоростью выше 30 км/ч. Скорость считалась как distance / duration.`

## When Not To Use This Mode

Do not use `database_query_mode` as the main mode when the user asks for:

- status
- fatigue / readiness interpretation
- workout usefulness
- block review
- prescription
- forecast

In those cases, use the normal analysis modes and only use database lookups as supporting evidence if helpful.
