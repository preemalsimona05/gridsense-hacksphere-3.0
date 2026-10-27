# HackSphere 3.0 Project Context

## Project

HackSphere 3.0 is a Smart Energy Microgrid & Demand Forecasting Engine. The
application forecasts hourly electricity demand and uses each forecast to
select a power source and raise overload alerts.

## Platform and stack

- **Zoho Catalyst** is the deployment platform.
- **QuickML** trains and publishes the demand regression model.
- **AppSail** hosts the Python backend (`app/appsail-python`).
- **Slate** hosts the frontend dashboard (`app/dashboard`).
- **Data Store** is the intended persistence layer for telemetry, forecasts,
  grid-state signals, and system logs.
- `app/catalyst.json` maps the AppSail service to `forecast-api` and the Slate
  service to `dashboard`.

## Data and model contract

- `train_telemetry.csv` contains 4,000 hourly training rows.
- `sample_test_input.csv` contains 1,000 hourly rows from a later period for
  local testing and inference validation.
- Input features for every forecast row:
  - `timestamp` (`YYYY-MM-DD HH:MM:SS`)
  - `ambient_temp_c`
  - `humidity_pct`
  - `solar_irradiance_wm2`
- Training target only: `target_demand_kw` (kW). It is not present in test or
  live inference input.
- Do not use lagged target features: the test input has no target values.
- A full forecast window supplies one feature row per forecast hour, normally
  24 rows.

## Prediction behavior

`predict.py` exposes `predict(input_df)` and returns one finite numeric
prediction per input row as a NumPy array. It builds the complete feature set
on the whole timestamp-sorted input before making concurrent one-row QuickML
requests. It restores the caller's original row order and preserves original
timestamps in CLI output.

Each QuickML request uses:

```json
{"data": {"ambient_temp_c": 0, "humidity_pct": 0, "solar_irradiance_wm2": 0}}
```

The request contains the 15 engineered model columns and excludes timestamp.
The response is parsed from `result[0]`. OAuth refresh is automatic when the three Zoho refresh credentials are
configured. Authentication failures stop clearly; other exhausted request
failures use the explicitly requested loud, counted local fallback so a
non-authentication outage cannot produce missing or non-finite output.

## Transition controller rules

Apply these rules independently to every forecast hour:

1. Use **Renewable Storage Mode** when predicted demand is **greater than
   160 kW**, or when the timestamp hour is **18 through 22 inclusive**.
   Hour 22 is included.
2. Otherwise use **Main Grid Mode**.
3. Independently raise a **Critical Overload Alert** when predicted demand is
   **greater than or equal to 200 kW**. An overload alert does not replace or
   alter the grid-mode decision.

## Scoring

- QuickML model RMSE from `predict.py`: **35%**
- Live deployment and end-to-end functionality: **35%**
- Transition logic correctness: **20%**
- UI and user experience: **10%**

## Current implementation and validation

- `test_eval.py` checks that `predict.py` exists, imports successfully, returns
  one finite prediction for every sample row, and emits `SUCCESS`.
- AppSail provides health, sample, forecast, and dispatch endpoints.
- Slate provides the deployed GridSense dashboard.
- Backend tests cover controller boundaries and feature parity.
- Before submission, run:

```text
python test_eval.py
python predict.py --input sample_test_input.csv --output predictions.csv
```

The eventual submission must include a public Catalyst app URL, the complete
frontend/backend source, a working QuickML endpoint configuration, and setup
documentation that keeps credentials secure.
