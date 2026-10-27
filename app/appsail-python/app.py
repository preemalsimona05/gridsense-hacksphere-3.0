"""Flask AppSail backend for forecasting and dispatch."""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from flask import Flask, jsonify, request

from controller import simulate_battery
from feature_engineering import FEATURE_COLUMNS, build_features, model_row

app = Flask(__name__)
MAX_WORKERS = 10
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
WEATHER_COLUMNS = ("ambient_temp_c", "humidity_pct", "solar_irradiance_wm2")
REQUIRED_ENV = (
    "QUICKML_ENDPOINT_URL",
    "QUICKML_ENDPOINT_KEY",
    "CATALYST_ORG",
    "CATALYST_ENVIRONMENT",
)
REFRESH_ENV = ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN")
SETTING_NAMES = {
    "QUICKML_ENDPOINT_URL": "HS_QML_URL",
    "QUICKML_ENDPOINT_KEY": "HS_QML_KEY",
    "CATALYST_ORG": "HS_ORG_ID",
    "CATALYST_ENVIRONMENT": "HS_ENV_NAME",
    "ZOHO_CLIENT_ID": "HS_OAUTH_ID",
    "ZOHO_CLIENT_SECRET": "HS_OAUTH_SECRET",
    "ZOHO_REFRESH_TOKEN": "HS_OAUTH_REFRESH",
    "ZOHO_ACCOUNTS_URL": "HS_OAUTH_URL",
}


def setting(name: str) -> str:
    return os.environ.get(SETTING_NAMES.get(name, ""), "") or os.environ.get(name, "")


class AuthError(RuntimeError):
    pass


class AuthState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.refreshed = False
        self.authorization = setting("QUICKML_AUTH")
        if all(setting(name) for name in REFRESH_ENV):
            self.refresh_once()

    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-QUICKML-ENDPOINT-KEY": setting("QUICKML_ENDPOINT_KEY"),
            "Authorization": self.authorization,
            "CATALYST-ORG": setting("CATALYST_ORG"),
            "Environment": setting("CATALYST_ENVIRONMENT"),
        }

    def refresh_once(self) -> None:
        with self.lock:
            if self.refreshed:
                return
            self.refreshed = True
            if not all(setting(name) for name in REFRESH_ENV):
                raise AuthError("QuickML authentication failed; refresh credentials are not configured.")
            accounts_url = setting("ZOHO_ACCOUNTS_URL")
            if not accounts_url:
                raise AuthError("QuickML authentication failed; ZOHO_ACCOUNTS_URL is not configured.")
            try:
                response = requests.post(
                    f"{accounts_url.rstrip('/')}/oauth/v2/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": setting("ZOHO_CLIENT_ID"),
                        "client_secret": setting("ZOHO_CLIENT_SECRET"),
                        "refresh_token": setting("ZOHO_REFRESH_TOKEN"),
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                token = response.json()["access_token"]
            except (requests.RequestException, KeyError, TypeError, ValueError) as error:
                raise AuthError("QuickML authentication refresh failed.") from error
            self.authorization = f"Zoho-oauthtoken {token}"


def _configuration() -> None:
    missing = [name for name in REQUIRED_ENV if not setting(name)]
    if not setting("QUICKML_AUTH") and not all(
        setting(name) for name in REFRESH_ENV
    ):
        missing.append("QUICKML_AUTH or OAuth refresh credentials")
    if missing:
        raise RuntimeError("Missing required configuration: " + ", ".join(missing))


def _predict_row(row: dict[str, Any], auth: AuthState) -> float:
    last_error: Exception | None = None
    auth_retry = False
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.post(
                setting("QUICKML_ENDPOINT_URL"),
                json={"data": model_row(row)},
                headers=auth.headers(),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code == 401 and not auth_retry:
                auth.refresh_once()
                auth_retry = True
                continue
            if response.status_code in (401, 403):
                raise AuthError("QuickML authorization failed.")
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                    error_code = error_payload.get("code") or error_payload.get("error")
                except (ValueError, TypeError):
                    error_code = None
                status_detail = f"QuickML returned HTTP {response.status_code}"
                if error_code:
                    status_detail += f" ({error_code})"
                last_error = RuntimeError(
                    status_detail + "."
                )
                if attempt < MAX_RETRIES:
                    time.sleep(0.25 * (attempt + 1))
                continue
            response.raise_for_status()
            value = float(response.json()["result"][0])
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError("QuickML returned a non-finite prediction.")
            return value
        except AuthError:
            raise
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as error:
            last_error = error
            if attempt < MAX_RETRIES:
                time.sleep(0.25 * (attempt + 1))
    detail = str(last_error) if last_error else "unknown error"
    raise RuntimeError(f"QuickML request failed after retries: {detail}") from last_error


def _read_rows() -> list[dict[str, Any]]:
    if request.is_json:
        body = request.get_json()
        rows = body.get("rows", body) if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ValueError("JSON body must be an array of rows or an object with a rows array.")
        return rows
    if request.mimetype == "text/plain":
        try:
            body = json.loads(request.get_data(as_text=True))
        except (TypeError, ValueError) as error:
            raise ValueError("Request body must contain valid JSON rows.") from error
        rows = body.get("rows", body) if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ValueError("JSON body must be an array of rows or an object with a rows array.")
        return rows
    upload = request.files.get("file")
    if upload is None:
        raise ValueError("Provide JSON rows or upload a CSV file as 'file'.")
    return list(csv.DictReader(io.TextIOWrapper(upload.stream, encoding="utf-8")))


def _validate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"timestamp", *WEATHER_COLUMNS}
    if not rows:
        raise ValueError("At least one forecast row is required.")
    for index, row in enumerate(rows):
        missing = required.difference(row)
        if missing:
            raise ValueError(f"row {index} missing columns: {', '.join(sorted(missing))}")
    return rows


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.get("/")
def health():
    names = (
        "QUICKML_ENDPOINT_URL",
        "QUICKML_ENDPOINT_KEY",
        "CATALYST_ORG",
        "CATALYST_ENVIRONMENT",
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "ZOHO_REFRESH_TOKEN",
        "ZOHO_ACCOUNTS_URL",
    )
    return jsonify(
        {
            "status": "ok",
            "service": "forecast-api",
            "configuration": {
                name: {
                    "set": bool(setting(name)),
                    "length": len(setting(name)),
                }
                for name in names
            },
        }
    )


@app.get("/api/sample")
def sample():
    return jsonify(
        [
            {
                "timestamp": f"2025-01-01 {hour:02d}:00:00",
                "ambient_temp_c": 20.0,
                "humidity_pct": 60.0,
                "solar_irradiance_wm2": 0.0 if hour < 7 or hour > 17 else 200.0,
            }
            for hour in range(24)
        ]
    )


@app.post("/api/forecast")
def forecast():
    try:
        _configuration()
        rows = _validate_rows(_read_rows())
        features = build_features([dict(row) for row in rows])
        auth = AuthState()
        predictions = [0.0] * len(features)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_predict_row, row, auth): index
                for index, row in enumerate(features)
            }
            for future in as_completed(futures):
                predictions[futures[future]] = future.result()
        return jsonify(
            [
                {
                    "timestamp": row["timestamp"],
                    "target_demand_kw": prediction,
                }
                for row, prediction in zip(features, predictions)
            ]
        )
    except AuthError as error:
        return jsonify({"error": str(error)}), 401
    except (RuntimeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/dispatch")
def dispatch():
    try:
        if request.is_json:
            body = request.get_json()
        elif request.mimetype == "text/plain":
            body = json.loads(request.get_data(as_text=True))
        else:
            raise ValueError("Request body must contain JSON predictions.")
        rows = body.get("predictions", body) if isinstance(body, dict) else body
        if not isinstance(rows, list):
            raise ValueError("JSON body must be an array or an object with predictions.")
        hours = []
        for index, row in enumerate(rows):
            timestamp = row.get("timestamp")
            demand = row.get("demand_kw", row.get("target_demand_kw"))
            if timestamp is None or demand is None:
                raise ValueError(f"prediction row {index} needs timestamp and demand_kw.")
            parsed = build_features(
                [
                    {
                        "timestamp": timestamp,
                        "ambient_temp_c": 0,
                        "humidity_pct": 0,
                        "solar_irradiance_wm2": 0,
                    }
                ]
            )[0]["_parsed_timestamp"]
            hours.append({"timestamp": parsed, "demand_kw": float(demand)})
        return jsonify(simulate_battery(hours))
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("X_ZOHO_CATALYST_LISTEN_PORT", "9000"))
    app.run(host="0.0.0.0", port=port)
