/*
 * platform-health.js — Phase 15: Platform Health & Readiness.
 * Single source of truth: GET /api/health/platform. Every status,
 * count, and metric shown here comes from that response — the page
 * never asserts readiness the backend didn't actually verify.
 */

document.addEventListener("DOMContentLoaded", loadPlatformHealth);

async function loadPlatformHealth() {
  const ids = ["status-grid", "checks-table", "asset-detail"];
  ids.forEach((id) => renderLoading(document.getElementById(id), "Loading…"));

  let data;
  try {
    data = await apiFetch("/api/health/platform", { useCache: false });
  } catch (err) {
    ids.forEach((id) => renderError(document.getElementById(id), err, loadPlatformHealth));
    return;
  }

  renderOverallBadge(data);
  renderStatusCards(data);
  renderChecksTable(data.checks || []);
  renderAssetDetail(data.checks || []);
  renderList("model-governance-list", data.model_governance);
  renderList("analytical-guardrails-list", data.analytical_guardrails);

  const final = data.final_governance_statement || {};
  if (final.title) document.getElementById("final-governance-title").textContent = final.title;
  renderList("final-governance-list", final.statements);
}

function statusBadgeClass(status) {
  return { PASS: "badge--confidence-high", WARN: "badge--confidence-medium", FAIL: "badge--risk-high" }[status] || "badge--confidence-low";
}

function renderOverallBadge(data) {
  const el = document.getElementById("overall-status-badge");
  const label = { HEALTHY: "HEALTHY", HEALTHY_WITH_WARNINGS: "HEALTHY WITH WARNINGS", DEGRADED: "DEGRADED" }[data.status] || data.status;
  el.textContent = label;
}

function findCheck(checks, name) {
  return checks.find((c) => c.name === name);
}

function statusWord(check, readyLabel) {
  if (!check) return "UNKNOWN";
  if (check.status === "PASS") return readyLabel;
  if (check.status === "WARN") return "WARNINGS";
  return "NOT READY";
}

function renderStatusCards(data) {
  const el = document.getElementById("status-grid");
  const checks = data.checks || [];
  const s = data.summary || {};

  const dataset = findCheck(checks, "Required schema");
  const model = findCheck(checks, "Model artifact");
  const api = findCheck(checks, "API endpoints");
  const ui = findCheck(checks, "Frontend templates");
  const tests = findCheck(checks, "Test suite summary");

  const overallLabel = { HEALTHY: "HEALTHY", HEALTHY_WITH_WARNINGS: "HEALTHY (WARNINGS)", DEGRADED: "DEGRADED" }[data.status] || data.status;
  const overallColor = data.status === "HEALTHY" ? "var(--accent-teal)" : data.status === "DEGRADED" ? "var(--danger)" : "var(--warn)";

  el.innerHTML = `
    <div class="card"><div class="card__label">Overall Status</div><div class="card__value" style="font-size:15px; color:${overallColor};">${overallLabel}</div><p class="card__meta">${s.passed || 0} passed · ${s.warnings || 0} warn · ${s.failed || 0} fail</p></div>
    <div class="card"><div class="card__label">Dataset</div><div class="card__value" style="font-size:15px;">${statusWord(dataset, "READY")}</div></div>
    <div class="card"><div class="card__label">Model</div><div class="card__value" style="font-size:15px;">${statusWord(model, "READY")}</div></div>
    <div class="card"><div class="card__label">APIs</div><div class="card__value" style="font-size:15px;">${statusWord(api, "READY")}</div></div>
    <div class="card"><div class="card__label">Frontend</div><div class="card__value" style="font-size:15px;">${statusWord(ui, "READY")}</div></div>
    <div class="card"><div class="card__label">Test Suite</div><div class="card__value" style="font-size:15px;">${tests && tests.status === "PASS" ? "PASSING" : tests && tests.status === "WARN" ? "NOT RECORDED" : "FAILING"}</div></div>
  `;
}

function renderChecksTable(checks) {
  const el = document.getElementById("checks-table");
  if (!checks.length) {
    renderEmpty(el, "No checks returned.");
    return;
  }
  const rows = checks
    .map(
      (c) => `
    <tr>
      <td>${escapeHealthHtml(c.name)}</td>
      <td><span class="badge ${statusBadgeClass(c.status)}">${c.status}</span></td>
      <td>${escapeHealthHtml(c.severity)}</td>
      <td style="font-size:11.5px; color:var(--text-secondary);">${escapeHealthHtml(c.message)}</td>
    </tr>`
    )
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Check</th><th>Status</th><th>Severity</th><th>Message</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function renderAssetDetail(checks) {
  const el = document.getElementById("asset-detail");
  const integrity = findCheck(checks, "Dataset integrity");
  const rowCheck = findCheck(checks, "Dataset row count");
  const colCheck = findCheck(checks, "Dataset column count");
  const metadata = findCheck(checks, "Model metadata");

  const d = (integrity && integrity.details) || {};
  const m = (metadata && metadata.details) || {};

  const datasetCard = `
    <div class="insight-card insight-card--opportunity">
      <div class="insight-card__tag">Dataset</div>
      <div class="insight-card__row"><strong>Rows:</strong> ${rowCheck && rowCheck.details ? Number(rowCheck.details.rows).toLocaleString() : "—"}</div>
      <div class="insight-card__row"><strong>Columns:</strong> ${colCheck && colCheck.details ? colCheck.details.columns : "—"}</div>
      <div class="insight-card__row"><strong>Integrity:</strong> ${integrity ? escapeHealthHtml(integrity.message) : "—"}</div>
      ${d.sha256 ? `<div class="insight-card__row" style="font-family:var(--font-mono); font-size:10.5px; word-break:break-all;"><strong>SHA-256:</strong> ${escapeHealthHtml(d.sha256)}</div>` : ""}
    </div>`;

  const modelCard = `
    <div class="insight-card insight-card--optimization">
      <div class="insight-card__tag">Model</div>
      <div class="insight-card__row"><strong>Model:</strong> ${m.model_name ? escapeHealthHtml(m.model_name) : "—"}</div>
      <div class="insight-card__row"><strong>R²:</strong> ${m.r2 != null ? (m.r2 * 100).toFixed(2) + "%" : "—"}</div>
      <div class="insight-card__row"><strong>MAE:</strong> ${m.mae != null ? Number(m.mae).toFixed(4) : "—"} · <strong>RMSE:</strong> ${m.rmse != null ? Number(m.rmse).toFixed(4) : "—"}</div>
      <div class="insight-card__row"><strong>Train / Test:</strong> ${m.train_sample_count ? Number(m.train_sample_count).toLocaleString() : "—"} / ${m.test_sample_count ? Number(m.test_sample_count).toLocaleString() : "—"}</div>
      <div class="insight-card__row" style="color:var(--text-faint);">${m.governance_note ? escapeHealthHtml(m.governance_note) : ""}</div>
    </div>`;

  el.innerHTML = datasetCard + modelCard;
}

function renderList(elementId, items) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.innerHTML = (items || []).map((i) => `<li>${escapeHealthHtml(i)}</li>`).join("");
}

function escapeHealthHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
