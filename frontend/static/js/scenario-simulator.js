/*
 * scenario-simulator.js — Page 8 (Phase 5): Scenario Simulator.
 *
 * Reuses the same categorical option lists as roi-prediction.js
 * (fetched from /api/campaign-types, /api/customer-segments, and a
 * sample of /api/campaigns — never hardcoded). All predictions come
 * from POST /api/scenario/compare and POST /api/scenario/sensitivity,
 * which in turn reuse the existing cached model — this file never
 * fabricates a number.
 *
 * Chart rendering is isolated from result-card/table rendering
 * throughout (same fault-isolation pattern used to fix the Phase 4
 * bugs), so a charting failure can never blank out working results.
 */

let scenarioOptions = { campaignTypes: [], audiences: [], channels: [], languages: [], segments: [] };
let scenarios = [];
let scenarioCounter = 0;

document.addEventListener("DOMContentLoaded", async () => {
  applyChartDefaults();
  loadModelTransparency();
  await loadScenarioOptions();
  resetScenarios();
  bindControls();
});

async function loadModelTransparency() {
  const el = document.getElementById("model-transparency-card");
  try {
    const data = await apiFetch("/api/model-info");
    const m = data.metrics || {};
    el.innerHTML = `
      <div class="card"><div class="card__label">Model</div><div class="card__value" style="font-size:15px;">${data.model_name || "—"}</div></div>
      <div class="card"><div class="card__label">Prediction Type</div><div class="card__value" style="font-size:15px;">Early-stage decision support</div></div>
      <div class="card"><div class="card__label">R²</div><div class="card__value" style="font-size:15px;">${formatPercent(m.r2)}</div></div>
      <div class="card"><div class="card__label">MAE</div><div class="card__value" style="font-size:15px;">${formatNumber(m.mae, 4)}</div></div>
    `;
  } catch (err) {
    renderError(el, err, loadModelTransparency);
  }
}

async function loadScenarioOptions() {
  try {
    const [types, segments, sample] = await Promise.all([
      apiFetch("/api/campaign-types"),
      apiFetch("/api/customer-segments"),
      apiFetch("/api/campaigns?page=1&page_size=500"),
    ]);
    scenarioOptions.campaignTypes = types.campaign_types.map((t) => t.name);
    scenarioOptions.segments = segments.customer_segments.map((s) => s.name);
    scenarioOptions.audiences = [...new Set((sample.results || []).map((r) => r.Target_Audience).filter(Boolean))].sort();
    scenarioOptions.languages = [...new Set((sample.results || []).map((r) => r.Language).filter(Boolean))].sort();
    scenarioOptions.channels = [...new Set((sample.results || []).map((r) => r.Channel_Used).filter(Boolean))].sort();
  } catch (err) {
    // Cards will still render; selects will just be empty if this fails.
  }
}

function newScenario(index) {
  scenarioCounter += 1;
  return {
    id: scenarioCounter,
    name: `Scenario ${String.fromCharCode(65 + index)}`,
    campaign_type: scenarioOptions.campaignTypes[index % Math.max(scenarioOptions.campaignTypes.length, 1)] || "",
    target_audience: scenarioOptions.audiences[0] || "",
    duration: 20,
    channel: scenarioOptions.channels[0] || "",
    language: scenarioOptions.languages[0] || "",
    customer_segment: scenarioOptions.segments[index % Math.max(scenarioOptions.segments.length, 1)] || "",
    acquisition_cost: 500 + index * 250,
  };
}

function resetScenarios() {
  scenarios = [0, 1, 2].map((i) => newScenario(i));
  renderScenarioCards();
  document.getElementById("comparison-section").hidden = true;
  document.getElementById("sensitivity-content").innerHTML = "";
}

function bindControls() {
  document.getElementById("add-scenario-btn").addEventListener("click", () => {
    if (scenarios.length >= 8) return;
    scenarios.push(newScenario(scenarios.length));
    renderScenarioCards();
  });

  document.getElementById("reset-scenarios-btn").addEventListener("click", resetScenarios);

  document.getElementById("compare-btn").addEventListener("click", runComparison);
  document.getElementById("run-sensitivity-btn").addEventListener("click", runSensitivity);
}

function selectOptions(values, selected) {
  return values.map((v) => `<option value="${v}" ${v === selected ? "selected" : ""}>${v}</option>`).join("");
}

function renderScenarioCards() {
  const el = document.getElementById("scenario-cards");
  el.innerHTML = scenarios
    .map(
      (s) => `
    <div class="scenario-card" data-id="${s.id}">
      <div class="scenario-card__header">
        <input type="text" class="scenario-card__name-input" value="${s.name}" data-field="name" />
        <button type="button" class="scenario-card__remove-btn" data-remove="${s.id}" ${scenarios.length <= 1 ? "disabled" : ""} title="Remove scenario">&times;</button>
      </div>
      <div class="field">
        <label>Campaign Type</label>
        <select data-field="campaign_type">${selectOptions(scenarioOptions.campaignTypes, s.campaign_type)}</select>
      </div>
      <div class="field">
        <label>Target Audience</label>
        <select data-field="target_audience">${selectOptions(scenarioOptions.audiences, s.target_audience)}</select>
      </div>
      <div class="field">
        <label>Duration (days)</label>
        <input type="number" min="1" max="365" data-field="duration" value="${s.duration}" />
      </div>
      <div class="field">
        <label>Channel</label>
        <select data-field="channel">${selectOptions(scenarioOptions.channels, s.channel)}</select>
      </div>
      <div class="field">
        <label>Language</label>
        <select data-field="language">${selectOptions(scenarioOptions.languages, s.language)}</select>
      </div>
      <div class="field">
        <label>Customer Segment</label>
        <select data-field="customer_segment">${selectOptions(scenarioOptions.segments, s.customer_segment)}</select>
      </div>
      <div class="field">
        <label>Acquisition Cost</label>
        <input type="number" min="0" step="0.01" data-field="acquisition_cost" value="${s.acquisition_cost}" />
      </div>
    </div>
  `
    )
    .join("");

  el.querySelectorAll(".scenario-card").forEach((card) => {
    const id = Number(card.getAttribute("data-id"));
    card.querySelectorAll("[data-field]").forEach((input) => {
      input.addEventListener("change", () => updateScenarioField(id, input));
      input.addEventListener("input", () => updateScenarioField(id, input));
    });
  });

  el.querySelectorAll("[data-remove]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.getAttribute("data-remove"));
      scenarios = scenarios.filter((s) => s.id !== id);
      renderScenarioCards();
    });
  });

  updateSensitivityDropdown();
}

function updateScenarioField(id, input) {
  const scenario = scenarios.find((s) => s.id === id);
  if (!scenario) return;
  const field = input.getAttribute("data-field");
  const value = field === "duration" || field === "acquisition_cost" ? Number(input.value) : input.value;
  scenario[field] = value;
  if (field === "name") updateSensitivityDropdown();
}

function updateSensitivityDropdown() {
  const select = document.getElementById("sensitivity-base-scenario");
  const current = select.value;
  select.innerHTML = scenarios.map((s) => `<option value="${s.id}">${s.name}</option>`).join("");
  if (scenarios.some((s) => String(s.id) === current)) select.value = current;
}

/* ============================================================
   COMPARE SCENARIOS
   ============================================================ */

async function runComparison() {
  const section = document.getElementById("comparison-section");
  const resultsEl = document.getElementById("comparison-results");
  const recEl = document.getElementById("recommended-scenario");
  const btn = document.getElementById("compare-btn");

  section.hidden = false;
  renderLoading(resultsEl, "Running scenario analysis…");
  recEl.innerHTML = "";
  btn.disabled = true;
  btn.textContent = "Running…";

  let data;
  try {
    data = await apiFetch("/api/scenario/compare", {
      method: "POST",
      useCache: false,
      body: { scenarios: scenarios.map((s) => ({ ...s })) },
    });
  } catch (err) {
    resultsEl.innerHTML = `
      <div class="state state--error">
        <div class="state__message">Unable to run scenario analysis. ${err.friendlyMessage || ""}</div>
        <button class="state__retry-btn" type="button" id="comparison-retry-btn">Retry</button>
      </div>
    `;
    document.getElementById("comparison-retry-btn").addEventListener("click", runComparison);
    btn.disabled = false;
    btn.textContent = "Compare Scenarios";
    return;
  } finally {
    btn.disabled = false;
    btn.textContent = "Compare Scenarios";
  }

  renderComparisonResults(resultsEl, data);
  renderRecommendation(recEl, data);
  renderComparisonChartSafely(data.scenarios || []);
}

function renderComparisonResults(el, data) {
  const results = data.scenarios || [];
  if (!results.length) {
    renderEmpty(el, "No scenario results returned.");
    return;
  }

  el.innerHTML = `
    <div class="scenario-results-grid">
      ${results
        .map(
          (r) => `
        <div class="scenario-result-card ${r.name === data.best_scenario ? "scenario-result-card--best" : ""}">
          ${r.name === data.best_scenario ? '<div class="scenario-result-card__best-tag">Highest ROI</div>' : ""}
          <div class="scenario-result-card__name">${r.name}</div>
          <div class="scenario-result-card__row"><span>Predicted ROI</span><strong>${formatROI(r.predicted_roi)}</strong></div>
          <div class="scenario-result-card__row"><span>Acquisition Cost</span><strong>${formatCurrency(r.acquisition_cost, { compact: false })}</strong></div>
          <div class="scenario-result-card__row"><span>Illustrative Est. Profit</span><strong>${formatCurrency(r.illustrative_estimated_profit, { compact: false })}</strong></div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

function renderRecommendation(el, data) {
  const best = (data.scenarios || []).find((r) => r.name === data.best_scenario);
  if (!best) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = `
    <div class="recommendation-banner">
      <div class="recommendation-banner__title">Recommended Scenario</div>
      <div class="recommendation-banner__body">
        <strong>${best.name}</strong> currently has the highest predicted ROI (${formatROI(best.predicted_roi)}) among the
        tested planning scenarios, with an illustrative estimated profit of ${formatCurrency(best.illustrative_estimated_profit, { compact: false })}
        on an acquisition cost of ${formatCurrency(best.acquisition_cost, { compact: false })}.
      </div>
    </div>
  `;
}

function renderComparisonChartSafely(results) {
  const canvas = document.getElementById("chart-scenario-roi");
  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");
    if (canvas._chartInstance) canvas._chartInstance.destroy();

    canvas._chartInstance = new Chart(canvas, {
      type: "bar",
      data: {
        labels: results.map((r) => r.name),
        datasets: [{ label: "Predicted ROI", data: results.map((r) => r.predicted_roi), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatROI(ctx.parsed.y) } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } },
          y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => v.toFixed(1) + "x" } },
        },
      },
    });
  } catch (err) {
    if (canvas && canvas.parentElement) {
      canvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    }
  }
}

/* ============================================================
   BUDGET SENSITIVITY
   ============================================================ */

async function runSensitivity() {
  const el = document.getElementById("sensitivity-content");
  const btn = document.getElementById("run-sensitivity-btn");
  const baseId = Number(document.getElementById("sensitivity-base-scenario").value);
  const base = scenarios.find((s) => s.id === baseId) || scenarios[0];

  if (!base) return;

  renderLoading(el, "Running scenario analysis…");
  btn.disabled = true;
  btn.textContent = "Running…";

  let data;
  try {
    data = await apiFetch("/api/scenario/sensitivity", {
      method: "POST",
      useCache: false,
      body: { scenario: { ...base } },
    });
  } catch (err) {
    el.innerHTML = `
      <div class="state state--error">
        <div class="state__message">Unable to run scenario analysis. ${err.friendlyMessage || ""}</div>
        <button class="state__retry-btn" type="button" id="sensitivity-retry-btn">Retry</button>
      </div>
    `;
    document.getElementById("sensitivity-retry-btn").addEventListener("click", runSensitivity);
    return;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Sensitivity Analysis";
  }

  renderSensitivityTable(el, data.results || [], base.name);
  renderSensitivityChartsSafely(data.results || []);
}

function renderSensitivityTable(el, results, baseName) {
  if (!results.length) {
    renderEmpty(el, "No sensitivity results returned.");
    return;
  }

  const rows = results
    .map(
      (r) => `
    <tr>
      <td>${formatCurrency(r.acquisition_cost, { compact: false })}</td>
      <td>${formatROI(r.predicted_roi)}</td>
      <td>${formatCurrency(r.illustrative_estimated_profit, { compact: false })}</td>
    </tr>`
    )
    .join("");

  el.innerHTML = `
    <p class="panel__text" style="margin: 14px 0;">Base scenario: <strong style="color: var(--text);">${baseName}</strong> (all fields held constant except Acquisition Cost)</p>
    <div class="table-wrap" style="margin-bottom:16px;">
      <table class="data-table">
        <thead><tr><th>Budget</th><th>Predicted ROI</th><th>Illustrative Estimated Profit</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="grid grid--2">
      <div class="chart-panel" style="margin-bottom:0;">
        <div class="chart-panel__title">Predicted ROI vs Acquisition Cost</div>
        <div class="chart-canvas-wrap"><canvas id="chart-sensitivity-roi"></canvas></div>
      </div>
      <div class="chart-panel" style="margin-bottom:0;">
        <div class="chart-panel__title">Illustrative Estimated Profit vs Acquisition Cost</div>
        <div class="chart-canvas-wrap"><canvas id="chart-sensitivity-return"></canvas></div>
      </div>
    </div>
  `;
}

function renderSensitivityChartsSafely(results) {
  const roiCanvas = document.getElementById("chart-sensitivity-roi");
  const returnCanvas = document.getElementById("chart-sensitivity-return");

  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");

    const labels = results.map((r) => formatCurrency(r.acquisition_cost, { compact: false }));

    new Chart(roiCanvas, {
      type: "line",
      data: {
        labels,
        datasets: [{ label: "Predicted ROI", data: results.map((r) => r.predicted_roi), borderColor: CHART_COLORS.teal, backgroundColor: "transparent", tension: 0.3, pointRadius: 3 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatROI(ctx.parsed.y) } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => v.toFixed(1) + "x" } } },
      },
    });

    new Chart(returnCanvas, {
      type: "line",
      data: {
        labels,
        datasets: [{ label: "Illustrative Estimated Profit", data: results.map((r) => r.illustrative_estimated_profit), borderColor: CHART_COLORS.violet, backgroundColor: "transparent", tension: 0.3, pointRadius: 3 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatCurrency(ctx.parsed.y, { compact: false }) } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => formatCurrency(v) } } },
      },
    });
  } catch (err) {
    if (roiCanvas && roiCanvas.parentElement) roiCanvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    if (returnCanvas && returnCanvas.parentElement) returnCanvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
  }
}
