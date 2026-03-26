from __future__ import annotations

import sqlite3
import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Optional

from app.intervals_client import IntervalsClient

INCREMENTAL_NOTES_LOOKBACK_DAYS = 7
ProgressCallback = Optional[Callable[[str], None]]


def start_sync_run(
    connection: sqlite3.Connection,
    source: str,
    sync_type: str,
    window_start: Optional[str],
    window_end: Optional[str],
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO sync_runs (
            source,
            sync_type,
            started_at,
            status,
            window_start,
            window_end
        )
        VALUES (?, ?, CURRENT_TIMESTAMP, 'running', ?, ?)
        """,
        (source, sync_type, window_start, window_end),
    )
    connection.commit()
    return int(cursor.lastrowid)


def finish_sync_run(
    connection: sqlite3.Connection,
    sync_run_id: int,
    status: str,
    records_seen: int = 0,
    records_upserted: int = 0,
    error_message: Optional[str] = None,
) -> None:
    connection.execute(
        """
        UPDATE sync_runs
        SET finished_at = CURRENT_TIMESTAMP,
            status = ?,
            records_seen = ?,
            records_upserted = ?,
            error_message = ?
        WHERE id = ?
        """,
        (status, records_seen, records_upserted, error_message, sync_run_id),
    )
    connection.commit()


def sync_intervals_days(
    connection: sqlite3.Connection,
    client: IntervalsClient,
    days: int,
    progress_callback: ProgressCallback = None,
) -> dict:
    started_at = time.perf_counter()
    today = datetime.now(timezone.utc).date()
    oldest = today - timedelta(days=days - 1)
    newest = today

    _report_progress(
        progress_callback,
        f"Starting Intervals sync for {days} days: {oldest.isoformat()} -> {newest.isoformat()}",
    )

    sync_run_id = start_sync_run(
        connection=connection,
        source="intervals",
        sync_type="incremental",
        window_start=oldest.isoformat(),
        window_end=newest.isoformat(),
    )

    try:
        _report_progress(progress_callback, "Fetching wellness rows...")
        fetch_started_at = time.perf_counter()
        wellness_rows = client.fetch_wellness(oldest=oldest, newest=newest)
        wellness_fetch_seconds = round(time.perf_counter() - fetch_started_at, 3)
        _report_progress(
            progress_callback,
            f"Fetched wellness: {len(wellness_rows)} rows in {wellness_fetch_seconds:.3f}s",
        )

        notes_oldest = today - timedelta(days=max(days, INCREMENTAL_NOTES_LOOKBACK_DAYS) - 1)
        _report_progress(
            progress_callback,
            f"Fetching notes: {notes_oldest.isoformat()} -> {newest.isoformat()}...",
        )
        fetch_started_at = time.perf_counter()
        note_rows = client.fetch_notes(oldest=notes_oldest, newest=newest)
        notes_fetch_seconds = round(time.perf_counter() - fetch_started_at, 3)
        _report_progress(
            progress_callback,
            f"Fetched notes: {len(note_rows)} rows in {notes_fetch_seconds:.3f}s",
        )

        summary_oldest = oldest
        _report_progress(
            progress_callback,
            f"Fetching weekly summary: {summary_oldest.isoformat()} -> {newest.isoformat()}...",
        )
        fetch_started_at = time.perf_counter()
        weekly_summary_rows = client.fetch_athlete_summary(start=summary_oldest, end=newest)
        weekly_summary_fetch_seconds = round(time.perf_counter() - fetch_started_at, 3)
        _report_progress(
            progress_callback,
            f"Fetched weekly summary: {len(weekly_summary_rows)} rows in {weekly_summary_fetch_seconds:.3f}s",
        )

        activities_oldest = oldest
        _report_progress(
            progress_callback,
            f"Fetching activities: {activities_oldest.isoformat()} -> {newest.isoformat()}...",
        )
        fetch_started_at = time.perf_counter()
        activity_rows = client.fetch_activities(oldest=activities_oldest, newest=newest)
        activities_fetch_seconds = round(time.perf_counter() - fetch_started_at, 3)
        _report_progress(
            progress_callback,
            f"Fetched activities: {len(activity_rows)} rows in {activities_fetch_seconds:.3f}s",
        )

        _report_progress(progress_callback, "Upserting wellness rows...")
        upsert_started_at = time.perf_counter()
        wellness_upserts = upsert_wellness_rows(connection, wellness_rows)
        wellness_upsert_seconds = round(time.perf_counter() - upsert_started_at, 3)
        _report_progress(
            progress_callback,
            f"Upserted wellness: {wellness_upserts} rows in {wellness_upsert_seconds:.3f}s",
        )

        _report_progress(progress_callback, "Upserting note rows...")
        upsert_started_at = time.perf_counter()
        note_upserts = upsert_note_rows(connection, note_rows)
        note_upsert_seconds = round(time.perf_counter() - upsert_started_at, 3)
        _report_progress(
            progress_callback,
            f"Upserted notes: {note_upserts} rows in {note_upsert_seconds:.3f}s",
        )

        _report_progress(progress_callback, "Upserting weekly summary rows...")
        upsert_started_at = time.perf_counter()
        weekly_summary_upserts = upsert_weekly_summary_rows(
            connection, client.athlete_id, weekly_summary_rows
        )
        weekly_summary_upsert_seconds = round(time.perf_counter() - upsert_started_at, 3)
        _report_progress(
            progress_callback,
            "Upserted weekly summary: "
            f"{weekly_summary_upserts} rows in {weekly_summary_upsert_seconds:.3f}s",
        )

        _report_progress(progress_callback, "Upserting activities and activity notes...")
        upsert_started_at = time.perf_counter()
        activity_upserts = upsert_activity_rows(
            connection,
            activity_rows,
            progress_callback=progress_callback,
        )
        activity_upsert_seconds = round(time.perf_counter() - upsert_started_at, 3)
        _report_progress(
            progress_callback,
            f"Upserted activities: {activity_upserts} rows in {activity_upsert_seconds:.3f}s",
        )

        finish_sync_run(
            connection=connection,
            sync_run_id=sync_run_id,
            status="success",
            records_seen=(
                len(wellness_rows)
                + len(note_rows)
                + len(weekly_summary_rows)
                + len(activity_rows)
            ),
            records_upserted=(
                wellness_upserts
                + note_upserts
                + weekly_summary_upserts
                + activity_upserts
            ),
        )
        total_elapsed_seconds = round(time.perf_counter() - started_at, 3)
        _report_progress(
            progress_callback,
            f"Intervals sync finished successfully in {total_elapsed_seconds:.3f}s",
        )
        return {
            "days": days,
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "notes_oldest": notes_oldest.isoformat(),
            "weekly_summary_oldest": summary_oldest.isoformat(),
            "activities_oldest": activities_oldest.isoformat(),
            "wellness_rows": len(wellness_rows),
            "note_rows": len(note_rows),
            "weekly_summary_rows": len(weekly_summary_rows),
            "activity_rows": len(activity_rows),
            "wellness_upserts": wellness_upserts,
            "note_upserts": note_upserts,
            "weekly_summary_upserts": weekly_summary_upserts,
            "activity_upserts": activity_upserts,
            "fetch_timings_seconds": {
                "wellness": wellness_fetch_seconds,
                "notes": notes_fetch_seconds,
                "weekly_summary": weekly_summary_fetch_seconds,
                "activities": activities_fetch_seconds,
                "total_fetch": round(
                    wellness_fetch_seconds
                    + notes_fetch_seconds
                    + weekly_summary_fetch_seconds
                    + activities_fetch_seconds,
                    3,
                ),
            },
            "upsert_timings_seconds": {
                "wellness": wellness_upsert_seconds,
                "notes": note_upsert_seconds,
                "weekly_summary": weekly_summary_upsert_seconds,
                "activities": activity_upsert_seconds,
                "total_upsert": round(
                    wellness_upsert_seconds
                    + note_upsert_seconds
                    + weekly_summary_upsert_seconds
                    + activity_upsert_seconds,
                    3,
                ),
            },
            "total_elapsed_seconds": total_elapsed_seconds,
        }
    except Exception as exc:
        finish_sync_run(
            connection=connection,
            sync_run_id=sync_run_id,
            status="failed",
            error_message=str(exc),
        )
        raise


def upsert_wellness_rows(
    connection: sqlite3.Connection,
    rows: list[dict],
) -> int:
    upserts = 0

    for row in rows:
        metric_date = row.get("date")
        if not metric_date:
            continue

        connection.execute(
            """
            INSERT INTO athlete_metrics_daily (
                metric_date,
                weight_kg,
                sleep_seconds,
                sleep_score,
                sleep_quality_score,
                avg_sleeping_hr_bpm,
                resting_hr_bpm,
                hrv_ms,
                vo2max,
                hrv_sdnn_ms,
                readiness_score,
                mood_score,
                fatigue_score,
                soreness_score,
                stress_score,
                motivation_score,
                spo2_percent,
                respiration_rate,
                steps_count,
                ctl,
                atl,
                ramp_rate,
                ctl_load,
                atl_load,
                ride_eftp_watts,
                run_eftp,
                swim_eftp,
                notes,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(metric_date) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                sleep_seconds = excluded.sleep_seconds,
                sleep_score = excluded.sleep_score,
                sleep_quality_score = excluded.sleep_quality_score,
                avg_sleeping_hr_bpm = excluded.avg_sleeping_hr_bpm,
                resting_hr_bpm = excluded.resting_hr_bpm,
                hrv_ms = excluded.hrv_ms,
                vo2max = excluded.vo2max,
                hrv_sdnn_ms = excluded.hrv_sdnn_ms,
                readiness_score = excluded.readiness_score,
                mood_score = excluded.mood_score,
                fatigue_score = excluded.fatigue_score,
                soreness_score = excluded.soreness_score,
                stress_score = excluded.stress_score,
                motivation_score = excluded.motivation_score,
                spo2_percent = excluded.spo2_percent,
                respiration_rate = excluded.respiration_rate,
                steps_count = excluded.steps_count,
                ctl = excluded.ctl,
                atl = excluded.atl,
                ramp_rate = excluded.ramp_rate,
                ctl_load = excluded.ctl_load,
                atl_load = excluded.atl_load,
                ride_eftp_watts = excluded.ride_eftp_watts,
                run_eftp = excluded.run_eftp,
                swim_eftp = excluded.swim_eftp,
                notes = excluded.notes,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                metric_date,
                _to_float(row.get("weight")),
                _to_int(row.get("sleepSecs")),
                _to_float(row.get("sleepScore")),
                _to_float(row.get("sleepQuality")),
                _to_float(row.get("avgSleepingHR")),
                _to_float(row.get("restingHR")),
                _to_float(row.get("hrv")),
                _to_float(row.get("vo2max")),
                _to_float(row.get("hrvSDNN")),
                _to_float(row.get("readiness")),
                _to_float(row.get("mood")),
                _to_float(row.get("fatigue")),
                _to_float(row.get("soreness")),
                _to_float(row.get("stress")),
                _to_float(row.get("motivation")),
                _to_float(row.get("spO2")),
                _to_float(row.get("respiration")),
                _to_int(row.get("steps")),
                _to_float(row.get("ctl")),
                _to_float(row.get("atl")),
                _to_float(row.get("rampRate")),
                _to_float(row.get("ctlLoad")),
                _to_float(row.get("atlLoad")),
                _to_float(row.get("Ride_eftp")),
                _to_float(row.get("Run_eftp")),
                _to_float(row.get("Swim_eftp")),
                row.get("comments") or None,
                json.dumps(row, ensure_ascii=True),
            ),
        )
        upserts += 1

    connection.commit()
    return upserts


def upsert_note_rows(
    connection: sqlite3.Connection,
    rows: list[dict],
) -> int:
    upserts = 0

    for row in rows:
        external_id = row.get("id")
        start_date_local = row.get("start_date_local")
        if not external_id or not start_date_local:
            continue

        local_date = start_date_local[:10]
        connection.execute(
            """
            INSERT INTO intervals_notes (
                source,
                external_id,
                start_date_local,
                end_date_local,
                local_date,
                title,
                note_text,
                category,
                is_week_note,
                updated_at_remote,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source, external_id) DO UPDATE SET
                start_date_local = excluded.start_date_local,
                end_date_local = excluded.end_date_local,
                local_date = excluded.local_date,
                title = excluded.title,
                note_text = excluded.note_text,
                category = excluded.category,
                is_week_note = excluded.is_week_note,
                updated_at_remote = excluded.updated_at_remote,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                "intervals",
                str(external_id),
                start_date_local,
                row.get("end_date_local"),
                local_date,
                row.get("name"),
                row.get("description"),
                row.get("category"),
                1 if row.get("for_week") else 0,
                row.get("updated"),
                json.dumps(row, ensure_ascii=False),
            ),
        )
        upserts += 1

    connection.commit()
    return upserts


def upsert_weekly_summary_rows(
    connection: sqlite3.Connection,
    athlete_external_id: Optional[str],
    rows: list[dict],
) -> int:
    upserts = 0

    for row in rows:
        week_start_date = row.get("date")
        athlete_ref = row.get("athlete_id")
        if not week_start_date or (athlete_external_id and athlete_ref != athlete_external_id):
            continue

        connection.execute(
            """
            INSERT INTO intervals_weekly_stats (
                source,
                week_start_date,
                workouts_count,
                time_seconds,
                moving_time_seconds,
                elapsed_time_seconds,
                calories_kcal,
                elevation_gain_meters,
                training_load,
                session_rpe_load,
                distance_meters,
                fitness,
                fatigue,
                form,
                ramp_rate,
                weight_kg,
                most_recent_wellness_id,
                by_category_json,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source, week_start_date) DO UPDATE SET
                workouts_count = excluded.workouts_count,
                time_seconds = excluded.time_seconds,
                moving_time_seconds = excluded.moving_time_seconds,
                elapsed_time_seconds = excluded.elapsed_time_seconds,
                calories_kcal = excluded.calories_kcal,
                elevation_gain_meters = excluded.elevation_gain_meters,
                training_load = excluded.training_load,
                session_rpe_load = excluded.session_rpe_load,
                distance_meters = excluded.distance_meters,
                fitness = excluded.fitness,
                fatigue = excluded.fatigue,
                form = excluded.form,
                ramp_rate = excluded.ramp_rate,
                weight_kg = excluded.weight_kg,
                most_recent_wellness_id = excluded.most_recent_wellness_id,
                by_category_json = excluded.by_category_json,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                "intervals",
                week_start_date,
                _to_int(row.get("count")),
                _to_int(row.get("time")),
                _to_int(row.get("moving_time")),
                _to_int(row.get("elapsed_time")),
                _to_float(row.get("calories")),
                _to_float(row.get("total_elevation_gain")),
                _to_float(row.get("training_load")),
                _to_float(row.get("srpe")),
                _to_float(row.get("distance")),
                _to_float(row.get("fitness")),
                _to_float(row.get("fatigue")),
                _to_float(row.get("form")),
                _to_float(row.get("rampRate")),
                _to_float(row.get("weight")),
                row.get("mostRecentWellnessId"),
                json.dumps(row.get("byCategory"), ensure_ascii=False),
                json.dumps(row, ensure_ascii=False),
            ),
        )
        upserts += 1

    connection.commit()
    return upserts


def upsert_activity_rows(
    connection: sqlite3.Connection,
    rows: list[dict],
    progress_callback: ProgressCallback = None,
) -> int:
    upserts = 0
    useful_seen = 0

    for index, row in enumerate(rows, start=1):
        if not _is_useful_activity(row):
            continue
        useful_seen += 1
        if useful_seen == 1 or useful_seen % 25 == 0 or useful_seen == len(rows):
            _report_progress(
                progress_callback,
                f"Processing activities: useful {useful_seen} / raw {len(rows)} (row {index})",
            )

        external_id = row.get("id")
        started_at_utc = row.get("start_date")
        start_date_local = row.get("start_date_local")
        if not external_id or not started_at_utc or not start_date_local:
            continue

        local_date = start_date_local[:10]
        connection.execute(
            """
            INSERT INTO workouts (
                source,
                external_id,
                started_at_utc,
                ended_at_utc,
                local_date,
                title,
                sport_type,
                sub_type,
                source_device,
                elapsed_time_seconds,
                moving_time_seconds,
                distance_meters,
                elevation_gain_meters,
                calories_kcal,
                avg_hr_bpm,
                max_hr_bpm,
                avg_power_watts,
                max_power_watts,
                normalized_power_watts,
                training_load,
                perceived_exertion,
                description,
                average_speed_mps,
                max_speed_mps,
                is_trainer,
                is_race,
                is_commute,
                raw_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source, external_id) DO UPDATE SET
                started_at_utc = excluded.started_at_utc,
                ended_at_utc = excluded.ended_at_utc,
                local_date = excluded.local_date,
                title = excluded.title,
                sport_type = excluded.sport_type,
                sub_type = excluded.sub_type,
                source_device = excluded.source_device,
                elapsed_time_seconds = excluded.elapsed_time_seconds,
                moving_time_seconds = excluded.moving_time_seconds,
                distance_meters = excluded.distance_meters,
                elevation_gain_meters = excluded.elevation_gain_meters,
                calories_kcal = excluded.calories_kcal,
                avg_hr_bpm = excluded.avg_hr_bpm,
                max_hr_bpm = excluded.max_hr_bpm,
                avg_power_watts = excluded.avg_power_watts,
                max_power_watts = excluded.max_power_watts,
                normalized_power_watts = excluded.normalized_power_watts,
                training_load = excluded.training_load,
                perceived_exertion = excluded.perceived_exertion,
                description = excluded.description,
                average_speed_mps = excluded.average_speed_mps,
                max_speed_mps = excluded.max_speed_mps,
                is_trainer = excluded.is_trainer,
                is_race = excluded.is_race,
                is_commute = excluded.is_commute,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                _first_non_empty(row.get("source"), "intervals"),
                str(external_id),
                started_at_utc,
                _end_time_from_activity(row),
                local_date,
                row.get("name"),
                row.get("type"),
                row.get("trainer_ride_type"),
                _first_non_empty(row.get("device_name"), row.get("device")),
                _to_int(_first_non_empty(row.get("elapsed_time"), row.get("moving_time"))),
                _to_int(row.get("moving_time")),
                _to_float(row.get("distance")),
                _to_float(_first_non_empty(row.get("total_elevation_gain"), row.get("elevation_gain"))),
                _to_float(row.get("calories")),
                _to_float(row.get("average_heartrate")),
                _to_float(row.get("max_heartrate")),
                _to_float(_first_non_empty(row.get("icu_average_watts"), row.get("average_watts"))),
                _to_float(row.get("max_watts")),
                _to_float(
                    _first_non_empty(
                        row.get("icu_norm_power"),
                        row.get("icu_weighted_avg_watts"),
                        row.get("weighted_avg_watts"),
                    )
                ),
                _to_float(row.get("icu_training_load")),
                _to_float(row.get("icu_rpe")),
                row.get("description"),
                _to_float(row.get("average_speed")),
                _to_float(row.get("max_speed")),
                1 if row.get("trainer") is True else 0 if row.get("trainer") is False else None,
                1 if row.get("race") is True else 0 if row.get("race") is False else None,
                1 if row.get("commute") is True else 0 if row.get("commute") is False else None,
                json.dumps(row, ensure_ascii=False),
            ),
        )

        workout_id = connection.execute(
            """
            SELECT id
            FROM workouts
            WHERE source = ? AND external_id = ?
            LIMIT 1
            """,
            (_first_non_empty(row.get("source"), "intervals"), str(external_id)),
        ).fetchone()
        if workout_id:
            _upsert_workout_metric(
                connection,
                int(workout_id[0]),
                "average_cadence",
                _to_float(row.get("average_cadence")),
                "rpm",
            )
            _upsert_workout_metric(
                connection,
                int(workout_id[0]),
                "intensity_factor",
                _to_float(row.get("icu_intensity")),
                "ratio",
            )
            _upsert_workout_metric(
                connection,
                int(workout_id[0]),
                "eftp",
                _to_float(_first_non_empty(row.get("icu_ftp"), row.get("icu_pm_ftp_watts"))),
                "watts",
            )
            _upsert_workout_metric(
                connection,
                int(workout_id[0]),
                "weighted_avg_watts",
                _to_float(
                    _first_non_empty(
                        row.get("icu_norm_power"),
                        row.get("icu_weighted_avg_watts"),
                        row.get("weighted_avg_watts"),
                    )
                ),
                "watts",
            )

        upserts += 1

    connection.commit()
    return upserts


def _report_progress(progress_callback: ProgressCallback, message: str) -> None:
    if progress_callback is not None:
        progress_callback(message)


def _upsert_workout_metric(
    connection: sqlite3.Connection,
    workout_id: int,
    metric_name: str,
    metric_value: Optional[float],
    metric_unit: Optional[str],
) -> None:
    if metric_value is None:
        return

    connection.execute(
        """
        INSERT INTO workout_metrics (
            workout_id,
            metric_name,
            metric_value,
            metric_unit,
            updated_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(workout_id, metric_name) DO UPDATE SET
            metric_value = excluded.metric_value,
            metric_unit = excluded.metric_unit,
            updated_at = CURRENT_TIMESTAMP
        """,
        (workout_id, metric_name, metric_value, metric_unit),
    )


def summarize_recent_data(
    connection: sqlite3.Connection,
    days: int,
) -> dict:
    today = date.today()
    oldest = today - timedelta(days=days - 1)

    daily_rows = connection.execute(
        """
        SELECT metric_date, weight_kg, sleep_seconds, sleep_score, sleep_quality_score,
               avg_sleeping_hr_bpm, resting_hr_bpm, hrv_ms, vo2max, hrv_sdnn_ms, readiness_score,
               mood_score, motivation_score,
               spo2_percent, respiration_rate, steps_count, ctl, atl, ramp_rate,
               ctl_load, atl_load, ride_eftp_watts, run_eftp, swim_eftp
        FROM athlete_metrics_daily
        WHERE metric_date >= ?
        ORDER BY metric_date DESC
        """,
        (oldest.isoformat(),),
    ).fetchall()

    note_rows = connection.execute(
        """
        SELECT local_date, start_date_local, end_date_local, title, category,
               is_week_note, updated_at_remote, note_text
        FROM intervals_notes
        WHERE local_date >= ?
        ORDER BY start_date_local DESC
        """,
        (oldest.isoformat(),),
    ).fetchall()

    return {
        "daily_metrics": [dict(row) for row in daily_rows],
        "notes": [dict(row) for row in note_rows],
    }


def _to_float(value: object) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> Optional[int]:
    number = _to_float(value)
    if number is None:
        return None
    return int(round(number))


def _first_non_empty(*values: object) -> object:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _end_time_from_activity(row: dict) -> Optional[str]:
    started_at = row.get("start_date")
    elapsed_seconds = _to_int(_first_non_empty(row.get("elapsed_time"), row.get("moving_time")))
    if not started_at or elapsed_seconds is None:
        return None

    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (started + timedelta(seconds=elapsed_seconds)).isoformat().replace("+00:00", "Z")


def _is_useful_activity(row: dict) -> bool:
    if not row:
        return False
    if str(row.get("source") or "").upper() == "STRAVA":
        return False

    has_identity = any(
        row.get(key) not in (None, "")
        for key in ("name", "type", "device_name", "device")
    )
    has_duration = (
        _to_int(_first_non_empty(row.get("elapsed_time"), row.get("moving_time"))) is not None
    )
    has_load = _to_float(row.get("icu_training_load")) is not None
    has_power = _to_float(
        _first_non_empty(
            row.get("icu_norm_power"),
            row.get("icu_weighted_avg_watts"),
            row.get("weighted_avg_watts"),
            row.get("icu_average_watts"),
            row.get("average_watts"),
        )
    ) is not None
    has_hr = _to_float(_first_non_empty(row.get("average_heartrate"), row.get("max_heartrate"))) is not None

    return has_identity and (has_duration or has_load or has_power or has_hr)
