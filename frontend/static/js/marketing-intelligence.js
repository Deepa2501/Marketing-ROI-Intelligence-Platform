/*
 * marketing-intelligence.js — Phase 10: Marketing Intelligence Upgrade.
 * Single source of truth: GET /api/marketing-intelligence. All trend
 * points, correlations, funnel numbers, efficiency buckets, and
 * insights rendered here come directly from that response.
 *
 * Chart rendering uses the same fault-isolation pattern already fixed
 * in campaign-analytics.js / executive-center.js: card/table
 * rendering happens first and independently, charts render last and
 * in isolation, and any existing Chart.js instance on a canvas is
 * destroyed before a new one is created.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadMarketingIntelligence();
});

async function loadMarketingIntelligence() {
  const ids = ["driver-type-table", "driver-segment-table", "funnel-summary", "efficiency-highlights", "efficiency-table", "insights-grid"];
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  let data;
  try {
    data = await apiFetch("/api/marketing-intelligence", { useCache: false });
  } catch (err) {
    ids.forEach((id) => renderError(document.getElementById(id), err, loadMarketingIntelligence));
    return;
  }

  renderDrivers(data.drivers);
  renderFunnelSummary(data.funnel);
  renderEfficiency(data.efficiency);
  renderInsights(data.insights);

  // Charts render last, independently, so a charting failure never
  // affects the tables/cards above.
  renderTrendCharts(data.trends);
  renderDriverChart(data.drivers);
  renderFunnelChart(data.funnel);
  renderEfficiencyChart(data.efficiency);
}

/* ============================================================
   PERFORMANCE DRIVERS
   ============================================================ */

function renderDrivers(drivers) {
  document.getElementById("driver-disclaimer").textContent = drivers && drivers.correlation_disclaimer ? drivers.correlation_disclaimer : "";

  const typeEl = document.getElementById("driver-type-table");
  const segmentEl = document.getElementById("driver-segment-table");

  const groups = (drivers && drivers.group_comparisons) || {};
  renderGroupMiniTable(typeEl, groups.campaign_type || []);
  renderGroupMiniTable(segmentEl, groups.customer_segment || []);
}

function renderGroupMiniTable(el, rows) {
  if (!rows.length) {
    renderEmpty(el, "No data available.");
    return;
  }
  const trs = rows.map((r) => `<tr><td>${r.name}</td><td>${formatROI(r.average_roi)}</td><td>${formatCurrency(r.total_revenue)}</td><td>${formatCompactNumber(r.campaign_count)}</td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Group</th><th>Avg ROI</th><th>Revenue</th><th>Count</th></tr></thead><tbody>${trs}</tbody></table></div>`;
}

/* ============================================================
   FUNNEL
   ============================================================ */

function renderFunnelSummary(funnel) {
  const el = document.getElementById("funnel-summary");
  const stages = (funnel && funnel.stages) || [];
  if (!stages.length) {
    renderEmpty(el, "Funnel data not available.");
    return;
  }
  el.innerHTML = stages
    .map(
      (s) => `
    <div class="card">
      <div class="card__label">${s.stage}</div>
      <div class="card__value">${formatCompactNumber(s.total)}</div>
      <p class="card__meta">${s.stage_conversion_rate_pct !== null ? "Stage rate: " + s.stage_conversion_rate_pct + "%" : "Funnel entry point"}${s.drop_off_pct !== null ? " · Drop-off: " + s.drop_off_pct + "%" : ""}</p>
    </div>`
    )
    .join("");
}

/* ============================================================
   EFFICIENCY
   ============================================================ */

function renderEfficiency(efficiency) {
  document.getElementById("efficiency-note").textContent = efficiency && efficiency.note ? efficiency.note : "";

  const highlightsEl = document.getElementById("efficiency-highlights");
  const most = efficiency && efficiency.most_efficient_campaign_type;
  const least = efficiency && efficiency.least_efficient_campaign_type;
  if (most || least) {
    highlightsEl.innerHTML = `
      ${most ? `<div class="highlight-card"><div class="highlight-card__label">Most Efficient Campaign Type</div><div class="highlight-card__value">${most.name} (${formatNumber(most.conversions_per_unit_cost, 3)} conv/unit cost)</div></div>` : ""}
      ${least ? `<div class="highlight-card"><div class="highlight-card__label">Least Efficient Campaign Type</div><div class="highlight-card__value">${least.name} (${formatNumber(least.conversions_per_unit_cost, 3)} conv/unit cost)</div></div>` : ""}
    `;
  }

  const tableEl = document.getElementById("efficiency-table");
  const buckets = (efficiency && efficiency.cost_buckets) || [];
  if (!buckets.length) {
    renderEmpty(tableEl, "Efficiency data not available.");
    return;
  }
  const rows = buckets
    .map(
      (b) => `
    <tr>
      <td>${b.cost_range}</td>
      <td>${formatCompactNumber(b.campaign_count)}</td>
      <td>${formatCurrency(b.average_revenue, { compact: false })}</td>
      <td>${formatROI(b.average_roi)}</td>
      <td>${b.conversions_per_unit_cost !== null ? formatNumber(b.conversions_per_unit_cost, 3) : "—"}</td>
    </tr>`
    )
    .join("");
  tableEl.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Acquisition Cost Range</th><th>Campaigns</th><th>Avg Revenue</th><th>Avg ROI</th><th>Conversions / Unit Cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   INSIGHTS
   ============================================================ */

function renderInsights(insights) {
  const el = document.getElementById("insights-grid");
  if (!insights || !insights.length) {
    renderEmpty(el, "No insights available.");
    return;
  }
  el.innerHTML = insights
    .map(
      (i) => `
    <div class="insight-card insight-card--opportunity">
      <div class="insight-card__tag">${i.question}</div>
      <div class="insight-card__row">${i.finding}</div>
      <div class="insight-card__row"><span class="badge badge--evidence">${i.evidence_basis}</span></div>
    </div>`
    )
    .join("");
}

/* ============================================================
   CHARTS — isolated, safe rendering (destroy-before-create)
   ============================================================ */

function renderTrendCharts(trends) {
  const points = (trends && trends.points) || [];
  const labels = points.map((p) => p.period);

  renderChartSafely("chart-trend-revenue", () =>
    new Chart(document.getElementById("chart-trend-revenue"), {
      type: "line",
      data: { labels, datasets: [{ data: points.map((p) => p.total_revenue), borderColor: CHART_COLORS.blue, backgroundColor: "transparent", tension: 0.3, pointRadius: 2 }] },
      options: trendChartOptions((v) => formatCurrency(v)),
    })
  );
  renderChartSafely("chart-trend-roi", () =>
    new Chart(document.getElementById("chart-trend-roi"), {
      type: "line",
      data: { labels, datasets: [{ data: points.map((p) => p.average_roi), borderColor: CHART_COLORS.teal, backgroundColor: "transparent", tension: 0.3, pointRadius: 2 }] },
      options: trendChartOptions((v) => formatROI(v)),
    })
  );
  renderChartSafely("chart-trend-conversions", () =>
    new Chart(document.getElementById("chart-trend-conversions"), {
      type: "line",
      data: { labels, datasets: [{ data: points.map((p) => p.total_conversions), borderColor: CHART_COLORS.violet, backgroundColor: "transparent", tension: 0.3, pointRadius: 2 }] },
      options: trendChartOptions((v) => formatCompactNumber(v)),
    })
  );
  renderChartSafely("chart-trend-engagement", () =>
    new Chart(document.getElementById("chart-trend-engagement"), {
      type: "line",
      data: { labels, datasets: [{ data: points.map((p) => p.average_engagement_score), borderColor: CHART_COLORS.amber, backgroundColor: "transparent", tension: 0.3, pointRadius: 2 }] },
      options: trendChartOptions((v) => formatNumber(v, 1)),
    })
  );
}

function renderDriverChart(drivers) {
  renderChartSafely("chart-driver-correlations", () => {
    const correlations = (drivers && drivers.roi_correlations) || [];
    const colors = correlations.map((c) => (c.correlation_with_roi >= 0 ? CHART_COLORS.teal : CHART_COLORS.amber));
    return new Chart(document.getElementById("chart-driver-correlations"), {
      type: "bar",
      data: { labels: correlations.map((c) => c.variable), datasets: [{ data: correlations.map((c) => c.correlation_with_roi), backgroundColor: colors, borderRadius: 4 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `r = ${ctx.parsed.x.toFixed(4)}` } } },
        scales: { x: { min: -1, max: 1, grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text } }, y: { grid: { display: false }, ticks: { color: CHART_COLORS.text } } },
      },
    });
  });
}

function renderFunnelChart(funnel) {
  renderChartSafely("chart-funnel", () => {
    const stages = (funnel && funnel.stages) || [];
    return new Chart(document.getElementById("chart-funnel"), {
      type: "bar",
      data: { labels: stages.map((s) => s.stage), datasets: [{ data: stages.map((s) => s.total), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatCompactNumber(ctx.parsed.y) } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => formatCompactNumber(v) } } },
      },
    });
  });
}

function renderEfficiencyChart(efficiency) {
  renderChartSafely("chart-efficiency-buckets", () => {
    const buckets = (efficiency && efficiency.cost_buckets) || [];
    return new Chart(document.getElementById("chart-efficiency-buckets"), {
      type: "bar",
      data: { labels: buckets.map((b) => b.cost_range), datasets: [{ data: buckets.map((b) => b.average_roi), backgroundColor: CHART_COLORS.teal, borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatROI(ctx.parsed.y) } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text, maxRotation: 30, minRotation: 30 } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => v.toFixed(1) + "x" } } },
      },
    });
  });
}

function trendChartOptions(tickFormatter) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => tickFormatter(ctx.parsed.y) } } },
    scales: {
      x: { grid: { display: false }, ticks: { color: CHART_COLORS.text, maxTicksLimit: 8 } },
      y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => tickFormatter(v) } },
    },
  };
}

/**
 * Same safe-render pattern established in campaign-analytics.js /
 * executive-center.js: destroy any existing chart on this canvas
 * first; on failure, show an inline message WITHOUT removing the
 * canvas or disturbing the rest of the page layout.
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
      const msg = document.createElement("div");
      msg.className = "state state--empty";
      msg.textContent = "Chart could not be rendered.";
      canvas.style.display = "none";
      canvas.insertAdjacentElement("afterend", msg);
    }
  }
}
