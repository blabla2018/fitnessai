from __future__ import annotations

import sqlite3
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.intervals_client import IntervalsClient

INCREMENTAL_NOTES_LOOKBACK_DAYS = 21
INCREMENTAL_WEEKLY_SUMMARY_LOOKBACK_DAYS = 63


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
    athlete_id: int,
    days: int,
) -> dict:
    today = datetime.now(timezone.utc).date()
    oldest = today - timedelta(days=days - 1)
    newest = today

    sync_run_id = start_sync_run(
        connection=connection,
        source="intervals",
        sync_type="incremental",
        window_start=oldest.isoformat(),
        window_end=newest.isoformat(),
    )

    try:
        wellness_rows = client.fetch_wellness(oldest=oldest, newest=newest)
        notes_oldest = today - timedelta(days=max(days, INCREMENTAL_NOTES_LOOKBACK_DAYS) - 1)
        note_rows = client.fetch_notes(oldest=notes_oldest, newest=newest)
        summary_oldest = today - timedelta(
            days=max(days, INCREMENTAL_WEEKLY_SUMMARY_LOOKBACK_DAYS) - 1
        )
        weekly_summary_rows = client.fetch_athlete_summary(start=summary_oldest, end=newest)
        wellness_upserts = upsert_wellness_rows(connection, athlete_id, wellness_rows)
        note_upserts = upsert_note_rows(connection, athlete_id, note_rows)
        weekly_summary_upserts = upsert_weekly_summary_rows(
            connection, athlete_id, client.athlete_id, weekly_summary_rows
        )

        finish_sync_run(
            connection=connection,
            sync_run_id=sync_run_id,
            status="success",
            records_seen=len(wellness_rows) + len(note_rows) + len(weekly_summary_rows),
            records_upserted=wellness_upserts + note_upserts + weekly_summary_upserts,
        )
        return {
            "days": days,
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "wellness_rows": len(wellness_rows),
            "note_rows": len(note_rows),
            "weekly_summary_rows": len(weekly_summary_rows),
            "wellness_upserts": wellness_upserts,
            "note_upserts": note_upserts,
            "weekly_summary_upserts": weekly_summary_upserts,
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
    athlete_id: int,
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
                athlete_id,
                metric_date,
                weight_kg,
                sleep_seconds,
                sleep_score,
                sleep_quality_score,
                avg_sleeping_hr_bpm,
                resting_hr_bpm,
                hrv_ms,
                hrv_sdnn_ms,
                readiness_score,
                mood_score,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(athlete_id, metric_date) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                sleep_seconds = excluded.sleep_seconds,
                sleep_score = excluded.sleep_score,
                sleep_quality_score = excluded.sleep_quality_score,
                avg_sleeping_hr_bpm = excluded.avg_sleeping_hr_bpm,
                resting_hr_bpm = excluded.resting_hr_bpm,
                hrv_ms = excluded.hrv_ms,
                hrv_sdnn_ms = excluded.hrv_sdnn_ms,
                readiness_score = excluded.readiness_score,
                mood_score = excluded.mood_score,
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
                athlete_id,
                metric_date,
                _to_float(row.get("weight")),
                _to_int(row.get("sleepSecs")),
                _to_float(row.get("sleepScore")),
                _to_float(row.get("sleepQuality")),
                _to_float(row.get("avgSleepingHR")),
                _to_float(row.get("restingHR")),
                _to_float(row.get("hrv")),
                _to_float(row.get("hrvSDNN")),
                _to_float(row.get("readiness")),
                _to_float(row.get("mood")),
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
    athlete_id: int,
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
                athlete_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                athlete_id,
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
    athlete_id: int,
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
                athlete_id,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
                athlete_id,
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


def summarize_recent_data(
    connection: sqlite3.Connection,
    days: int,
) -> dict:
    today = date.today()
    oldest = today - timedelta(days=days - 1)

    daily_rows = connection.execute(
        """
        SELECT metric_date, weight_kg, sleep_seconds, sleep_score, sleep_quality_score,
               avg_sleeping_hr_bpm, resting_hr_bpm, hrv_ms, hrv_sdnn_ms, readiness_score,
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
