# Screenshots

Screenshots are **captured manually** — none are generated, mocked, or
committed as placeholders. This directory is intentionally empty until
you capture them.

## How to capture

1. Start the application:
   ```bash
   python run.py
   ```
2. Open `http://127.0.0.1:5000` in a maximized browser window
   (**1920x1080 recommended**; 1440px width minimum for the wider tables).
3. Let each page finish loading — wait for charts to render and for
   loading states to clear before capturing.
4. Save into this directory using the exact filenames below.

## Recommended shot list

| Filename | Page | What it should show |
|---|---|---|
| `01-overview.png` | `/` | KPI cards plus the four performance charts |
| `02-campaign-analytics.png` | `/campaign-analytics` | Filter panel with an active filter, updated KPIs, and the campaign table |
| `03-statistical-intelligence.png` | `/statistics` | Correlation chart and significance table |
| `04-roi-prediction.png` | `/roi-prediction` | A completed prediction with the gauge and prediction-context panel |
| `05-model-intelligence.png` | `/model-intelligence` | Model metrics, comparison cards, and Acquisition Cost dominance section |
| `06-recommendations.png` | `/recommendations` | Recommendation cards with evidence and confidence badges |
| `07-forecasting.png` | `/forecasting` | A historical + forecast chart showing the dashed forecast segment |
| `08-budget-optimizer.png` | `/budget-optimizer` | Allocation table plus the allocation-by-group chart |
| `09-data-quality.png` | `/data-quality` | Quality overview cards and the completeness table |
| `10-copilot.png` | `/copilot` | A conversation with at least one answered question showing evidence/source badges |
| `11-platform-health.png` | `/platform-health` | Status cards and the system checks table |

## Optional additions

| Filename | Page | Notes |
|---|---|---|
| `12-executive-center.png` | `/executive-center` | Portfolio health score and strategic priorities |
| `13-marketing-intelligence.png` | `/marketing-intelligence` | Trend charts and funnel stages |
| `14-scenario-simulator.png` | `/scenario-simulator` | Three configured scenarios compared |
| `15-ab-testing.png` | `/ab-testing` | Experiment result banner and test statistics |

## Tips

- For the Copilot shot, ask a question with rich supporting metrics —
  *"Which campaign type has the highest average ROI?"* works well.
- For Campaign Analytics, apply a filter first so the screenshot
  demonstrates that KPIs update dynamically.
- For Platform Health, note that a `WARN` on `SECRET_KEY` is expected on
  a fresh checkout — it demonstrates that the health check reports real
  findings rather than always showing green.
