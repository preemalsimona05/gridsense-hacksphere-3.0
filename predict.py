"""Generate demand predictions through the published QuickML endpoint."""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
import requests

from features import build_features

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()


REQUIRED_ENV_VARS = (
    "QUICKML_ENDPOINT_URL",
    "QUICKML_ENDPOINT_KEY",
    "CATALYST_ORG",
    "CATALYST_ENVIRONMENT",
)
REFRESH_ENV_VARS = (
    "ZOHO_CLIENT_ID",
    "ZOHO_CLIENT_SECRET",
    "ZOHO_REFRESH_TOKEN",
)
FEATURE_COLUMNS = [
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
MAX_WORKERS = 10
MAX_RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30


def normalize_environment_values() -> None:
    """Normalize configured QuickML environment values without exposing them."""
    for name in (*REQUIRED_ENV_VARS, "QUICKML_AUTH", *REFRESH_ENV_VARS, "ZOHO_ACCOUNTS_URL"):
        value = os.environ.get(name)
        if value is None:
            continue
        value = value.strip()
        while len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1].strip()
        if name == "QUICKML_AUTH":
            value = value.replace("<", "").replace(">", "").strip()
            if value.startswith("1000."):
                value = "Zoho-oauthtoken " + value
        os.environ[name] = value


normalize_environment_values()


class QuickMLAuthError(RuntimeError):
    """Raised when the endpoint rejects the configured authentication."""


class QuickMLRequestError(RuntimeError):
    """Raised for a failed or invalid non-authenticated endpoint response."""


class QuickMLAuth:
    def __init__(self, headers: dict[str, str]):
        self._headers = headers
        self._lock = threading.Lock()
        self._refresh_attempted = False

    def headers(self) -> dict[str, str]:
        with self._lock:
            return dict(self._headers)

    def refresh_once(self) -> dict[str, str]:
        with self._lock:
            if self._refresh_attempted:
                return dict(self._headers)
            self._refresh_attempted = True

            refresh_values = [os.environ.get(name, "") for name in REFRESH_ENV_VARS]
            if not all(refresh_values):
                raise QuickMLAuthError(
                    "QuickML authentication failed; set ZOHO_CLIENT_ID, "
                    "ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN to enable "
                    "automatic token refresh."
                )
            accounts_url = os.environ.get("ZOHO_ACCOUNTS_URL", "")
            if not accounts_url:
                raise QuickMLAuthError(
                    "QuickML authentication failed; ZOHO_ACCOUNTS_URL is "
                    "required for automatic token refresh."
                )

            try:
                response = requests.post(
                    f"{accounts_url.rstrip('/')}/oauth/v2/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": refresh_values[0],
                        "client_secret": refresh_values[1],
                        "refresh_token": refresh_values[2],
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                access_token = response.json()["access_token"]
            except (
                requests.RequestException,
                KeyError,
                TypeError,
                ValueError,
            ) as error:
                raise QuickMLAuthError(
                    "QuickML authentication failed; automatic token refresh "
                    "was unsuccessful."
                ) from error

            if not isinstance(access_token, str) or not access_token:
                raise QuickMLAuthError(
                    "QuickML authentication failed; refresh returned no access token."
                )
            self._headers["Authorization"] = f"Zoho-oauthtoken {access_token}"
            return dict(self._headers)


def _quickml_configuration() -> tuple[str, dict[str, str]]:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    refresh_configured = all(os.environ.get(name) for name in REFRESH_ENV_VARS)
    auth_configured = bool(os.environ.get("QUICKML_AUTH"))
    if not refresh_configured and not auth_configured:
        missing.append("QUICKML_AUTH")
    if missing:
        raise RuntimeError(
            "Missing required QuickML environment variable(s): "
            + ", ".join(missing)
        )

    return os.environ["QUICKML_ENDPOINT_URL"], {
        "Content-Type": "application/json",
        "X-QUICKML-ENDPOINT-KEY": os.environ["QUICKML_ENDPOINT_KEY"],
        "Authorization": os.environ["QUICKML_AUTH"],
        "CATALYST-ORG": os.environ["CATALYST_ORG"],
        "Environment": os.environ["CATALYST_ENVIRONMENT"],
    }


def _fallback_prediction(row: pd.Series) -> float:
    hour = float(row["hour"])
    temperature = float(row["ambient_temp_c"])
    base_load = 120.0 + 30.0 * np.sin(2 * np.pi * (hour - 6) / 24)
    cooling_load = max(0.0, temperature - 24.0) * 8.5
    return float(base_load + cooling_load)


def _request_prediction(
    row: dict[str, Any],
    endpoint_url: str,
    auth: QuickMLAuth,
    stop_event: Any,
) -> float:
    if stop_event.is_set():
        raise QuickMLRequestError("Prediction cancelled after another request failed.")

    last_error: Exception | None = None
    auth_retry_done = False
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                endpoint_url,
                json={"data": row},
                headers=auth.headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 401 and not auth_retry_done:
                auth.refresh_once()
                auth_retry_done = True
                continue
            if response.status_code in (401, 403):
                stop_event.set()
                raise QuickMLAuthError(
                    "QuickML returned an authentication error; the "
                    "QuickML authorization needs refreshing."
                )
            response.raise_for_status()
            result = response.json()
            prediction = float(result["result"][0])
            if not np.isfinite(prediction):
                raise ValueError("QuickML returned a non-finite prediction.")
            return prediction
        except QuickMLAuthError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
            last_error = error
            if attempt < MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))

    raise QuickMLRequestError("QuickML request failed after retries.") from last_error


def predict(input_df: pd.DataFrame) -> np.ndarray:
    """Return one finite prediction per input row in the original row order."""
    endpoint_url, headers = _quickml_configuration()
    auth = QuickMLAuth(headers)
    if input_df.empty:
        return np.array([], dtype=float)

    original_rows = input_df.copy()
    original_rows["_input_order"] = np.arange(len(original_rows))
    engineered = build_features(original_rows)
    request_rows = engineered[FEATURE_COLUMNS].to_dict(orient="records")
    stop_event = __import__("threading").Event()
    predictions = np.empty(len(request_rows), dtype=float)
    fallback_count = 0
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    futures = {
        executor.submit(
            _request_prediction,
            row,
            endpoint_url,
            auth,
            stop_event,
        ): index
        for index, row in enumerate(request_rows)
    }
    try:
        for future in as_completed(futures):
            index = futures[future]
            try:
                predictions[index] = future.result()
            except QuickMLAuthError:
                stop_event.set()
                for pending in futures:
                    pending.cancel()
                raise
            except QuickMLRequestError:
                fallback_count += 1
                predictions[index] = _fallback_prediction(engineered.iloc[index])
    finally:
        executor.shutdown(wait=True)

    restored_predictions = np.empty(len(predictions), dtype=float)
    restored_predictions[
        engineered["_input_order"].to_numpy(dtype=int)
    ] = predictions

    if fallback_count:
        print(
            "!!! WARNING: QuickML failed for "
            f"{fallback_count} row(s); local fallback predictions were used."
        )
    if not np.isfinite(restored_predictions).all():
        raise RuntimeError("Prediction output contains NaN or infinite values.")
    return restored_predictions


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate QuickML demand predictions.")
    parser.add_argument("--input", required=True, help="Input CSV path.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        input_df = pd.read_csv(args.input)
        predictions = predict(input_df)
    except QuickMLAuthError as error:
        raise SystemExit(f"Authentication error: {error}") from error
    except RuntimeError as error:
        raise SystemExit(f"Configuration or prediction error: {error}") from error

    output_df = pd.DataFrame(
        {
            "timestamp": input_df["timestamp"],
            "target_demand_kw": predictions,
        }
    )
    output_df.to_csv(args.output, index=False)
    print(f"Wrote {len(output_df)} predictions to {args.output}.")


if __name__ == "__main__":
    sys.exit(main())
