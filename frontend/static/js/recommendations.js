/*
 * recommendations.js — Phase 8: Recommendation Intelligence.
 * All recommendation content (titles, metrics, confidence, risk
 * flags, evidence text) comes directly from GET /api/recommendations.
 * This file only renders — it never computes or invents a metric.
 */

document.addEventListener("DOMContentLoaded", () => {
  bindTypeFilter();
  loadRecommendations();
});

function bindTypeFilter() {
  document.getElementById("type-filter").addEventListener("change", (e) => {
    loadRecommendations(e.target.value || null);
  });
}

async function loadRecommendations(type = null) {
  const summaryEl = document.getElementById("summary-grid");
  const cardsEl = document.getElementById("recommendation-cards");
  renderLoading(summaryEl, "Loading…");
  renderLoading(cardsEl, "Loading recommendations…");

  const url = "/api/recommendations" + (type ? `?type=${encodeURIComponent(type)}` : "");

  try {
    const data = await apiFetch(url, { useCache: false });
    renderSummary(summaryEl, data.summary, data.recommendations);
    renderCards(cardsEl, data.recommendations);
  } catch (err) {
    renderError(summaryEl, err, () => loadRecommendations(type));
    renderError(cardsEl, err, () => loadRecommendations(type));
  }
}

function renderSummary(el, summary, recommendations) {
  const opportunities = (recommendations || []).filter((r) => r.recommendation_type !== "Risk").length;
  el.innerHTML = `
    <div class="card"><div class="card__label">Total Recommendations</div><div class="card__value">${summary.total}</div></div>
    <div class="card"><div class="card__label">High Priority</div><div class="card__value card__value--good">${summary.high_priority}</div></div>
    <div class="card"><div class="card__label">Opportunities</div><div class="card__value">${opportunities}</div></div>
    <div class="card"><div class="card__label">Risk Flags</div><div class="card__value" style="color: var(--danger);">${summary.warnings}</div></div>
  `;
}

function renderCards(el, recommendations) {
  if (!recommendations || !recommendations.length) {
    renderEmpty(el, "No recommendations available for the selected category.");
    return;
  }

  el.innerHTML = recommendations.map((rec, idx) => renderCard(rec, idx)).join("");

  el.querySelectorAll(".rec-why-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const detail = btn.nextElementSibling;
      const isOpen = !detail.hidden;
      detail.hidden = isOpen;
      btn.textContent = isOpen ? "Why this recommendation? +" : "Why this recommendation? −";
    });
  });
}

function cardVariantClass(rec) {
  if (rec.recommendation_type === "Risk") return "rec-card--risk";
  if (rec.recommendation_type === "Experiment Signal") return "rec-card--experiment";
  if (rec.recommendation_type === "Budget / Cost Signal") return "rec-card--budget";
  return "";
}

function confidenceBadgeClass(level) {
  return { High: "badge--confidence-high", Medium: "badge--confidence-medium", Low: "badge--confidence-low" }[level] || "badge--confidence-low";
}

function riskBadgeClass(level) {
  return { High: "badge--risk-high", Medium: "badge--risk-medium", Low: "badge--risk-low" }[level] || "badge--risk-low";
}

function renderMetricChips(metrics) {
  if (!metrics) return "";
  return Object.entries(metrics)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => {
      const label = k.replace(/_/g, " ");
      const value = typeof v === "number" ? formatMetricValue(k, v) : v;
      return `<span class="metric-chip">${label}: ${value}</span>`;
    })
    .join("");
}

function formatMetricValue(key, value) {
  if (key.includes("roi") && !key.includes("correlation")) return formatROI(value);
  if (key.includes("revenue")) return formatCurrency(value);
  if (key.includes("cost") && !key.includes("r2")) return formatCurrency(value, { compact: false });
  if (key.includes("r2") || key.includes("rate") || key.includes("pct")) return formatNumber(value, 4);
  if (key.includes("count")) return formatCompactNumber(value);
  return formatNumber(value, 4);
}

function renderCard(rec, idx) {
  const variant = cardVariantClass(rec);
  const flags = (rec.risk_flags || [])
    .map((f) => `<div class="rec-flag">${f.flag}: ${f.message}</div>`)
    .join("");

  const why = rec.why || {};

  return `
    <div class="rec-card ${variant}">
      <div class="rec-card__header">
        <div>
          <div class="rec-card__type">${rec.recommendation_type}</div>
          <div class="rec-card__title">${rec.title}</div>
        </div>
      </div>
      <div class="badge-row">
        <span class="badge badge--evidence">${rec.evidence_basis || "OBSERVED"}</span>
        <span class="badge ${confidenceBadgeClass(rec.confidence)}">Confidence: ${rec.confidence}</span>
        <span class="badge ${riskBadgeClass(rec.risk_level)}">Risk: ${rec.risk_level}</span>
      </div>
      <div class="rec-card__text">${rec.recommendation}</div>
      <div class="metric-chip-row">${renderMetricChips(rec.supporting_metrics)}</div>
      ${flags ? `<div class="rec-flags">${flags}</div>` : ""}
      <button type="button" class="rec-why-toggle" id="why-toggle-${idx}">Why this recommendation? +</button>
      <div class="rec-why-detail" hidden>
        <div class="rec-why-detail__row"><strong>Evidence</strong><span>${why.evidence || "—"}</span></div>
        <div class="rec-why-detail__row"><strong>Interpretation</strong><span>${why.interpretation || "—"}</span></div>
        <div class="rec-why-detail__row"><strong>Caution</strong><span>${why.caution || "—"}</span></div>
      </div>
    </div>
  `;
}
