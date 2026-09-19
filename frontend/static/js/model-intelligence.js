/*
 * model-intelligence.js — Page 6: Model Intelligence.
 * Pulls GET /api/model-info, GET /api/model-comparison,
 * GET /api/model-feature-importance. All metrics/importances shown
 * are exactly what those endpoints return.
 *
 * IMPORTANT (bugfix): loadComparison() now renders the comparison
 * CARDS and the two comparison CHARTS in separate try/catch blocks.
 * Previously a chart failure (e.g. Chart.js not loaded) would throw
 * after the cards had already rendered successfully, and the shared
 * catch handler then overwrote those working cards with a generic
 * error — even though /api/model-comparison had returned valid data.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadModelInfo();
  loadComparison();
  loadFeatureImportance();
  loadModelIntelligenceExtras(); // Phase 6: dominance, can/cannot, limitations
});

async function loadModelInfo() {
  const el = document.getElementById("model-info-grid");
  try {
    const data = await apiFetch("/api/model-info");
    const m = data.metrics || {};
    el.innerHTML = `
      <div class="card"><div class="card__label">Model</div><div class="card__value" style="font-size:16px;">${data.model_name || "—"}</div></div>
      <div class="card"><div class="card__label">Status</div><div class="card__value card__value--good" style="font-size:16px;">${data.model_status || "—"}</div></div>
      <div class="card"><div class="card__label">Train / Test Samples</div><div class="card__value" style="font-size:16px;">${formatCompactNumber(data.train_sample_count)} / ${formatCompactNumber(data.test_sample_count)}</div></div>
      <div class="card"><div class="card__label">R²</div><div class="card__value" style="font-size:16px;">${formatPercent(m.r2)}</div></div>
      <div class="card"><div class="card__label">MAE</div><div class="card__value" style="font-size:16px;">${formatNumber(m.mae, 4)}</div></div>
      <div class="card"><div class="card__label">RMSE</div><div class="card__value" style="font-size:16px;">${formatNumber(m.rmse, 4)}</div></div>
    `;

    const interpEl = document.getElementById("interpretation-content");
    interpEl.innerHTML = `
      <div class="insight-card insight-card--risk">
        <div class="insight-card__tag">Dominant Feature</div>
        <div class="insight-card__row">${data.dominant_feature_warning || "Acquisition Cost has a strong structural relationship with ROI."}</div>
      </div>
      <div class="insight-card insight-card--optimization">
        <div class="insight-card__tag">Interpretation</div>
        <div class="insight-card__row">Model predictions are <strong>decision-support estimates</strong>, not evidence that campaign strategy independently causes ROI. Model performance should not be interpreted as causal proof.</div>
      </div>
    `;
  } catch (err) {
    renderError(el, err, loadModelInfo);
  }
}

async function loadComparison() {
  const cardsEl = document.getElementById("comparison-cards");
  let entries;

  // Stage 1: fetch + render cards. Real errors here mean the API call itself failed.
  try {
    const data = await apiFetch("/api/model-comparison");
    const comparison = data.comparison || {};
    entries = Object.entries(comparison);

    if (!entries.length) {
      renderEmpty(cardsEl, "No comparison data available.");
      return;
    }

    cardsEl.innerHTML = entries
      .map(
        ([key, m]) => `
      <div class="comparison-card ${key === "early_stage" ? "comparison-card--primary" : ""}">
        <div class="comparison-card__name">${m.model_name || key}</div>
        <div class="comparison-card__metric"><span>R²</span><strong>${formatPercent(m.r2)}</strong></div>
        <div class="comparison-card__metric"><span>MAE</span><strong>${formatNumber(m.mae, 4)}</strong></div>
        <div class="comparison-card__metric"><span>RMSE</span><strong>${formatNumber(m.rmse, 4)}</strong></div>
      </div>`
      )
      .join("");
  } catch (err) {
    renderError(cardsEl, err, loadComparison);
    return;
  }

  // Stage 2: render charts from the SAME data. Any failure here (e.g.
  // the charting library) is isolated to the chart panels and never
  // touches the comparison cards rendered above.
  renderComparisonChartsSafely(entries);
}

function renderComparisonChartsSafely(entries) {
  const r2Canvas = document.getElementById("chart-r2");
  const errorCanvas = document.getElementById("chart-error");

  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");

    const labels = entries.map(([, m]) => m.model_name);

    new Chart(r2Canvas, {
      type: "bar",
      data: { labels, datasets: [{ label: "R²", data: entries.map(([, m]) => m.r2), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatPercent(ctx.parsed.y) } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => (v * 100).toFixed(0) + "%" } } },
      },
    });

    new Chart(errorCanvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          { label: "MAE", data: entries.map(([, m]) => m.mae), backgroundColor: CHART_COLORS.teal, borderRadius: 4 },
          { label: "RMSE", data: entries.map(([, m]) => m.rmse), backgroundColor: CHART_COLORS.violet, borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: CHART_COLORS.text } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text } } },
      },
    });
  } catch (err) {
    if (r2Canvas && r2Canvas.parentElement) r2Canvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    if (errorCanvas && errorCanvas.parentElement) errorCanvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
  }
}

async function loadFeatureImportance() {
  const el = document.getElementById("feature-importance-content");
  try {
    const data = await apiFetch("/api/model-feature-importance");
    const top = (data.feature_importance || []).slice(0, 15);
    if (!top.length) {
      renderEmpty(el, "No feature importance data available.");
      return;
    }
    const maxImportance = Math.max(...top.map((f) => f.importance));

    el.innerHTML = `
      <div class="importance-list">
        ${top
          .map((f) => {
            const isDominant = f.feature.toLowerCase().includes("acquisition_cost");
            return `
          <div class="importance-row">
            <div class="importance-row__label" style="${isDominant ? "color: var(--accent-teal); font-weight: 600;" : ""}">${f.feature}</div>
            <div class="importance-row__bar-track">
              <div class="importance-row__bar" style="width:${(f.importance / maxImportance) * 100}%; ${isDominant ? "background: linear-gradient(90deg, var(--accent-teal), var(--accent-blue));" : ""}"></div>
            </div>
            <div class="importance-row__value">${(f.importance * 100).toFixed(2)}%</div>
          </div>`;
          })
          .join("")}
      </div>
    `;
  } catch (err) {
    renderError(el, err, loadFeatureImportance);
  }
}

/* ============================================================
 * PHASE 6 — Model Intelligence & Explainability additions.
 * Single new call to GET /api/model-intelligence populates three
 * new sections: Acquisition Cost Dominance, What the Model Can/
 * Cannot Tell Us, and Model Limitations. This is purely additive —
 * loadModelInfo/loadComparison/loadFeatureImportance above are
 * untouched and keep working exactly as before.
 * ============================================================ */

async function loadModelIntelligenceExtras() {
  const dominanceEl = document.getElementById("acquisition-cost-dominance-content");
  const canCannotEl = document.getElementById("can-cannot-content");
  const limitationsEl = document.getElementById("limitations-content");

  try {
    const data = await apiFetch("/api/model-intelligence");
    renderAcquisitionCostDominance(dominanceEl, data.acquisition_cost_dominance);
    renderCanCannot(canCannotEl, data.interpretation);
    renderLimitations(limitationsEl, data.limitations || []);
  } catch (err) {
    renderError(dominanceEl, err, loadModelIntelligenceExtras);
    renderError(canCannotEl, err, loadModelIntelligenceExtras);
    renderError(limitationsEl, err, loadModelIntelligenceExtras);
  }
}

function renderAcquisitionCostDominance(el, dominance) {
  if (!dominance || dominance.cost_only_r2 == null || dominance.full_early_stage_r2 == null) {
    renderEmpty(el, "Acquisition Cost dominance data not available.");
    return;
  }

  el.innerHTML = `
    <div class="dominance-summary">
      <div class="dominance-summary__card">
        <div class="dominance-summary__label">Cost-only R²</div>
        <div class="dominance-summary__value">${formatPercent(dominance.cost_only_r2)}</div>
      </div>
      <div class="dominance-summary__card dominance-summary__card--highlight">
        <div class="dominance-summary__label">Full Early-Stage R²</div>
        <div class="dominance-summary__value" style="color: var(--accent-teal);">${formatPercent(dominance.full_early_stage_r2)}</div>
      </div>
      <div class="dominance-summary__card">
        <div class="dominance-summary__label">Additional (percentage points)</div>
        <div class="dominance-summary__value">+${(dominance.incremental_r2 * 100).toFixed(2)}</div>
      </div>
    </div>
    <p class="panel__text">${dominance.explanation}</p>
  `;
}

function renderCanCannot(el, interpretation) {
  const canList = (interpretation && interpretation.what_the_model_can_tell_us) || [];
  const cannotList = (interpretation && interpretation.what_the_model_cannot_tell_us) || [];

  if (!canList.length && !cannotList.length) {
    renderEmpty(el, "Interpretation data not available.");
    return;
  }

  el.innerHTML = `
    <div class="insight-card insight-card--opportunity">
      <div class="insight-card__tag">What the model CAN tell us</div>
      <ul class="can-cannot-list can-cannot-list--can">
        ${canList.map((item) => `<li>${item}</li>`).join("")}
      </ul>
    </div>
    <div class="insight-card insight-card--risk">
      <div class="insight-card__tag">What the model CANNOT tell us</div>
      <ul class="can-cannot-list can-cannot-list--cannot">
        ${cannotList.map((item) => `<li>${item}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderLimitations(el, limitations) {
  if (!limitations.length) {
    renderEmpty(el, "Model limitations data not available.");
    return;
  }

  el.innerHTML = limitations
    .map(
      (l) => `
    <div class="limitation-item">
      <div class="limitation-item__title">${l.title}</div>
      <div class="limitation-item__detail">${l.detail}</div>
    </div>`
    )
    .join("");
}
