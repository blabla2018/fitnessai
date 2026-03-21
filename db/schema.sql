CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    sync_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    window_start TEXT,
    window_end TEXT,
    records_seen INTEGER NOT NULL DEFAULT 0,
    records_upserted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS athlete_metrics_daily (
    id INTEGER PRIMARY KEY,
    metric_date TEXT NOT NULL,
    weight_kg REAL,
    sleep_seconds INTEGER,
    sleep_score REAL,
    sleep_quality_score REAL,
    avg_sleeping_hr_bpm REAL,
    resting_hr_bpm REAL,
    hrv_ms REAL,
    hrv_sdnn_ms REAL,
    readiness_score REAL,
    mood_score REAL,
    fatigue_score REAL,
    soreness_score REAL,
    stress_score REAL,
    motivation_score REAL,
    spo2_percent REAL,
    respiration_rate REAL,
    steps_count INTEGER,
    ctl REAL,
    atl REAL,
    ramp_rate REAL,
    ctl_load REAL,
    atl_load REAL,
    ride_eftp_watts REAL,
    run_eftp REAL,
    swim_eftp REAL,
    notes TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_athlete_metrics_daily_unique
    ON athlete_metrics_daily(metric_date);

CREATE INDEX IF NOT EXISTS idx_athlete_metrics_daily_date
    ON athlete_metrics_daily(metric_date);

CREATE TABLE IF NOT EXISTS intervals_notes (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'intervals',
    external_id TEXT NOT NULL,
    start_date_local TEXT NOT NULL,
    end_date_local TEXT,
    local_date TEXT NOT NULL,
    title TEXT,
    note_text TEXT,
    category TEXT,
    is_week_note INTEGER NOT NULL DEFAULT 0,
    updated_at_remote TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_intervals_notes_source_external
    ON intervals_notes(source, external_id);

CREATE INDEX IF NOT EXISTS idx_intervals_notes_local_date
    ON intervals_notes(local_date);

CREATE TABLE IF NOT EXISTS intervals_weekly_stats (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'intervals',
    week_start_date TEXT NOT NULL,
    workouts_count INTEGER,
    time_seconds INTEGER,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    calories_kcal REAL,
    elevation_gain_meters REAL,
    training_load REAL,
    session_rpe_load REAL,
    distance_meters REAL,
    fitness REAL,
    fatigue REAL,
    form REAL,
    ramp_rate REAL,
    weight_kg REAL,
    most_recent_wellness_id TEXT,
    by_category_json TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_intervals_weekly_stats_unique
    ON intervals_weekly_stats(source, week_start_date);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'intervals',
    external_id TEXT NOT NULL,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    local_date TEXT NOT NULL,
    title TEXT,
    sport_type TEXT,
    sub_type TEXT,
    source_device TEXT,
    duration_seconds INTEGER,
    distance_meters REAL,
    elevation_gain_meters REAL,
    calories_kcal REAL,
    avg_hr_bpm REAL,
    max_hr_bpm REAL,
    avg_power_watts REAL,
    max_power_watts REAL,
    normalized_power_watts REAL,
    training_load REAL,
    perceived_exertion REAL,
    workout_notes TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workouts_source_external
    ON workouts(source, external_id);

CREATE INDEX IF NOT EXISTS idx_workouts_started
    ON workouts(started_at_utc);

CREATE INDEX IF NOT EXISTS idx_workouts_local_date
    ON workouts(local_date);

CREATE TABLE IF NOT EXISTS workout_metrics (
    id INTEGER PRIMARY KEY,
    workout_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    metric_unit TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (workout_id) REFERENCES workouts(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workout_metrics_unique
    ON workout_metrics(workout_id, metric_name);

CREATE INDEX IF NOT EXISTS idx_workout_metrics_name
    ON workout_metrics(metric_name);

CREATE TABLE IF NOT EXISTS daily_training_aggregates (
    id INTEGER PRIMARY KEY,
    aggregate_date TEXT NOT NULL,
    workouts_count INTEGER NOT NULL DEFAULT 0,
    total_duration_seconds INTEGER NOT NULL DEFAULT 0,
    total_distance_meters REAL NOT NULL DEFAULT 0,
    total_training_load REAL NOT NULL DEFAULT 0,
    bike_duration_seconds INTEGER NOT NULL DEFAULT 0,
    gym_duration_seconds INTEGER NOT NULL DEFAULT 0,
    hard_sessions_count INTEGER NOT NULL DEFAULT 0,
    moderate_sessions_count INTEGER NOT NULL DEFAULT 0,
    easy_sessions_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_training_aggregates_unique
    ON daily_training_aggregates(aggregate_date);
