# Portfolio Project Summary

## Project Title

**Marketing ROI Intelligence Platform** — an evidence-driven marketing
analytics and decision-support platform.

## Problem

Marketing teams accumulate large volumes of campaign data but struggle
to convert it into defensible decisions. Typical BI dashboards make
this worse in a specific way: they present correlation as causation,
point forecasts as certainties, and ranked lists as optimal
allocations. Budget gets moved on evidence that doesn't actually
support the move.

## Solution

A 16-page Flask application over a real 55,555-campaign dataset, where
every analytical capability is a separate service, every claim is
labelled with its evidence basis, and the governing limitations are
surfaced in the UI rather than buried in a footnote.

The organising principle is **analytical honesty**: the platform is
designed to be *harder* to misuse than a conventional dashboard.

## Key Features

- **Executive Decision Center** — portfolio health score, strategic priorities, risk monitor
- **Campaign Analytics** — 10 filters, server-side pagination, five analysis dimensions, CSV export
- **Statistical Intelligence** — correlations with p-values, distributions, IQR outliers
- **A/B Testing** — Welch's t-test with Cohen's d and significance interpretation
- **ROI Prediction** — leakage-safe early-stage Random Forest with error context
- **Scenario Simulator** — multi-scenario comparison and budget sensitivity
- **Model Intelligence** — metrics, feature importance, dominance analysis, explicit limitations
- **Forecasting** — 3-month directional outlook with evidence strength and a real backtest
- **Recommendations** — evidence-tagged, confidence-scored, with "why" breakdowns
- **Budget Optimizer** — three strategies, constraint solving, transparent scoring
- **Data Quality & Governance** — read-only integrity inspection, never mutates data
- **Marketing Analyst Copilot** — rule-based NL interface, no external AI service
- **Platform Health** — system integrity and governance audit

## Technical Architecture

Layered Flask application: thin routes → services (all logic) → cached
data/model layer.

- 14 route modules, 15 service modules, 17 templates, 18 page scripts
- Dataset and model artifact each loaded **once per process** and cached
- Later phases reuse earlier services rather than duplicating logic
- Vanilla JavaScript, no build step, Chart.js vendored locally
- 42 API endpoints with consistent JSON error contracts

## Data Pipeline

`CSV → cached pandas DataFrame → service-layer aggregation → JSON API → vanilla-JS rendering`

The dataset is read once and never written to. A dedicated data-quality
module verifies completeness, types, ranges, funnel consistency,
duplicates, and dates — reporting issues without ever modifying source
data.

## ML Approach

Random Forest regression on **planning-stage features only** —
outcome variables (revenue, clicks, leads, conversions, engagement)
are deliberately excluded to prevent target leakage, so the model is
usable *before* a campaign launches.

Held-out performance: **R² 0.8093, MAE 1.1346, RMSE 1.9760**.

The most valuable finding came from a deliberate ablation:

| Model | R² |
|---|---|
| Cost-only | 0.7908 |
| Full early-stage | 0.8093 |
| Strategy-only | −0.0025 |

Acquisition Cost alone nearly matches the full model; campaign strategy
alone predicts essentially nothing. Rather than hiding this, the
platform features it prominently — it is the single most important
constraint on how the model may be used.

## Statistical Analysis

Pearson correlations with significance testing, skewness, IQR outlier
detection (retained, never removed), and Welch's t-test with Cohen's d
effect size. The headline A/B comparison (Social Media vs Paid Ads)
returns p = 0.598 — **not significant** — and the platform reports it as
such rather than manufacturing a recommendation from noise.

## Forecasting

Deliberately simple and auditable: monthly aggregation, OLS fit on the
recent 6-month window, 3-month extrapolation, with UP/DOWN/STABLE
classification against a documented tolerance and HIGH/MEDIUM/LOW
evidence strength. A historical backtest reports genuine MAE/RMSE — and
honestly surfaces large error where the series contains a regime shift.

## Decision-Support Components

Recommendation Intelligence, Budget Allocation Optimizer, Scenario
Simulator, and the Marketing Analyst Copilot. Each returns structured,
auditable output: what the finding is, what evidence supports it, how
confident it is, and what cannot be concluded from it.

## Governance

- Three evidence types (OBSERVED / PREDICTIVE / EXPERIMENTAL), never blended
- No causal language anywhere — enforced by automated tests
- Forecasts always directional; allocations always illustrative
- Model limitations displayed in-product, not just documented
- Data quality module is strictly read-only

## Testing

**370 pytest tests, all passing.** Coverage includes every API endpoint
and page route, edge cases (empty data, missing columns, missing model,
short history), all validation paths, cross-phase regression after every
change, 10 parameterized injection-safety payloads with filesystem
side-effect verification, dataset-immutability checks via hash
comparison, and assertions that no causal or guarantee language appears
in API responses.

## Key Business Insights

- **Social Media** has the highest observed average ROI (2.75x) among campaign types — but the A/B test vs Paid Ads is **not statistically significant** (p = 0.598, Cohen's d = 0.007), so the gap doesn't justify reallocation on its own.
- **Working Women** is the strongest customer segment by both revenue (₹5.81B) and average ROI (2.77x).
- **23.8%** of campaigns have negative observed ROI — a legitimate outcome, flagged for review rather than treated as bad data.
- The largest funnel drop-off is **Impressions → Clicks** (~91.5%, CTR ≈ 8.5%).
- **Acquisition Cost** is the dominant predictive signal; campaign strategy alone has no predictive power.

## Limitations

- Observational dataset — no causal inference is possible
- Model performance is driven largely by Acquisition Cost
- Forecasting uses a simple linear method, with no seasonality modelling
- The Copilot uses deterministic keyword routing, so unusual phrasing may be declined rather than understood (a deliberate trade — a false refusal is safer than a fabricated answer)
- No authentication; intended as a local demonstration

## Future Scope

Authentication and RBAC; PostgreSQL migration (already anticipated in
config); scheduled retraining with drift monitoring; seasonality-aware
forecasting alongside the linear baseline; experiment-design tooling to
validate reallocations; semantic intent matching to complement the
Copilot's deterministic router.

---

## Resume Project Description

- **Built a 16-page marketing analytics and decision-support platform** (Python, Flask, pandas, scikit-learn) over a 55,555-campaign dataset, delivering 42 REST endpoints across descriptive analytics, statistical testing, ML prediction, forecasting, recommendations, budget optimization, data governance, and a rule-based analytical copilot.
- **Engineered a leakage-safe ROI prediction model** (Random Forest, R² 0.81) using planning-stage features only, and ran an ablation study proving Acquisition Cost drives nearly all predictive power while strategy variables contribute none (R² −0.0025) — surfacing this limitation in-product rather than obscuring it.
- **Designed a three-tier evidence framework** (OBSERVED / PREDICTIVE / EXPERIMENTAL) enforced across every recommendation, forecast, and API response, with automated tests asserting no causal or guarantee language reaches users.
- **Achieved 370 passing automated tests** covering all endpoints, edge cases, injection-safety payloads, dataset-immutability verification, and full cross-phase regression, plus a self-diagnosing platform health endpoint reporting real system integrity status.
