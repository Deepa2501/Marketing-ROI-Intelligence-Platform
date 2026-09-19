# Marketing ROI Intelligence Platform

> **Evidence-driven marketing analytics and decision-support platform** built with Python and Flask to help teams understand campaign performance, estimate ROI, evaluate scenarios, forecast directional trends, generate evidence-based recommendations, and explore budget allocation strategies.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-black)
![pandas](https://img.shields.io/badge/pandas-2.x-150458)
![scikit--learn](https://img.shields.io/badge/scikit--learn-1.5-F7931E)
![Tests](https://img.shields.io/badge/tests-370%20passing-success)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

**No external AI service or API key is required.** The platform runs locally using deterministic analytics, statistical methods, machine learning, forecasting, and a controlled analytical Copilot.

---

## 📌 Project at a Glance

| Area | Details |
|---|---|
| **Dataset** | 55,555 marketing campaigns |
| **Features** | 16 columns |
| **Backend** | Python + Flask |
| **Analytics** | pandas + NumPy + SciPy |
| **Machine Learning** | scikit-learn Random Forest |
| **Frontend** | Jinja2 + JavaScript + Chart.js |
| **Testing** | 370 automated tests |
| **Database** | None — CSV-based analytical pipeline |
| **External APIs** | None |
| **AI API Key** | Not required |
| **Application Type** | Local analytical web platform |

---

## 🎯 Business Problem

Marketing teams often have large amounts of campaign data but struggle to turn it into reliable decisions.

Typical questions include:

- Which campaign types and customer segments perform better historically?
- Which relationships in the data are statistically meaningful?
- Can expected ROI be estimated before launching a campaign?
- What does recent performance suggest about the next few months?
- How could a given budget be distributed across segments?
- Are recommendations supported by enough evidence?
- Is the underlying dataset suitable for analysis?

A major challenge is **analytical overclaiming**: correlation may be mistaken for causation, forecasts may be treated as guarantees, and historical performance may be presented as an optimal future strategy.

This project was designed to address those issues through **evidence labels, statistical context, model limitations, validation, and governance controls**.

---

## 💡 Solution

The **Marketing ROI Intelligence Platform** combines multiple analytical layers into one web application:

```text
                    ┌─────────────────────────┐
                    │   Marketing Campaign    │
                    │         Dataset         │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Data Quality & ETL     │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       Descriptive          Statistical        Machine Learning
        Analytics             Analysis             & Forecasting
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │ Decision Intelligence   │
                    │ Recommendations         │
                    │ Scenarios               │
                    │ Budget Allocation       │
                    │ Analytical Copilot      │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │ Executive Dashboard     │
                    │ & Decision Support      │
                    └─────────────────────────┘
```

The platform does **not** claim that historical associations prove causality. Analytical outputs are clearly separated into observed, predictive, and experimental evidence.

---

# 🚀 Key Features

## 1. Executive Decision Center

Provides a high-level view of portfolio performance, including:

- Executive KPIs
- Strategic priorities
- Risk monitoring
- Opportunity scorecard
- Evidence-backed decision signals

---

## 2. Campaign Analytics

Interactive campaign-level analysis with:

- Multiple filters
- Sortable and paginated campaign table
- Campaign-type analysis
- Channel-group analysis
- Customer-segment analysis
- Target-audience analysis
- Language analysis
- ROI distribution
- CSV export

---

## 3. Marketing Intelligence

Combines multiple analytical perspectives:

- Monthly performance trends
- Performance drivers
- Marketing funnel analysis
- Conversion-stage analysis
- Cost-efficiency analysis
- Historical performance patterns

---

## 4. Statistical Intelligence

Provides statistical context rather than only dashboard numbers:

- Pearson correlations
- p-values
- Distribution analysis
- Skewness
- IQR-based outlier detection
- Statistical comparisons

---

## 5. A/B Testing

Compares campaign groups using:

- Welch's t-test
- p-value
- Cohen's d
- Sample sizes
- Statistical interpretation

The platform avoids treating a non-significant difference as proof that one strategy causes better performance.

---

## 6. ROI Prediction

An early-stage Random Forest model estimates ROI using information that can be available before campaign outcomes occur.

### Planning-stage features

- Campaign Type
- Target Audience
- Duration
- Channel Used
- Language
- Customer Segment
- Acquisition Cost

Outcome variables such as Revenue, Clicks, Leads, Conversions, and Engagement are deliberately excluded to reduce target leakage.

### Held-out test performance

| Metric | Result |
|---|---:|
| **R²** | 0.8093 |
| **MAE** | 1.1346 |
| **RMSE** | 1.9760 |

### Important model finding

| Model | R² |
|---|---:|
| Cost-only Random Forest | 0.7908 |
| Full early-stage Random Forest | 0.8093 |
| Strategy-only Linear Regression | -0.0025 |

Acquisition Cost accounts for most of the model's predictive performance in this dataset. Strategy-only variables provide very limited predictive power.

This finding is intentionally surfaced as a **model limitation**, not hidden behind a single headline accuracy number.

---

## 7. Scenario Simulator

Allows users to compare hypothetical campaign configurations and examine:

- Predicted ROI
- Scenario differences
- Budget sensitivity
- Illustrative estimated profit

> **Important:** Estimated profit is model-derived and illustrative. It is not guaranteed financial profit or revenue.

---

## 8. Forecasting & Future Outlook

The forecasting module provides a deliberately simple and explainable baseline:

- Monthly aggregation
- OLS trend fitting
- Most recent six months used for the trend
- Three-month directional outlook
- UP / DOWN / STABLE classification
- Evidence-strength classification
- Historical backtesting
- MAE / RMSE reporting

Forecasts are presented as **directional estimates**, not guaranteed outcomes.

---

## 9. Recommendation Intelligence

Recommendations are generated from analytical outputs across:

- Campaigns
- Customer segments
- Audiences
- Channel groups
- Budget and cost
- Risk

Each recommendation includes:

- Finding
- Evidence basis
- Supporting metrics
- Confidence
- Risk level
- Explanation
- Caution / limitation

---

## 10. Budget Allocation Optimizer

The optimizer generates three historical-performance-based strategies:

1. **Equal Allocation**
2. **Performance Allocation**
3. **Risk-Adjusted Allocation**

The allocation score combines:

- ROI performance — 40%
- ROI consistency — 25%
- Cost efficiency — 20%
- Evidence volume — 15%

Risk considers:

- ROI volatility
- Negative-ROI share
- Evidence scarcity

Constraints are enforced so that allocations sum to exactly **100%**. Infeasible constraints produce an explicit validation error instead of being silently overridden.

> **Important:** These are illustrative historical-performance-based scenarios, not guaranteed optimal allocations.

---

## 11. Data Quality & Governance

The governance layer performs read-only checks for:

- Missing values
- Data types
- Range validity
- Funnel consistency
- IQR outliers
- Duplicate records
- Date quality
- Analytical readiness
- Governance flags
- Data dictionary information

The module **does not modify the dataset**.

Outliers are reported rather than automatically removed. Negative ROI is treated as a legitimate business outcome rather than automatically classified as a data defect.

Current analytical result:

- **Data Quality Score:** 100/100
- **Readiness:** READY WITH CAUTION

---

## 12. Marketing Analyst Copilot

The Copilot is a **controlled analytical interface**, not a general-purpose chatbot.

It uses deterministic keyword/regex routing across approved analytical intents and delegates requests to existing services.

### Design principles

- No external LLM API
- No API key
- No invented statistics
- No unsupported causal claims
- No guaranteed-outcome claims
- Uses existing analytical services
- Returns evidence and caveats

Each response can expose:

- Intent
- Answer
- Evidence basis
- Supporting metrics
- Source area
- Caveats

---

## 13. Platform Health

The platform includes an integrity and readiness layer that checks:

- Dataset availability
- Model artifact availability
- Required project assets
- API/system integrity
- Governance status
- Test summary

Endpoint:

```text
GET /api/health/platform
```

---

# 📊 Dataset

File:

```text
data/cleaned/marketing_campaign_cleaned.csv
```

### Dataset size

**55,555 rows × 16 columns**

### Columns

```text
Campaign_ID
Campaign_Type
Target_Audience
Duration
Channel_Used
Impressions
Clicks
Leads
Conversions
Revenue
Acquisition_Cost
ROI
Language
Engagement_Score
Customer_Segment
Date
```

### Dataset summary

| Metric | Value |
|---|---:|
| Revenue | ₹28.66B |
| Average ROI | 2.71x |
| Conversions | 57.38M |
| Average Acquisition Cost | ₹377.35 |

### Channel representation

`Channel_Used` contains recorded multi-channel combinations such as:

```text
WhatsApp, YouTube
```

The platform treats these as recorded channel groups and does **not** split them into individual-channel attribution because the dataset does not support reliable attribution at that level.

---

# 🧠 Analytical Guardrails

Every analytical layer follows an explicit evidence framework.

| Evidence | Meaning |
|---|---|
| **OBSERVED** | Descriptive finding directly derived from historical records |
| **PREDICTIVE** | Model- or forecast-derived estimate |
| **EXPERIMENTAL** | Statistical or A/B testing result |

Examples of the project's analytical language:

> “X has the highest observed average ROI”

instead of:

> “X causes higher ROI”

And:

> “The directional outlook suggests…”

instead of:

> “Revenue will increase.”

This distinction is a core design principle of the platform.

---

# 🏗️ Architecture

The application follows a layered Flask architecture:

```text
Routes
   ↓
Services
   ↓
Cached DataFrame / Model Artifact
   ↓
JSON / HTML Response
```

### Routes

Routes handle:

- Request validation
- Parameter parsing
- Response serialization

Business logic is kept out of route handlers.

### Services

Services contain the analytical logic and are reused across multiple modules.

For example, the Executive Decision Center and Copilot can delegate to existing recommendation and analytical services rather than duplicating calculations.

### Caching

The cleaned CSV and model pipeline are loaded once per process and cached in memory.

---

# 🛠️ Technology Stack

### Backend

- Python 3.10+
- Flask 3.0
- pandas
- NumPy
- SciPy
- scikit-learn
- joblib

### Frontend

- Jinja2
- HTML5
- CSS3
- Vanilla JavaScript ES2020
- Chart.js 4.4.4
- Custom dark UI design system

### Testing

- pytest
- 370 automated tests

### Infrastructure

- CSV-based data pipeline
- Local model artifact
- No database required
- No frontend build step
- No external API dependency

---

# 📁 Project Structure

```text
Marketing-ROI-Intelligence-Platform/
│
├── backend/
│   ├── app.py
│   ├── config.py
│   ├── routes/
│   ├── services/
│   ├── tests/
│   └── utils/
│
├── frontend/
│   ├── templates/
│   └── static/
│       ├── css/
│       └── js/
│
├── data/
│   └── cleaned/
│       └── marketing_campaign_cleaned.csv
│
├── models/
│   └── roi_early_stage_model.joblib
│
├── reports/
│   ├── roi_model_metadata.json
│   └── platform_test_summary.json
│
├── python/
│   ├── train_roi_model.py
│   └── generate_test_summary.py
│
├── docs/
│   └── screenshots/
│
├── run.py
├── requirements.txt
├── README.md
├── RUN_GUIDE.md
├── ENVIRONMENT.md
├── SECURITY_NOTES.md
├── DEMO_GUIDE.md
└── PHASE15_COMPLETION_REPORT.md
```

---

# ⚙️ Installation

## 1. Clone the repository

```bash
git clone https://github.com/Deepa2501/Marketing-ROI-Intelligence-Platform.git
cd Marketing-ROI-Intelligence-Platform
```

## 2. Create a virtual environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

For additional environment and compatibility details, see:

- `RUN_GUIDE.md`
- `ENVIRONMENT.md`

---

# ▶️ Run the Application

Start the Flask application:

```bash
python run.py
```

Open:

```text
http://127.0.0.1:5000
```

---

# 🧪 Testing

Run the complete backend test suite:

```bash
python -m pytest backend/tests -v
```

### Current test status

**370 tests passed**

The test suite covers:

- API endpoints
- Page routes
- Service logic
- Validation
- Edge cases
- Missing data/model scenarios
- Security/injection-safety cases
- Cross-module regression
- Governance checks

Generate the machine-readable test summary:

```bash
python python/generate_test_summary.py
```

---

# 🔌 API Overview

The platform exposes **42 registered API routes**.

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Basic liveness check |
| `/api/health/platform` | GET | Platform integrity report |
| `/api/summary` | GET | Executive KPIs |
| `/api/campaign-types` | GET | Campaign-type performance |
| `/api/customer-segments` | GET | Segment performance |
| `/api/statistics` | GET | Correlations, distributions, outliers |
| `/api/ab-test` | GET | Welch's t-test result |
| `/api/campaign-analytics/*` | GET | Filtered campaign analytics |
| `/api/marketing-intelligence` | GET | Trends, drivers, funnel, efficiency |
| `/api/forecasting` | GET | Directional forecast + backtest |
| `/api/recommendations` | GET | Evidence-tagged recommendations |
| `/api/executive-summary` | GET | Executive decision payload |
| `/api/data-quality` | GET | Data quality report |
| `/api/model-intelligence` | GET | Model metrics and limitations |
| `/api/predict-roi` | POST | Single ROI prediction |
| `/api/scenario/compare` | POST | Scenario comparison |
| `/api/budget-optimizer` | GET/POST | Budget allocation |
| `/api/copilot/ask` | POST | Analytical Copilot |
| `/api/copilot/capabilities` | GET | Supported Copilot intents |
| `/api/copilot/reset` | POST | Reset Copilot session context |

### Error handling

The API uses structured error responses:

- `400` — invalid input
- `503` — dataset/model unavailable
- `500` — unexpected server error

Internal stack traces are not exposed through the API response.

---

# 📸 Screenshots & Demo

Recommended screenshots are maintained under:

```text
docs/screenshots/
```

Capture guidance is documented in:

```text
docs/screenshots/README.md
```

For a guided demonstration, see:

```text
DEMO_GUIDE.md
```

---

# ⚠️ Model Limitations

The project intentionally documents its limitations.

1. Acquisition Cost dominates predictive performance.
2. Strategy-only variables have very limited predictive power.
3. The model does not establish causality.
4. Predictions are estimates, not guarantees.
5. Historical relationships may not continue in future data.
6. Outliers exist and were deliberately retained.
7. Budget allocations are illustrative scenarios.
8. The platform is intended to support — not replace — business judgment.

---

# 🔮 Future Scope

Potential extensions include:

- Authentication and role-based access
- PostgreSQL-backed data storage
- Scheduled model retraining
- Model drift monitoring
- Seasonality-aware forecasting
- SARIMA / Prophet comparison
- Experiment-design tooling for budget changes
- Semantic intent matching for the Copilot
- Multi-user deployment
- Automated data ingestion pipelines

---

# 📌 Project Status

**Status: Portfolio / Demonstration Ready**

The project includes:

- Full-stack Flask application
- 16 analytical pages/modules
- 42 API routes
- Machine learning pipeline
- Forecasting module
- Recommendation engine
- Budget optimizer
- Data governance layer
- Controlled analytical Copilot
- Platform health checks
- 370 passing automated tests
- Documentation and demo guidance

> This project is designed as a portfolio and analytical demonstration platform. It should not be interpreted as a production financial or marketing decision engine without additional authentication, infrastructure, monitoring, data validation, and business-domain validation.

---

# 👩‍💻 Author

**Deepa Saxena**

**Data Analyst | Business Intelligence | SQL | Python | Power BI**

GitHub:  
https://github.com/Deepa2501

LinkedIn:  
https://www.linkedin.com/in/deepa-saxena-694082390/

---

# 📄 Supporting Documentation

| Document | Purpose |
|---|---|
| `RUN_GUIDE.md` | Detailed setup and execution guide |
| `ENVIRONMENT.md` | Environment and compatibility notes |
| `SECURITY_NOTES.md` | Security considerations |
| `DEMO_GUIDE.md` | Project demonstration flow |
| `PHASE15_COMPLETION_REPORT.md` | Final implementation and validation report |

---

## Governance Statement

This platform combines historical analytics, statistical analysis, predictive modeling, forecasting, recommendations, and illustrative budget scenarios.

**All outputs are intended to support human decision-making.**

Historical association does not establish causality. Predictions and forecasts are estimates. Budget allocations are illustrative and should be validated before real-world deployment.
