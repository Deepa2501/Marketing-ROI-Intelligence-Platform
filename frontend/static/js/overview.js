/*
 * overview.js — Page 1: Overview / executive dashboard.
 * Pulls from GET /api/summary, GET /api/campaign-types,
 * GET /api/customer-segments. All numbers rendered here come directly
 * from those responses — nothing is hardcoded.
 *
 * IMPORTANT (bugfix): table/card rendering and chart rendering are in
 * SEPARATE try/catch blocks, and each individual chart is wrapped in
 * its own try/catch. A Chart.js failure (e.g. the library not loading)
 * can therefore only blank out that one chart panel — it can never
 * overwrite the campaign-type table or insight cards that already
 * rendered successfully from the same API response.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadKpis();
  loadOverviewData();
});

async function loadKpis() {
  try {
    const data = await apiFetch("/api/summary");
    if (data.status !== "connected") {
      document.querySelectorAll("#kpi-grid .card__value").forEach((el) => (el.textContent = "No data"));
      return;
    }
    const k = data.kpis;
    document.getElementById("kpi-total-campaigns").textContent = formatCompactNumber(k.total_campaigns);
    document.getElementById("kpi-total-revenue").textContent = formatCurrency(k.total_revenue);
    document.getElementById("kpi-avg-roi").textContent = formatROI(k.average_roi);
    document.getElementById("kpi-total-conversions").textContent = formatCompactNumber(k.total_conversions);
    document.getElementById("kpi-avg-cost").textContent = formatCurrency(k.average_acquisition_cost, { compact: false });
    document.getElementById("kpi-avg-engagement").textContent = formatNumber(k.average_engagement_score, 2);
  } catch (err) {
    document.querySelectorAll("#kpi-grid .card__value").forEach((el) => (el.textContent = "Error"));
  }
}

async function loadOverviewData() {
  const tableEl = document.getElementById("type-performance-table");
  const insightsEl = document.getElementById("insight-cards");

  let types, segments;

  // Stage 1: fetch + render the table and insight cards. If this fails,
  // it's a real data problem (API/network) — show a real error.
  try {
    const [typesData, segmentsData] = await Promise.all([
      apiFetch("/api/campaign-types"),
      apiFetch("/api/customer-segments"),
    ]);
    types = typesData.campaign_types || [];
    segments = segmentsData.customer_segments || [];

    if (!types.length) {
      renderEmpty(tableEl, "No campaign type data found.");
      renderEmpty(insightsEl, "No insight data available.");
      return;
    }

    renderTypeTable(tableEl, types);
    renderInsights(insightsEl, types, segments);
  } catch (err) {
    renderError(tableEl, err, loadOverviewData);
    renderError(insightsEl, err, loadOverviewData);
    return;
  }

  // Stage 2: render charts from the SAME data, already fetched above.
  // Any failure here (e.g. the charting library) is isolated to the
  // individual chart panel and never touches the table/cards above.
  renderChartSafely("chart-revenue-by-type", () =>
    new Chart(document.getElementById("chart-revenue-by-type"), {
      type: "bar",
      data: {
        labels: types.map((t) => t.name),
        datasets: [{ label: "Revenue", data: types.map((t) => t.total_revenue), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }],
      },
      options: baseChartOptions((v) => formatCurrency(v)),
    })
  );

  renderChartSafely("chart-roi-by-type", () =>
    new Chart(document.getElementById("chart-roi-by-type"), {
      type: "bar",
      data: {
        labels: types.map((t) => t.name),
        datasets: [{ label: "Average ROI", data: types.map((t) => t.average_roi), backgroundColor: CHART_COLORS.teal, borderRadius: 4 }],
      },
      options: { ...baseChartOptions((v) => formatROI(v)), indexAxis: "y" },
    })
  );

  renderChartSafely("chart-revenue-by-segment", () =>
    new Chart(document.getElementById("chart-revenue-by-segment"), {
      type: "bar",
      data: {
        labels: segments.map((s) => s.name),
        datasets: [{ label: "Revenue", data: segments.map((s) => s.total_revenue), backgroundColor: CHART_COLORS.violet, borderRadius: 4 }],
      },
      options: baseChartOptions((v) => formatCurrency(v)),
    })
  );

  renderChartSafely("chart-roi-by-segment", () =>
    new Chart(document.getElementById("chart-roi-by-segment"), {
      type: "bar",
      data: {
        labels: segments.map((s) => s.name),
        datasets: [{ label: "Average ROI", data: segments.map((s) => s.average_roi), backgroundColor: CHART_COLORS.amber, borderRadius: 4 }],
      },
      options: baseChartOptions((v) => formatROI(v)),
    })
  );
}

/**
 * Runs a chart-creation function; if it throws (e.g. Chart.js isn't
 * available), replaces just that one canvas's wrapper with an inline
 * message instead of letting the error propagate anywhere else.
 */
function renderChartSafely(canvasId, createChartFn) {
  try {
    if (typeof Chart === "undefined") {
      throw new Error("chart_library_unavailable");
    }
    createChartFn();
  } catch (err) {
    const canvas = document.getElementById(canvasId);
    if (canvas && canvas.parentElement) {
      canvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    }
  }
}

function renderTypeTable(el, types) {
  const rows = types
    .map(
      (t) => `
    <tr>
      <td>${t.name}</td>
      <td>${formatCompactNumber(t.campaign_count)}</td>
      <td>${formatCurrency(t.total_revenue)}</td>
      <td>${formatROI(t.average_roi)}</td>
      <td>${formatROI(t.median_roi)}</td>
      <td>${formatCompactNumber(t.total_conversions)}</td>
    </tr>`
    )
    .join("");

  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead>
          <tr><th>Campaign Type</th><th>Campaign Count</th><th>Revenue</th><th>Avg ROI</th><th>Median ROI</th><th>Conversions</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function baseChartOptions(tickFormatter) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: { label: (ctx) => tickFormatter(ctx.parsed.y ?? ctx.parsed.x) },
      },
    },
    scales: {
      x: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text } },
      y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => tickFormatter(v) } },
    },
  };
}

function renderInsights(el, types, segments) {
  const topRoiType = [...types].sort((a, b) => b.average_roi - a.average_roi)[0];
  const topRevenueType = [...types].sort((a, b) => b.total_revenue - a.total_revenue)[0];
  const topRoiSegment = [...segments].sort((a, b) => b.average_roi - a.average_roi)[0];
  const topRevenueSegment = [...segments].sort((a, b) => b.total_revenue - a.total_revenue)[0];

  const cards = [
    { tag: "Highest Average ROI · Campaign Type", value: topRoiType.name, meta: `${formatROI(topRoiType.average_roi)} average ROI across ${formatCompactNumber(topRoiType.campaign_count)} campaigns` },
    { tag: "Highest Revenue · Campaign Type", value: topRevenueType.name, meta: `${formatCurrency(topRevenueType.total_revenue)} total revenue` },
    { tag: "Highest Average ROI · Customer Segment", value: topRoiSegment.name, meta: `${formatROI(topRoiSegment.average_roi)} average ROI across ${formatCompactNumber(topRoiSegment.campaign_count)} campaigns` },
    { tag: "Highest Revenue · Customer Segment", value: topRevenueSegment.name, meta: `${formatCurrency(topRevenueSegment.total_revenue)} total revenue` },
  ];

  el.innerHTML = cards
    .map(
      (c) => `
    <div class="insight-card insight-card--opportunity">
      <div class="insight-card__tag">${c.tag}</div>
      <div class="insight-card__title">${c.value}</div>
      <div class="insight-card__row">${c.meta}</div>
    </div>`
    )
    .join("");
}
