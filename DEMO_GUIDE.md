# Demo Guide — 10 Minute Walkthrough

A sequenced demo flow. Timings are approximate; the whole run fits in
10 minutes at a steady pace.

**Before you start:** `python run.py`, open `http://127.0.0.1:5000`,
maximize the browser.

**Framing line to open with:**
> "This is a marketing decision-support platform over 55,555 real
> campaigns. What makes it different from a standard dashboard is that
> every claim is labelled with its evidence basis, and the limitations
> are shown in the product rather than hidden."

---

## 1. Overview (~45s)

**Show:** KPI cards and the four performance charts.

**Say:** "₹28.66B revenue across 55,555 campaigns, 2.71x average ROI.
Every number here is computed from the dataset at request time."

**Key insight:** Social Media leads on average ROI; Influencer leads on
total revenue — different winners depending on the metric.

**Caveat:** "These are observed historical figures, not projections."

---

## 2. Campaign Analytics (~60s)

**Show:** Apply `Campaign Type = Social Media`. Point out the KPIs
updating. Scroll to the channel analysis table.

**Say:** "Filtering is server-side — the browser never receives all
55,555 rows. Notice the KPIs recalculate against the filtered set, not
the global totals."

**Key insight:** Channel data contains 156 recorded *multi-channel
combinations*, so the platform reports recorded channel groups rather
than inventing per-channel attribution.

**Caveat:** "We deliberately don't split multi-channel records — the
data doesn't support that attribution."

---

## 3. Statistical Intelligence (~45s)

**Show:** The ROI correlation chart and the significance table.

**Say:** "Revenue correlates with ROI at r = 0.786, Acquisition Cost
negatively at −0.371, each with a p-value."

**Key insight:** Correlation strength is reported alongside significance
so a strong-looking bar can't be read in isolation.

**Caveat:** "Every one of these is an association. None of it
establishes causation."

---

## 4. ROI Prediction (~60s)

**Show:** Fill the form, click **Predict ROI**. Point at the gauge, then
scroll to the Prediction Context panel.

**Say:** "This is a Random Forest trained only on planning-stage
inputs — no revenue, clicks, or conversions — so it works before launch."

**Key insight:** The result includes error context (±MAE) and the
primary model driver, making the prediction auditable.

**Caveat:** "Labelled 'error context, not a statistical confidence
interval' — because MAE isn't a confidence interval."

---

## 5. Model Intelligence (~75s) — *the strongest moment*

**Show:** Model metrics, then scroll to **Acquisition Cost Dominance**.

**Say:** "R² is 0.81. But here's the honest part: a cost-only model
reaches 0.79, and a strategy-only model reaches *minus* 0.0025."

**Key insight:** Acquisition Cost drives nearly all predictive power;
campaign strategy variables alone predict essentially nothing.

**Caveat:** "Which is exactly why the page says the model doesn't
establish that campaign strategy causes ROI. We found this and featured
it rather than hiding it."

---

## 6. Recommendations (~45s)

**Show:** A recommendation card; expand "Why this recommendation?".

**Say:** "Each recommendation carries an evidence basis, confidence
level, supporting metrics, and an explicit caution."

**Key insight:** Recommendations are generated from live analytics, not
authored copy.

**Caveat:** "The caution line states what *cannot* be concluded."

---

## 7. Forecasting (~50s)

**Show:** A historical + forecast chart (dashed segment), then the
Historical Backtest table.

**Say:** "Three-month directional outlook from a simple linear fit on
the recent window — deliberately explainable, not a black box."

**Key insight:** The backtest reports genuine error, including large
error on Revenue where the series has a regime shift.

**Caveat:** "Showing a bad backtest result is the point — a forecast you
can't audit isn't decision support."

---

## 8. Budget Allocation (~60s)

**Show:** Run with defaults. Show the allocation table, then Strategy
Comparison.

**Say:** "Three strategies — equal, performance-weighted, risk-adjusted.
The Allocation Score blends ROI, consistency, cost efficiency, and
evidence volume, with documented weights."

**Key insight:** The three strategies produce nearly identical estimated
profit here, because the underlying ROIs are tightly clustered — the
comparison shows that plainly instead of overselling the weighted option.

**Caveat:** "Called an *illustrative* allocation. Not optimal, not
guaranteed."

---

## 9. Data Quality (~45s)

**Show:** Quality overview cards, then the governance flags.

**Say:** "Score 100/100 — no missing values, no duplicates, no funnel
violations. But readiness is READY WITH CAUTION, because real
statistical outliers exist."

**Key insight:** Clean data and cautious readiness aren't the same
judgment.

**Caveat:** "Outliers are reported, never removed. Negative ROI is
flagged INFO — it's a business outcome, not a data defect."

---

## 10. Marketing Analyst Copilot (~75s)

**Show:** Ask *"Which campaign type has the highest average ROI?"*, then
*"Which campaign strategy caused ROI to increase?"*

**Say:** "Rule-based routing over approved analytics — no LLM, no API
key, fully local. Every answer shows evidence basis, source, metrics,
and caveats."

**Key insight:** The second question is **refused**: *"The current
observational data and model do not establish causality."*

**Caveat:** "Refusing is the feature. It can't invent a statistic, and
it won't answer a causal question the data can't support."

---

## 11. Platform Health (~45s)

**Show:** Status cards and the system checks table.

**Say:** "Self-diagnosing: dataset integrity with SHA-256, model
artifacts, all services, templates, routes, navigation, environment, and
the recorded test result — 370 passing."

**Key insight:** Status reads HEALTHY_WITH_WARNINGS, not a green
checkmark, because `SECRET_KEY` is still the development default.

**Caveat:** "It reports a real warning rather than always showing green.
The docs describe this as portfolio-ready, not production-ready."

---

## Closing (~30s)

> "Fifteen build phases, 370 automated tests, 42 API endpoints. The
> throughline is analytical discipline: the platform is designed to be
> harder to misuse than a standard dashboard — evidence types are never
> blended, correlation is never dressed up as causation, and the most
> inconvenient finding, that Acquisition Cost dominates the model, is
> the one displayed most prominently."

## Questions you should expect

| Question | Answer |
|---|---|
| "Is it production ready?" | "Portfolio/demonstration ready. It needs auth, a non-default secret key, and rate limiting first — all documented in SECURITY_NOTES.md." |
| "Why not use an LLM for the Copilot?" | "Determinism. A rule-based router can't hallucinate a statistic, and it makes the behaviour testable." |
| "Why is the model's R² only 0.81?" | "The honest answer is that even 0.81 overstates it — cost alone gets 0.79. That's the finding, and it's on the Model Intelligence page." |
| "Could you improve the forecast?" | "Yes — seasonality modelling. The linear method was chosen for explainability and auditability first." |
