# Marketing ROI Intelligence Platform

An evidence-driven marketing analytics and decision-support platform combining descriptive analytics, statistical testing, machine learning, forecasting, recommendations, budget allocation, data governance, and a controlled analytical copilot.

Built with Python, Flask, pandas, and scikit-learn. **No external AI service and no API key required — the platform runs entirely locally.**

---

## 1. Overview

A 16-page analytical web application built over a real 55,555-campaign
marketing dataset. Every figure shown in the UI is computed from that
dataset at request time; nothing is hard-coded or mocked.

The platform's defining characteristic is **analytical discipline**:
every claim is labelled with its evidence basis (OBSERVED / PREDICTIVE
/ EXPERIMENTAL), correlation is never presented as causation, forecasts
are always directional, and budget allocations are always described as
illustrative.

## 2. Business Problem

Marketing teams sit on large volumes of campaign data but struggle to
answer practical questions from it:

- Which campaign types, segments, audiences, and channels actually perform?
- Is an apparent performance gap real, or noise?
- What ROI can a planned campaign expect before launch?
- Where should budget go — and how confident can we be?
- Is the underlying data even trustworthy?

Worse, dashboards often *overclaim* — presenting correlation as
causation, or point forecasts as certainties — which leads to
misallocated spend.

## 3. Solution

A unified decision-support platform where each analytical capability is
a separate service, each answer carries its evidence basis, and the
governance limitations are surfaced in the UI rather than buried.

## 4. Key Capabilities

| Module | What it does |
|---|---|
| **Executive Decision Center** | Portfolio health score, strategic priorities, risk monitor, opportunity scorecard |
| **Overview** | Executive KPIs and campaign/segment performance |
| **Campaign Analytics** | 10 filters, sortable/paginated table, type/channel/segment/audience/language analysis, ROI distribution, CSV export |
| **Marketing Intelligence** | Monthly trends, performance drivers, funnel intelligence, efficiency analysis |
| **Forecasting & Future Outlook** | 3-month directional outlook with evidence strength and historical backtest |
| **Statistical Intelligence** | ROI correlations with p-values, distributions, IQR outliers |
| **A/B Testing** | Welch's t-test, Cohen's d, significance interpretation |
| **ROI Prediction** | Early-stage Random Forest prediction with error context |
| **Scenario Simulator** | Multi-scenario comparison and budget sensitivity |
| **Model Intelligence** | Model metrics, feature importance, Acquisition Cost dominance, limitations |
| **Business Insights** | Data-derived findings with evidence and implications |
| **Recommendation Intelligence** | Evidence-tagged, confidence-scored recommendations |
| **Data Quality & Governance** | Completeness, validation, outliers, duplicates, quality score, readiness |
| **Budget Allocation Optimizer** | Three allocation strategies with constraints and risk scoring |
| **Marketing Analyst Copilot** | Rule-based natural-language analytical interface |
| **Platform Health** | System integrity, asset checks, governance audit |

## 5. Architecture

Layered Flask application:

```
Routes (thin)  ->  Services (all logic)  ->  Cached DataFrame / Model artifact
```

- **Routes** validate input and serialize responses. No business logic.
- **Services** own all computation. Later phases reuse earlier services
  rather than recomputing (e.g. the Copilot and Executive Center both
  delegate to `recommendation_service`).
- **Data/model caching**: the CSV and the model pipeline are each
  loaded **once per process** and cached in memory.

## 6. Technology Stack

**Backend:** Python 3.10+, Flask 3.0, pandas, NumPy, SciPy, scikit-learn, joblib
**Frontend:** Jinja2 templates, vanilla JavaScript (ES2020), Chart.js 4.4.4 (vendored locally), custom dark CSS design system
**Testing:** pytest (370 tests)

No frontend build step. No database. No external APIs.

## 7. Dataset

`data/cleaned/marketing_campaign_cleaned.csv` — **55,555 rows x 16 columns**, spanning Jan 2024 – Dec 2025.

Columns: `Campaign_ID`, `Campaign_Type`, `Target_Audience`, `Duration`,
`Channel_Used`, `Impressions`, `Clicks`, `Leads`, `Conversions`,
`Revenue`, `Acquisition_Cost`, `ROI`, `Language`, `Engagement_Score`,
`Customer_Segment`, `Date`.

Verified totals: **₹28.66B revenue**, **2.71x average ROI**, **57.38M conversions**, **₹377.35 average acquisition cost**.

> `Channel_Used` contains 156 recorded **multi-channel combinations**
> (e.g. `"WhatsApp, YouTube"`). The platform treats these as recorded
> channel groups and never splits them into per-channel attribution,
> because the data does not support that attribution.

## 8. Analytics

Descriptive aggregation by campaign type, customer segment, target
audience, channel group, and language; ROI distribution and
illustrative performance bands; funnel intelligence
(Impressions → Clicks → Leads → Conversions, with stage rates and
drop-off); and cost-quintile efficiency analysis.

**Statistical layer:** Pearson correlations with p-values, skewness,
IQR outlier detection, and Welch's t-test with Cohen's d.

## 9. Machine Learning

**Model:** Random Forest (early-stage), trained via `python/train_roi_model.py`.

**Features (planning-stage only):** `Campaign_Type`, `Target_Audience`,
`Duration`, `Channel_Used`, `Language`, `Customer_Segment`,
`Acquisition_Cost`. Outcome variables (Revenue, Clicks, Leads,
Conversions, Engagement) are deliberately **excluded** to avoid target
leakage — the model is usable before a campaign launches.

**Performance (held-out test set):** R² **0.8093**, MAE **1.1346**, RMSE **1.9760**.

**Model comparison — the project's most important finding:**

| Model | R² |
|---|---|
| Cost-only Random Forest | 0.7908 |
| Full early-stage Random Forest | 0.8093 |
| Strategy-only Linear Regression | −0.0025 |

Acquisition Cost alone reaches nearly the full model's performance,
while campaign strategy variables alone have essentially **no**
predictive power. This is surfaced prominently in the UI rather than
hidden, because it materially constrains how the model should be used.

## 10. Forecasting

Deliberately simple and explainable — monthly aggregation, OLS linear
fit over the most recent 6 months, extrapolated 3 months forward.
Direction is classified UP/DOWN/STABLE against a documented ±1.5%
tolerance; evidence strength (HIGH/MEDIUM/LOW) reflects history length,
fit quality, and volatility. A historical backtest reports real MAE/RMSE
— including when the error is large.

## 11. Recommendations

Generated from live analytics across six categories (campaign, segment,
audience, channel, budget/cost, risk). Each carries a title, finding,
evidence basis, supporting metrics, confidence, risk level, and an
expandable "why" breakdown (evidence / interpretation / caution).

## 12. Budget Allocation

Given a budget and constraints, produces three allocation strategies —
Equal, Performance, Risk-Adjusted. The **Allocation Score** (0–100)
blends ROI performance (40%), ROI consistency (25%), cost efficiency
(20%), and evidence volume (15%). A separate **Risk Level** averages
ROI volatility, negative-ROI share, and evidence scarcity.

Constraints are enforced by iterative water-filling; allocations always
sum to exactly 100%, and infeasible constraints return a clear error
rather than being silently overridden.

## 13. Data Quality & Governance

Read-only inspection: completeness, type validation, range validity,
funnel consistency, IQR outliers, duplicates, date quality, an
Analytical Data Quality Score, analytics readiness, governance flags,
and a searchable data dictionary.

**This module never modifies the dataset.** Outliers are reported, never
removed. Negative ROI is treated as a legitimate business outcome, not a
data defect.

Current result: score **100/100 (Excellent)**, readiness **READY WITH
CAUTION** — clean data, but real statistical outliers are present.

## 14. Marketing Analyst Copilot

A **controlled** natural-language interface — not a generic chatbot.
Deterministic keyword/regex routing over 14 approved intents, each
delegating to an existing service. It cannot invent a statistic, and
refuses questions requiring causal claims or guaranteed outcomes.

Every answer returns intent, answer, evidence basis, supporting metrics,
source area, and caveats — making it fully auditable.

## 15. Model Limitations

1. Acquisition Cost dominates predictive performance.
2. Strategy-only variables have essentially no predictive power (R² ≈ −0.0025).
3. The model does not establish causality.
4. Predictions are estimates, not guarantees.
5. Historical relationships may not continue.
6. Outliers are present and were deliberately retained.
7. The model should support, not replace, business judgment.

## 16. Analytical Guardrails

| Evidence type | Meaning |
|---|---|
| **OBSERVED** | Descriptive finding read from historical records |
| **PREDICTIVE** | Model- or forecast-derived estimate |
| **EXPERIMENTAL** | A/B test / statistical comparison result |

These are labelled on every recommendation, insight, and Copilot answer,
and are never blended within a single claim.

The platform consistently says *"X has the highest observed average ROI"*
rather than *"X causes higher ROI"*; *"directional outlook suggests"*
rather than *"revenue will increase"*; and *"illustrative
historical-performance-based allocation"* rather than *"optimal
allocation"*.

## 17. Project Structure

```
backend/
  app.py                  Flask app factory, blueprint + page registration
  config.py               Environment-based configuration
  routes/                 14 route modules (thin controllers)
  services/               15 service modules (all business logic)
  tests/                  6 pytest modules (370 tests)
  utils/
frontend/
  templates/              17 Jinja2 templates
  static/css/main.css     Dark design system
  static/js/              18 page scripts + api.js helper
  static/js/vendor/       Chart.js 4.4.4 (vendored)
models/
  roi_early_stage_model.joblib
reports/
  roi_model_metadata.json
  platform_test_summary.json
data/cleaned/
  marketing_campaign_cleaned.csv
python/
  train_roi_model.py
  generate_test_summary.py
docs/screenshots/
run.py
requirements.txt
```

## 18. Installation

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

See `RUN_GUIDE.md` for full step-by-step instructions and
`ENVIRONMENT.md` for compatibility notes.

## 19. Running the Application

```bash
python run.py
```

Then open **http://127.0.0.1:5000**

## 20. Testing

```bash
python -m pytest backend/tests -v
```

**370 tests, all passing.** Coverage includes every API endpoint, page
route, edge case (empty data, missing columns, missing model),
validation path, injection-safety case, and cross-phase regression.

Regenerate the machine-readable summary from a real run:

```bash
python python/generate_test_summary.py
```

## 21. API Overview

42 registered API routes. Key endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Basic liveness check |
| `/api/health/platform` | GET | Full platform integrity report |
| `/api/summary` | GET | Executive KPIs |
| `/api/campaign-types` | GET | Per-campaign-type performance |
| `/api/customer-segments` | GET | Per-segment performance |
| `/api/statistics` | GET | Correlations, distributions, outliers |
| `/api/ab-test` | GET | Welch's t-test result |
| `/api/campaign-analytics/*` | GET | 12 filtered analytics endpoints |
| `/api/marketing-intelligence` | GET | Trends, drivers, funnel, efficiency |
| `/api/forecasting` | GET | Directional outlook + backtest |
| `/api/recommendations` | GET | Evidence-tagged recommendations |
| `/api/executive-summary` | GET | Executive decision payload |
| `/api/data-quality` | GET | Full data quality report |
| `/api/model-intelligence` | GET | Model metrics, importance, limitations |
| `/api/predict-roi` | POST | Single ROI prediction |
| `/api/scenario/compare` | POST | Multi-scenario comparison |
| `/api/budget-optimizer` | GET/POST | Allocation strategies |
| `/api/copilot/ask` | POST | Natural-language analytical question |
| `/api/copilot/capabilities` | GET | Supported question categories |
| `/api/copilot/reset` | POST | Clear Copilot session context |

**Error handling:** `400` invalid input, `503` dataset/model
unavailable, `500` unexpected. Stack traces are never exposed.

## 22. Screenshots

Capture instructions and the recommended shot list are in
`docs/screenshots/README.md`. Screenshots are captured manually — none
are generated or mocked.

## 23. Future Scope

- Authentication and role-based access for multi-user deployment
- PostgreSQL backend (the config layer already anticipates this)
- Scheduled model retraining with drift monitoring
- Seasonality-aware forecasting (SARIMA / Prophet) alongside the current linear baseline
- Experiment design tooling to validate budget reallocations before deployment
- Semantic intent matching for the Copilot, to complement the deterministic router

---

## Governance Statement

This platform combines historical analytics, statistical evidence,
predictive modeling, forecasting, recommendations, and illustrative
budget scenarios. **Outputs are intended to support human
decision-making.** Historical association does not establish causality.
Predictions and forecasts are estimates. Budget allocations are
illustrative and should be validated before real-world deployment.
#   M a r k e t i n g - R O I - I n t e l l i g e n c e - P l a t f o r m  
 