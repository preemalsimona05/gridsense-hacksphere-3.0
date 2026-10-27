import csv
import math
import sys
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).parents[1]
PROJECT_ROOT = APP_DIR.parents[1]
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from feature_engineering import FEATURE_COLUMNS, build_features
from features import build_features as build_pandas_features


def test_sample_features_match_root_implementation():
    with (PROJECT_ROOT / "sample_test_input.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    backend_rows = build_features(rows)
    pandas_features = build_pandas_features(pd.read_csv(PROJECT_ROOT / "sample_test_input.csv"))

    for backend_row, (_, pandas_row) in zip(backend_rows, pandas_features.iterrows()):
        for column in FEATURE_COLUMNS:
            assert math.isclose(
                backend_row[column],
                float(pandas_row[column]),
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
