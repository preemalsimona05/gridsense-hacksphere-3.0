"""Safely inspect QuickML endpoint configuration and one prediction response."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from features import build_features
from predict import (
    REQUIRED_ENV_VARS,
    _quickml_configuration,
    normalize_environment_values,
)


def redact_token_like_strings(text: str) -> str:
    text = re.sub(
        r"(?i)(Zoho-oauthtoken\s+)[^\s\"']+",
        r"\1REDACTED",
        text,
    )
    return re.sub(
        r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{20,}(?![A-Za-z0-9])",
        "REDACTED",
        text,
    )


def main() -> None:
    import os

    normalize_environment_values()
    for name in REQUIRED_ENV_VARS:
        value = os.environ.get(name, "")
        print(f"{name}: set={'yes' if value else 'no'}, length={len(value)}")

    auth = os.environ.get("QUICKML_AUTH", "")
    auth_format_valid = auth.startswith("Zoho-oauthtoken ") and auth[
        len("Zoho-oauthtoken ") :
    ].startswith("1000.")
    print(f'QUICKML_AUTH format: {"valid" if auth_format_valid else "invalid"}')

    endpoint_url, headers = _quickml_configuration()
    sample = pd.read_csv(PROJECT_ROOT / "sample_test_input.csv")
    engineered = build_features(sample)
    row = engineered.iloc[[0]]
    payload = {
        "data": row[
            [
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
            ]
        ].iloc[0].to_dict()
    }

    response = requests.post(
        endpoint_url,
        json=payload,
        headers=headers,
        timeout=30,
    )
    print(f"HTTP status code: {response.status_code}")
    print(f"Response body: {redact_token_like_strings(response.text)}")


if __name__ == "__main__":
    main()
