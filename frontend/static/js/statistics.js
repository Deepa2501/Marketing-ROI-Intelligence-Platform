/*
 * statistics.js — Page 3: Statistical Intelligence.
 * Single source of truth: GET /api/statistics.
 *
 * IMPORTANT (bugfix): the correlation CHART is rendered in its own
 * try/catch, separate from the significance/distribution/outlier
 * TABLES. Previously a single try block covered both, so if the chart
 * failed (e.g. Chart.js not loaded) the catch handler overwrote the
 * already-successfully-fetched table sections with a generic error —
 * even though /api/statistics itself had returned valid data.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadStatistics();
});

async function loadStatistics() {
  const sigEl = document.getElementById("significance-table");
  const distEl = document.getElementById("distribution-cards");
  const outlierEl = document.getElementById("outlier-table");

  let data;
  try {
    data = await apiFetch("/api/statistics");
  } catch (err) {
    renderError(sigEl, err, loadStatistics);
    renderError(distEl, err, loadStatistics);
    renderError(outlierEl, err, loadStatistics);
    return;
  }

  // Tables render independently of the chart below.
  renderSignificanceTable(sigEl, data.roi_correlations || []);
  renderDistributionCards(distEl, data.distribution || []);
  renderOutlierTable(outlierEl, data.outliers || []);

  // Chart rendering is isolated: if it fails, only the chart panel
  // shows a fallback message — the tables above are unaffected.
  renderChartSafely(data.roi_correlations || []);
}

function renderChartSafely(correlations) {
  const canvas = document.getElementById("chart-correlations");
  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");
    if (!correlations.length) {
      canvas.parentElement.innerHTML = '<div class="state state--empty">No correlation data available.</div>';
      return;
    }

    const labels = correlations.map((c) => c.variable);
    const values = correlations.map((c) => c.correlation_with_roi);
    const colors = correlations.map((c) => (c.correlation_with_roi >= 0 ? CHART_COLORS.teal : CHART_COLORS.amber));

    new Chart(canvas, {
      type: "bar",
      data: { labels, datasets: [{ label: "Correlation with ROI", data: values, backgroundColor: colors, borderRadius: 4 }] },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `r = ${ctx.parsed.x.toFixed(4)}` } },
        },
        scales: {
          x: { min: -1, max: 1, grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text } },
          y: { grid: { display: false }, ticks: { color: CHART_COLORS.text } },
        },
      },
    });
  } catch (err) {
    if (canvas && canvas.parentElement) {
      canvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    }
  }
}

function renderSignificanceTable(el, correlations) {
  if (!correlations.length) {
    renderEmpty(el, "No statistical data available.");
    return;
  }
  const rows = correlations
    .map(
      (c) => `
    <tr>
      <td>${c.variable}</td>
      <td>${formatNumber(c.correlation_with_roi, 4)}</td>
      <td>${c.p_value < 0.0001 ? "&lt; 0.0001" : formatNumber(c.p_value, 6)}</td>
      <td><span class="sig-badge ${c.significant_at_0_05 ? "sig-badge--yes" : "sig-badge--no"}">${c.significant_at_0_05 ? "Significant" : "Not significant"}</span></td>
    </tr>`
    )
    .join("");

  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Variable</th><th>Correlation</th><th>P-value</th><th>Significant at 0.05</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderDistributionCards(el, distribution) {
  if (!distribution.length) {
    renderEmpty(el, "No distribution data available.");
    return;
  }
  el.innerHTML = distribution
    .map(
      (d) => `
    <div class="card">
      <div class="card__label">${d.variable}</div>
      <div class="card__value" style="font-size: 16px;">Skew: ${formatNumber(d.skewness, 3)}</div>
      <p class="card__meta">
        Mean ${formatNumber(d.mean, 2)} · Median ${formatNumber(d.median, 2)} · Std Dev ${formatNumber(d.std_dev, 2)}
      </p>
    </div>`
    )
    .join("");
}

function renderOutlierTable(el, outliers) {
  if (!outliers.length) {
    renderEmpty(el, "No outlier data available.");
    return;
  }
  const rows = outliers
    .map(
      (o) => `
    <tr>
      <td>${o.variable}</td>
      <td>${formatCompactNumber(o.outlier_count)}</td>
      <td>${formatNumber(o.outlier_percentage, 2)}%</td>
      <td>${formatNumber(o.lower_bound, 2)}</td>
      <td>${formatNumber(o.upper_bound, 2)}</td>
    </tr>`
    )
    .join("");

  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Variable</th><th>Outlier Count</th><th>Outlier %</th><th>Lower Bound</th><th>Upper Bound</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}
