# GridSense AppSail API

Flask backend for the GridSense demand forecasting dashboard. It validates
telemetry, performs pure-Python feature engineering, calls the published
QuickML endpoint, and applies the microgrid dispatch controller.

Run the backend locally from this directory with:

```powershell
python app.py
```

Run its tests from the project root with:

```powershell
python -m pytest app\appsail-python\tests
```

# Deploying

Run `D:\HACKSPHERE\scripts\deploy.ps1` from PowerShell to deploy. The script
reads `.env` locally and temporarily places only the required deployment
variables in `app-config.json`; the values are restored and the temporary
backup is deleted after deployment. `.env` is never committed.

The local `.env` uses the original variable names:

- `QUICKML_ENDPOINT_URL`
- `QUICKML_ENDPOINT_KEY`
- `CATALYST_ORG`
- `CATALYST_ENVIRONMENT`
- `ZOHO_CLIENT_ID`
- `ZOHO_CLIENT_SECRET`
- `ZOHO_REFRESH_TOKEN`
- `ZOHO_ACCOUNTS_URL`

During deployment, these are injected into AppSail under neutral names to
avoid Catalyst reserved keywords:

| `.env` name | AppSail name |
| --- | --- |
| `QUICKML_ENDPOINT_URL` | `HS_QML_URL` |
| `QUICKML_ENDPOINT_KEY` | `HS_QML_KEY` |
| `CATALYST_ORG` | `HS_ORG_ID` |
| `CATALYST_ENVIRONMENT` | `HS_ENV_NAME` |
| `ZOHO_CLIENT_ID` | `HS_OAUTH_ID` |
| `ZOHO_CLIENT_SECRET` | `HS_OAUTH_SECRET` |
| `ZOHO_REFRESH_TOKEN` | `HS_OAUTH_REFRESH` |
| `ZOHO_ACCOUNTS_URL` | `HS_OAUTH_URL` |

The backend reads the `HS_` names first and falls back to the original names
for local runs.

Use `D:\HACKSPHERE\scripts\deploy.ps1 -SkipDeploy` to validate configuration
injection and restoration without deploying.
