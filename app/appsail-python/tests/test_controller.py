import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from controller import evaluate_hour


def test_demand_thresholds():
    timestamp = datetime(2025, 1, 1, 12)
    assert evaluate_hour(timestamp, 160.0)["mode"] == "Main Grid Mode"
    assert evaluate_hour(timestamp, 160.01)["mode"] == "Renewable Storage Mode"
    assert evaluate_hour(timestamp, 199.99)["overload_alert"] is False
    assert evaluate_hour(timestamp, 200.0)["overload_alert"] is True


def test_evening_peak_hours_are_inclusive():
    assert evaluate_hour(datetime(2025, 1, 1, 17), 100)["mode"] == "Main Grid Mode"
    assert evaluate_hour(datetime(2025, 1, 1, 18), 100)["mode"] == "Renewable Storage Mode"
    assert evaluate_hour(datetime(2025, 1, 1, 22), 100)["mode"] == "Renewable Storage Mode"
    assert evaluate_hour(datetime(2025, 1, 1, 23), 100)["mode"] == "Main Grid Mode"
