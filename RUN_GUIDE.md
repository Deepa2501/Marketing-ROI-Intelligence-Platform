# Run Guide

How to run the Marketing ROI Intelligence Platform locally. Instructions
are written for Windows (PowerShell / Command Prompt); macOS and Linux
equivalents are noted where they differ.

## 1. Open the project directory

```bat
cd path\to\Marketing-ROI-Analytics
```

## 2. Create and activate a virtual environment

```bat
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install requirements

```bat
pip install -r requirements.txt
```

> **Note on scikit-learn:** the saved model artifact was trained with
> scikit-learn 1.5.1, which is pinned in `requirements.txt`. Installing
> a different major version may emit an `InconsistentVersionWarning`
> when loading `models/roi_early_stage_model.joblib`. Keep the pin
> unless you retrain the model.

## 4. Verify the dataset is present

The application expects:

```
data\cleaned\marketing_campaign_cleaned.csv
```

Expected shape: **55,555 rows x 16 columns**.

If the file is missing, the application still starts, but data-driven
pages will show a clear "dataset connection pending" state and APIs
return HTTP 503 instead of failing silently.

## 5. Run the tests

```bat
python -m pytest backend\tests -v
```

Quiet summary only:

```bat
python -m pytest backend\tests -q
```

To regenerate `reports\platform_test_summary.json` from a real run:

```bat
python python\generate_test_summary.py
```

## 6. Start the application

```bat
python run.py
```

## 7. Open the application

Navigate to:

```
http://127.0.0.1:5000
```

## 8. Verify platform health

Either open the **Platform Health** page in the sidebar, or call:

```
http://127.0.0.1:5000/api/health/platform
```

This reports dataset, model, service, template, route, navigation,
configuration, environment, and test-suite status. A `WARN` on
`SECRET_KEY` is expected on a fresh checkout — see `SECURITY_NOTES.md`.

## Optional: environment configuration

Copy `.env.example` to `.env` to override defaults:

```bat
copy .env.example .env
```

Available variables: `FLASK_ENV`, `SECRET_KEY`, `PORT`, `DATA_PATH`,
`MODEL_DIR`, `MODEL_PATH`, `MODEL_METADATA_PATH`, `DATABASE_URL`.

## Optional: retrain the ROI model

Only needed if `models\roi_early_stage_model.joblib` is missing:

```bat
python python\train_roi_model.py
```

This writes the model artifact and `reports\roi_model_metadata.json`.
Training takes several minutes on a single core.

## Production-style run (optional)

```bat
set FLASK_ENV=production
gunicorn run:app
```

(`gunicorn` is Unix-only; on Windows use `waitress` or run behind WSL.)

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Pages load but show "dataset connection pending" | CSV not at `data\cleaned\` | Place the dataset at the expected path, or set `DATA_PATH` |
| Model/prediction pages return 503 | Model artifact missing | Run `python python\train_roi_model.py` |
| `InconsistentVersionWarning` on startup | scikit-learn version mismatch | `pip install scikit-learn==1.5.1` |
| Port already in use | Another process on 5000 | Set `PORT` in `.env` |
