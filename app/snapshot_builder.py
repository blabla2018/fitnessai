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
        "snapshot_version": "v4",
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
    snapshot.update(_build_decision_layer(snapshot))
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
            w.elapsed_time_seconds,
            w.moving_time_seconds,
            w.distance_meters,
            w.avg_hr_bpm,
            w.max_hr_bpm,
            w.avg_power_watts,
            w.normalized_power_watts,
            w.training_load,
            w.perceived_exertion,
            w.description,
            w.average_speed_mps,
            w.max_speed_mps,
            w.is_trainer,
            w.is_race,
            w.is_commute,
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
    elapsed_time_seconds = _first_non_null(
        *[item.get("elapsed_time_seconds") for item in items],
        *[raw.get("elapsed_time") for raw in raws],
        *[raw.get("moving_time") for raw in raws],
    )
    moving_time_seconds = _first_non_null(
        *[item.get("moving_time_seconds") for item in items],
        *[raw.get("moving_time") for raw in raws],
    )
    distance_meters = _first_non_null(
        *[item.get("distance_meters") for item in items],
        *[raw.get("distance") for raw in raws],
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
        *[raw.get("description") for raw in raws],
    )
    session_rpe_load = _first_non_null(*[raw.get("session_rpe") for raw in raws])
    feel = _first_non_null(*[raw.get("feel") for raw in raws])
    power_load = _first_non_null(*[raw.get("power_load") for raw in raws])
    hr_load = _first_non_null(*[raw.get("hr_load") for raw in raws])
    decoupling = _first_non_null(*[raw.get("decoupling") for raw in raws])
    efficiency_factor = _first_non_null(*[raw.get("icu_efficiency_factor") for raw in raws])
    variability_index = _first_non_null(*[raw.get("icu_variability_index") for raw in raws])
    joules_above_ftp = _first_non_null(*[raw.get("icu_joules_above_ftp") for raw in raws])
    max_wbal_depletion = _first_non_null(*[raw.get("icu_max_wbal_depletion") for raw in raws])
    power_zone_times = _first_non_null(*[_normalize_power_zone_times(raw.get("icu_zone_times")) for raw in raws])
    hr_zone_times = _first_non_null(*[_normalize_hr_zone_times(raw.get("icu_hr_zone_times")) for raw in raws])
    commute_like = _first_non_null(
        *[_sqlite_bool(item.get("is_commute")) for item in items],
    )
    if commute_like is None:
        commute_like = _is_commute_like(title, sport_type, raws)
    session_class = _session_class(sport_type, title, power_zone_times, intensity_factor, commute_like)
    upper_zone_leakage_pct = _upper_zone_leakage_pct(power_zone_times) if session_class == "endurance" else None

    if not any(
        value is not None
        for value in (title, sport_type, elapsed_time_seconds, power_np, hr_avg, training_load)
    ):
        return None

    workout = {
        "type": _session_type_label(sport_type),
        "name": title,
        "duration_min": _round_or_none(_seconds_to_minutes(elapsed_time_seconds), 1),
        "elapsed_time_min": _round_or_none(_seconds_to_minutes(elapsed_time_seconds), 1),
        "moving_time_min": _round_or_none(_seconds_to_minutes(moving_time_seconds), 1),
        "distance_km": _round_or_none(_meters_to_km(distance_meters), 2),
        "power_avg": _round_or_none(_to_float_or_none(power_avg), 0),
        "power_np": _round_or_none(_to_float_or_none(power_np), 0),
        "if": _round_or_none(_normalize_intensity_factor(intensity_factor), 2),
        "ftp_reference": _round_or_none(_to_float_or_none(ftp_reference), 0),
        "hr_avg": _round_or_none(_to_float_or_none(hr_avg), 0),
        "hr_max": _round_or_none(_to_float_or_none(hr_max), 0),
        "cadence_avg": _round_or_none(_to_float_or_none(cadence_avg), 0),
        "rpe": _round_or_none(_to_float_or_none(rpe), 1),
        "session_rpe_load": _round_or_none(_to_float_or_none(session_rpe_load), 0),
        "training_load": _round_or_none(_to_float_or_none(training_load), 1),
        "feel": _round_or_none(_to_float_or_none(feel), 0),
        "power_load": _round_or_none(_to_float_or_none(power_load), 1),
        "hr_load": _round_or_none(_to_float_or_none(hr_load), 1),
        "decoupling_pct": _round_or_none(_to_float_or_none(decoupling), 2),
        "efficiency_factor": _round_or_none(_to_float_or_none(efficiency_factor), 3),
        "variability_index": _round_or_none(_to_float_or_none(variability_index), 3),
        "joules_above_ftp": _round_or_none(_to_float_or_none(joules_above_ftp), 0),
        "max_wbal_depletion": _round_or_none(_to_float_or_none(max_wbal_depletion), 0),
        "power_zone_times": power_zone_times,
        "hr_zone_times": hr_zone_times,
        "session_class": session_class,
        "is_commute_like": commute_like,
        "is_trainer": _first_non_null(*[_sqlite_bool(item.get("is_trainer")) for item in items], *[raw.get("trainer") for raw in raws]),
        "is_race": _first_non_null(*[_sqlite_bool(item.get("is_race")) for item in items], *[raw.get("race") for raw in raws]),
        "is_commute": commute_like,
        "average_speed_mps": _round_or_none(
            _to_float_or_none(
                _first_non_null(*[item.get("average_speed_mps") for item in items], *[raw.get("average_speed") for raw in raws])
            ),
            3,
        ),
        "max_speed_mps": _round_or_none(
            _to_float_or_none(
                _first_non_null(*[item.get("max_speed_mps") for item in items], *[raw.get("max_speed") for raw in raws])
            ),
            3,
        ),
        "upper_zone_leakage_pct": _round_or_none(upper_zone_leakage_pct, 1),
        "description": workout_note,
        "sport_type_raw": sport_type,
        "source_device": _first_non_null(
            *[item.get("source_device") for item in items],
            *[raw.get("device_name") for raw in raws],
        ),
    }
    workout["execution_verdict_precalc"] = _execution_verdict_precalc(workout)
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
            "14d": _window_stat(
                rows_by_window[14], 14, lambda row: row.get("mood_score"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[14], rows_by_window[28], lambda row: row.get("mood_score"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
            ),
        },
        "motivation_score": {
            "7d": _window_stat(
                rows_by_window[7], 7, lambda row: row.get("motivation_score"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[7], rows_by_window[28], lambda row: row.get("motivation_score"), digits=2),
                delta_vs_reference_label="delta_vs_28d",
            ),
            "14d": _window_stat(
                rows_by_window[14], 14, lambda row: row.get("motivation_score"), digits=2,
                delta_vs_reference=_delta_vs_rows(rows_by_window[14], rows_by_window[28], lambda row: row.get("motivation_score"), digits=2),
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


def _build_decision_layer(snapshot: dict[str, Any]) -> dict[str, Any]:
    decision_inputs = _build_decision_inputs(snapshot)
    decision_support = _build_decision_support(snapshot)
    recovery_signals = _build_recovery_signals(snapshot, decision_inputs, decision_support)
    contradictions = _build_contradictions(snapshot, decision_inputs)
    decision_flags = _build_decision_flags(decision_inputs, recovery_signals, contradictions, decision_support)
    reason_codes = _build_reason_codes(decision_inputs, decision_support, recovery_signals, contradictions)
    recommended_load_action = _recommended_load_action(decision_inputs, contradictions, recovery_signals, decision_support)
    load_action_detail = _build_load_action_detail(recommended_load_action)
    plan_adherence = _build_plan_adherence(snapshot)
    confidence_precalc = _decision_confidence(decision_inputs, contradictions)
    decision_debug = _build_decision_debug(decision_inputs, contradictions, recovery_signals, confidence_precalc)
    result = {
        "decision_inputs": decision_inputs,
        "decision_flags": decision_flags,
        "reason_codes": reason_codes,
        "contradictions": contradictions,
        "decision_support": decision_support,
        "recovery_signals": recovery_signals,
        "load_action_detail": load_action_detail,
        "decision_debug": decision_debug,
        "recommended_load_action": recommended_load_action,
        "confidence_precalc": confidence_precalc,
    }
    if plan_adherence is not None:
        result["plan_adherence"] = plan_adherence
    return result


def _build_decision_inputs(snapshot: dict[str, Any]) -> dict[str, Any]:
    sleep_state = _sleep_state(snapshot)
    fatigue_state = _fatigue_state(snapshot)
    fitness_state = _fitness_state(snapshot)
    capacity_state = _capacity_state(snapshot)
    subjective_state = _subjective_state(snapshot)
    form_zone = _trend_value(snapshot, "form", "3d", "zone_majority") or _trend_value(snapshot, "form", "7d", "zone_majority")
    readiness_state = _readiness_state(snapshot, sleep_state, fatigue_state, subjective_state, form_zone)
    process_state = _process_state(readiness_state, fatigue_state, fitness_state, capacity_state, form_zone)
    data_quality_state = _data_quality_state(snapshot)
    return {
        "readiness_state": readiness_state,
        "fatigue_state": fatigue_state,
        "fitness_state": fitness_state,
        "capacity_state": capacity_state,
        "form_zone": form_zone,
        "sleep_state": sleep_state,
        "weight_state": _weight_state(snapshot),
        "subjective_state": subjective_state,
        "process_state": process_state,
        "data_quality_state": data_quality_state,
    }


def _build_decision_support(snapshot: dict[str, Any]) -> dict[str, Any]:
    current_day = ((snapshot.get("current_week") or {}).get("days") or [{}])[-1]
    capacity_metric = _capacity_metric_name(snapshot)
    recent_workouts = _recent_workouts(snapshot, lookback_days=14)
    execution_workouts = [item for item in recent_workouts if _workout_is_execution_eligible(item)]
    workouts_with_execution = [item for item in execution_workouts if _workout_has_execution_metrics(item)]
    expensive_workouts = [item for item in recent_workouts if _workout_is_expensive(item)]
    current_week_workouts = _recent_workouts(snapshot, current_week_only=True)
    last_workout = execution_workouts[0] if execution_workouts else None
    key_workout = _select_key_workout(snapshot)
    return {
        "sleep_7d_avg": _trend_avg(snapshot, "sleep_hours", "7d"),
        "sleep_delta_vs_28d": _trend_numeric(snapshot, "sleep_hours", "7d", "delta_vs_28d"),
        "sleep_delta_vs_90d": _delta_avg_vs_baseline(snapshot, "sleep_hours", "7d", "90d"),
        "sleep_7d_coverage_pct": _trend_int(snapshot, "sleep_hours", "7d", "coverage_pct"),
        "hrv_7d_avg": _trend_avg(snapshot, "hrv", "7d"),
        "hrv_delta_vs_14d": _trend_numeric(snapshot, "hrv", "7d", "delta_vs_14d"),
        "hrv_delta_vs_90d": _trend_numeric(snapshot, "hrv", "7d", "delta_vs_90d"),
        "hrv_7d_coverage_pct": _trend_int(snapshot, "hrv", "7d", "coverage_pct"),
        "rhr_7d_avg": _trend_avg(snapshot, "rhr", "7d"),
        "rhr_delta_vs_14d": _trend_numeric(snapshot, "rhr", "7d", "delta_vs_14d"),
        "rhr_delta_vs_90d": _trend_numeric(snapshot, "rhr", "7d", "delta_vs_90d"),
        "rhr_7d_coverage_pct": _trend_int(snapshot, "rhr", "7d", "coverage_pct"),
        "fatigue_7d_avg": _trend_avg(snapshot, "fatigue", "7d"),
        "fatigue_delta_vs_28d": _trend_numeric(snapshot, "fatigue", "7d", "delta_vs_28d"),
        "fitness_7d_avg": _trend_avg(snapshot, "fitness", "7d"),
        "fitness_delta_vs_28d": _trend_numeric(snapshot, "fitness", "7d", "delta_vs_28d"),
        "fatigue_current": _to_float_or_none(current_day.get("fatigue")),
        "fitness_current": _to_float_or_none(current_day.get("fitness")),
        "form_current": _to_float_or_none(current_day.get("form")),
        "form_3d_avg": _trend_avg(snapshot, "form", "3d"),
        "form_7d_avg": _trend_avg(snapshot, "form", "7d"),
        "form_zone": _trend_value(snapshot, "form", "3d", "zone_majority") or _trend_value(snapshot, "form", "7d", "zone_majority"),
        "capacity_metric": capacity_metric,
        "capacity_metric_group": _capacity_metric_group(capacity_metric),
        "capacity_source_priority": ["ride_eftp_watts", "ride_eftp_wkg", "run_eftp", "run_eftp_wkg"],
        "capacity_7d_avg": _trend_avg(snapshot, capacity_metric, "7d"),
        "capacity_delta_vs_28d": _trend_numeric(snapshot, capacity_metric, "7d", "delta_vs_28d"),
        "capacity_delta_vs_90d": _trend_numeric(snapshot, capacity_metric, "7d", "delta_vs_90d"),
        "capacity_7d_best": _trend_numeric(snapshot, capacity_metric, "7d", "best"),
        "weight_7d_avg": _trend_avg(snapshot, "weight_kg", "7d"),
        "weight_delta_vs_28d": _trend_numeric(snapshot, "weight_kg", "7d", "delta_vs_28d"),
        "weight_delta_vs_90d": _trend_numeric(snapshot, "weight_kg", "7d", "delta_vs_90d"),
        "weight_7d_coverage_pct": _trend_int(snapshot, "weight_kg", "7d", "coverage_pct"),
        "mood_7d_avg": _trend_avg(snapshot, "mood_score", "7d"),
        "motivation_7d_avg": _trend_avg(snapshot, "motivation_score", "7d"),
        "subjective_7d_coverage_pct": min(
            _trend_int(snapshot, "mood_score", "7d", "coverage_pct") or 0,
            _trend_int(snapshot, "motivation_score", "7d", "coverage_pct") or 0,
        ) or None,
        "recent_workouts_with_execution_metrics": len(workouts_with_execution),
        "expensive_sessions_14d": len(expensive_workouts),
        "steady_sessions_high_decoupling_14d": len([item for item in execution_workouts if _workout_has_high_decoupling(item)]),
        "hr_load_above_power_load_sessions_14d": len([item for item in execution_workouts if _workout_hr_load_above_power_load(item)]),
        "high_cost_sessions_14d": len([item for item in execution_workouts if _workout_cost_high_for_output(item)]),
        "expensive_sessions_current_week": len([item for item in current_week_workouts if _workout_is_expensive(item)]),
        "last_execution_session_expensive": _workout_is_expensive(last_workout) if last_workout is not None else None,
        "last_execution_session_type": (last_workout or {}).get("type"),
        "last_execution_session_decoupling_pct": _to_float_or_none((last_workout or {}).get("decoupling_pct")),
        "last_execution_session_if": _to_float_or_none((last_workout or {}).get("if")),
        "last_execution_session_rpe": _to_float_or_none((last_workout or {}).get("rpe")),
        "last_execution_session_feel": _to_float_or_none((last_workout or {}).get("feel")),
        "key_workout_date": (key_workout or {}).get("date"),
        "key_workout_name": (key_workout or {}).get("name"),
        "key_workout_type": (key_workout or {}).get("type"),
        "key_workout_session_class": (key_workout or {}).get("session_class"),
        "key_workout_execution_verdict": (key_workout or {}).get("execution_verdict_precalc"),
    }


def _build_recovery_signals(
    snapshot: dict[str, Any],
    decision_inputs: dict[str, Any],
    decision_support: dict[str, Any],
) -> dict[str, Any]:
    expensive_sessions_14d = _to_float_or_none(decision_support.get("expensive_sessions_14d"))
    signals = {
        "sleep_below_baseline": decision_inputs["sleep_state"] in {"below_baseline", "well_below_baseline"},
        "sleep_well_below_baseline": decision_inputs["sleep_state"] == "well_below_baseline",
        "hrv_suppressed": _hrv_suppressed(snapshot),
        "rhr_elevated": _rhr_elevated(snapshot),
        "fatigue_gt_fitness": _fatigue_gt_fitness(snapshot),
        "fatigue_above_recent_norm": decision_inputs["fatigue_state"] in {"elevated", "high"},
        "subjective_low": decision_inputs["subjective_state"] == "strained" if decision_inputs["subjective_state"] != "insufficient_data" else None,
        "form_deeply_negative": decision_inputs["form_zone"] == "high risk" if decision_inputs["form_zone"] is not None else None,
        "high_rpe_at_moderate_if": _high_rpe_at_moderate_if(snapshot),
        "recent_expensive_execution": _latest_workout_expensive(snapshot),
        "repeated_expensive_execution": expensive_sessions_14d is not None and expensive_sessions_14d >= 2,
    }
    expensive_execution_present = bool(signals["recent_expensive_execution"]) or bool(signals["repeated_expensive_execution"])
    total_signal_values = [
        signals["sleep_below_baseline"],
        signals["hrv_suppressed"],
        signals["rhr_elevated"],
        signals["fatigue_gt_fitness"],
        signals["fatigue_above_recent_norm"],
        signals["subjective_low"],
        signals["form_deeply_negative"],
        signals["high_rpe_at_moderate_if"],
        expensive_execution_present,
    ]
    strong_signal_values = [
        signals["sleep_well_below_baseline"],
        signals["form_deeply_negative"],
        signals["high_rpe_at_moderate_if"],
        signals["hrv_suppressed"],
        signals["rhr_elevated"],
        signals["repeated_expensive_execution"],
    ]
    signals["count_total"] = len([value for value in total_signal_values if value is True])
    signals["count_strong"] = len([value for value in strong_signal_values if value is True])
    return signals


def _build_contradictions(snapshot: dict[str, Any], decision_inputs: dict[str, Any]) -> list[str]:
    contradictions: list[str] = []
    sleep_state = decision_inputs["sleep_state"]
    capacity_state = decision_inputs["capacity_state"]
    readiness_state = decision_inputs["readiness_state"]
    subjective_state = decision_inputs["subjective_state"]
    mood_avg = _trend_avg(snapshot, "mood_score", "7d")
    motivation_avg = _trend_avg(snapshot, "motivation_score", "7d")

    if sleep_state in {"below_baseline", "well_below_baseline"} and not _hrv_suppressed(snapshot):
        contradictions.append("poor_sleep_but_hrv_neutral")
    if sleep_state in {"below_baseline", "well_below_baseline"} and not _rhr_elevated(snapshot):
        contradictions.append("poor_sleep_but_rhr_neutral")
    if mood_avg is not None and motivation_avg is not None and mood_avg <= 2.0 and motivation_avg >= 3.5:
        contradictions.append("good_mood_but_low_motivation")
    if mood_avg is not None and motivation_avg is not None and mood_avg >= 3.5 and motivation_avg <= 2.0:
        contradictions.append("high_motivation_but_low_mood")
    if capacity_state in {"stable", "improving"} and readiness_state in {"reduced", "poor"}:
        contradictions.append("stable_capacity_but_reduced_readiness")
    if subjective_state == "supportive" and decision_inputs["fatigue_state"] in {"elevated", "high"}:
        contradictions.append("good_subjective_but_elevated_load_signals")
    if subjective_state == "supportive" and _high_rpe_at_moderate_if(snapshot):
        contradictions.append("good_subjective_but_high_rpe_for_moderate_if")
    if capacity_state in {"stable", "improving"} and _recent_expensive_sessions_count(snapshot) >= 2:
        contradictions.append("stable_capacity_but_expensive_execution")
    return contradictions


def _build_decision_flags(
    decision_inputs: dict[str, Any],
    recovery_signals: dict[str, Any],
    contradictions: list[str],
    decision_support: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    if recovery_signals["sleep_below_baseline"]:
        flags.append("sleep_below_baseline")
    if recovery_signals["hrv_suppressed"]:
        flags.append("hrv_suppressed")
    if recovery_signals["rhr_elevated"]:
        flags.append("rhr_elevated")
    if recovery_signals["fatigue_above_recent_norm"]:
        flags.append("fatigue_above_recent_norm")
    if recovery_signals["fatigue_gt_fitness"]:
        flags.append("fatigue_gt_fitness")
    if decision_inputs["form_zone"] is not None:
        flags.append(f"form_{decision_inputs['form_zone'].replace(' ', '_')}")
    if decision_inputs["capacity_state"] != "insufficient_data":
        flags.append(f"capacity_{decision_inputs['capacity_state']}")
    if decision_inputs["weight_state"] in {"drifting_up", "drifting_down"}:
        flags.append(f"weight_{decision_inputs['weight_state']}")
    if decision_inputs["subjective_state"] in {"mixed", "strained"}:
        flags.append(f"subjective_{decision_inputs['subjective_state']}")
    if recovery_signals.get("recent_expensive_execution"):
        flags.append("recent_expensive_execution")
    if recovery_signals.get("repeated_expensive_execution"):
        flags.append("repeated_expensive_execution")
    if (decision_support.get("hr_load_above_power_load_sessions_14d") or 0) >= 1:
        flags.append("hr_load_above_power_load")
    if (decision_support.get("high_cost_sessions_14d") or 0) >= 1:
        flags.append("session_cost_high_for_output")
    if decision_support.get("capacity_metric_group"):
        flags.append(f"capacity_group_{decision_support['capacity_metric_group']}")
    if contradictions:
        flags.append("contradictions_present")
    return flags


def _build_reason_codes(
    decision_inputs: dict[str, Any],
    decision_support: dict[str, Any],
    recovery_signals: dict[str, Any],
    contradictions: list[str],
) -> list[str]:
    reasons: list[str] = []
    sleep_delta_28 = decision_support.get("sleep_delta_vs_28d")
    if sleep_delta_28 is not None and sleep_delta_28 <= -0.3:
        reasons.append("sleep_7d_below_28d")
    if decision_inputs["sleep_state"] == "well_below_baseline":
        reasons.append("sleep_7d_below_90d_typical_low")
    if recovery_signals["hrv_suppressed"]:
        reasons.append("hrv_7d_suppressed_vs_90d")
    if recovery_signals["rhr_elevated"]:
        reasons.append("rhr_7d_elevated_vs_90d")
    fatigue_delta_28 = decision_support.get("fatigue_delta_vs_28d")
    if fatigue_delta_28 is not None and fatigue_delta_28 >= 3:
        reasons.append("fatigue_7d_above_28d")
    if recovery_signals["fatigue_gt_fitness"]:
        reasons.append("fatigue_gt_fitness")
    if decision_inputs["form_zone"] is not None:
        reasons.append(f"form_3d_in_{decision_inputs['form_zone'].replace(' ', '_')}_zone")
    if decision_inputs["capacity_state"] == "stable":
        reasons.append(f"{_capacity_metric_prefix_from_metric(decision_support.get('capacity_metric'))}_7d_stable_vs_28d")
    elif decision_inputs["capacity_state"] == "improving":
        reasons.append(f"{_capacity_metric_prefix_from_metric(decision_support.get('capacity_metric'))}_7d_improving_vs_28d")
    elif decision_inputs["capacity_state"] in {"drifting_down", "clearly_down"}:
        reasons.append(f"{_capacity_metric_prefix_from_metric(decision_support.get('capacity_metric'))}_7d_down_vs_90d")
    if decision_inputs["weight_state"] == "drifting_up":
        reasons.append("weight_7d_up_vs_28d")
    elif decision_inputs["weight_state"] == "drifting_down":
        reasons.append("weight_7d_down_vs_28d")
    if decision_inputs["subjective_state"] == "strained":
        reasons.append("subjective_7d_strained")
    elif decision_inputs["subjective_state"] == "mixed":
        reasons.append("subjective_7d_mixed")
    if (decision_support.get("expensive_sessions_14d") or 0) >= 1:
        reasons.append("expensive_execution_14d_present")
    if (decision_support.get("expensive_sessions_14d") or 0) >= 2:
        reasons.append("repeated_expensive_execution")
    if (decision_support.get("hr_load_above_power_load_sessions_14d") or 0) >= 1:
        reasons.append("hr_load_above_power_load")
    if (decision_support.get("high_cost_sessions_14d") or 0) >= 1:
        reasons.append("session_cost_high_for_output")
    if recovery_signals["high_rpe_at_moderate_if"]:
        reasons.append("high_rpe_at_moderate_if")
    if "stable_capacity_but_reduced_readiness" in contradictions:
        reasons.append("stable_capacity_with_reduced_readiness")
    if "stable_capacity_but_expensive_execution" in contradictions:
        reasons.append("stable_capacity_with_expensive_execution")
    return reasons


def _sleep_state(snapshot: dict[str, Any]) -> str:
    trend = _trend_window(snapshot, "sleep_hours", "7d")
    if not _window_has_usable_coverage(trend, min_n=5):
        return "insufficient_data"
    avg = trend.get("avg")
    delta_28 = trend.get("delta_vs_28d")
    delta_90 = _delta_avg_vs_baseline(snapshot, "sleep_hours", "7d", "90d")
    baseline_avg = _baseline_value(snapshot, "sleep_hours", "90d", "avg")
    baseline_low = _baseline_value(snapshot, "sleep_hours", "90d", "typical_low")
    if avg is None:
        return "insufficient_data"
    if (baseline_low is not None and avg < baseline_low) or (delta_90 is not None and delta_90 <= -0.8):
        return "well_below_baseline"
    if (baseline_avg is not None and avg < baseline_avg) or (delta_28 is not None and delta_28 <= -0.3):
        return "below_baseline"
    if delta_28 is not None and delta_28 >= 0.3:
        return "above_baseline"
    return "near_baseline"


def _fatigue_state(snapshot: dict[str, Any]) -> str:
    fatigue_avg = _trend_avg(snapshot, "fatigue", "7d")
    fatigue_delta = _trend_value(snapshot, "fatigue", "7d", "delta_vs_28d")
    fitness_avg = _trend_avg(snapshot, "fitness", "7d")
    if fatigue_avg is None or fitness_avg is None:
        return "insufficient_data"
    balance = fitness_avg - fatigue_avg
    if fatigue_delta is not None and (fatigue_delta >= 20 or balance <= -20):
        return "high"
    if fatigue_delta is not None and (fatigue_delta >= 8 or balance <= -8):
        return "elevated"
    if fatigue_delta is not None and fatigue_delta <= -8 and balance >= 0:
        return "low"
    return "normal"


def _fitness_state(snapshot: dict[str, Any]) -> str:
    trend = _trend_window(snapshot, "fitness", "7d")
    if not _window_has_usable_coverage(trend, min_n=5):
        return "insufficient_data"
    delta_28 = trend.get("delta_vs_28d")
    if delta_28 is None:
        return "insufficient_data"
    if delta_28 >= 2.0:
        return "rising"
    if delta_28 <= -2.0:
        return "falling"
    return "stable"


def _capacity_state(snapshot: dict[str, Any]) -> str:
    metric_name = _capacity_metric_name(snapshot)
    trend = _trend_window(snapshot, metric_name, "7d")
    if not _window_has_usable_coverage(trend, min_n=5):
        return "insufficient_data"
    delta_28 = trend.get("delta_vs_28d")
    delta_90 = trend.get("delta_vs_90d")
    if delta_28 is None:
        return "insufficient_data"
    if delta_28 >= 2.0:
        return "improving"
    if (delta_28 <= -5.0) or (delta_90 is not None and delta_90 <= -8.0):
        return "clearly_down"
    if delta_28 <= -2.0:
        return "drifting_down"
    return "stable"


def _weight_state(snapshot: dict[str, Any]) -> str:
    trend = _trend_window(snapshot, "weight_kg", "7d")
    if not _window_has_usable_coverage(trend, min_n=3):
        return "insufficient_data"
    delta_28 = trend.get("delta_vs_28d")
    if delta_28 is None:
        return "insufficient_data"
    if delta_28 >= 0.7:
        return "drifting_up"
    if delta_28 <= -0.7:
        return "drifting_down"
    return "stable"


def _subjective_state(snapshot: dict[str, Any]) -> str:
    mood = _trend_window(snapshot, "mood_score", "7d")
    motivation = _trend_window(snapshot, "motivation_score", "7d")
    mood_coverage = int(mood.get("coverage_pct") or 0)
    motivation_coverage = int(motivation.get("coverage_pct") or 0)
    if mood_coverage < 50 or motivation_coverage < 50:
        return "insufficient_data"
    mood_avg = mood.get("avg")
    motivation_avg = motivation.get("avg")
    if mood_avg is None or motivation_avg is None:
        return "insufficient_data"
    if mood_avg <= 2.0 and motivation_avg <= 2.0:
        return "supportive"
    if mood_avg >= 3.0 and motivation_avg >= 3.0:
        return "strained"
    if (mood_avg >= 3.0 and motivation_avg <= 2.0) or (mood_avg <= 2.0 and motivation_avg >= 3.0):
        return "mixed"
    return "mixed"


def _readiness_state(
    snapshot: dict[str, Any],
    sleep_state: str,
    fatigue_state: str,
    subjective_state: str,
    form_zone: Optional[str],
) -> str:
    warnings = _recovery_signal_count(snapshot, sleep_state, fatigue_state, subjective_state, form_zone)
    if warnings >= 3:
        return "poor"
    if warnings >= 2:
        return "reduced"
    if warnings == 0 and sleep_state in {"near_baseline", "above_baseline"} and fatigue_state in {"low", "normal"}:
        if subjective_state in {"supportive", "insufficient_data"}:
            return "ready"
    if warnings == 0:
        return "stable"
    return "reduced"


def _process_state(
    readiness_state: str,
    fatigue_state: str,
    fitness_state: str,
    capacity_state: str,
    form_zone: Optional[str],
) -> str:
    if readiness_state == "poor" and fatigue_state == "high" and form_zone == "high risk":
        return "process_showing_overload"
    if readiness_state in {"reduced", "poor"} and capacity_state in {"stable", "improving"}:
        return "process_working_but_constrained"
    if readiness_state in {"ready", "stable"} and capacity_state in {"stable", "improving"} and fitness_state in {"rising", "stable"}:
        return "process_working_well"
    if capacity_state in {"drifting_down", "clearly_down"} or fitness_state == "falling":
        return "process_mixed_unstable"
    return "process_mixed_unstable"


def _recovery_signal_count(
    snapshot: dict[str, Any],
    sleep_state: str,
    fatigue_state: str,
    subjective_state: str,
    form_zone: Optional[str],
) -> int:
    count = 0
    if sleep_state in {"below_baseline", "well_below_baseline"}:
        count += 1
    if _hrv_suppressed(snapshot):
        count += 1
    if _rhr_elevated(snapshot):
        count += 1
    if fatigue_state in {"elevated", "high"}:
        count += 1
    if subjective_state == "strained":
        count += 1
    if form_zone == "high risk":
        count += 1
    return count


def _recommended_load_action(
    decision_inputs: dict[str, Any],
    contradictions: list[str],
    recovery_signals: dict[str, Any],
    decision_support: dict[str, Any],
) -> str:
    readiness_state = decision_inputs["readiness_state"]
    fatigue_state = decision_inputs["fatigue_state"]
    form_zone = decision_inputs["form_zone"]
    process_state = decision_inputs["process_state"]
    subjective_state = decision_inputs["subjective_state"]

    if process_state == "process_showing_overload" and form_zone == "high risk":
        return "deload_week"
    if recovery_signals["repeated_expensive_execution"] and fatigue_state in {"elevated", "high"}:
        return "reduce_20_30"
    if readiness_state == "poor" or recovery_signals["count_strong"] >= 2:
        return "recovery_day"
    if fatigue_state == "high" and recovery_signals["count_total"] >= 3:
        return "recovery_day"
    if readiness_state == "reduced" or fatigue_state in {"elevated", "high"}:
        return "reduce_20_30"
    if recovery_signals["recent_expensive_execution"] or (decision_support.get("expensive_sessions_14d") or 0) >= 2:
        return "keep_but_simplify"
    if subjective_state in {"mixed", "strained"} or contradictions:
        return "keep_but_simplify"
    return "keep"


def _build_load_action_detail(recommended_load_action: str) -> dict[str, Any]:
    base = {
        "primary": recommended_load_action,
        "reduce_volume_pct": 0,
        "reduce_intensity_pct": 0,
        "avoid_session_types": [],
        "prefer_session_types": [],
        "lift_restriction": "none",
        "session_complexity": "normal",
        "action_rationale_short": "Keep the planned structure."
    }
    if recommended_load_action == "keep_but_simplify":
        base.update({
            "reduce_volume_pct": 0,
            "reduce_intensity_pct": 0,
            "avoid_session_types": ["complex_threshold"],
            "prefer_session_types": ["z2", "technique"],
            "lift_restriction": "keep_submaximal",
            "session_complexity": "simplify",
            "action_rationale_short": "Keep frequency but lower psychological and execution cost.",
        })
    elif recommended_load_action == "reduce_20_30":
        base.update({
            "reduce_volume_pct": 20,
            "reduce_intensity_pct": 10,
            "avoid_session_types": ["vo2max", "long_threshold"],
            "prefer_session_types": ["z2", "easy_endurance", "technique"],
            "lift_restriction": "keep_submaximal",
            "session_complexity": "simplify",
            "action_rationale_short": "Reduce cost while preserving useful work.",
        })
    elif recommended_load_action == "recovery_day":
        base.update({
            "reduce_volume_pct": 60,
            "reduce_intensity_pct": 100,
            "avoid_session_types": ["vo2max", "threshold", "heavy_strength"],
            "prefer_session_types": ["recovery_spin", "walk", "mobility"],
            "lift_restriction": "skip_strength",
            "session_complexity": "recovery_only",
            "action_rationale_short": "Prioritize recovery over stimulus today.",
        })
    elif recommended_load_action == "deload_week":
        base.update({
            "reduce_volume_pct": 40,
            "reduce_intensity_pct": 50,
            "avoid_session_types": ["vo2max", "threshold", "heavy_strength", "long_threshold"],
            "prefer_session_types": ["z2", "easy_endurance", "mobility", "technique"],
            "lift_restriction": "avoid_heavy_lower",
            "session_complexity": "simplify",
            "action_rationale_short": "Reduce weekly stress and rebuild freshness.",
        })
    return base


def _build_plan_adherence(snapshot: dict[str, Any]) -> Optional[dict[str, Any]]:
    return None


def _build_decision_debug(
    decision_inputs: dict[str, Any],
    contradictions: list[str],
    recovery_signals: dict[str, Any],
    confidence_precalc: str,
) -> dict[str, Any]:
    if recovery_signals["count_strong"] >= 2:
        load_decision_trigger = "strong_recovery_signals"
    elif recovery_signals.get("repeated_expensive_execution"):
        load_decision_trigger = "repeated_expensive_execution"
    elif recovery_signals.get("recent_expensive_execution"):
        load_decision_trigger = "recent_expensive_execution"
    elif decision_inputs["fatigue_state"] in {"elevated", "high"} and decision_inputs["sleep_state"] in {"below_baseline", "well_below_baseline"}:
        load_decision_trigger = "fatigue_plus_sleep"
    elif contradictions:
        load_decision_trigger = "contradictions_plus_caution"
    else:
        load_decision_trigger = "baseline_stability"
    return {
        "load_decision_trigger": load_decision_trigger,
        "load_decision_overridden_by": None,
        "confidence_downgraded_by_contradictions": bool(contradictions) and confidence_precalc != "high",
        "sleep_state_rule": "well_below_baseline only below 90d typical_low or delta_vs_90d <= -0.8h",
        "subjective_state_rule": "mixed allowed when 7d coverage >= 50% and mood/motivation conflict is visible",
        "recovery_day_rule": "poor readiness or 2+ strong signals or high fatigue plus 3+ total signals",
    }


def _decision_confidence(
    decision_inputs: dict[str, Any],
    contradictions: list[str],
) -> str:
    data_quality_state = decision_inputs["data_quality_state"]
    core_states = (
        decision_inputs["readiness_state"],
        decision_inputs["fatigue_state"],
        decision_inputs["fitness_state"],
        decision_inputs["capacity_state"],
        decision_inputs["sleep_state"],
    )
    if data_quality_state == "weak":
        return "low"
    if any(value == "insufficient_data" for value in core_states):
        return "low"
    if contradictions:
        return "medium" if data_quality_state == "strong" else "low"
    if data_quality_state == "strong":
        return "high"
    return "medium"


def _data_quality_state(snapshot: dict[str, Any]) -> str:
    checks = [
        _window_has_usable_coverage(_trend_window(snapshot, "sleep_hours", "7d"), min_n=5),
        _window_has_usable_coverage(_trend_window(snapshot, "hrv", "7d"), min_n=3),
        _window_has_usable_coverage(_trend_window(snapshot, "rhr", "7d"), min_n=3),
        _window_has_usable_coverage(_trend_window(snapshot, "fatigue", "7d"), min_n=5),
        _window_has_usable_coverage(_trend_window(snapshot, "fitness", "7d"), min_n=5),
        _window_has_usable_coverage(_trend_window(snapshot, _capacity_metric_name(snapshot), "7d"), min_n=5),
    ]
    strong_count = len([item for item in checks if item])
    if strong_count >= 5:
        return "strong"
    if strong_count >= 3:
        return "limited"
    return "weak"


def _hrv_suppressed(snapshot: dict[str, Any]) -> bool:
    trend = _trend_window(snapshot, "hrv", "7d")
    if not _window_has_usable_coverage(trend, min_n=3):
        return False
    avg = trend.get("avg")
    baseline_avg = _baseline_value(snapshot, "hrv", "90d", "avg")
    typical_low = _baseline_value(snapshot, "hrv", "90d", "typical_low")
    if avg is None:
        return False
    if typical_low is not None and avg < typical_low:
        return True
    return baseline_avg is not None and avg <= baseline_avg - 3.0


def _rhr_elevated(snapshot: dict[str, Any]) -> bool:
    trend = _trend_window(snapshot, "rhr", "7d")
    if not _window_has_usable_coverage(trend, min_n=3):
        return False
    avg = trend.get("avg")
    baseline_avg = _baseline_value(snapshot, "rhr", "90d", "avg")
    typical_high = _baseline_value(snapshot, "rhr", "90d", "typical_high")
    if avg is None:
        return False
    if typical_high is not None and avg > typical_high:
        return True
    return baseline_avg is not None and avg >= baseline_avg + 3.0


def _fatigue_gt_fitness(snapshot: dict[str, Any]) -> bool:
    fatigue_avg = _trend_avg(snapshot, "fatigue", "7d")
    fitness_avg = _trend_avg(snapshot, "fitness", "7d")
    if fatigue_avg is None or fitness_avg is None:
        return False
    return fatigue_avg > fitness_avg


def _capacity_metric_name(snapshot: dict[str, Any]) -> str:
    ride_trend = _trend_window(snapshot, "ride_eftp_watts", "7d")
    if _window_has_usable_coverage(ride_trend, min_n=5):
        return "ride_eftp_watts"
    return "run_eftp"


def _capacity_metric_group(metric_name: str) -> str:
    if metric_name.startswith("ride_"):
        return "cycling"
    return "running"


def _capacity_metric_prefix_from_metric(metric_name: Any) -> str:
    if isinstance(metric_name, str) and metric_name.startswith("ride_"):
        return "ride_eftp"
    return "run_eftp"


def _capacity_metric_prefix(snapshot: dict[str, Any]) -> str:
    metric_name = _capacity_metric_name(snapshot)
    if metric_name.startswith("ride_"):
        return "ride_eftp"
    return "run_eftp"


def _trend_window(snapshot: dict[str, Any], metric_name: str, window_name: str) -> dict[str, Any]:
    return ((snapshot.get("current_trends") or {}).get(metric_name) or {}).get(window_name) or {}


def _trend_avg(snapshot: dict[str, Any], metric_name: str, window_name: str) -> Optional[float]:
    return _to_float_or_none(_trend_window(snapshot, metric_name, window_name).get("avg"))


def _trend_numeric(snapshot: dict[str, Any], metric_name: str, window_name: str, field_name: str) -> Optional[float]:
    return _to_float_or_none(_trend_window(snapshot, metric_name, window_name).get(field_name))


def _trend_int(snapshot: dict[str, Any], metric_name: str, window_name: str, field_name: str) -> Optional[int]:
    value = _trend_window(snapshot, metric_name, window_name).get(field_name)
    if value in (None, ""):
        return None
    return int(value)


def _trend_value(snapshot: dict[str, Any], metric_name: str, window_name: str, field_name: str) -> Any:
    return _trend_window(snapshot, metric_name, window_name).get(field_name)


def _baseline_value(snapshot: dict[str, Any], metric_name: str, window_name: str, field_name: str) -> Optional[float]:
    value = (((snapshot.get("personal_baselines") or {}).get(metric_name) or {}).get(window_name) or {}).get(field_name)
    return _to_float_or_none(value)


def _window_has_usable_coverage(window: dict[str, Any], min_n: int) -> bool:
    if not window:
        return False
    n = int(window.get("n") or 0)
    coverage_pct = int(window.get("coverage_pct") or 0)
    return n >= min_n and coverage_pct >= 60


def _delta_avg_vs_baseline(snapshot: dict[str, Any], metric_name: str, window_name: str, baseline_name: str) -> Optional[float]:
    avg = _trend_avg(snapshot, metric_name, window_name)
    baseline_avg = _baseline_value(snapshot, metric_name, baseline_name, "avg")
    if avg is None or baseline_avg is None:
        return None
    return round(avg - baseline_avg, 2)


def _high_rpe_at_moderate_if(snapshot: dict[str, Any]) -> Optional[bool]:
    current_week = snapshot.get("current_week") or {}
    days = current_week.get("days") or []
    seen = False
    for day in days:
        for workout in day.get("workouts") or []:
            if not _workout_is_execution_eligible(workout):
                continue
            intensity = _to_float_or_none(workout.get("if"))
            rpe = _to_float_or_none(workout.get("rpe"))
            if intensity is None or rpe is None:
                continue
            seen = True
            if intensity <= 0.8 and rpe >= 8.0:
                return True
    if seen:
        return False
    return None


def _recent_workouts(
    snapshot: dict[str, Any],
    lookback_days: int = 14,
    current_week_only: bool = False,
) -> list[dict[str, Any]]:
    current_week = snapshot.get("current_week") or {}
    current_days = current_week.get("days") or []
    if not current_days:
        return []
    current_date = current_days[-1].get("date")
    if not current_date:
        return []
    cutoff = date.fromisoformat(current_date) - timedelta(days=lookback_days - 1)

    weeks: list[dict[str, Any]] = [current_week]
    if not current_week_only:
        weeks.extend(reversed((snapshot.get("weekly_detailed_summary") or [])))

    items: list[dict[str, Any]] = []
    for week in weeks:
        for day in reversed(week.get("days") or []):
            day_date = day.get("date")
            if not day_date:
                continue
            day_obj = date.fromisoformat(day_date)
            if day_obj < cutoff:
                continue
            for workout in reversed(day.get("workouts") or []):
                items.append(
                    {
                        "date": day_date,
                        "day_of_week": day.get("day_of_week"),
                        **workout,
                    }
                )
    items.sort(key=lambda item: (item.get("date") or "", item.get("duration_min") or 0), reverse=True)
    return items


def _select_key_workout(snapshot: dict[str, Any]) -> Optional[dict[str, Any]]:
    workouts = _recent_workouts(snapshot, current_week_only=True)
    if not workouts:
        return None
    preferred_workouts = [item for item in workouts if _workout_is_execution_eligible(item)]
    if preferred_workouts:
        workouts = preferred_workouts

    def sort_key(item: dict[str, Any]) -> tuple[int, int, float, float]:
        session_class = item.get("session_class")
        planned_like_priority = 1 if session_class in {"vo2", "hiit", "threshold", "sweet_spot"} else 0
        expensive_priority = 1 if _workout_is_expensive(item) else 0
        endurance_priority = 1 if session_class == "endurance" else 0
        duration = _to_float_or_none(item.get("duration_min")) or 0.0
        training_load = _to_float_or_none(item.get("training_load")) or 0.0
        return (planned_like_priority, expensive_priority, endurance_priority, max(duration, training_load))

    return sorted(workouts, key=sort_key, reverse=True)[0]


def _is_commute_like(title: Any, sport_type: Any, raws: list[dict[str, Any]]) -> bool:
    title_text = str(title or "").lower()
    sport_text = str(sport_type or "").lower()
    if "commute" in title_text:
        return True
    if "commute" in sport_text:
        return True
    for raw in raws:
        if raw.get("commute") is True:
            return True
        if str(raw.get("sub_type") or "").upper() == "COMMUTE":
            return True
    return False


def _session_class(
    sport_type: Any,
    title: Any,
    power_zone_times: Optional[dict[str, int]],
    intensity_factor: Any,
    commute_like: bool,
) -> Optional[str]:
    sport_text = str(sport_type or "")
    sport_text_lower = sport_text.lower()
    title_text = str(title or "").lower()
    normalized_if = _normalize_intensity_factor(intensity_factor)
    zone_times = power_zone_times or {}
    z4 = int(zone_times.get("z4") or 0)
    ss = int(zone_times.get("ss") or 0)
    z5_plus = sum(int(zone_times.get(zone) or 0) for zone in ("z5", "z6", "z7"))

    if commute_like:
        return "commute"
    if sport_text_lower in {"workout", "weighttraining"} or "weight training" in title_text:
        if any(token in title_text for token in ("upper", "press", "pull", "push")):
            return "strength_upper"
        if any(token in title_text for token in ("leg", "squat", "deadlift", "lower")):
            return "strength_lower"
        return "strength"
    if z5_plus >= 300:
        return "vo2"
    if z5_plus >= 120:
        return "hiit"
    if z4 >= 900:
        return "threshold"
    if ss >= 1200:
        return "sweet_spot"
    if normalized_if is not None and normalized_if <= 0.8:
        return "endurance"
    if zone_times:
        return "mixed"
    if "long" in title_text or "z2" in title_text or "endurance" in title_text:
        return "endurance"
    return _session_type_label(sport_text)


def _upper_zone_leakage_pct(power_zone_times: Optional[dict[str, int]]) -> Optional[float]:
    if not power_zone_times:
        return None
    total = sum(int(value or 0) for value in power_zone_times.values())
    if total <= 0:
        return None
    upper = sum(int(power_zone_times.get(zone) or 0) for zone in ("z3", "z4", "z5", "z6", "z7"))
    return (upper / float(total)) * 100.0


def _workout_has_execution_metrics(workout: Optional[dict[str, Any]]) -> bool:
    if not workout:
        return False
    fields = (
        "decoupling_pct",
        "efficiency_factor",
        "variability_index",
        "power_load",
        "hr_load",
        "session_rpe_load",
        "feel",
        "power_zone_times",
        "hr_zone_times",
        "joules_above_ftp",
        "max_wbal_depletion",
    )
    return any(workout.get(field) is not None for field in fields)


def _workout_is_execution_eligible(workout: Optional[dict[str, Any]]) -> bool:
    if not workout:
        return False
    if workout.get("is_commute_like") is True:
        return False
    session_class = str(workout.get("session_class") or "")
    return session_class not in {"commute", "strength", "strength_upper", "strength_lower"}


def _workout_is_steady(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_execution_eligible(workout):
        return False
    intensity = _to_float_or_none(workout.get("if"))
    zone_times = workout.get("power_zone_times") or {}
    z5_plus = sum(
        int(zone_times.get(zone) or 0)
        for zone in ("z5", "z6", "z7")
    )
    duration = _to_float_or_none(workout.get("duration_min")) or 0.0
    if intensity is not None and intensity <= 0.8 and z5_plus <= 60:
        return True
    return duration >= 75.0 and z5_plus <= 120


def _workout_has_high_decoupling(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_steady(workout):
        return False
    decoupling = abs(_to_float_or_none((workout or {}).get("decoupling_pct")) or 0.0)
    return decoupling > 10.0


def _workout_hr_load_above_power_load(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_execution_eligible(workout):
        return False
    hr_load = _to_float_or_none(workout.get("hr_load"))
    power_load = _to_float_or_none(workout.get("power_load"))
    if hr_load is None or power_load is None:
        return False
    if power_load <= 0:
        return False
    return hr_load >= power_load + 10.0 and hr_load >= power_load * 1.15


def _workout_poor_feel_at_moderate_if(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_execution_eligible(workout):
        return False
    intensity = _to_float_or_none(workout.get("if"))
    feel = _to_float_or_none(workout.get("feel"))
    if intensity is None or feel is None:
        return False
    return intensity <= 0.85 and feel >= 4.0


def _workout_effective_rpe(workout: Optional[dict[str, Any]]) -> Optional[float]:
    if not workout:
        return None
    rpe = _to_float_or_none(workout.get("rpe"))
    if rpe is not None:
        return rpe
    duration = _to_float_or_none(workout.get("duration_min")) or 0.0
    session_rpe_load = _to_float_or_none(workout.get("session_rpe_load"))
    if duration < 20.0 or session_rpe_load is None:
        return None
    return session_rpe_load / duration


def _workout_high_variability_for_steady(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_steady(workout):
        return False
    vi = _to_float_or_none((workout or {}).get("variability_index"))
    return vi is not None and vi >= 1.1


def _workout_cost_high_for_output(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_execution_eligible(workout):
        return False
    intensity = _to_float_or_none(workout.get("if"))
    effective_rpe = _workout_effective_rpe(workout)
    poor_feel = _workout_poor_feel_at_moderate_if(workout)
    if intensity is not None and effective_rpe is not None and intensity <= 0.8 and effective_rpe >= 8.0:
        return True
    if intensity is not None and effective_rpe is not None and poor_feel and intensity <= 0.75 and effective_rpe >= 7.0:
        return True
    return False


def _workout_is_expensive(workout: Optional[dict[str, Any]]) -> bool:
    if not _workout_is_execution_eligible(workout):
        return False
    high_decoupling = _workout_has_high_decoupling(workout)
    hr_load_above_power = _workout_hr_load_above_power_load(workout)
    high_cost_for_output = _workout_cost_high_for_output(workout)
    high_variability = _workout_high_variability_for_steady(workout)
    poor_feel = _workout_poor_feel_at_moderate_if(workout)
    structural_cost_signals = [high_decoupling, hr_load_above_power, high_variability]
    if len([item for item in structural_cost_signals if item]) >= 2:
        return True
    if high_cost_for_output and any(structural_cost_signals):
        return True
    if hr_load_above_power and poor_feel:
        return True
    return False


def _execution_verdict_precalc(workout: Optional[dict[str, Any]]) -> Optional[str]:
    if not workout:
        return None
    session_class = workout.get("session_class")
    if session_class in {"commute", "strength", "strength_upper", "strength_lower"}:
        return None
    expensive = _workout_is_expensive(workout)
    failed = _workout_note_suggests_failure(workout)
    if failed:
        return "failed"
    if expensive and session_class in {"vo2", "hiit", "threshold", "sweet_spot"}:
        return "strong_but_costly"
    if expensive:
        return "expensive"
    if _workout_has_execution_metrics(workout):
        return "controlled"
    return None


def _workout_note_suggests_failure(workout: Optional[dict[str, Any]]) -> bool:
    if not workout:
        return False
    texts = [str(workout.get("description") or "").lower()]
    markers = ("failed", "could not", "couldn't", "bailed", "cut short", "didn't finish", "не смог", "сорвал", "не закончил")
    return any(any(marker in text for marker in markers) for text in texts)


def _latest_workout_expensive(snapshot: dict[str, Any]) -> Optional[bool]:
    recent = _recent_workouts(snapshot, lookback_days=14)
    for workout in recent:
        if _workout_is_execution_eligible(workout):
            return _workout_is_expensive(workout)
    return None


def _recent_expensive_sessions_count(snapshot: dict[str, Any], lookback_days: int = 14) -> int:
    return len([item for item in _recent_workouts(snapshot, lookback_days=lookback_days) if _workout_is_expensive(item)])


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


def _sqlite_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    return None


def _note_object(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item.get("title"),
        "text": item.get("note_text"),
    }


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


def _normalize_power_zone_times(value: Any) -> Optional[dict[str, int]]:
    if not isinstance(value, list):
        return None
    result: dict[str, int] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        zone_id = item.get("id")
        secs = _to_float_or_none(item.get("secs"))
        if not zone_id or secs is None:
            continue
        key = str(zone_id).strip().lower()
        if not key:
            continue
        result[key] = int(round(secs))
    return result or None


def _normalize_hr_zone_times(value: Any) -> Optional[dict[str, int]]:
    if not isinstance(value, list):
        return None
    result: dict[str, int] = {}
    for index, secs_value in enumerate(value, start=1):
        secs = _to_float_or_none(secs_value)
        if secs is None:
            continue
        result[f"z{index}"] = int(round(secs))
    return result or None


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
