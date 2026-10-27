"""Explore telemetry data and evaluate a time-based baseline model."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from features import build_features


DATA_PATH = PROJECT_ROOT / "train_telemetry.csv"
PLOTS_PATH = PROJECT_ROOT / "analysis" / "plots"
FEATURES_PATH = PROJECT_ROOT / "train_features.csv"
TARGET = "target_demand_kw"


def save_plot(plotter, filename: str) -> None:
    PLOTS_PATH.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(9, 5))
    plotter(axis)
    figure.tight_layout()
    figure.savefig(PLOTS_PATH / filename, dpi=150)
    plt.close(figure)


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="raise")
    data = data.sort_values("timestamp").reset_index(drop=True)

    print("Summary statistics:")
    print(data.describe(include="all").to_string())
    print("\nMissing values:")
    print(data.isna().sum().to_string())
    print(f"\nDuplicate timestamps: {data['timestamp'].duplicated().sum()}")

    save_plot(
        lambda axis: (
            data.groupby(data["timestamp"].dt.hour)[TARGET]
            .mean()
            .plot(ax=axis, marker="o", title="Average Demand by Hour of Day")
        ),
        "average_demand_by_hour.png",
    )
    save_plot(
        lambda axis: (
            data.groupby(data["timestamp"].dt.dayofweek)[TARGET]
            .mean()
            .rename(index=dict(enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])))
            .plot(ax=axis, marker="o", title="Average Demand by Day of Week")
        ),
        "average_demand_by_day_of_week.png",
    )

    weather_columns = [
        "ambient_temp_c",
        "humidity_pct",
        "solar_irradiance_wm2",
    ]
    for column in weather_columns:
        def plot_weather(axis, weather_column=column):
            axis.scatter(data[weather_column], data[TARGET], s=10, alpha=0.35)
            axis.set_title(f"Demand vs {weather_column}")
            axis.set_xlabel(weather_column)
            axis.set_ylabel(TARGET)

        save_plot(plot_weather, f"demand_vs_{column}.png")

    engineered = build_features(data)
    train_features = engineered.copy()
    train_features["timestamp"] = train_features["timestamp"].dt.strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    train_features.to_csv(FEATURES_PATH, index=False)

    model_data = engineered.drop(columns=["timestamp"])
    x = model_data.drop(columns=[TARGET])
    y = model_data[TARGET]
    split_index = int(len(model_data) * 0.8)
    x_train, x_validation = x.iloc[:split_index], x.iloc[split_index:]
    y_train, y_validation = y.iloc[:split_index], y.iloc[split_index:]

    model = GradientBoostingRegressor(random_state=42)
    model.fit(x_train, y_train)
    predictions = model.predict(x_validation)
    rmse = np.sqrt(mean_squared_error(y_validation, predictions))

    print(f"\nTime-based split: {split_index} train / {len(x_validation)} validation rows")
    print(f"Validation RMSE: {rmse:.4f} kW")
    print(f"\nSaved engineered features to {FEATURES_PATH}")
    print("train_features.csv columns:")
    print(", ".join(train_features.columns))
    print("\nSaved plots:")
    for plot_path in sorted(PLOTS_PATH.glob("*.png")):
        print(f"- {plot_path}")


if __name__ == "__main__":
    main()
