/*
 * data-quality.js — Phase 12: Data Quality & Governance Center.
 * Single source of truth: GET /api/data-quality. All profile numbers,
 * validation results, outlier stats, duplicate counts, dictionary
 * entries, and governance flags rendered here come directly from that
 * response — nothing is computed, cleaned, or invented client-side.
 *
 * Chart rendering (1 chart on this page, per the "avoid excessive
 * charts" guidance) uses the same fault-isolation pattern already
 * established across the platform: destroy-before-create, and a
 * chart failure shows a readable message without removing the canvas.
 */

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  loadDataQuality();
});

async function loadDataQuality() {
  const ids = [
    "overview-grid", "completeness-table", "type-validation-table", "range-validation-table",
    "date-validity-content", "funnel-validation-table", "outlier-table", "duplicate-content",
    "dictionary-table", "governance-flags-grid",
  ];
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  let data;
  try {
    data = await apiFetch("/api/data-quality", { useCache: false });
  } catch (err) {
    ids.forEach((id) => renderError(document.getElementById(id), err, loadDataQuality));
    return;
  }

  renderReadinessBadge(data.analytics_readiness);
  renderOverview(data);
  renderCompleteness(data.missing_values);
  renderTypeValidation(data.type_validation);
  renderRangeValidation(data.range_validation);
  renderDateValidity(data.date_quality);
  renderFunnelValidation(data.business_logic);
  renderOutlierTable(data.outliers);
  renderDuplicates(data.duplicates);
  renderDictionary(data.data_dictionary);
  renderGovernanceFlags(data.governance_flags);

  // Chart renders last and independently.
  renderOutlierChart(data.outliers);
}

/* ============================================================
   BADGE / STATUS HELPERS
   ============================================================ */

function resultBadgeClass(result) {
  return { PASS: "badge--confidence-high", GOOD: "badge--confidence-high", WARNING: "badge--confidence-medium", WATCH: "badge--confidence-medium", FAIL: "badge--risk-high", RISK: "badge--risk-high" }[result] || "badge--confidence-low";
}

function severityItemClass(severity) {
  return { INFO: "limitation-item--info", GOOD: "limitation-item--info", WATCH: "limitation-item--watch", RISK: "limitation-item--risk" }[severity] || "limitation-item--info";
}

/* ============================================================
   OVERVIEW
   ============================================================ */

function renderReadinessBadge(readiness) {
  const el = document.getElementById("readiness-badge");
  el.textContent = readiness ? readiness.status : "Unknown";
}

function renderOverview(data) {
  const el = document.getElementById("overview-grid");
  const score = data.quality_score || {};
  const missing = data.missing_values || {};
  const duplicates = data.duplicates || {};
  const readiness = data.analytics_readiness || {};

  const totalMissing = (missing.columns || []).reduce((sum, c) => sum + c.missing_count, 0);
  const validationIssues = [
    ...(data.type_validation || []).filter((t) => t.result !== "PASS"),
    ...(data.range_validation || []).filter((r) => r.result !== "PASS"),
    ...((data.business_logic || {}).checks || []).filter((c) => c.severity !== "INFO"),
  ].length;

  el.innerHTML = `
    <div class="card">
      <div class="card__label">Analytical Data Quality Score</div>
      <div class="card__value">${score.score != null ? score.score + " / 100" : "—"}</div>
      <p class="card__meta">${score.status || "—"}</p>
    </div>
    <div class="card">
      <div class="card__label">Missing Data</div>
      <div class="card__value">${formatCompactNumber(totalMissing)}</div>
      <p class="card__meta">${totalMissing === 0 ? "No missing values detected." : "values missing"}</p>
    </div>
    <div class="card">
      <div class="card__label">Duplicate Rows</div>
      <div class="card__value">${formatCompactNumber(duplicates.exact_duplicate_rows ?? 0)}</div>
      <p class="card__meta">${duplicates.exact_duplicate_percentage ?? 0}% of rows</p>
    </div>
    <div class="card">
      <div class="card__label">Validation Issues</div>
      <div class="card__value">${validationIssues}</div>
      <p class="card__meta">checks not fully PASS</p>
    </div>
    <div class="card">
      <div class="card__label">Analytics Readiness</div>
      <div class="card__value" style="font-size: 15px;">${readiness.status || "—"}</div>
      <p class="card__meta">${readiness.explanation || ""}</p>
    </div>
  `;
}

/* ============================================================
   COMPLETENESS
   ============================================================ */

function renderCompleteness(missingValues) {
  const el = document.getElementById("completeness-table");
  const noteEl = document.getElementById("completeness-note");
  const columns = (missingValues && missingValues.columns) || [];
  noteEl.textContent = (missingValues && missingValues.summary) || "";

  if (!columns.length) {
    renderEmpty(el, "No columns to assess.");
    return;
  }

  const rows = columns
    .map(
      (c) => `
    <tr>
      <td>${c.column}</td>
      <td>${(100 - c.missing_percentage).toFixed(2)}%</td>
      <td>${formatCompactNumber(c.missing_count)}</td>
      <td><span class="badge ${resultBadgeClass(c.status)}">${c.status}</span></td>
    </tr>`
    )
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Column</th><th>Non-Missing %</th><th>Missing Count</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   TYPE / RANGE VALIDATION
   ============================================================ */

function renderTypeValidation(checks) {
  const el = document.getElementById("type-validation-table");
  if (!checks || !checks.length) {
    renderEmpty(el, "No type validation checks available.");
    return;
  }
  const rows = checks.map((c) => `<tr><td>${c.field}</td><td>${c.check}</td><td><span class="badge ${resultBadgeClass(c.result)}">${c.result}</span></td><td style="font-size:11.5px; color:var(--text-faint);">${c.explanation}</td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Check</th><th>Result</th><th>Explanation</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderRangeValidation(checks) {
  const el = document.getElementById("range-validation-table");
  if (!checks || !checks.length) {
    renderEmpty(el, "No range validation checks available.");
    return;
  }
  const rows = checks.map((c) => `<tr><td>${c.rule}</td><td>${formatCompactNumber(c.violation_count)}</td><td><span class="badge ${resultBadgeClass(c.result)}">${c.result}</span></td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Rule</th><th>Violations</th><th>Result</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderDateValidity(dateQuality) {
  const el = document.getElementById("date-validity-content");
  if (!dateQuality || dateQuality.status === "unavailable") {
    renderEmpty(el, "Date validity not available.");
    return;
  }
  el.innerHTML = `
    <div class="group-card__stat"><span>Date range</span><strong>${dateQuality.min_date} to ${dateQuality.max_date}</strong></div>
    <div class="group-card__stat"><span>Invalid dates</span><strong>${formatCompactNumber(dateQuality.invalid_count)}</strong></div>
    <div class="group-card__stat"><span>Missing dates</span><strong>${formatCompactNumber(dateQuality.missing_count)}</strong></div>
    <div class="group-card__stat"><span>Future-dated rows</span><strong>${formatCompactNumber(dateQuality.future_date_count)}</strong></div>
  `;
}

function renderFunnelValidation(businessLogic) {
  const el = document.getElementById("funnel-validation-table");
  const checks = (businessLogic && businessLogic.checks) || [];
  if (!checks.length) {
    renderEmpty(el, "No funnel consistency checks available.");
    return;
  }
  const rows = checks.map((c) => `<tr><td>${c.rule}</td><td>${formatCompactNumber(c.violation_count)}</td><td><span class="badge ${resultBadgeClass(c.severity)}">${c.severity}</span></td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Rule</th><th>Violations</th><th>Severity</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   OUTLIERS
   ============================================================ */

function renderOutlierTable(outliers) {
  const el = document.getElementById("outlier-table");
  if (!outliers || !outliers.length) {
    renderEmpty(el, "No outlier data available.");
    return;
  }
  const rows = outliers.map((o) => `<tr><td>${o.field}</td><td>${formatCompactNumber(o.outlier_count)}</td><td>${o.outlier_percentage}%</td><td>${o.method}</td><td style="font-size:11.5px; color:var(--text-faint);">${o.interpretation}</td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Outlier Count</th><th>Outlier %</th><th>Method</th><th>Interpretation</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderOutlierChart(outliers) {
  renderChartSafely("chart-outliers", () => {
    const rows = outliers || [];
    return new Chart(document.getElementById("chart-outliers"), {
      type: "bar",
      data: { labels: rows.map((o) => o.field), datasets: [{ data: rows.map((o) => o.outlier_percentage), backgroundColor: CHART_COLORS.amber, borderRadius: 4 }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => ctx.parsed.y + "%" } } },
        scales: { x: { grid: { display: false }, ticks: { color: CHART_COLORS.text } }, y: { grid: { color: CHART_COLORS.grid }, ticks: { color: CHART_COLORS.text, callback: (v) => v + "%" } } },
      },
    });
  });
}

/* ============================================================
   DUPLICATES
   ============================================================ */

function renderDuplicates(duplicates) {
  const el = document.getElementById("duplicate-content");
  if (!duplicates) {
    renderEmpty(el, "Duplicate analysis not available.");
    return;
  }
  el.innerHTML = `
    <div class="grid" style="grid-template-columns: repeat(2,1fr); margin-bottom: 12px;">
      <div class="card"><div class="card__label">Exact Duplicate Rows</div><div class="card__value">${formatCompactNumber(duplicates.exact_duplicate_rows)}</div><p class="card__meta">${duplicates.exact_duplicate_percentage ?? 0}% of rows</p></div>
      <div class="card"><div class="card__label">Repeated Campaign_ID Values</div><div class="card__value">${formatCompactNumber(duplicates.duplicate_campaign_id_count ?? 0)}</div><p class="card__meta">${duplicates.duplicate_campaign_id_percentage ?? 0}% of rows</p></div>
    </div>
    <p class="panel__text">${duplicates.note || ""}</p>
  `;
}

/* ============================================================
   DATA DICTIONARY (with client-side search)
   ============================================================ */

let dictionaryEntries = [];

function renderDictionary(entries) {
  dictionaryEntries = entries || [];
  document.getElementById("dictionary-search").addEventListener("input", (e) => renderDictionaryTable(e.target.value));
  renderDictionaryTable("");
}

function renderDictionaryTable(query) {
  const el = document.getElementById("dictionary-table");
  const filtered = query
    ? dictionaryEntries.filter((e) => e.field.toLowerCase().includes(query.toLowerCase()) || e.analytical_role.toLowerCase().includes(query.toLowerCase()))
    : dictionaryEntries;

  if (!filtered.length) {
    renderEmpty(el, "No matching fields.");
    return;
  }
  const rows = filtered.map((e) => `<tr><td>${e.field}</td><td>${e.detected_type}</td><td>${e.non_missing_percentage}%</td><td>${formatCompactNumber(e.unique_values)}</td><td>${e.analytical_role}</td></tr>`).join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Field</th><th>Type</th><th>Non-Missing %</th><th>Unique Values</th><th>Role</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   GOVERNANCE FLAGS
   ============================================================ */

function renderGovernanceFlags(flags) {
  const el = document.getElementById("governance-flags-grid");
  if (!flags || !flags.length) {
    renderEmpty(el, "No governance flags.");
    return;
  }
  el.innerHTML = flags
    .map(
      (f) => `
    <div class="limitation-item ${severityItemClass(f.severity)}">
      <div class="limitation-item__title">${f.title} <span class="badge ${resultBadgeClass(f.severity)}" style="margin-left:6px;">${f.severity}</span></div>
      <div class="limitation-item__detail">${f.explanation}</div>
      <div class="dq-metric-note">${f.metric}</div>
      <div class="limitation-item__detail" style="margin-top:6px;"><strong style="color:var(--text);">Recommended action:</strong> ${f.recommended_action}</div>
    </div>`
    )
    .join("");
}

/* ============================================================
   SAFE CHART RENDER (same pattern used across the platform)
   ============================================================ */

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
