from __future__ import annotations

import json
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
        "trends": _trend_block(connection, current_date, {"3d": 3, "7d": 7, "14d": 14, "28d": 28}),
    }
    snapshot["long_term_baselines"] = _build_long_term_baselines(connection, current_date)
    return snapshot


def export_metrics_file(
    snapshot: dict[str, Any],
    output_json_path: Path,
) -> None:
    export_snapshot = _prune_for_export(snapshot)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(export_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
    trends: dict[str, Any] = {}
    for label, days in windows.items():
        rows = _load_metrics_rows(connection, current_date, days)
        trends[label] = {
            "rows": len(rows),
            "coverage": _round_or_none(len(rows) / float(days), 2),
            "avg_sleep_hours": _round_or_none(
                _mean(_seconds_to_hours(row.get("sleep_seconds")) for row in rows), 2
            ),
            "avg_resting_hr_bpm": _round_or_none(
                _mean(row.get("resting_hr_bpm") for row in rows), 2
            ),
            "avg_weight_kg": _round_or_none(_mean(row.get("weight_kg") for row in rows), 2),
            "avg_hrv_ms": _round_or_none(_mean(row.get("hrv_ms") for row in rows), 2),
            "hrv_cv_pct": _round_or_none(_coefficient_of_variation(row.get("hrv_ms") for row in rows), 2),
            "avg_fitness": _round_or_none(_mean(row.get("ctl") for row in rows), 2),
            "avg_fatigue": _round_or_none(_mean(row.get("atl") for row in rows), 2),
            "avg_form": _round_or_none(
                _mean(_safe_subtract(row.get("ctl"), row.get("atl")) for row in rows), 2
            ),
            "avg_ramp_rate": _round_or_none(_mean(row.get("ramp_rate") for row in rows), 2),
            "avg_ride_eftp_watts": _round_or_none(
                _mean(row.get("ride_eftp_watts") for row in rows), 2
            ),
            "avg_ride_eftp_wkg": _round_or_none(
                _mean(
                    _watts_per_kg(
                        row.get("ride_eftp_watts"),
                        _first_non_null(row.get("weight_kg"), _latest_known_weight_from_rows(rows, row.get("metric_date"))),
                    )
                    for row in rows
                ),
                2,
            ),
            "avg_run_eftp": _round_or_none(_mean(row.get("run_eftp") for row in rows), 2),
            "avg_run_eftp_wkg": _round_or_none(
                _mean(
                    _watts_per_kg(
                        row.get("run_eftp"),
                        _first_non_null(row.get("weight_kg"), _latest_known_weight_from_rows(rows, row.get("metric_date"))),
                    )
                    for row in rows
                ),
                2,
            ),
            "subjective_averages": {
                "motivation_score": _round_or_none(_mean(row.get("motivation_score") for row in rows), 2),
                "mood_score": _round_or_none(_mean(row.get("mood_score") for row in rows), 2),
            },
        }
    return trends


def _build_long_term_baselines(
    connection: sqlite3.Connection,
    current_date: str,
) -> dict[str, Any]:
    return {
        "daily_90d": _daily_baseline(connection, current_date, 90),
        "daily_365d": _daily_baseline(connection, current_date, 365),
        "weekly_12w": _weekly_baseline_window(connection, current_date, 12),
        "weekly_52w": _weekly_baseline_window(connection, current_date, 52),
    }


def _daily_baseline(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> dict[str, Any]:
    rows = _load_metrics_rows(connection, current_date, days)
    return {
        "days": days,
        "rows": len(rows),
        "coverage": _round_or_none(len(rows) / float(days), 2),
        "sleep_hours_mean": _round_or_none(
            _mean(_seconds_to_hours(row.get("sleep_seconds")) for row in rows), 2
        ),
        "weight_mean": _round_or_none(_mean(row.get("weight_kg") for row in rows), 2),
        "resting_hr_mean": _round_or_none(_mean(row.get("resting_hr_bpm") for row in rows), 2),
        "hrv_mean": _round_or_none(_mean(row.get("hrv_ms") for row in rows), 2),
        "fitness_mean": _round_or_none(_mean(row.get("ctl") for row in rows), 2),
        "fatigue_mean": _round_or_none(_mean(row.get("atl") for row in rows), 2),
        "ride_eftp_mean": _round_or_none(_mean(row.get("ride_eftp_watts") for row in rows), 2),
        "ride_eftp_wkg_mean": _round_or_none(
            _mean(
                _watts_per_kg(
                    row.get("ride_eftp_watts"),
                    _first_non_null(row.get("weight_kg"), _latest_known_weight_from_rows(rows, row.get("metric_date"))),
                )
                for row in rows
            ),
            2,
        ),
        "run_eftp_mean": _round_or_none(_mean(row.get("run_eftp") for row in rows), 2),
        "run_eftp_wkg_mean": _round_or_none(
            _mean(
                _watts_per_kg(
                    row.get("run_eftp"),
                    _first_non_null(row.get("weight_kg"), _latest_known_weight_from_rows(rows, row.get("metric_date"))),
                )
                for row in rows
            ),
            2,
        ),
    }


def _weekly_baseline_window(
    connection: sqlite3.Connection,
    current_date: str,
    weeks: int,
) -> dict[str, Any]:
    oldest = (date.fromisoformat(current_date) - timedelta(days=(weeks * 7) - 1)).isoformat()
    rows = connection.execute(
        """
        SELECT distance_meters, elevation_gain_meters, calories_kcal, training_load, session_rpe_load
        FROM intervals_weekly_stats
        WHERE week_start_date >= ?
        ORDER BY week_start_date DESC
        """,
        (oldest,),
    ).fetchall()
    dict_rows = [dict(row) for row in rows]
    return {
        "weeks": weeks,
        "rows": len(dict_rows),
        "coverage": _round_or_none(len(dict_rows) / float(weeks), 2),
        "distance_km_mean": _round_or_none(
            _mean(_meters_to_km(row.get("distance_meters")) for row in dict_rows), 2
        ),
        "elevation_gain_m_mean": _round_or_none(
            _mean(row.get("elevation_gain_meters") for row in dict_rows), 1
        ),
        "calories_kcal_mean": _round_or_none(_mean(row.get("calories_kcal") for row in dict_rows), 0),
        "training_load_mean": _round_or_none(_mean(row.get("training_load") for row in dict_rows), 1),
        "session_rpe_load_mean": _round_or_none(
            _mean(row.get("session_rpe_load") for row in dict_rows), 1
        ),
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
