"""Pure dispatch-controller functions."""

from __future__ import annotations

from datetime import datetime

BATTERY_CAPACITY_KWH = 500.0
STARTING_CHARGE_KWH = 250.0
CHARGE_RATE_KW = 25.0
DISCHARGE_RATE_KW = 50.0


def evaluate_hour(timestamp: datetime, demand_kw: float) -> dict[str, object]:
    return {
        "mode": (
            "Renewable Storage Mode"
            if demand_kw > 160.0 or 18 <= timestamp.hour <= 22
            else "Main Grid Mode"
        ),
        "overload_alert": demand_kw >= 200.0,
    }


def simulate_battery(hours: list[dict[str, object]]) -> list[dict[str, object]]:
    charge = STARTING_CHARGE_KWH
    results = []
    for hour in hours:
        timestamp = hour["timestamp"]
        demand = float(hour["demand_kw"])
        decision = evaluate_hour(timestamp, demand)
        if decision["mode"] == "Renewable Storage Mode":
            charge = max(0.0, charge - min(DISCHARGE_RATE_KW, charge))
        else:
            charge = min(BATTERY_CAPACITY_KWH, charge + CHARGE_RATE_KW)
        results.append(
            {
                "timestamp": timestamp.isoformat(sep=" "),
                "demand_kw": demand,
                **decision,
                "battery_soc_kwh": round(charge, 3),
                "battery_soc_pct": round(charge / BATTERY_CAPACITY_KWH * 100, 3),
            }
        )
    return results
