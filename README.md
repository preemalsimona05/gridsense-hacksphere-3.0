# GridSense — Smart Energy Microgrid

GridSense is HackSphere 3.0's end-to-end demand forecasting and microgrid
dispatch application. It forecasts hourly electricity demand with a published
Zoho Catalyst QuickML regression model, then applies deterministic operating
rules to select Main Grid or Renewable Storage Mode and raise overload alerts.

## Live deployment

- **Slate dashboard:** `https://dashboard-oetrdqbn.onslate.in`
- **AppSail API:** `https://forecast-api-50047160503.development.catalystappsail.in`

Open the Slate URL for the public application. The AppSail URL is the backend
health and API service.

## Architecture

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Dashboard | Catalyst Slate, plain HTML/CSS/JavaScript, Chart.js | Input, charts, alerts, dispatch table |
| API | Catalyst AppSail, Flask/Python 3.11 | Validation, feature engineering, QuickML calls |
| Model | Catalyst QuickML | Demand regression inference |
| Controller | Pure Python | Grid mode, overload alerts, battery simulation |

The backend runtime uses only the Python standard library, Flask, and requests.
It does not require pandas or NumPy.

## Input and model features

Each forecast row contains:

```text
timestamp, ambient_temp_c, humidity_pct, solar_irradiance_wm2
```

The shared feature pipeline adds:

- hour, day of week, month, weekend flag, evening-peak flag
- sine/cosine hour encoding
- temperature lag 1 hour and 3 hours
- rolling 3-hour temperature mean
- humidity lag 1 hour
- solar irradiance lag 1 hour

Rows are sorted chronologically before lag and rolling features are calculated.
Missing weather values are interpolated and then filled with a median fallback.
No target-demand lag is used because inference data has no target column.
If a non-authentication QuickML request still fails after retries, the local
CLI uses a loud, counted fallback prediction; authentication failures never
use that fallback and stop with a refresh message.

## Controller rules

For every forecast hour:

- **Renewable Storage Mode** when demand is greater than 160 kW, or the hour is
  18:00 through 22:00 inclusive.
- **Main Grid Mode** otherwise.
- **Critical Overload Alert** independently when demand is at least 200 kW.

The battery simulation starts at 250 kWh in a 500 kWh battery, charges at
25 kW in Main Grid Mode, and discharges at 50 kW in Renewable Storage Mode.

## Local setup

Install the analysis and prediction dependencies in a local virtual
environment, then configure the ignored `.env` file. Use `.env.example` as the
template. Never commit `.env`.

Run the required prediction self-test:

```powershell
python test_eval.py
```

Run the batch predictor:

```powershell
python predict.py --input sample_test_input.csv --output predictions.csv
```

Run backend tests:

```powershell
python -m pytest app\appsail-python\tests
```

Run the dashboard locally with any static HTTP server, for example:

```powershell
python -m http.server 18765 --directory app\dashboard
```

The dashboard API base URL is the `API_BASE` constant at the top of
`app/dashboard/main.js`.

## API

- `GET /` — health check
- `GET /api/sample` — 24-row demo weather input
- `POST /api/forecast` — JSON rows or a CSV upload; returns timestamps and
  QuickML demand predictions
- `POST /api/dispatch` — predictions to controller decisions and battery state

The dashboard sends JSON as `text/plain;charset=UTF-8` to avoid Catalyst's
platform-level CORS preflight behavior; the backend parses it as JSON. CSV
uploads use multipart form data.

## Secure deployment

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
```

The script reads `.env` locally, injects only the required values temporarily
into `app-config.json`, runs `catalyst deploy`, and always restores the config.
It never prints secret values. Use `-SkipDeploy` to validate the mapping without
deploying.

Local `.env` names are mapped to neutral AppSail names to avoid Catalyst
reserved keywords:

| Local name | AppSail name |
| --- | --- |
| `QUICKML_ENDPOINT_URL` | `HS_QML_URL` |
| `QUICKML_ENDPOINT_KEY` | `HS_QML_KEY` |
| `CATALYST_ORG` | `HS_ORG_ID` |
| `CATALYST_ENVIRONMENT` | `HS_ENV_NAME` |
| `ZOHO_CLIENT_ID` | `HS_OAUTH_ID` |
| `ZOHO_CLIENT_SECRET` | `HS_OAUTH_SECRET` |
| `ZOHO_REFRESH_TOKEN` | `HS_OAUTH_REFRESH` |
| `ZOHO_ACCOUNTS_URL` | `HS_OAUTH_URL` |

The backend prefers the `HS_` names in AppSail and falls back to the original
names for local execution. OAuth access tokens are refreshed in memory and are
never sent to the frontend or logged.

## Submission checklist

- [x] Published QuickML model and one-row request contract
- [x] Chronological feature engineering with no target lags
- [x] Time-based local validation and generated analysis plots
- [x] AppSail API deployed and tested end to end
- [x] Slate dashboard deployed
- [x] 160 kW / 18–22 storage rule and 200 kW overload rule
- [x] Responsive dashboard with charts, alerts, battery state, and logs
- [x] Secure environment configuration and deployment cleanup
- [x] `test_eval.py` and backend tests passing
