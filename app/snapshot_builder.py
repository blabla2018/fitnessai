from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional


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
    snapshot = {
        "current_snapshot": _build_current_snapshot(connection, current, current_date),
        "daily_series": _build_daily_series(connection, current_date, 14),
        "fitness_model_series": _build_fitness_model_series(connection, current_date, 14),
        "subjective_series": _build_subjective_series(connection, current_date, 14),
        "weekly_series": _build_weekly_series(connection, current_date, 8),
        "trends": _trend_block(connection, current_date, {"3d": 3, "7d": 7, "14d": 14, "28d": 28}),
        "notes_context": _build_notes_context(connection, current_date, 21, limit=5),
        "interpretation_hints": _interpretation_hints(current, connection, current_date),
    }
    snapshot["weekly_derived"] = _build_weekly_derived(snapshot["weekly_series"])
    snapshot["long_term_baselines"] = _build_long_term_baselines(connection, current_date)
    return snapshot


def export_snapshot_files(
    snapshot: dict[str, Any],
    output_json_path: Path,
    output_prompt_path: Path,
    prompt_template_path: Path,
) -> None:
    export_snapshot = _prune_for_export(snapshot)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(export_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    prompt_text = build_manual_prompt(export_snapshot, prompt_template_path)
    output_prompt_path.write_text(prompt_text, encoding="utf-8")


def build_manual_prompt(snapshot: dict[str, Any], prompt_template_path: Path) -> str:
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    template = prompt_template_path.read_text(encoding="utf-8")
    return template.replace("{{SNAPSHOT_JSON}}", snapshot_json)


def _build_current_snapshot(
    connection: sqlite3.Connection,
    current: dict[str, Any],
    current_date: str,
) -> dict[str, Any]:
    fitness = current.get("ctl")
    fatigue = current.get("atl")
    weight_kg = _first_non_null(
        current.get("weight_kg"),
        _latest_known_metric(connection, current_date, "weight_kg"),
    )
    ride_eftp_watts = current.get("ride_eftp_watts")
    run_eftp = current.get("run_eftp")
    return {
        "metric_date": current.get("metric_date"),
        "weight_kg": weight_kg,
        "sleep_hours": _round_or_none(_seconds_to_hours(current.get("sleep_seconds")), 2),
        "sleep_score": current.get("sleep_score"),
        "sleep_quality_score": current.get("sleep_quality_score"),
        "resting_hr_bpm": current.get("resting_hr_bpm"),
        "hrv_ms": current.get("hrv_ms"),
        "mood_score": current.get("mood_score"),
        "motivation_score": current.get("motivation_score"),
        "fitness": fitness,
        "fatigue": fatigue,
        "form": _round_or_none(_safe_subtract(fitness, fatigue), 2),
        "ramp_rate": current.get("ramp_rate"),
        "ride_eftp_watts": ride_eftp_watts,
        "ride_eftp_wkg": _round_or_none(_watts_per_kg(ride_eftp_watts, weight_kg), 2),
        "run_eftp": run_eftp,
        "run_eftp_wkg": _round_or_none(_watts_per_kg(run_eftp, weight_kg), 2),
        "swim_eftp": current.get("swim_eftp"),
    }


def _build_daily_series(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> dict[str, list[dict[str, Any]]]:
    rows = _load_metrics_rows(connection, current_date, days)
    return {
        "sleep_hours": _series(rows, "sleep_seconds", transform=_seconds_to_hours, digits=2),
        "weight_kg": _series(rows, "weight_kg", digits=2),
        "hrv_ms": _series(rows, "hrv_ms", digits=2),
        "resting_hr_bpm": _series(rows, "resting_hr_bpm", digits=2),
        "form": _derived_form_series(rows),
        "ride_eftp_watts": _series(rows, "ride_eftp_watts", digits=2),
        "ride_eftp_wkg": _derived_wkg_series(rows, "ride_eftp_watts"),
        "run_eftp": _series(rows, "run_eftp", digits=2),
        "run_eftp_wkg": _derived_wkg_series(rows, "run_eftp"),
    }


def _build_fitness_model_series(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> dict[str, list[dict[str, Any]]]:
    rows = _load_metrics_rows(connection, current_date, days)
    series = {
        "fitness": _series(rows, "ctl", digits=2),
        "fatigue": _series(rows, "atl", digits=2),
        "ramp_rate": _series(rows, "ramp_rate", digits=2),
    }
    series["form"] = _derived_form_series(rows)
    return series


def _build_subjective_series(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> dict[str, Any]:
    rows = _load_metrics_rows(connection, current_date, days)
    fields = ["motivation_score", "mood_score"]
    all_series = {field: _series(rows, field, digits=2) for field in fields}
    series = {}
    missing_in_source = []
    for field, field_series in all_series.items():
        non_null_points = sum(1 for point in field_series if point["value"] is not None)
        if non_null_points > 0:
            series[field] = field_series
        else:
            missing_in_source.append(field)

    return {
        "series": series,
        "missing_in_source": missing_in_source,
    }


def _build_weekly_series(
    connection: sqlite3.Connection,
    current_date: str,
    weeks: int,
) -> list[dict[str, Any]]:
    oldest = (date.fromisoformat(current_date) - timedelta(days=(weeks * 7) - 1)).isoformat()
    rows = connection.execute(
        """
        SELECT week_start_date, workouts_count, distance_meters, elevation_gain_meters,
               calories_kcal, training_load, session_rpe_load, fitness, fatigue, form,
               ramp_rate, weight_kg, by_category_json
        FROM intervals_weekly_stats
        WHERE week_start_date >= ?
        ORDER BY week_start_date ASC
        """,
        (oldest,),
    ).fetchall()

    weekly_series = []
    for row in rows:
        item = dict(row)
        by_category = _parse_json_or_none(item.get("by_category_json"))
        week_start_date = item.get("week_start_date")
        weekly_series.append(
            {
                "week_start_date": week_start_date,
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
                "weight_kg_end": _round_or_none(item.get("weight_kg"), 2),
                "ride_eftp_watts": _round_or_none(
                    _first_non_null(
                        _category_eftp(by_category, "Ride"),
                        _category_eftp(by_category, "Bike"),
                        _latest_metric_within_week(connection, week_start_date, "ride_eftp_watts"),
                    ),
                    2,
                ),
                "run_eftp": _round_or_none(
                    _first_non_null(
                        _category_eftp(by_category, "Run"),
                        _latest_metric_within_week(connection, week_start_date, "run_eftp"),
                    ),
                    2,
                ),
                "ride_eftp_wkg": _round_or_none(
                    _watts_per_kg(
                        _first_non_null(
                            _category_eftp(by_category, "Ride"),
                            _category_eftp(by_category, "Bike"),
                            _latest_metric_within_week(connection, week_start_date, "ride_eftp_watts"),
                        ),
                        item.get("weight_kg"),
                    ),
                    2,
                ),
                "run_eftp_wkg": _round_or_none(
                    _watts_per_kg(
                        _first_non_null(
                            _category_eftp(by_category, "Run"),
                            _latest_metric_within_week(connection, week_start_date, "run_eftp"),
                        ),
                        item.get("weight_kg"),
                    ),
                    2,
                ),
            }
        )
    return weekly_series


def _build_weekly_derived(weekly_series: list[dict[str, Any]]) -> dict[str, Any]:
    if not weekly_series:
        return {
            "current_week": None,
            "previous_week": None,
            "baseline_4w": None,
            "current_vs_previous": None,
            "current_vs_4w_baseline": None,
        }

    current_week = weekly_series[-1]
    previous_week = weekly_series[-2] if len(weekly_series) >= 2 else None
    baseline_source = weekly_series[-5:-1] if len(weekly_series) >= 5 else weekly_series[:-1]
    baseline_4w = _weekly_baseline(baseline_source)

    return {
        "current_week": {
            "week_start_date": current_week.get("week_start_date"),
            "distance_km": current_week.get("distance_km"),
            "elevation_gain_m": current_week.get("elevation_gain_m"),
            "calories_kcal": current_week.get("calories_kcal"),
            "training_load": current_week.get("training_load"),
            "session_rpe_load": current_week.get("session_rpe_load"),
        },
        "previous_week": {
            "week_start_date": previous_week.get("week_start_date"),
            "distance_km": previous_week.get("distance_km"),
            "elevation_gain_m": previous_week.get("elevation_gain_m"),
            "calories_kcal": previous_week.get("calories_kcal"),
            "training_load": previous_week.get("training_load"),
            "session_rpe_load": previous_week.get("session_rpe_load"),
        } if previous_week else None,
        "baseline_4w": baseline_4w,
        "current_vs_previous": _weekly_delta_block(current_week, previous_week),
        "current_vs_4w_baseline": _weekly_delta_block(current_week, baseline_4w),
    }


def _trend_block(
    connection: sqlite3.Connection,
    current_date: str,
    windows: dict[str, int],
) -> dict[str, Any]:
    trends: dict[str, Any] = {}
    for label, days in windows.items():
        rows = _load_metrics_rows(connection, current_date, days)
        trends[label] = {
            "days": days,
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


def _weekly_baseline(weeks: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not weeks:
        return None
    return {
        "weeks": len(weeks),
        "distance_km_mean": _round_or_none(_mean(week.get("distance_km") for week in weeks), 2),
        "elevation_gain_m_mean": _round_or_none(
            _mean(week.get("elevation_gain_m") for week in weeks), 1
        ),
        "calories_kcal_mean": _round_or_none(_mean(week.get("calories_kcal") for week in weeks), 0),
        "training_load_mean": _round_or_none(_mean(week.get("training_load") for week in weeks), 1),
        "session_rpe_load_mean": _round_or_none(
            _mean(week.get("session_rpe_load") for week in weeks), 1
        ),
    }


def _weekly_delta_block(
    current_week: Optional[dict[str, Any]],
    reference_week: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    if not current_week or not reference_week:
        return None

    if "distance_km" in reference_week:
        distance_ref = reference_week.get("distance_km")
        elevation_ref = reference_week.get("elevation_gain_m")
        calories_ref = reference_week.get("calories_kcal")
        training_load_ref = reference_week.get("training_load")
        srpe_ref = reference_week.get("session_rpe_load")
    else:
        distance_ref = reference_week.get("distance_km_mean")
        elevation_ref = reference_week.get("elevation_gain_m_mean")
        calories_ref = reference_week.get("calories_kcal_mean")
        training_load_ref = reference_week.get("training_load_mean")
        srpe_ref = reference_week.get("session_rpe_load_mean")

    return {
        "distance_km_delta_abs": _round_or_none(
            _safe_subtract(current_week.get("distance_km"), distance_ref), 2
        ),
        "distance_km_delta_pct": _round_or_none(
            _percent_delta(current_week.get("distance_km"), distance_ref), 1
        ),
        "elevation_gain_m_delta_abs": _round_or_none(
            _safe_subtract(current_week.get("elevation_gain_m"), elevation_ref), 1
        ),
        "elevation_gain_m_delta_pct": _round_or_none(
            _percent_delta(current_week.get("elevation_gain_m"), elevation_ref), 1
        ),
        "calories_kcal_delta_abs": _round_or_none(
            _safe_subtract(current_week.get("calories_kcal"), calories_ref), 0
        ),
        "calories_kcal_delta_pct": _round_or_none(
            _percent_delta(current_week.get("calories_kcal"), calories_ref), 1
        ),
        "training_load_delta_abs": _round_or_none(
            _safe_subtract(current_week.get("training_load"), training_load_ref), 1
        ),
        "training_load_delta_pct": _round_or_none(
            _percent_delta(current_week.get("training_load"), training_load_ref), 1
        ),
        "session_rpe_load_delta_abs": _round_or_none(
            _safe_subtract(current_week.get("session_rpe_load"), srpe_ref), 1
        ),
        "session_rpe_load_delta_pct": _round_or_none(
            _percent_delta(current_week.get("session_rpe_load"), srpe_ref), 1
        ),
    }


def _build_notes_context(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    oldest = (date.fromisoformat(current_date) - timedelta(days=days - 1)).isoformat()
    rows = connection.execute(
        """
        SELECT local_date, title, note_text, is_week_note, updated_at_remote
        FROM intervals_notes
        WHERE local_date >= ?
        ORDER BY start_date_local DESC
        LIMIT ?
        """,
        (oldest, limit),
    ).fetchall()

    notes = []
    for row in rows:
        note = dict(row)
        notes.append(
            {
                "local_date": note.get("local_date"),
                "note_type": "weekly" if note.get("is_week_note") else "daily",
                "tags": _infer_note_tags(note.get("title"), note.get("note_text"), bool(note.get("is_week_note"))),
                "title": note.get("title"),
                "note_text": note.get("note_text"),
                "updated_at_remote": note.get("updated_at_remote"),
            }
        )
    return notes


def _interpretation_hints(
    current: dict[str, Any],
    connection: sqlite3.Connection,
    current_date: str,
) -> dict[str, Any]:
    baseline_7d = _load_window_average(connection, current_date, 7)
    baseline_14d = _load_window_average(connection, current_date, 14)
    baseline_28d = _load_window_average(connection, current_date, 28)
    sleep_hours = _seconds_to_hours(current.get("sleep_seconds"))

    return {
        "sleep_vs_7d_hours": _round_or_none(_safe_subtract(sleep_hours, baseline_7d.get("sleep_hours")), 2),
        "resting_hr_vs_14d": _round_or_none(
            _safe_subtract(current.get("resting_hr_bpm"), baseline_14d.get("resting_hr_bpm")),
            2,
        ),
        "hrv_vs_14d": _round_or_none(_safe_subtract(current.get("hrv_ms"), baseline_14d.get("hrv_ms")), 2),
        "form": _round_or_none(_safe_subtract(current.get("ctl"), current.get("atl")), 2),
        "ride_eftp_vs_28d": _round_or_none(
            _safe_subtract(current.get("ride_eftp_watts"), baseline_28d.get("ride_eftp_watts")),
            2,
        ),
        "hrv_cv_7d_pct": _round_or_none(
            _coefficient_of_variation(
                row.get("hrv_ms") for row in _load_metrics_rows(connection, current_date, 7)
            ),
            2,
        ),
    }


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


def _load_window_average(
    connection: sqlite3.Connection,
    current_date: str,
    days: int,
) -> dict[str, Optional[float]]:
    rows = _load_metrics_rows(connection, current_date, days)
    return {
        "sleep_hours": _mean(_seconds_to_hours(row.get("sleep_seconds")) for row in rows),
        "resting_hr_bpm": _mean(row.get("resting_hr_bpm") for row in rows),
        "hrv_ms": _mean(row.get("hrv_ms") for row in rows),
        "ride_eftp_watts": _mean(row.get("ride_eftp_watts") for row in rows),
    }


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


def _latest_known_metric(
    connection: sqlite3.Connection,
    current_date: str,
    column: str,
) -> Optional[float]:
    row = connection.execute(
        f"""
        SELECT {column}
        FROM athlete_metrics_daily
        WHERE metric_date <= ? AND {column} IS NOT NULL
        ORDER BY metric_date DESC
        LIMIT 1
        """,
        (current_date,),
    ).fetchone()
    if row is None:
        return None
    return row[0]


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


def _series(
    rows: list[dict[str, Any]],
    key: str,
    transform: Optional[Any] = None,
    digits: int = 2,
) -> list[dict[str, Any]]:
    series = []
    for row in sorted(rows, key=lambda item: item["metric_date"]):
        raw_value = row.get(key)
        value = transform(raw_value) if transform else raw_value
        series.append(
            {
                "date": row.get("metric_date"),
                "value": _round_or_none(value, digits) if value is not None else None,
            }
        )
    return series


def _derived_form_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    series = []
    for row in sorted(rows, key=lambda item: item["metric_date"]):
        series.append(
            {
                "date": row.get("metric_date"),
                "value": _round_or_none(_safe_subtract(row.get("ctl"), row.get("atl")), 2),
            }
        )
    return series


def _derived_wkg_series(rows: list[dict[str, Any]], ftp_key: str) -> list[dict[str, Any]]:
    series = []
    for row in sorted(rows, key=lambda item: item["metric_date"]):
        weight_kg = _first_non_null(
            row.get("weight_kg"),
            _latest_known_weight_from_rows(rows, row.get("metric_date")),
        )
        series.append(
            {
                "date": row.get("metric_date"),
                "value": _round_or_none(_watts_per_kg(row.get(ftp_key), weight_kg), 2),
            }
        )
    return series


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


def _infer_note_tags(title: Optional[str], note_text: Optional[str], is_week_note: bool) -> list[str]:
    combined = f"{title or ''} {note_text or ''}".lower()
    tags = []

    if is_week_note:
        tags.append("weekly")
    else:
        tags.append("daily")
    if "зал" in combined or "жим" in combined or "присед" in combined:
        tags.append("gym")
    if "шоссе" in combined or "веле" in combined or "ftp" in combined or "вт" in combined:
        tags.append("bike")
    if "простуд" in combined or "зноб" in combined or "слаб" in combined:
        tags.append("illness_like")
    if "мотива" in combined or "доволен" in combined:
        tags.append("motivation")
    if "план" in combined or "ошиб" in combined:
        tags.append("planning_error")

    return tags


def _seconds_to_hours(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value) / 3600.0


def _meters_to_km(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value) / 1000.0


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    cleaned = [float(value) for value in values if value is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


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


def _percent_delta(current: Any, baseline: Any) -> Optional[float]:
    if current is None or baseline in (None, 0, 0.0):
        return None
    return ((float(current) - float(baseline)) / float(baseline)) * 100.0


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
