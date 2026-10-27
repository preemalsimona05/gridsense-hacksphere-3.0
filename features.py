"""Shared feature engineering for demand forecasting."""

from __future__ import annotations

import numpy as np
import pandas as pd


WEATHER_COLUMNS = [
    "ambient_temp_c",
    "humidity_pct",
    "solar_irradiance_wm2",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build time, cyclical, and weather-history features without target lags.

    Rows are sorted chronologically before weather lags and rolling values are
    computed. Missing lag and rolling values are filled from the available
    weather observations, then with zero if an entire weather column is
    missing.
    """
    required_columns = {"timestamp", *WEATHER_COLUMNS}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            "Missing required columns: " + ", ".join(sorted(missing_columns))
        )

    features = df.copy()
    timestamps = pd.to_datetime(features["timestamp"], errors="raise")
    features["timestamp"] = timestamps
    features = features.sort_values("timestamp").reset_index(drop=True)
    timestamps = features["timestamp"]
    features["hour"] = timestamps.dt.hour
    features["day_of_week"] = timestamps.dt.dayofweek
    features["month"] = timestamps.dt.month
    features["is_weekend"] = (features["day_of_week"] >= 5).astype(int)
    features["is_evening_peak"] = features["hour"].between(18, 22).astype(int)
    features["hour_sin"] = np.sin(2 * np.pi * features["hour"] / 24)
    features["hour_cos"] = np.cos(2 * np.pi * features["hour"] / 24)

    for column in WEATHER_COLUMNS:
        numeric_values = pd.to_numeric(features[column], errors="coerce")
        features[column] = numeric_values
        features[f"{column}_lag_1h"] = numeric_values.shift(1)
        if column == "ambient_temp_c":
            features[f"{column}_lag_3h"] = numeric_values.shift(3)
            features[f"{column}_rolling_3h_mean"] = numeric_values.rolling(
                window=3, min_periods=1
            ).mean()

    fill_columns = [
        column
        for column in features.columns
        if column != "timestamp" and pd.api.types.is_numeric_dtype(features[column])
    ]
    for column in fill_columns:
        features[column] = features[column].bfill().ffill().fillna(0)

    return features
