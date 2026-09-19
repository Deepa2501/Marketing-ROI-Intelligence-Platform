/*
 * budget-optimizer.js — Phase 13: Budget Allocation Optimizer.
 * Single source of truth: GET/POST /api/budget-optimizer. Every
 * allocation percentage, score, risk level, and estimated profit
 * rendered here comes directly from that response — nothing is
 * computed or invented client-side except the budget-sensitivity
 * table, which only rescales the server-returned percentages.
 *
 * Chart rendering follows the platform's established fault-isolation
 * pattern: tables/cards render first and independently, the chart
 * renders last, destroy-before-create, and a chart failure shows a
 * readable message WITHOUT removing the canvas or breaking layout.
 */

let currentData = null;

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  bindControls();
  runOptimization();
});

function bindControls() {
  document.getElementById("optimize-btn").addEventListener("click", runOptimization);
  document.getElementById("strategy-select").addEventListener("change", () => {
    if (currentData) renderForSelectedStrategy(currentData);
  });
}

function readInputs() {
  return {
    dimension: document.getElementById("opt-dimension").value,
    total_budget: Number(document.getElementById("opt-budget").value),
    min_allocation: Number(document.getElementById("opt-min").value),
    max_allocation: Number(document.getElementById("opt-max").value),
    risk_mode: document.getElementById("opt-risk-mode").value,
  };
}

async function runOptimization() {
  const errorEl = document.getElementById("opt-error");
  const btn = document.getElementById("optimize-btn");
  const ids = ["summary-grid", "allocation-table", "comparison-table", "sensitivity-table", "explanations-list"];

  errorEl.hidden = true;
  btn.disabled = true;
  btn.textContent = "Optimizing…";
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  try {
    const data = await apiFetch("/api/budget-optimizer", { method: "POST", body: readInputs(), useCache: false });
    currentData = data;
    renderGuardrails(data.limitations, data.assumptions);
    renderComparison(data.comparison);
    renderForSelectedStrategy(data);
  } catch (err) {
    errorEl.textContent = err.friendlyMessage || "Unable to run the optimization.";
    errorEl.hidden = false;
    ids.forEach((id) => renderEmpty(document.getElementById(id), "Adjust the inputs above and try again."));
  } finally {
    btn.disabled = false;
    btn.textContent = "Optimize Allocation";
  }
}

function renderForSelectedStrategy(data) {
  const key = document.getElementById("strategy-select").value;
  const strategy = data.strategies[key];
  if (!strategy) return;

  renderSummary(data, strategy);
  renderAllocationTable(data, strategy);
  renderSensitivity(data, strategy);
  renderExplanations(data.explanations, strategy);

  document.getElementById("chart-subtitle").textContent = `Allocation percentage for: ${strategy.strategy}.`;
  renderAllocationChart(strategy);
}

/* ============================================================
   SUMMARY
   ============================================================ */

function riskBadgeClassFor(level) {
  return { LOW: "badge--confidence-high", MEDIUM: "badge--confidence-medium", HIGH: "badge--risk-high" }[level] || "badge--confidence-low";
}

function renderSummary(data, strategy) {
  const el = document.getElementById("summary-grid");
  const allocations = strategy.allocations || [];
  const top = allocations.reduce((best, a) => (!best || a.allocation_percentage > best.allocation_percentage ? a : best), null);
  const estProfit = allocations.reduce((sum, a) => sum + (a.illustrative_estimated_profit || 0), 0);

  el.innerHTML = `
    <div class="card"><div class="card__label">Total Budget</div><div class="card__value">${formatCurrency(data.total_budget)}</div></div>
    <div class="card"><div class="card__label">Number of Groups</div><div class="card__value">${data.constraints.group_count}</div></div>
    <div class="card"><div class="card__label">Selected Strategy</div><div class="card__value" style="font-size:14px;">${strategy.strategy}</div></div>
    <div class="card"><div class="card__label">Highest Allocation</div><div class="card__value" style="font-size:14px;">${top ? top.group : "—"}</div><p class="card__meta">${top ? top.allocation_percentage + "%" : ""}</p></div>
    <div class="card"><div class="card__label">Illustrative Estimated Profit</div><div class="card__value">${formatCurrency(estProfit)}</div><p class="card__meta">Historical-performance-based estimate</p></div>
  `;
}

/* ============================================================
   ALLOCATION TABLE
   ============================================================ */

function renderAllocationTable(data, strategy) {
  const el = document.getElementById("allocation-table");
  const allocations = strategy.allocations || [];
  if (!allocations.length) {
    renderEmpty(el, "No allocation available.");
    return;
  }

  const scoreByGroup = Object.fromEntries((data.groups || []).map((g) => [g.group, g]));

  const rows = [...allocations]
    .sort((a, b) => b.allocation_percentage - a.allocation_percentage)
    .map((a) => {
      const g = scoreByGroup[a.group] || {};
      return `
      <tr>
        <td>${a.group}</td>
        <td>${formatROI(a.average_roi)}</td>
        <td>${a.allocation_score}</td>
        <td><span class="badge ${riskBadgeClassFor(a.risk_level)}">${a.risk_level}</span></td>
        <td>${a.allocation_percentage}%</td>
        <td>${formatCurrency(a.allocated_budget, { compact: false })}</td>
        <td><span class="badge badge--evidence">${a.evidence_basis}</span></td>
      </tr>`;
    })
    .join("");

  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Group</th><th>Historical Avg ROI</th><th>Allocation Score</th><th>Risk</th><th>Allocation %</th><th>Allocated Budget</th><th>Evidence</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   COMPARISON
   ============================================================ */

function renderComparison(comparison) {
  const el = document.getElementById("comparison-table");
  document.getElementById("comparison-note").textContent = (comparison && comparison.note) || "";

  const keys = ["equal", "performance", "risk_adjusted"];
  const rows = keys
    .filter((k) => comparison && comparison[k])
    .map((k) => {
      const c = comparison[k];
      return `
      <tr>
        <td>${c.strategy}</td>
        <td>${formatCurrency(c.illustrative_estimated_profit)}</td>
        <td>${formatCurrency(c.illustrative_estimated_return)}</td>
        <td>${c.allocation_concentration}</td>
        <td>${c.risk_profile}</td>
      </tr>`;
    })
    .join("");

  if (!rows) {
    renderEmpty(el, "No comparison available.");
    return;
  }
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Strategy</th><th>Illustrative Estimated Profit</th><th>Illustrative Estimated Return</th><th>Concentration</th><th>Risk Profile</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   BUDGET SENSITIVITY
   ============================================================ */

function renderSensitivity(data, strategy) {
  const el = document.getElementById("sensitivity-table");
  const allocations = strategy.allocations || [];
  if (!allocations.length) {
    renderEmpty(el, "No sensitivity data available.");
    return;
  }

  const base = data.total_budget;
  const multipliers = [0.5, 0.75, 1, 1.5, 2];

  const rows = multipliers
    .map((m) => {
      const budget = base * m;
      // Percentages are held constant; only the budget is rescaled.
      const profit = allocations.reduce((sum, a) => sum + (budget * a.allocation_percentage / 100) * (a.average_roi || 0), 0);
      const top = allocations.reduce((best, a) => (!best || a.allocation_percentage > best.allocation_percentage ? a : best), null);
      const topAmount = top ? budget * top.allocation_percentage / 100 : 0;
      return `
      <tr${m === 1 ? ' style="background: var(--surface-hover);"' : ""}>
        <td>${formatCurrency(budget)}${m === 1 ? " (current)" : ""}</td>
        <td>${top ? top.group + ": " + formatCurrency(topAmount, { compact: false }) : "—"}</td>
        <td>${formatCurrency(profit)}</td>
      </tr>`;
    })
    .join("");

  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Total Budget</th><th>Largest Allocated Amount</th><th>Illustrative Estimated Profit</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="panel__text" style="margin-top:12px;">Illustrative estimate assuming the selected historical ROI relationship remains approximately representative. Changing budget does not guarantee proportional future returns.</p>`;
}

/* ============================================================
   EXPLANATIONS
   ============================================================ */

function renderExplanations(explanations, strategy) {
  const el = document.getElementById("explanations-list");
  if (!explanations || !explanations.length) {
    renderEmpty(el, "No explanations available.");
    return;
  }

  // Explanations are generated server-side against the risk-adjusted
  // strategy; note that clearly when another strategy is selected.
  const isRiskAdjusted = strategy.strategy === "Risk-Adjusted Allocation";
  const note = isRiskAdjusted
    ? ""
    : `<p class="panel__text" style="margin-bottom:14px;">The reasoning below reflects the Risk-Adjusted Allocation scoring. The currently selected strategy is <strong style="color:var(--text);">${strategy.strategy}</strong>.</p>`;

  el.innerHTML =
    note +
    explanations
      .map(
        (e, i) => `
    <div class="rec-card" style="margin-bottom:10px;">
      <div class="rec-card__title">${e.group} — ${e.allocation_percentage}%</div>
      <div class="rec-card__text">${e.reason}</div>
      <button type="button" class="rec-why-toggle" id="why-toggle-${i}">Show evidence +</button>
      <div class="rec-why-detail" hidden>
        <div class="rec-why-detail__row"><strong>Historical ROI evidence</strong><span>${e.historical_roi_evidence}</span></div>
        <div class="rec-why-detail__row"><strong>Consistency</strong><span>${e.consistency}</span></div>
        <div class="rec-why-detail__row"><strong>Cost efficiency</strong><span>${e.cost_efficiency}</span></div>
        <div class="rec-why-detail__row"><strong>Campaign volume</strong><span>${e.campaign_volume}</span></div>
        <div class="rec-why-detail__row"><strong>Risk adjustment</strong><span>${e.risk_adjustment}</span></div>
        <div class="rec-why-detail__row"><strong>Evidence strength</strong><span>${e.evidence_strength}</span></div>
        <div class="rec-why-detail__row"><strong>Caution</strong><span>${e.caution}</span></div>
      </div>
    </div>`
      )
      .join("");

  el.querySelectorAll(".rec-why-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const detail = btn.nextElementSibling;
      const isOpen = !detail.hidden;
      detail.hidden = isOpen;
      btn.textContent = isOpen ? "Show evidence +" : "Hide evidence −";
    });
  });
}

/* ============================================================
   GUARDRAILS
   ============================================================ */

function renderGuardrails(limitations, assumptions) {
  const el = document.getElementById("guardrails-list");
  const items = [...(limitations || []), ...(assumptions || [])];
  el.innerHTML = items.map((l) => `<li>${l}</li>`).join("");
}

/* ============================================================
   CHART — isolated, safe rendering
   ============================================================ */

function renderAllocationChart(strategy) {
  renderChartSafely("chart-allocation", () => {
    const allocations = [...(strategy.allocations || [])].sort((a, b) => b.allocation_percentage - a.allocation_percentage);
    const colors = allocations.map((a) => ({ LOW: CHART_COLORS.teal, MEDIUM: CHART_COLORS.blue, HIGH: CHART_COLORS.amber }[a.risk_level] || CHART_COLORS.blue));

    return new Chart(document.getElementById("chart-allocation"), {
      type: "bar",
      data: {
        labels: allocations.map((a) => a.group),
        datasets: [{ data: allocations.map((a) => a.allocation_percentage), backgroundColor: colors, borderRadius: 4 }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x}% (${allocations[ctx.dataIndex].risk_level} risk)` } },
        },
        scales: {
          x: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => v + "%" } },
          y: { grid: { display: false }, ticks: { color: CHART_COLORS.text } },
        },
      },
    });
  });
}

function renderChartSafely(canvasId, createChartFn) {
  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");
    const canvas = document.getElementById(canvasId);
    if (!canvas) throw new Error(`canvas_not_found:${canvasId}`);
    const existing = Chart.getChart ? Chart.getChart(canvas) : null;
    if (existing) existing.destroy();
    canvas.style.display = "";
    const stale = canvas.nextElementSibling;
    if (stale && stale.classList.contains("state--empty")) stale.remove();
    createChartFn();
  } catch (err) {
    const canvas = document.getElementById(canvasId);
    if (canvas) {
      const sibling = canvas.nextElementSibling;
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
