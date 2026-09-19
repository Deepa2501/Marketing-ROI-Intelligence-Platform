/*
 * forecasting.js — Phase 11: Forecasting & Future Outlook.
 * Single source of truth: GET /api/forecasting. All historical values,
 * forecast values, trend directions, evidence strength, backtest
 * numbers, and outlook signals rendered here come directly from that
 * response — nothing is computed or invented client-side.
 *
 * Chart rendering uses the same fault-isolation pattern already fixed
 * in campaign-analytics.js / executive-center.js / marketing-intelligence.js:
 * card/table rendering happens first and independently, charts render
 * last and in isolation, and any existing Chart.js instance on a
 * canvas is destroyed before a new one is created. A chart failure
 * shows a readable message WITHOUT removing the canvas.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadForecasting();
});

async function loadForecasting() {
  const ids = ["kpi-grid", "trend-summary-table", "backtest-table", "methodology-content", "outlook-signals-grid"];
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  let data;
  try {
    data = await apiFetch("/api/forecasting", { useCache: false });
  } catch (err) {
    ids.forEach((id) => renderError(document.getElementById(id), err, loadForecasting));
    return;
  }

  if (data.status === "insufficient_history") {
    ids.forEach((id) => renderEmpty(document.getElementById(id), data.message || "Insufficient historical data to build a forecast."));
    return;
  }

  renderKpis(data.forecasts);
  renderTrendSummary(data.trend_summary);
  renderBacktest(data.backtest);
  renderMethodology(data.methodology);
  renderOutlookSignals(data.outlook_signals);

  // Charts render last and independently, so a charting failure never
  // affects the tables/cards above.
  renderForecastCharts(data.forecasts);
}

function directionBadgeClass(direction) {
  return { UP: "roi-badge--positive", DOWN: "roi-badge--negative", STABLE: "roi-badge--neutral" }[direction] || "roi-badge--neutral";
}

function evidenceBadgeClass(level) {
  return { HIGH: "badge--confidence-high", MEDIUM: "badge--confidence-medium", LOW: "badge--confidence-low" }[level] || "badge--confidence-low";
}

/* ============================================================
   KPI CARDS
   ============================================================ */

function renderKpis(forecasts) {
  const el = document.getElementById("kpi-grid");
  if (!forecasts || !forecasts.length) {
    renderEmpty(el, "Forecast data not available.");
    return;
  }
  const byMetric = Object.fromEntries(forecasts.map((f) => [f.metric, f]));

  const metricCard = (label, f) => {
    if (!f || f.status !== "ok") {
      return `<div class="card"><div class="card__label">${label}</div><div class="card__value">Insufficient data</div></div>`;
    }
    return `
      <div class="card">
        <div class="card__label">Recent ${label} Trend</div>
        <div class="card__value"><span class="roi-badge ${directionBadgeClass(f.trend_direction)}">${f.trend_direction}</span></div>
        <p class="card__meta">Evidence strength: ${f.evidence_strength}</p>
      </div>`;
  };

  el.innerHTML = `
    ${metricCard("Revenue", byMetric["Revenue"])}
    ${metricCard("ROI", byMetric["ROI"])}
    ${metricCard("Conversions", byMetric["Conversions"])}
    <div class="card">
      <div class="card__label">Forecast Horizon</div>
      <div class="card__value" style="font-size: 18px;">Next 3 Months</div>
      <p class="card__meta">Estimated, directional — not guaranteed</p>
    </div>
  `;
}

/* ============================================================
   TREND SUMMARY
   ============================================================ */

function renderTrendSummary(trendSummary) {
  const el = document.getElementById("trend-summary-table");
  if (!trendSummary || !trendSummary.length) {
    renderEmpty(el, "Trend summary not available.");
    return;
  }
  const rows = trendSummary
    .map(
      (t) => `
    <tr>
      <td>${t.metric}</td>
      <td>${t.direction ? `<span class="roi-badge ${directionBadgeClass(t.direction)}">${t.direction}</span>` : "—"}</td>
      <td><span class="badge ${evidenceBadgeClass(t.evidence_strength)}">${t.evidence_strength}</span></td>
      <td>${t.interpretation}</td>
    </tr>`
    )
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Metric</th><th>Direction</th><th>Evidence Strength</th><th>Interpretation</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   BACKTEST
   ============================================================ */

function renderBacktest(backtest) {
  const el = document.getElementById("backtest-table");
  if (!backtest || !Object.keys(backtest).length) {
    renderEmpty(el, "Backtest not available.");
    return;
  }
  const rows = Object.entries(backtest)
    .map(([metric, bt]) => {
      if (bt.status !== "ok") {
        return `<tr><td>${metric}</td><td colspan="4">${bt.message || "Backtest unavailable."}</td></tr>`;
      }
      return `
      <tr>
        <td>${metric}</td>
        <td>${formatNumber(bt.mae, 4)}</td>
        <td>${formatNumber(bt.rmse, 4)}</td>
        <td>${bt.test_period}</td>
        <td>${bt.interpretation}</td>
      </tr>`;
    })
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Metric</th><th>MAE</th><th>RMSE</th><th>Test Period</th><th>Interpretation</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   METHODOLOGY
   ============================================================ */

function renderMethodology(methodology) {
  const el = document.getElementById("methodology-content");
  if (!methodology) {
    renderEmpty(el, "Methodology not available.");
    return;
  }
  const steps = (methodology.steps || []).map((s, i) => `<li>${i + 1}. ${s}</li>`).join("");
  el.innerHTML = `
    <ul class="can-cannot-list can-cannot-list--can" style="margin-bottom:14px;">${steps}</ul>
    <p class="panel__text" style="margin-bottom:8px;"><strong style="color:var(--text);">Trend classification:</strong> ${methodology.trend_classification || ""}</p>
    <p class="panel__text" style="margin-bottom:8px;"><strong style="color:var(--text);">Evidence strength logic:</strong> ${methodology.evidence_strength_logic || ""}</p>
    <p class="panel__text"><strong style="color:var(--text);">Forecast horizon:</strong> ${methodology.forecast_horizon || ""}</p>
  `;
}

/* ============================================================
   OUTLOOK SIGNALS
   ============================================================ */

function renderOutlookSignals(signals) {
  const el = document.getElementById("outlook-signals-grid");
  if (!signals || !signals.length) {
    renderEmpty(el, "No outlook signals available.");
    return;
  }
  el.innerHTML = signals
    .map(
      (s) => `
    <div class="insight-card ${s.evidence_basis === "PREDICTIVE" ? "insight-card--experiment" : "insight-card--opportunity"}">
      <div class="insight-card__tag">${s.title}</div>
      <div class="badge-row" style="margin: 6px 0;"><span class="badge badge--evidence">${s.evidence_basis}</span></div>
      <div class="insight-card__row">${s.interpretation}</div>
      <div class="insight-card__row"><strong>Caution:</strong> ${s.caution}</div>
    </div>`
    )
    .join("");
}

/* ============================================================
   CHARTS — historical (solid) + forecast (dashed), isolated/safe
   ============================================================ */

function renderForecastCharts(forecasts) {
  const byMetric = Object.fromEntries((forecasts || []).map((f) => [f.metric, f]));
  renderSingleForecastChart("chart-forecast-revenue", byMetric["Revenue"], (v) => formatCurrency(v));
  renderSingleForecastChart("chart-forecast-roi", byMetric["ROI"], (v) => formatROI(v));
  renderSingleForecastChart("chart-forecast-conversions", byMetric["Conversions"], (v) => formatCompactNumber(v));
}

function renderSingleForecastChart(canvasId, forecast, tickFormatter) {
  renderChartSafely(canvasId, () => {
    if (!forecast || forecast.status !== "ok") {
      throw new Error("insufficient_data");
    }

    const historical = forecast.historical_values || [];
    const future = forecast.forecast_values || [];
    const labels = [...historical.map((h) => h.period), ...future.map((f) => f.period)];

    // Historical dataset: real values across the historical range, null afterward.
    const historicalData = [...historical.map((h) => h.value), ...future.map(() => null)];

    // Forecast dataset: null across historical range except the last
    // historical point (so the dashed line visually connects), then
    // the estimated forecast values.
    const forecastData = historical.map((_, i) => (i === historical.length - 1 ? historical[historical.length - 1].value : null));
    future.forEach((f) => forecastData.push(f.estimated_value));

    return new Chart(document.getElementById(canvasId), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Historical",
            data: historicalData,
            borderColor: CHART_COLORS.blue,
            backgroundColor: "transparent",
            tension: 0.25,
            pointRadius: 2,
            spanGaps: false,
          },
          {
            label: "Estimated Forecast",
            data: forecastData,
            borderColor: CHART_COLORS.teal,
            backgroundColor: "transparent",
            borderDash: [6, 4],
            tension: 0.25,
            pointRadius: 3,
            spanGaps: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: CHART_COLORS.text } },
          tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${tickFormatter(ctx.parsed.y)}` } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: CHART_COLORS.text, maxTicksLimit: 10 } },
          y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => tickFormatter(v) } },
        },
      },
    });
  });
}

/**
 * Same safe-render pattern established across the platform: destroy
 * any existing chart on this canvas first; on failure, show an inline
 * message WITHOUT removing the canvas or disturbing the page layout.
 */
function renderChartSafely(canvasId, createChartFn) {
  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");
    const canvas = document.getElementById(canvasId);
    if (!canvas) throw new Error(`canvas_not_found:${canvasId}`);
    const existing = Chart.getChart ? Chart.getChart(canvas) : null;
    if (existing) existing.destroy();
    createChartFn();
  } catch (err) {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
      let sibling = canvas.nextElementSibling;
      if (!sibling || !sibling.classList.contains("state--empty")) {
        const msg = document.createElement("div");
        msg.className = "state state--empty";
        msg.textContent = "Chart could not be rendered.";
        canvas.insertAdjacentElement("afterend", msg);
      }
      canvas.style.display = "none";
    }
  }
}
