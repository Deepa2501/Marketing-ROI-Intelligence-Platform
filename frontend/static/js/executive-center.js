/*
 * executive-center.js — Phase 9: Executive Decision Center.
 * Single source of truth: GET /api/executive-summary. All numbers,
 * priorities, opportunities, risks, and guardrails rendered here come
 * directly from that response — nothing is computed or invented here.
 *
 * Chart rendering uses the same fault-isolation pattern already fixed
 * in campaign-analytics.js: chart creation is isolated from card/list
 * rendering, and any existing Chart.js instance on a canvas is
 * destroyed before a new one is created, so a chart failure never
 * removes the canvas or breaks the rest of the page layout.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadExecutiveSummary();
});

async function loadExecutiveSummary() {
  const ids = ["health-score-card", "health-kpi-grid", "snapshot-grid", "priorities-list", "opportunity-table", "risk-list", "guardrails-panel"];
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  let data;
  try {
    data = await apiFetch("/api/executive-summary", { useCache: false });
  } catch (err) {
    ids.forEach((id) => renderError(document.getElementById(id), err, loadExecutiveSummary));
    return;
  }

  renderHealthScore(data.portfolio_health);
  renderHealthKpis(data.kpis, data.portfolio_interpretation);
  renderSnapshot(data.snapshot);
  renderPriorities(data.strategic_priorities);
  renderOpportunities(data.opportunities);
  renderRisks(data.risks);
  renderGuardrails(data.decision_guardrails);

  renderCharts(data.charts);
}

function statusClass(status) {
  return { Strong: "status--strong", Stable: "status--stable", Watch: "status--watch", "At Risk": "status--at-risk" }[status] || "status--stable";
}

function renderHealthScore(health) {
  const el = document.getElementById("health-score-card");
  if (!health || health.score === null || health.score === undefined) {
    renderEmpty(el, "Portfolio health score not available.");
    return;
  }
  el.innerHTML = `
    <div class="exec-health-score-card__label">${health.label}</div>
    <div class="exec-health-score-card__value">${health.score}<span> / 100</span></div>
    <div class="exec-health-score-card__status ${statusClass(health.status)}">${health.status}</div>
    <div class="exec-health-score-card__note">${health.note}</div>
  `;
}

function renderHealthKpis(kpis, interpretation) {
  const el = document.getElementById("health-kpi-grid");
  if (!kpis) {
    renderEmpty(el, "KPI data not available.");
    return;
  }
  el.innerHTML = `
    <div class="card"><div class="card__label">Total Revenue</div><div class="card__value">${formatCurrency(kpis.total_revenue)}</div></div>
    <div class="card"><div class="card__label">Average ROI</div><div class="card__value">${formatROI(kpis.average_roi)}</div></div>
    <div class="card"><div class="card__label">Total Conversions</div><div class="card__value">${formatCompactNumber(kpis.total_conversions)}</div></div>
    <div class="card"><div class="card__label">Negative ROI %</div><div class="card__value" style="color: var(--danger);">${interpretation ? interpretation.negative_roi_campaign_percentage : "—"}%</div></div>
  `;
}

function renderSnapshot(snapshot) {
  const el = document.getElementById("snapshot-grid");
  if (!snapshot) {
    renderEmpty(el, "Snapshot data not available.");
    return;
  }
  const cards = [snapshot.strongest_observed_performance, snapshot.biggest_risk, snapshot.key_cost_signal, snapshot.most_important_experiment].filter(Boolean);
  if (!cards.length) {
    renderEmpty(el, "Snapshot data not available.");
    return;
  }
  el.innerHTML = cards
    .map(
      (c) => `
    <div class="card">
      <div class="card__label">${c.title}</div>
      <div class="card__value" style="font-size: 15px;">${c.metric}</div>
      <p class="card__meta">
        <span class="badge badge--evidence" style="margin-right:6px;">${c.evidence_basis}</span>
        ${c.interpretation}
      </p>
    </div>`
    )
    .join("");
}

function importanceBadge(importance) {
  const cls = { HIGH: "exec-importance-badge--high", MEDIUM: "exec-importance-badge--medium", LOW: "exec-importance-badge--low" }[importance] || "exec-importance-badge--low";
  return `<span class="exec-importance-badge ${cls}">${importance}</span>`;
}

function renderPriorities(priorities) {
  const el = document.getElementById("priorities-list");
  if (!priorities || !priorities.length) {
    renderEmpty(el, "No strategic priorities available.");
    return;
  }
  el.innerHTML = priorities
    .map(
      (p) => `
    <div class="priority-card">
      <div class="priority-card__number">${p.priority}</div>
      <div>
        <div class="priority-card__title">${p.title}${importanceBadge(p.importance)}<span style="color: var(--text-faint); font-weight:400; font-size:11px; margin-left:8px;">${p.category}</span></div>
        <div class="priority-card__text">${p.recommendation}</div>
        <div class="priority-card__meta">Evidence: ${p.evidence} · Caution: ${p.caution}</div>
      </div>
    </div>`
    )
    .join("");
}

function renderOpportunities(opportunities) {
  const el = document.getElementById("opportunity-table");
  if (!opportunities || !opportunities.length) {
    renderEmpty(el, "No opportunities available.");
    return;
  }
  const rows = opportunities
    .map(
      (o) => `
    <tr>
      <td>${o.opportunity_name}</td>
      <td>${o.dimension}</td>
      <td>${formatROI(o.observed_average_roi)}</td>
      <td>${o.comparison_to_portfolio_average || "—"}</td>
      <td>${formatCompactNumber(o.campaign_count)}</td>
      <td><span class="badge badge--evidence">${o.evidence_basis}</span></td>
      <td><span class="badge ${o.confidence === "High" ? "badge--confidence-high" : o.confidence === "Medium" ? "badge--confidence-medium" : "badge--confidence-low"}">${o.confidence}</span></td>
    </tr>`
    )
    .join("");
  el.innerHTML = `
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr><th>Opportunity</th><th>Dimension</th><th>Observed ROI</th><th>vs Portfolio Avg</th><th>Campaign Count</th><th>Evidence</th><th>Confidence</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderRisks(risks) {
  const el = document.getElementById("risk-list");
  if (!risks || !risks.length) {
    renderEmpty(el, "No risks flagged.");
    return;
  }
  el.innerHTML = risks
    .map(
      (r) => `
    <div class="insight-card ${r.severity === "High" ? "insight-card--risk" : "insight-card--experiment"}">
      <div class="insight-card__tag">${r.risk_title}</div>
      <div class="badge-row" style="margin: 6px 0;">
        <span class="badge badge--evidence">${r.evidence_basis}</span>
        <span class="badge ${r.severity === "High" ? "badge--risk-high" : r.severity === "Medium" ? "badge--risk-medium" : "badge--risk-low"}">Severity: ${r.severity}</span>
      </div>
      <div class="insight-card__row">${r.interpretation}</div>
      <div class="insight-card__row"><strong>Management action:</strong> ${r.management_action}</div>
    </div>`
    )
    .join("");
}

function renderGuardrails(guardrails) {
  const el = document.getElementById("guardrails-panel");
  if (!guardrails || !guardrails.length) {
    renderEmpty(el, "Guardrails not available.");
    return;
  }
  el.innerHTML = `<ul>${guardrails.map((g) => `<li>${g}</li>`).join("")}</ul>`;
}

/* ============================================================
   CHARTS — isolated, safe rendering
   ============================================================ */

function renderCharts(charts) {
  if (!charts) return;
  renderChartSafely("chart-exec-type-roi", () => {
    const rows = charts.roi_by_campaign_type || [];
    return new Chart(document.getElementById("chart-exec-type-roi"), {
      type: "bar",
      data: { labels: rows.map((r) => r.name), datasets: [{ data: rows.map((r) => r.average_roi), backgroundColor: CHART_COLORS.teal, borderRadius: 4 }] },
      options: baseExecChartOptions((v) => formatROI(v)),
    });
  });

  renderChartSafely("chart-exec-segment-roi", () => {
    const rows = charts.roi_by_customer_segment || [];
    return new Chart(document.getElementById("chart-exec-segment-roi"), {
      type: "bar",
      data: { labels: rows.map((r) => r.name), datasets: [{ data: rows.map((r) => r.average_roi), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }] },
      options: baseExecChartOptions((v) => formatROI(v)),
    });
  });

  renderChartSafely("chart-exec-exposure", () => {
    const exposure = charts.roi_exposure || {};
    const positive = exposure.positive_roi_campaign_percentage ?? 0;
    const negative = exposure.negative_roi_campaign_percentage ?? 0;
    return new Chart(document.getElementById("chart-exec-exposure"), {
      type: "bar",
      data: {
        labels: ["Positive ROI", "Negative ROI"],
        datasets: [{ data: [positive, negative], backgroundColor: [CHART_COLORS.teal, CHART_COLORS.amber], borderRadius: 4 }],
      },
      options: { ...baseExecChartOptions((v) => v + "%"), indexAxis: "y" },
    });
  });
}

function baseExecChartOptions(tickFormatter) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => tickFormatter(ctx.parsed.y ?? ctx.parsed.x) } } },
    scales: {
      x: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text } },
      y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => tickFormatter(v) } },
    },
  };
}

/**
 * Same safe-render pattern established in campaign-analytics.js:
 * destroy any existing chart on this canvas first, and on failure,
 * show an inline message WITHOUT removing the canvas or disturbing
 * the rest of the page.
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
