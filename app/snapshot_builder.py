from __future__ import annotations

import json
import os
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional

RECENT_DETAILED_WEEKS = 8


def build_snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    current_row = connection.execute(
        """
        SELECT *
        FROM athlete_metrics_daily
        ORDER BY metric_date DESC
        LIMIT 1
        """
    ).fetchone()
    if current_row is None:
        raise ValueError("No athlete daily metrics found. Run sync first.")

    current = dict(current_row)
    current_date = current["metric_date"]
    current_week_start = _week_start_date(current_date)
    snapshot = {
        "current_week": _build_current_week(connection, current_date, current_week_start),
        "weekly_detailed_summary": _build_weeks(
            connection, current_date, current_week_start, RECENT_DETAILED_WEEKS
        ),
        "weekly_history_summary": _build_weekly_history_summary(
            connection,
            current_date,
            current_week_start,
            104,
            RECENT_DETAILED_WEEKS,
        ),
        "current_trends": _trend_block(connection, current_date, {"3d": 3, "7d": 7, "14d": 14, "28d": 28}),
    }
    snapshot["personal_baselines"] = _build_long_term_baselines(connection, current_date)
    return snapshot


def export_metrics_file(
    snapshot: dict[str, Any],
    output_json_path: Path,
) -> None:
    export_snapshot = _prune_for_export(snapshot)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(export_snapshot, ensure_ascii=False, indent=2)
    temp_path = output_json_path.with_suffix(f"{output_json_path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(serialized)
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(output_json_path)


def _build_current_week(
    connection: sqlite3.Connection,
    current_date: str,
    current_week_start: str,
) -> dict[str, Any]:
    week_row = _load_weekly_row(connection, current_week_start)
    week = _build_week_object(
        connection=connection,
        week_start_date=current_week_start,
        week_row=week_row,
        include_days=True,
        current_date=current_date,
        is_partial=True,
    )
    return week


def _build_weeks(
    connection: sqlite3.Connection,
    current_date: str,
    current_week_start: str,
    limit_weeks: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM intervals_weekly_stats
        WHERE week_start_date < ?
        ORDER BY week_start_date DESC
        LIMIT ?
        """,
        (current_week_start, limit_weeks),
    ).fetchall()
    weeks = [
        _build_week_object(
            connection=connection,
            week_start_date=dict(row)["week_start_date"],
            week_row=dict(row),
            include_days=True,
            current_date=current_date,
            is_partial=False,
        )
        for row in rows
    ]
    return list(reversed(weeks))


def _build_weekly_history_summary(
    connection: sqlite3.Connection,
    current_date: str,
    current_week_start: str,
    limit_weeks: int,
    skip_recent_weeks: int,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM intervals_weekly_stats
        WHERE week_start_date < ?
        ORDER BY week_start_date DESC
        LIMIT ?
        OFFSET ?
        """,
        (current_week_start, limit_weeks, skip_recent_weeks),
    ).fetchall()
    weeks = [
        _build_week_object(
            connection=connection,
            week_start_date=dict(row)["week_start_date"],
            week_row=dict(row),
            include_days=False,
            current_date=current_date,
            is_partial=False,
        )
        for row in rows
    ]
    return list(reversed(weeks))


def _build_week_object(
    connection: sqlite3.Connection,
    week_start_date: str,
    week_row: Optional[dict[str, Any]],
    include_days: bool,
    current_date: str,
    is_partial: bool,
) -> dict[str, Any]:
    base = _weekly_summary_from_row(connection, week_start_date, week_row)
    base["notes"] = _load_week_notes(connection, week_start_date)
    if include_days:
        base["days"] = _build_days_for_week(connection, week_start_date, current_date, is_partial)
    if is_partial:
        base["is_partial"] = True
    return base


def _weekly_summary_from_row(
    connection: sqlite3.Connection,
    week_start_date: str,
    row: Optional[dict[str, Any]],
) -> dict[str, Any]:
    item = row or {}
    by_category = _parse_json_or_none(item.get("by_category_json"))
    weight_kg = item.get("weight_kg")
    ride_eftp_watts = _first_non_null(
        _category_eftp(by_category, "Ride"),
        _category_eftp(by_category, "Bike"),
        _latest_metric_within_week(connection, week_start_date, "ride_eftp_watts"),
    )
    run_eftp = _first_non_null(
        _category_eftp(by_category, "Run"),
        _latest_metric_within_week(connection, week_start_date, "run_eftp"),
    )
    return {
        "week_start_date": week_start_date,
        "week_of_year": _iso_week_number(week_start_date),
        "workouts_count": item.get("workouts_count"),
        "distance_km": _round_or_none(_meters_to_km(item.get("distance_meters")), 2),
        "elevation_gain_m": _round_or_none(item.get("elevation_gain_meters"), 1),
        "calories_kcal": _round_or_none(item.get("calories_kcal"), 0),
        "training_load": _round_or_none(item.get("training_load"), 1),
        "session_rpe_load": _round_or_none(item.get("session_rpe_load"), 1),
        "fitness": _round_or_none(item.get("fitness"), 2),
        "fatigue": _round_or_none(item.get("fatigue"), 2),
        "form": _round_or_none(item.get("form"), 2),
        "ramp_rate": _round_or_none(item.get("ramp_rate"), 2),
        "weight_kg_end": _round_or_none(weight_kg, 2),
        "ride_eftp_watts": _round_or_none(ride_eftp_watts, 2),
        "ride_eftp_wkg": _round_or_none(_watts_per_kg(ride_eftp_watts, weight_kg), 2),
        "run_eftp": _round_or_none(run_eftp, 2),
        "run_eftp_wkg": _round_or_none(_watts_per_kg(run_eftp, weight_kg), 2),
    }


def _build_days_for_week(
    connection: sqlite3.Connection,
    week_start_date: str,
    current_date: str,
    is_partial: bool,
) -> list[dict[str, Any]]:
    week_start = date.fromisoformat(week_start_date)
    week_end = week_start + timedelta(days=6)
    if is_partial:
        week_end = min(week_end, date.fromisoformat(current_date))

    metrics_by_date = _load_metrics_by_date(connection, week_start.isoformat(), week_end.isoformat())
    workouts_by_date = _load_workouts_by_date(connection, week_start.isoformat(), week_end.isoformat())
    workout_counts_by_date = _load_workout_counts_by_date(
        connection, week_start.isoformat(), week_end.isoformat()
    )
    daily_notes_by_date = _load_daily_notes_by_date(connection, week_start.isoformat(), week_end.isoformat())

    days = []
    day_cursor = week_start
    while day_cursor <= week_end:
        day_iso = day_cursor.isoformat()
        row = metrics_by_date.get(day_iso)
        days.append(
            _build_day_object(
                day_iso,
                row,
                daily_notes_by_date.get(day_iso, []),
                workouts_by_date.get(day_iso, []),
                workout_counts_by_date.get(day_iso, 0),
            )
        )
        day_cursor += timedelta(days=1)
    return days


def _build_day_object(
    day_iso: str,
    row: Optional[dict[str, Any]],
    notes: list[dict[str, Any]],
    workouts: list[dict[str, Any]],
    workouts_count: int,
) -> dict[str, Any]:
    row = row or {}
    weight_kg = row.get("weight_kg")
    ride_eftp_watts = row.get("ride_eftp_watts")
    run_eftp = row.get("run_eftp")
    fitness = row.get("ctl")
    fatigue = row.get("atl")
    return {
        "date": day_iso,
        "day_of_week": date.fromisoformat(day_iso).isoweekday(),
        "workouts_count": workouts_count,
        "sleep_hours": _round_or_none(_seconds_to_hours(row.get("sleep_seconds")), 2),
        "sleep_score": _round_or_none(_to_float_or_none(row.get("sleep_score")), 1),
        "sleep_quality_score": _round_or_none(_to_float_or_none(row.get("sleep_quality_score")), 1),
        "weight_kg": _round_or_none(_to_float_or_none(weight_kg), 2),
        "hrv_ms": _round_or_none(_to_float_or_none(row.get("hrv_ms")), 2),
        "vo2max": _round_or_none(_to_float_or_none(row.get("vo2max")), 2),
        "resting_hr_bpm": _round_or_none(_to_float_or_none(row.get("resting_hr_bpm")), 2),
        "mood_score": _round_or_none(_to_float_or_none(row.get("mood_score")), 1),
        "motivation_score": _round_or_none(_to_float_or_none(row.get("motivation_score")), 1),
        "fitness": _round_or_none(_to_float_or_none(fitness), 2),
        "fatigue": _round_or_none(_to_float_or_none(fatigue), 2),
        "form": _round_or_none(_safe_subtract(fitness, fatigue), 2),
        "ramp_rate": _round_or_none(_to_float_or_none(row.get("ramp_rate")), 2),
        "ride_eftp_watts": _round_or_none(_to_float_or_none(ride_eftp_watts), 2),
        "ride_eftp_wkg": _round_or_none(_watts_per_kg(ride_eftp_watts, weight_kg), 2),
        "run_eftp": _round_or_none(_to_float_or_none(run_eftp), 2),
        "run_eftp_wkg": _round_or_none(_watts_per_kg(run_eftp, weight_kg), 2),
        "notes": notes,
        "workouts": workouts,
    }


def _load_metrics_by_date(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM athlete_metrics_daily
        WHERE metric_date >= ? AND metric_date <= ?
        ORDER BY metric_date ASC
        """,
        (start_date, end_date),
    ).fetchall()
    return {dict(row)["metric_date"]: dict(row) for row in rows}


def _load_daily_notes_by_date(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT local_date, title, note_text
        FROM intervals_notes
        WHERE is_week_note = 0 AND local_date >= ? AND local_date <= ?
        ORDER BY local_date ASC, start_date_local ASC
        """,
        (start_date, end_date),
    ).fetchall()
    notes_by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        notes_by_date.setdefault(item["local_date"], []).append(_note_object(item))
    return notes_by_date


def _load_week_notes(
    connection: sqlite3.Connection,
    week_start_date: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT title, note_text
        FROM intervals_notes
        WHERE is_week_note = 1 AND local_date = ?
        ORDER BY start_date_local ASC
        """,
        (week_start_date,),
    ).fetchall()
    return [_note_object(dict(row)) for row in rows]


def _load_workouts_by_date(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT
            w.id,
            w.external_id,
            w.source,
            w.local_date,
            w.title,
            w.sport_type,
            w.sub_type,
            w.source_device,
            w.duration_seconds,
            w.avg_hr_bpm,
            w.max_hr_bpm,
            w.avg_power_watts,
            w.normalized_power_watts,
            w.training_load,
            w.perceived_exertion,
            w.workout_notes,
            w.raw_json,
            (
                SELECT wm.metric_value
                FROM workout_metrics wm
                WHERE wm.workout_id = w.id AND wm.metric_name = 'average_cadence'
                LIMIT 1
            ) AS cadence_avg,
            (
                SELECT wm.metric_value
                FROM workout_metrics wm
                WHERE wm.workout_id = w.id AND wm.metric_name = 'intensity_factor'
                LIMIT 1
            ) AS intensity_factor,
            (
                SELECT wm.metric_value
                FROM workout_metrics wm
                WHERE wm.workout_id = w.id AND wm.metric_name = 'eftp'
                LIMIT 1
            ) AS ftp_reference
        FROM workouts w
        WHERE w.local_date >= ? AND w.local_date <= ?
        ORDER BY w.local_date ASC, w.started_at_utc ASC
        """,
        (start_date, end_date),
    ).fetchall()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        item = dict(row)
        group_key = (
            item["local_date"],
            str(_first_non_null(item.get("external_id"), item.get("id"))),
        )
        grouped.setdefault(group_key, []).append(item)

    workouts_by_date: dict[str, list[dict[str, Any]]] = {}
    for (local_date, _), items in grouped.items():
        workout = _build_workout_object(items)
        if workout is None:
            continue
        workouts_by_date.setdefault(local_date, []).append(workout)
    return workouts_by_date


def _load_workout_counts_by_date(
    connection: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT
            local_date,
            COUNT(DISTINCT COALESCE(external_id, CAST(id AS TEXT))) AS workouts_count
        FROM workouts
        WHERE local_date >= ? AND local_date <= ?
        GROUP BY local_date
        ORDER BY local_date ASC
        """,
        (start_date, end_date),
    ).fetchall()
    return {dict(row)["local_date"]: int(dict(row)["workouts_count"]) for row in rows}


def _build_workout_object(items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    items = sorted(items, key=_workout_source_priority)
    raws = [_parse_json_or_none(item.get("raw_json")) or {} for item in items]

    title = _first_non_null(*[item.get("title") for item in items], *[raw.get("name") for raw in raws])
    sport_type = _first_non_null(
        *[item.get("sport_type") for item in items],
        *[raw.get("type") for raw in raws],
    )
    duration_seconds = _first_non_null(
        *[item.get("duration_seconds") for item in items],
        *[raw.get("elapsed_time") for raw in raws],
        *[raw.get("moving_time") for raw in raws],
    )
    power_avg = _first_non_null(
        *[item.get("avg_power_watts") for item in items],
        *[raw.get("icu_average_watts") for raw in raws],
        *[raw.get("average_watts") for raw in raws],
    )
    power_np = _first_non_null(
        *[item.get("normalized_power_watts") for item in items],
        *[raw.get("icu_norm_power") for raw in raws],
        *[raw.get("icu_weighted_avg_watts") for raw in raws],
        *[raw.get("weighted_avg_watts") for raw in raws],
    )
    intensity_factor = _first_non_null(
        *[item.get("intensity_factor") for item in items],
        *[raw.get("icu_intensity") for raw in raws],
    )
    ftp_reference = _first_non_null(
        *[item.get("ftp_reference") for item in items],
        *[raw.get("icu_ftp") for raw in raws],
        *[raw.get("icu_pm_ftp_watts") for raw in raws],
    )
    hr_avg = _first_non_null(
        *[item.get("avg_hr_bpm") for item in items],
        *[raw.get("average_heartrate") for raw in raws],
    )
    hr_max = _first_non_null(
        *[item.get("max_hr_bpm") for item in items],
        *[raw.get("max_heartrate") for raw in raws],
    )
    cadence_avg = _first_non_null(
        *[item.get("cadence_avg") for item in items],
        *[raw.get("average_cadence") for raw in raws],
    )
    rpe = _first_non_null(
        *[item.get("perceived_exertion") for item in items],
        *[raw.get("icu_rpe") for raw in raws],
    )
    training_load = _first_non_null(
        *[item.get("training_load") for item in items],
        *[raw.get("icu_training_load") for raw in raws],
    )
    workout_note = _first_non_null(
        *[item.get("workout_notes") for item in items],
        *[raw.get("description") for raw in raws],
    )

    if not any(
        value is not None
        for value in (title, sport_type, duration_seconds, power_np, hr_avg, training_load)
    ):
        return None

    workout = {
        "type": _session_type_label(sport_type),
        "name": title,
        "duration_min": _round_or_none(_seconds_to_minutes(duration_seconds), 1),
        "power_avg": _round_or_none(_to_float_or_none(power_avg), 0),
        "power_np": _round_or_none(_to_float_or_none(power_np), 0),
        "if": _round_or_none(_normalize_intensity_factor(intensity_factor), 2),
        "ftp_reference": _round_or_none(_to_float_or_none(ftp_reference), 0),
        "hr_avg": _round_or_none(_to_float_or_none(hr_avg), 0),
        "hr_max": _round_or_none(_to_float_or_none(hr_max), 0),
        "cadence_avg": _round_or_none(_to_float_or_none(cadence_avg), 0),
        "rpe": _round_or_none(_to_float_or_none(rpe), 1),
        "training_load": _round_or_none(_to_float_or_none(training_load), 1),
        "notes": _workout_notes_array(workout_note),
        "sport_type_raw": sport_type,
        "source_device": _first_non_null(
            *[item.get("source_device") for item in items],
            *[raw.get("device_name") for raw in raws],
        ),
    }
    return workout


def _trend_block(
    connection: sqlite3.Connection,
    current_date: str,
    windows: dict[str, int],
) -> dict[str, Any]:
    rows_by_window = {days: _load_metrics_rows(connection, current_date, days) for days in windows.values()}
    daily_90_rows = _load_metrics_rows(connection, current_date, 90)

    trends = {
        "sleep_hours": {
            "3d": _window_stat(
                rows_by_window[3],
                3,
                lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                digits=2,
                delta_vs_prev_window=_delta_between_windows(
                    rows_by_window[3],
                    _load_previous_metrics_rows(connection, current_date, 3),
                    lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                    digits=2,
                ),
                delta_vs_reference=_delta_vs_rows(
                    rows_by_window[3],
                    rows_by_window[28],
                    lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                    digits=2,
                ),
                delta_vs_reference_label="delta_vs_28d",
            ),
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                digits=2,
                delta_vs_reference=_delta_vs_rows(
                    rows_by_window[7],
                    rows_by_window[28],
                    lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                    digits=2,
                ),
                delta_vs_reference_label="delta_vs_28d",
            ),
            "14d": _window_stat(
                rows_by_window[14],
                14,
                lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                digits=2,
                delta_vs_reference=_delta_vs_rows(
                    rows_by_window[14],
                    rows_by_window[28],
                    lambda row: _seconds_to_hours(row.get("sleep_seconds")),
                    digits=2,
                ),
                delta_vs_reference_label="delta_vs_28d",
            ),
            "28d": _window_stat(rows_by_window[28], 28, lambda row: _seconds_to_hours(row.get("sleep_seconds")), digits=2),
        },
        "hrv": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("hrv_ms"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[14], lambda row: row.get("hrv_ms"), digits=2),
                delta_vs_reference_label="delta_vs_14d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("hrv_ms"), digits=2),
                },
            ),
            "14d": _window_stat(
                rows_by_window[14],
                14,
                lambda row: row.get("hrv_ms"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[14], daily_90_rows, lambda row: row.get("hrv_ms"), digits=2),
                },
            ),
        },
        "rhr": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("resting_hr_bpm"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[14], lambda row: row.get("resting_hr_bpm"), digits=2),
                delta_vs_reference_label="delta_vs_14d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("resting_hr_bpm"), digits=2),
                },
            ),
            "14d": _window_stat(
                rows_by_window[14],
                14,
                lambda row: row.get("resting_hr_bpm"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[14], daily_90_rows, lambda row: row.get("resting_hr_bpm"), digits=2),
                },
            ),
        },
        "vo2max": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("vo2max"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("vo2max"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("vo2max"), digits=2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: row.get("vo2max"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: row.get("vo2max"), digits=2),
                },
            ),
        },
        "form": {
            "3d": _window_stat(
                rows_by_window[3],
                3,
                lambda row: _safe_subtract(row.get("ctl"), row.get("atl")),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[3], rows_by_window[7], lambda row: _safe_subtract(row.get("ctl"), row.get("atl")), digits=2),
                delta_vs_reference_label="delta_vs_7d",
                extra_fields={"zone_majority": _form_zone_majority(rows_by_window[3])},
                include_sd=False,
            ),
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: _safe_subtract(row.get("ctl"), row.get("atl")),
                digits=2,
                extra_fields={"zone_majority": _form_zone_majority(rows_by_window[7])},
                include_sd=False,
            ),
        },
        "fatigue": {
            "7d": _window_stat(
                rows_by_window[7], 7, lambda row: row.get("atl"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("atl"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
            ),
            "28d": _window_stat(rows_by_window[28], 28, lambda row: row.get("atl"), digits=2),
        },
        "fitness": {
            "7d": _window_stat(
                rows_by_window[7], 7, lambda row: row.get("ctl"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("ctl"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                include_sd=False,
            ),
            "28d": _window_stat(rows_by_window[28], 28, lambda row: row.get("ctl"), digits=2, include_sd=False),
        },
        "weight_kg": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("weight_kg"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("weight_kg"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("weight_kg"), digits=2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: row.get("weight_kg"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: row.get("weight_kg"), digits=2),
                },
            ),
        },
        "ride_eftp_watts": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("ride_eftp_watts"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("ride_eftp_watts"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("ride_eftp_watts"), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[7], lambda row: row.get("ride_eftp_watts")), 2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: row.get("ride_eftp_watts"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: row.get("ride_eftp_watts"), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[28], lambda row: row.get("ride_eftp_watts")), 2),
                },
            ),
        },
        "ride_eftp_wkg": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: _row_ride_eftp_wkg(row, rows_by_window[7]),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: _row_ride_eftp_wkg(row, rows_by_window[7]), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: _row_ride_eftp_wkg(row, rows_by_window[7]), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[7], lambda row: _row_ride_eftp_wkg(row, rows_by_window[7])), 2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: _row_ride_eftp_wkg(row, rows_by_window[28]),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: _row_ride_eftp_wkg(row, rows_by_window[28]), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[28], lambda row: _row_ride_eftp_wkg(row, rows_by_window[28])), 2),
                },
            ),
        },
        "run_eftp": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: row.get("run_eftp"),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("run_eftp"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: row.get("run_eftp"), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[7], lambda row: row.get("run_eftp")), 2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: row.get("run_eftp"),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: row.get("run_eftp"), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[28], lambda row: row.get("run_eftp")), 2),
                },
            ),
        },
        "run_eftp_wkg": {
            "7d": _window_stat(
                rows_by_window[7],
                7,
                lambda row: _row_run_eftp_wkg(row, rows_by_window[7]),
                digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: _row_run_eftp_wkg(row, rows_by_window[7]), digits=2),
                delta_vs_reference_label="delta_vs_28d",
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[7], daily_90_rows, lambda row: _row_run_eftp_wkg(row, rows_by_window[7]), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[7], lambda row: _row_run_eftp_wkg(row, rows_by_window[7])), 2),
                },
            ),
            "28d": _window_stat(
                rows_by_window[28],
                28,
                lambda row: _row_run_eftp_wkg(row, rows_by_window[28]),
                digits=2,
                extra_fields={
                    "delta_vs_90d": _delta_vs_rows(rows_by_window[28], daily_90_rows, lambda row: _row_run_eftp_wkg(row, rows_by_window[28]), digits=2),
                    "best": _round_or_none(_max_value(rows_by_window[28], lambda row: _row_run_eftp_wkg(row, rows_by_window[28])), 2),
                },
            ),
        },
        "mood_score": {
            "7d": _window_stat(
                rows_by_window[7], 7, lambda row: row.get("mood_score"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("mood_score"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
            ),
        },
        "motivation_score": {
            "7d": _window_stat(
                rows_by_window[7], 7, lambda row: row.get("motivation_score"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("motivation_score"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
            ),
        },
    }
    return trends


def _build_long_term_baselines(
    connection: sqlite3.Connection,
    current_date: str,
) -> dict[str, Any]:
    rows_90 = _load_metrics_rows(connection, current_date, 90)
    rows_365 = _load_metrics_rows(connection, current_date, 365)
    rows_30 = _load_metrics_rows(connection, current_date, 30)
    return {
        "sleep_hours": {
            "90d": _baseline_stat(rows_90, 90, lambda row: _seconds_to_hours(row.get("sleep_seconds")), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: _seconds_to_hours(row.get("sleep_seconds")), digits=2),
        },
        "hrv": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("hrv_ms"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("hrv_ms"), digits=2),
        },
        "rhr": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("resting_hr_bpm"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("resting_hr_bpm"), digits=2),
        },
        "vo2max": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("vo2max"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("vo2max"), digits=2),
        },
        "form": {
            "90d": _baseline_stat(rows_90, 90, lambda row: _safe_subtract(row.get("ctl"), row.get("atl")), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: _safe_subtract(row.get("ctl"), row.get("atl")), digits=2),
        },
        "fatigue": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("atl"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("atl"), digits=2),
        },
        "fitness": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("ctl"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("ctl"), digits=2),
        },
        "weight_kg": {
            "90d": _baseline_stat(rows_90, 90, lambda row: row.get("weight_kg"), digits=2),
            "365d": _baseline_stat(rows_365, 365, lambda row: row.get("weight_kg"), digits=2),
        },
        "ride_eftp_watts": {
            "90d": _baseline_stat(
                rows_90,
                90,
                lambda row: row.get("ride_eftp_watts"),
                digits=2,
                extra_fields={
                    "best_30d": _round_or_none(_max_value(rows_30, lambda row: row.get("ride_eftp_watts")), 2),
                    "best_90d": _round_or_none(_max_value(rows_90, lambda row: row.get("ride_eftp_watts")), 2),
                },
            ),
            "365d": _baseline_stat(
                rows_365,
                365,
                lambda row: row.get("ride_eftp_watts"),
                digits=2,
                extra_fields={
                    "best_365d": _round_or_none(_max_value(rows_365, lambda row: row.get("ride_eftp_watts")), 2),
                },
            ),
        },
        "ride_eftp_wkg": {
            "90d": _baseline_stat(
                rows_90,
                90,
                lambda row: _row_ride_eftp_wkg(row, rows_90),
                digits=2,
                extra_fields={
                    "best_30d": _round_or_none(_max_value(rows_30, lambda row: _row_ride_eftp_wkg(row, rows_30)), 2),
                    "best_90d": _round_or_none(_max_value(rows_90, lambda row: _row_ride_eftp_wkg(row, rows_90)), 2),
                },
            ),
            "365d": _baseline_stat(
                rows_365,
                365,
                lambda row: _row_ride_eftp_wkg(row, rows_365),
                digits=2,
                extra_fields={
                    "best_365d": _round_or_none(_max_value(rows_365, lambda row: _row_ride_eftp_wkg(row, rows_365)), 2),
                },
            ),
        },
        "run_eftp": {
            "90d": _baseline_stat(
                rows_90,
                90,
                lambda row: row.get("run_eftp"),
                digits=2,
                extra_fields={
                    "best_30d": _round_or_none(_max_value(rows_30, lambda row: row.get("run_eftp")), 2),
                    "best_90d": _round_or_none(_max_value(rows_90, lambda row: row.get("run_eftp")), 2),
                },
            ),
            "365d": _baseline_stat(
                rows_365,
                365,
                lambda row: row.get("run_eftp"),
                digits=2,
                extra_fields={
                    "best_365d": _round_or_none(_max_value(rows_365, lambda row: row.get("run_eftp")), 2),
                },
            ),
        },
        "run_eftp_wkg": {
            "90d": _baseline_stat(
                rows_90,
                90,
                lambda row: _row_run_eftp_wkg(row, rows_90),
                digits=2,
                extra_fields={
                    "best_30d": _round_or_none(_max_value(rows_30, lambda row: _row_run_eftp_wkg(row, rows_30)), 2),
                    "best_90d": _round_or_none(_max_value(rows_90, lambda row: _row_run_eftp_wkg(row, rows_90)), 2),
                },
            ),
            "365d": _baseline_stat(
                rows_365,
                365,
                lambda row: _row_run_eftp_wkg(row, rows_365),
                digits=2,
                extra_fields={
                    "best_365d": _round_or_none(_max_value(rows_365, lambda row: _row_run_eftp_wkg(row, rows_365)), 2),
                },
            ),
        },
    }


def _load_weekly_row(
    connection: sqlite3.Connection,
    week_start_date: str,
) -> Optional[dict[str, Any]]:
    row = connection.execute(
        """
        SELECT *
        FROM intervals_weekly_stats
        WHERE week_start_date = ?
        LIMIT 1
        """,
        (week_start_date,),
    ).fetchone()
    return dict(row) if row is not None else None


def _load_metrics_rows(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> list[dict[str, Any]]:
    oldest = (date.fromisoformat(current_date) - timedelta(days=days - 1)).isoformat()
    rows = connection.execute(
        """
        SELECT *
        FROM athlete_metrics_daily
        WHERE metric_date <= ? AND metric_date >= ?
        ORDER BY metric_date DESC
        """,
        (current_date, oldest),
    ).fetchall()
    return [dict(row) for row in rows]


def _load_previous_metrics_rows(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> list[dict[str, Any]]:
    current_end = date.fromisoformat(current_date)
    previous_end = current_end - timedelta(days=days)
    previous_start = previous_end - timedelta(days=days - 1)
    rows = connection.execute(
        """
        SELECT *
        FROM athlete_metrics_daily
        WHERE metric_date >= ? AND metric_date <= ?
        ORDER BY metric_date DESC
        """,
        (previous_start.isoformat(), previous_end.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_metric_within_week(
    connection: sqlite3.Connection,
    week_start_date: Optional[str],
    column: str,
) -> Optional[float]:
    if not week_start_date:
        return None
    week_end_date = (date.fromisoformat(week_start_date) + timedelta(days=6)).isoformat()
    row = connection.execute(
        f"""
        SELECT {column}
        FROM athlete_metrics_daily
        WHERE metric_date >= ? AND metric_date <= ? AND {column} IS NOT NULL
        ORDER BY metric_date DESC
        LIMIT 1
        """,
        (week_start_date, week_end_date),
    ).fetchone()
    if row is None:
        return None
    return row[0]


def _category_eftp(by_category: Optional[list[dict[str, Any]]], category_name: str) -> Optional[float]:
    if not by_category:
        return None
    for item in by_category:
        if item.get("category") == category_name:
            eftp = item.get("eftp")
            if eftp is not None:
                return float(eftp)
    return None


def _watts_per_kg(power_watts: Optional[float], weight_kg: Optional[float]) -> Optional[float]:
    if power_watts is None or weight_kg in (None, 0):
        return None
    return float(power_watts) / float(weight_kg)


def _latest_known_weight_from_rows(rows: list[dict[str, Any]], metric_date: Optional[str]) -> Optional[float]:
    if metric_date is None:
        return None
    candidates = [
        row.get("weight_kg")
        for row in rows
        if row.get("metric_date") is not None
        and row.get("metric_date") <= metric_date
        and row.get("weight_kg") is not None
    ]
    return candidates[0] if candidates else None


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _note_object(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "text": item.get("note_text"),
    }


def _workout_notes_array(note_text: Optional[str]) -> list[dict[str, Any]]:
    if not note_text:
        return []
    return [{"title": None, "text": note_text}]


def _workout_source_priority(item: dict[str, Any]) -> tuple[int, int]:
    source = (item.get("source") or "").upper()
    priority_map = {
        "OAUTH_CLIENT": 0,
        "INTERVALS": 1,
        "": 2,
        "STRAVA": 9,
    }
    # Prefer richer upstream activity rows first; keep a deterministic fallback on id.
    return (priority_map.get(source, 3), int(item.get("id") or 0))


def _week_start_date(day_iso: str) -> str:
    day = date.fromisoformat(day_iso)
    return (day - timedelta(days=day.weekday())).isoformat()


def _iso_week_number(day_iso: str) -> int:
    return date.fromisoformat(day_iso).isocalendar().week


def _seconds_to_hours(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value) / 3600.0


def _seconds_to_minutes(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value) / 60.0


def _meters_to_km(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value) / 1000.0


def _session_type_label(sport_type: Optional[str]) -> Optional[str]:
    if not sport_type:
        return None
    mapping = {
        "VirtualRide": "bike_indoor",
        "Ride": "bike_outdoor",
        "Run": "run",
        "VirtualRun": "run_indoor",
        "Workout": "gym",
    }
    return mapping.get(sport_type, sport_type)


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _stdev(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(value) for value in values if value is not None]
    if len(cleaned) < 2:
        return None
    mean_value = sum(cleaned) / len(cleaned)
    variance = sum((value - mean_value) ** 2 for value in cleaned) / len(cleaned)
    return variance ** 0.5


def _max_value(rows: list[dict[str, Any]], value_fn: Any) -> Optional[float]:
    cleaned = [value_fn(row) for row in rows]
    cleaned = [float(value) for value in cleaned if value is not None]
    if not cleaned:
        return None
    return max(cleaned)


def _to_float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_intensity_factor(value: Any) -> Optional[float]:
    numeric = _to_float_or_none(value)
    if numeric is None:
        return None
    if numeric > 2.0:
        return numeric / 100.0
    return numeric


def _coefficient_of_variation(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(value) for value in values if value is not None]
    if len(cleaned) < 2:
        return None
    mean_value = sum(cleaned) / len(cleaned)
    if mean_value == 0:
        return None
    variance = sum((value - mean_value) ** 2 for value in cleaned) / len(cleaned)
    stdev = variance ** 0.5
    return (stdev / mean_value) * 100.0


def _safe_subtract(left: Any, right: Any) -> Optional[float]:
    if left is None or right is None:
        return None
    return float(left) - float(right)


def _round_or_none(value: Optional[float], digits: int) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def _parse_json_or_none(value: Optional[str]) -> Any:
    if not value:
        return None
    return json.loads(value)


def _prune_for_export(value: Any) -> Any:
    if isinstance(value, dict):
        pruned = {}
        for key, item in value.items():
            if item is None:
                continue
            cleaned = _prune_for_export(item)
            if cleaned is None:
                continue
            pruned[key] = cleaned
        return pruned

    if isinstance(value, list):
        pruned_list = []
        for item in value:
            if isinstance(item, dict) and "value" in item and item.get("value") is None:
                continue
            cleaned = _prune_for_export(item)
            if cleaned is None:
                continue
            pruned_list.append(cleaned)
        return pruned_list

    return value


def _window_stat(
    rows: list[dict[str, Any]],
    window_days: int,
    value_fn: Any,
    digits: int,
    delta_vs_prev_window: Optional[float] = None,
    delta_vs_reference: Optional[float] = None,
    delta_vs_reference_label: Optional[str] = None,
    extra_fields: Optional[dict[str, Any]] = None,
    include_sd: bool = True,
) -> dict[str, Any]:
    values = [value_fn(row) for row in rows]
    avg = _mean(values)
    item: dict[str, Any] = {
        "avg": _round_or_none(avg, digits),
        "n": len([value for value in values if value is not None]),
        "coverage_pct": _coverage_pct(values, window_days),
    }
    if include_sd:
        item["sd"] = _round_or_none(_stdev(values), digits)
    if delta_vs_prev_window is not None:
        item["delta_vs_prev_window"] = _round_or_none(delta_vs_prev_window, digits)
    if delta_vs_reference is not None and delta_vs_reference_label is not None:
        item[delta_vs_reference_label] = _round_or_none(delta_vs_reference, digits)
    if extra_fields:
        for key, value in extra_fields.items():
            item[key] = value
    return item


def _baseline_stat(
    rows: list[dict[str, Any]],
    window_days: int,
    value_fn: Any,
    digits: int,
    extra_fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    values = [value_fn(row) for row in rows]
    avg = _mean(values)
    sd = _stdev(values)
    item: dict[str, Any] = {
        "avg": _round_or_none(avg, digits),
        "sd": _round_or_none(sd, digits),
        "typical_low": _round_or_none(avg - sd, digits) if avg is not None and sd is not None else None,
        "typical_high": _round_or_none(avg + sd, digits) if avg is not None and sd is not None else None,
        "n": len([value for value in values if value is not None]),
        "coverage_pct": _coverage_pct(values, window_days),
    }
    if extra_fields:
        for key, value in extra_fields.items():
            item[key] = value
    return item


def _coverage_pct(values: list[Optional[float]], expected_count: int) -> int:
    if expected_count <= 0:
        return 0
    present = len([value for value in values if value is not None])
    return int(round((present / float(expected_count)) * 100.0))


def _delta_vs_rows(
    rows: list[dict[str, Any]],
    reference_rows: list[dict[str, Any]],
    value_fn: Any,
    digits: int,
) -> Optional[float]:
    current_avg = _mean(value_fn(row) for row in rows)
    reference_avg = _mean(value_fn(row) for row in reference_rows)
    if current_avg is None or reference_avg is None:
        return None
    return round(current_avg - reference_avg, digits)


def _delta_between_windows(
    rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    value_fn: Any,
    digits: int,
) -> Optional[float]:
    return _delta_vs_rows(rows, previous_rows, value_fn, digits)


def _form_zone(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    if value < -30:
        return "high risk"
    if value < -10:
        return "optimal"
    if value <= 5:
        return "grey"
    if value <= 20:
        return "fresh"
    return "transition"


def _form_zone_majority(rows: list[dict[str, Any]]) -> Optional[str]:
    counts: dict[str, int] = {}
    for row in rows:
        zone = _form_zone(_safe_subtract(row.get("ctl"), row.get("atl")))
        if zone is None:
            continue
        counts[zone] = counts.get(zone, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _row_weight(row: dict[str, Any], rows_context: list[dict[str, Any]]) -> Optional[float]:
    return _first_non_null(row.get("weight_kg"), _latest_known_weight_from_rows(rows_context, row.get("metric_date")))


def _row_ride_eftp_wkg(row: dict[str, Any], rows_context: list[dict[str, Any]]) -> Optional[float]:
    return _watts_per_kg(row.get("ride_eftp_watts"), _row_weight(row, rows_context))


def _row_run_eftp_wkg(row: dict[str, Any], rows_context: list[dict[str, Any]]) -> Optional[float]:
    return _watts_per_kg(row.get("run_eftp"), _row_weight(row, rows_context))
