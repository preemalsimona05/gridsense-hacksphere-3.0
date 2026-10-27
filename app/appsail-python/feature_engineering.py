"""Pure-Python feature engineering shared by AppSail inference routes."""

from __future__ import annotations

import math
from datetime import datetime
from statistics import median
from typing import Any


WEATHER_COLUMNS = (
    "ambient_temp_c",
    "humidity_pct",
    "solar_irradiance_wm2",
)
FEATURE_COLUMNS = (
    "ambient_temp_c",
    "humidity_pct",
    "solar_irradiance_wm2",
    "hour",
    "day_of_week",
    "month",
    "is_weekend",
    "is_evening_peak",
    "hour_sin",
    "hour_cos",
    "ambient_temp_c_lag_1h",
    "ambient_temp_c_lag_3h",
    "ambient_temp_c_rolling_3h_mean",
    "humidity_pct_lag_1h",
    "solar_irradiance_wm2_lag_1h",
)


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty string")
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid timestamp: {value}") from error


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _fill_weather(rows: list[dict[str, Any]], column: str) -> None:
    values = [_number(row.get(column)) for row in rows]
    valid = [value for value in values if value is not None]
    fallback = median(valid) if valid else 0.0
    for index, value in enumerate(values):
        if value is not None:
            continue
        previous = next(
            (position for position in range(index - 1, -1, -1) if values[position] is not None),
            None,
        )
        following = next(
            (position for position in range(index + 1, len(values)) if values[position] is not None),
            None,
        )
        if previous is not None and following is not None:
            fraction = (index - previous) / (following - previous)
            values[index] = values[previous] + fraction * (
                values[following] - values[previous]
            )
        elif previous is not None:
            values[index] = values[previous]
        elif following is not None:
            values[index] = values[following]
        else:
            values[index] = fallback
    for row, value in zip(rows, values):
        row[column] = value


def build_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort rows and return feature dictionaries matching root features.py."""
    required = {"timestamp", *WEATHER_COLUMNS}
    for index, row in enumerate(rows):
        missing = required.difference(row)
        if missing:
            raise ValueError(
                f"row {index} missing required columns: {', '.join(sorted(missing))}"
            )
        row["_parsed_timestamp"] = parse_timestamp(row["timestamp"])

    ordered = sorted(rows, key=lambda row: row["_parsed_timestamp"])
    for column in WEATHER_COLUMNS:
        _fill_weather(ordered, column)

    for row in ordered:
        timestamp = row["_parsed_timestamp"]
        hour = timestamp.hour
        row.update(
            {
                "hour": hour,
                "day_of_week": timestamp.weekday(),
                "month": timestamp.month,
                "is_weekend": int(timestamp.weekday() >= 5),
                "is_evening_peak": int(18 <= hour <= 22),
                "hour_sin": math.sin(2 * math.pi * hour / 24),
                "hour_cos": math.cos(2 * math.pi * hour / 24),
            }
        )

    temperatures = [row["ambient_temp_c"] for row in ordered]
    humidities = [row["humidity_pct"] for row in ordered]
    solar = [row["solar_irradiance_wm2"] for row in ordered]
    for index, row in enumerate(ordered):
        row["ambient_temp_c_lag_1h"] = temperatures[max(0, index - 1)]
        row["ambient_temp_c_lag_3h"] = temperatures[max(0, index - 3)]
        row["ambient_temp_c_rolling_3h_mean"] = sum(
            temperatures[max(0, index - 2) : index + 1]
        ) / min(index + 1, 3)
        row["humidity_pct_lag_1h"] = humidities[max(0, index - 1)]
        row["solar_irradiance_wm2_lag_1h"] = solar[max(0, index - 1)]

    return ordered


def model_row(row: dict[str, Any]) -> dict[str, Any]:
    return {column: row[column] for column in FEATURE_COLUMNS}
