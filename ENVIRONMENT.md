# Environment

Runtime environment, dependencies, and compatibility notes.

## Python

- **Required:** Python 3.10 or newer
- **Verified on:** Python 3.12.3 (this build) and Python 3.13.x (target local environment)

## Core dependencies

Pinned in `requirements.txt`:

| Package | Pinned version | Purpose |
|---|---|---|
| Flask | 3.0.3 | Web framework, routing, templating, JSON APIs |
| python-dotenv | 1.0.1 | Loads `.env` configuration |
| pandas | 2.2.2 | All dataset loading and analytical aggregation |
| numpy | 1.26.4 | Numeric operations, linear fits, normalization |
| scipy | 1.13.1 | Pearson correlation, Welch's t-test |
| scikit-learn | 1.5.1 | ROI model pipeline (training + inference) |
| joblib | 1.4.2 | Model artifact serialization |
| gunicorn | 22.0.0 | Production WSGI server (Unix) |
| pytest | 8.3.3 | Test suite |

Dependencies were reviewed in Phase 15: all nine are actually imported
by application or test code, none are duplicated, and none were
upgraded during this phase.

## Model compatibility note

`models/roi_early_stage_model.joblib` was trained with
**scikit-learn 1.5.1**. Loading it under a different major version may
produce an `InconsistentVersionWarning` and, in principle, altered
behaviour. The pin exists specifically to prevent that — do not upgrade
scikit-learn without retraining via `python/train_roi_model.py`.

## Frontend dependencies

There is **no frontend build step** — no npm, webpack, or bundler.

- **Chart.js 4.4.4** is vendored locally at
  `frontend/static/js/vendor/chart.umd.js`. It is served from the
  application itself, not a CDN, so the platform works fully offline.
- **Google Fonts** (Space Grotesk, Inter, IBM Plex Mono) are requested
  over the network in `base.html`. If offline, the browser falls back
  to the declared system font stacks; layout is unaffected.
- All page logic is vanilla JavaScript (ES2020) in
  `frontend/static/js/`. No framework.

## Dataset

- **Location:** `data/cleaned/marketing_campaign_cleaned.csv`
- **Shape:** 55,555 rows x 16 columns
- **Override:** set `DATA_PATH` in `.env`

The dataset is loaded once per process and cached in memory
(`backend/services/data_service.py`). No service re-reads the CSV per
request, and no service ever writes to it.

## Model artifacts

- `models/roi_early_stage_model.joblib` — full sklearn Pipeline
  (preprocessing + RandomForestRegressor)
- `reports/roi_model_metadata.json` — metrics, feature list, train/test
  sizes, model comparison, governance note

Both are loaded once per process and cached
(`backend/services/ml_service.py`).

## Configuration

Set via environment variables or `.env` (see `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `FLASK_ENV` | `development` | Use `production` for non-local runs |
| `SECRET_KEY` | dev default | **Set a unique value before any shared deployment** |
| `PORT` | `5000` | |
| `DATA_PATH` | `data/cleaned/marketing_campaign_cleaned.csv` | |
| `MODEL_PATH` | `models/roi_early_stage_model.joblib` | |
| `MODEL_METADATA_PATH` | `reports/roi_model_metadata.json` | |
| `DATABASE_URL` | `sqlite:///marketing_roi.db` | Reserved; no SQL layer is currently used |

**No secrets are committed to this repository.** `.env.example`
contains placeholders only.

## External services

None. The platform makes no outbound network calls at request time:

- The Marketing Analyst Copilot is entirely rule-based — **no LLM API,
  no API key required**.
- No telemetry, analytics beacons, or third-party endpoints.
