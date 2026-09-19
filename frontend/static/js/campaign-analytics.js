/*
 * campaign-analytics.js — Phase 7: full interactive Campaign Analytics.
 *
 * All data comes from GET /api/campaign-analytics/* (never the full
 * 55,555-row dataset loaded into the browser). Every filter change
 * refetches every section server-side, so KPIs/charts/tables/rankings
 * all reflect the SAME active filter set — never stale global numbers.
 *
 * Chart rendering is isolated from table/card rendering throughout
 * (same fault-isolation pattern used elsewhere in this app): a
 * charting failure can only blank its own chart panel, never a
 * working table.
 */

const state = {
  filters: {},
  table: { page: 1, pageSize: 25, sortBy: null, sortDir: "desc" },
  topMetric: "roi",
  topLimit: 10,
  underMetric: "lowest_roi",
  underLimit: 10,
};

const RANGE_FIELD_IDS = {
  duration_min: "f-duration-min",
  duration_max: "f-duration-max",
  acquisition_cost_min: "f-cost-min",
  acquisition_cost_max: "f-cost-max",
  roi_min: "f-roi-min",
  roi_max: "f-roi-max",
  revenue_min: "f-revenue-min",
  revenue_max: "f-revenue-max",
  conversions_min: "f-conversions-min",
  conversions_max: "f-conversions-max",
};

document.addEventListener("DOMContentLoaded", () => {
  applyChartDefaults();
  populateFilterDropdowns();
  bindControls();
  refreshAll();
});

/* ============================================================
   FILTER QUERY BUILDING
   ============================================================ */

function buildFilterQuery(extra = {}) {
  const params = new URLSearchParams();
  Object.entries(state.filters).forEach(([k, v]) => {
    if (v) params.set(k, v);
  });
  Object.entries(extra).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") params.set(k, v);
  });
  return params.toString();
}

function readFiltersFromForm() {
  const form = document.getElementById("filter-form");
  const data = new FormData(form);
  const filters = {};
  for (const [key, value] of data.entries()) {
    if (value) filters[key] = value;
  }
  Object.entries(RANGE_FIELD_IDS).forEach(([param, id]) => {
    const val = document.getElementById(id).value;
    if (val !== "") filters[param] = val;
  });
  state.filters = filters;
}

/* ============================================================
   CONTROLS
   ============================================================ */

function bindControls() {
  const form = document.getElementById("filter-form");
  let debounceTimer;

  const debouncedRefresh = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      readFiltersFromForm();
      state.table.page = 1;
      refreshAll();
    }, 400);
  };

  // BUGFIX: previously this "input" listener was bound to the whole
  // <form>, and a separate "change" listener was ALSO bound to the
  // whole <form>. Modern browsers fire BOTH "input" and "change" when
  // a <select> value changes, so every dropdown selection triggered
  // TWO overlapping refreshAll() calls — one immediately (change) and
  // one ~400ms later (debounced input). Each call created a new
  // Chart.js instance on the same canvases without destroying the
  // previous one, which is exactly Chart.js's "Canvas is already in
  // use" failure — the four charts on the busiest / latest-resolving
  // sections lost that race and rendered a blank/error state.
  //
  // Fix: bind the debounced "input" listener only to genuine free-text
  // fields (search/channel), and keep "change" for <select> elements.
  // No control now receives both handlers.
  const textInputIds = ["f-channel", "f-search"];
  textInputIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", debouncedRefresh);
  });

  form.addEventListener("change", (e) => {
    if (textInputIds.includes(e.target.id)) return; // already handled by debouncedRefresh above
    readFiltersFromForm();
    state.table.page = 1;
    refreshAll();
  });

  Object.values(RANGE_FIELD_IDS).forEach((id) => {
    document.getElementById(id).addEventListener("input", debouncedRefresh);
  });

  document.getElementById("reset-filters-btn").addEventListener("click", () => {
    form.reset();
    Object.values(RANGE_FIELD_IDS).forEach((id) => (document.getElementById(id).value = ""));
    state.filters = {};
    state.table.page = 1;
    refreshAll();
  });

  document.getElementById("export-btn").addEventListener("click", () => {
    window.open("/api/campaign-analytics/export?" + buildFilterQuery(), "_blank");
  });

  document.getElementById("table-page-size").addEventListener("change", (e) => {
    state.table.pageSize = Number(e.target.value);
    state.table.page = 1;
    loadTable();
  });
  document.getElementById("table-page-prev").addEventListener("click", () => {
    if (state.table.page > 1) {
      state.table.page -= 1;
      loadTable();
    }
  });
  document.getElementById("table-page-next").addEventListener("click", () => {
    state.table.page += 1;
    loadTable();
  });

  document.getElementById("top-metric").addEventListener("change", (e) => {
    state.topMetric = e.target.value;
    loadTopCampaigns();
  });
  document.getElementById("top-limit").addEventListener("change", (e) => {
    state.topLimit = Number(e.target.value);
    loadTopCampaigns();
  });
  document.getElementById("under-metric").addEventListener("change", (e) => {
    state.underMetric = e.target.value;
    loadUnderperforming();
  });
  document.getElementById("under-limit").addEventListener("change", (e) => {
    state.underLimit = Number(e.target.value);
    loadUnderperforming();
  });
}

async function populateFilterDropdowns() {
  try {
    const [types, segments, audiences, languages] = await Promise.all([
      apiFetch("/api/campaign-analytics/campaign-types"),
      apiFetch("/api/campaign-analytics/customer-segments"),
      apiFetch("/api/campaign-analytics/audiences"),
      apiFetch("/api/campaign-analytics/languages"),
    ]);
    fillSelect(document.getElementById("f-campaign-type"), types.campaign_types.map((t) => t.name));
    fillSelect(document.getElementById("f-customer-segment"), segments.customer_segments.map((s) => s.name));
    fillSelect(document.getElementById("f-target-audience"), audiences.audiences.map((a) => a.name));
    fillSelect(document.getElementById("f-language"), languages.languages.map((l) => l.name));
  } catch (err) {
    // Dropdowns are a convenience; sections still load without them.
  }
}

function fillSelect(select, values) {
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  });
}

function renderActiveFilters() {
  const el = document.getElementById("active-filters-row");
  const entries = Object.entries(state.filters);
  if (!entries.length) {
    el.innerHTML = '<span class="active-filters-label">No active filters — showing all campaigns.</span>';
    return;
  }
  const labelMap = {
    campaign_type: "Campaign Type", customer_segment: "Customer Segment", target_audience: "Target Audience",
    channel: "Channel contains", language: "Language", search: "Campaign ID contains",
    duration_min: "Duration ≥", duration_max: "Duration ≤",
    acquisition_cost_min: "Acquisition Cost ≥", acquisition_cost_max: "Acquisition Cost ≤",
    roi_min: "ROI ≥", roi_max: "ROI ≤", revenue_min: "Revenue ≥", revenue_max: "Revenue ≤",
    conversions_min: "Conversions ≥", conversions_max: "Conversions ≤",
  };
  el.innerHTML =
    '<span class="active-filters-label">Active Filters:</span>' +
    entries.map(([k, v]) => `<span class="active-filter-chip">${labelMap[k] || k}: ${v}</span>`).join("");
}

/* ============================================================
   ORCHESTRATION
   ============================================================ */

function refreshAll() {
  renderActiveFilters();
  loadSummary();
  loadTable();
  loadTypeAnalysis();
  loadChannelAnalysis();
  loadSegmentAnalysis();
  loadAudienceAnalysis();
  loadLanguageAnalysis();
  loadRoiDistribution();
  loadPerformanceTiers();
  loadTopCampaigns();
  loadUnderperforming();
}

/* ============================================================
   FILTERED SUMMARY
   ============================================================ */

async function loadSummary() {
  const el = document.getElementById("filtered-summary-grid");
  renderLoading(el, "Loading…");
  try {
    const data = await apiFetch("/api/campaign-analytics/summary?" + buildFilterQuery(), { useCache: false });
    const s = data.summary;
    if (!s.filtered_campaigns) {
      renderEmpty(el, "No campaigns match the selected filters.");
      return;
    }
    el.innerHTML = `
      <div class="card"><div class="card__label">Filtered Campaigns</div><div class="card__value">${formatCompactNumber(s.filtered_campaigns)}</div></div>
      <div class="card"><div class="card__label">Total Revenue</div><div class="card__value">${formatCurrency(s.total_revenue)}</div></div>
      <div class="card"><div class="card__label">Average ROI</div><div class="card__value">${formatROI(s.average_roi)}</div></div>
      <div class="card"><div class="card__label">Median ROI</div><div class="card__value">${formatROI(s.median_roi)}</div></div>
      <div class="card"><div class="card__label">Total Conversions</div><div class="card__value">${formatCompactNumber(s.total_conversions)}</div></div>
      <div class="card"><div class="card__label">Avg. Acquisition Cost</div><div class="card__value">${formatCurrency(s.average_acquisition_cost, { compact: false })}</div></div>
      <div class="card"><div class="card__label">Avg. Engagement Score</div><div class="card__value">${formatNumber(s.average_engagement_score, 2)}</div></div>
    `;
  } catch (err) {
    renderError(el, err, loadSummary);
  }
}

/* ============================================================
   TABLE
   ============================================================ */

async function loadTable() {
  const el = document.getElementById("campaigns-table");
  renderLoading(el, "Loading campaigns…");

  const query = buildFilterQuery({
    page: state.table.page,
    page_size: state.table.pageSize,
    sort_by: state.table.sortBy || undefined,
    sort_dir: state.table.sortDir,
  });

  try {
    const data = await apiFetch("/api/campaign-analytics/table?" + query, { useCache: false });
    if (!data.results.length) {
      renderEmpty(el, "No campaigns match the selected filters.");
      updateTablePaginationUI(data.pagination);
      return;
    }
    renderCampaignTable(el, data.results);
    updateTablePaginationUI(data.pagination);
  } catch (err) {
    renderError(el, err, loadTable);
  }
}

const SORTABLE_COLUMNS = { Revenue: "Revenue", Acquisition_Cost: "Acquisition Cost", ROI: "ROI", Conversions: "Conversions", Duration: "Duration" };

function renderCampaignTable(el, rows) {
  const headers = ["Campaign ID", "Campaign Type", "Target Audience", "Channel", "Language", "Customer Segment", "Duration", "Revenue", "Acquisition Cost", "ROI", "Conversions", "Engagement Score"];
  const headerHtml = headers
    .map((h) => {
      const field = h.replace(/ /g, "_");
      const sortable = SORTABLE_COLUMNS[field];
      const isSorted = state.table.sortBy === field;
      return sortable
        ? `<th class="${isSorted ? "is-sorted" : ""}" data-sort="${field}">${h}${isSorted ? (state.table.sortDir === "asc" ? " ▲" : " ▼") : ""}</th>`
        : `<th>${h}</th>`;
    })
    .join("");

  const rowsHtml = rows
    .map((r) => {
      const roiClass = r.ROI > 1 ? "roi-badge--positive" : r.ROI >= 0 ? "roi-badge--neutral" : "roi-badge--negative";
      return `
      <tr>
        <td>${r.Campaign_ID ?? "—"}</td>
        <td>${r.Campaign_Type ?? "—"}</td>
        <td>${r.Target_Audience ?? "—"}</td>
        <td>${r.Channel_Used ?? "—"}</td>
        <td>${r.Language ?? "—"}</td>
        <td>${r.Customer_Segment ?? "—"}</td>
        <td>${r.Duration ?? "—"}</td>
        <td>${formatCurrency(r.Revenue, { compact: false })}</td>
        <td>${formatCurrency(r.Acquisition_Cost, { compact: false })}</td>
        <td><span class="roi-badge ${roiClass}">${formatROI(r.ROI)}</span></td>
        <td>${formatCompactNumber(r.Conversions)}</td>
        <td>${formatNumber(r.Engagement_Score, 2)}</td>
      </tr>`;
    })
    .join("");

  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr>${headerHtml}</tr></thead><tbody>${rowsHtml}</tbody></table></div>`;

  el.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const field = th.getAttribute("data-sort");
      if (state.table.sortBy === field) {
        state.table.sortDir = state.table.sortDir === "asc" ? "desc" : "asc";
      } else {
        state.table.sortBy = field;
        state.table.sortDir = "desc";
      }
      state.table.page = 1;
      loadTable();
    });
  });
}

function updateTablePaginationUI(pagination) {
  const info = document.getElementById("table-page-info");
  const prevBtn = document.getElementById("table-page-prev");
  const nextBtn = document.getElementById("table-page-next");
  if (!pagination) {
    info.textContent = "—";
    return;
  }
  info.textContent = `${formatCompactNumber(pagination.total_results)} campaigns · Page ${pagination.page} of ${pagination.total_pages}`;
  prevBtn.disabled = pagination.page <= 1;
  nextBtn.disabled = pagination.page >= pagination.total_pages;
}

/* ============================================================
   CAMPAIGN TYPE ANALYSIS
   ============================================================ */

async function loadTypeAnalysis() {
  const tableEl = document.getElementById("type-table");
  try {
    const data = await apiFetch("/api/campaign-analytics/campaign-types?" + buildFilterQuery(), { useCache: false });
    const types = data.campaign_types || [];
    if (!types.length) {
      renderEmpty(tableEl, "No campaigns match the selected filters.");
      return;
    }
    renderGroupTable(tableEl, types, "Campaign Type");
    renderChartSafely("chart-type-revenue", () => new Chart(document.getElementById("chart-type-revenue"), {
      type: "bar", data: { labels: types.map((t) => t.name), datasets: [{ data: types.map((t) => t.total_revenue), backgroundColor: CHART_COLORS.blue, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatCurrency(v)),
    }));
    renderChartSafely("chart-type-roi", () => new Chart(document.getElementById("chart-type-roi"), {
      type: "bar", data: { labels: types.map((t) => t.name), datasets: [{ data: types.map((t) => t.average_roi), backgroundColor: CHART_COLORS.teal, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatROI(v)),
    }));
    renderChartSafely("chart-type-count", () => new Chart(document.getElementById("chart-type-count"), {
      type: "bar", data: { labels: types.map((t) => t.name), datasets: [{ data: types.map((t) => t.campaign_count), backgroundColor: CHART_COLORS.violet, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatCompactNumber(v)),
    }));
  } catch (err) {
    renderError(tableEl, err, loadTypeAnalysis);
  }
}

/* ============================================================
   CHANNEL ANALYSIS
   ============================================================ */

async function loadChannelAnalysis() {
  const el = document.getElementById("channel-table");
  const noteEl = document.getElementById("channel-note");
  try {
    const data = await apiFetch("/api/campaign-analytics/channels?" + buildFilterQuery(), { useCache: false });
    noteEl.textContent = data.note || "";
    const channels = data.channels || [];
    if (!channels.length) {
      renderEmpty(el, "No campaigns match the selected filters.");
      return;
    }
    const rows = channels
      .map((c) => `
      <tr>
        <td>${c.recorded_channel_combination}</td>
        <td>${formatCompactNumber(c.campaign_count)}</td>
        <td>${formatCurrency(c.total_revenue)}</td>
        <td>${formatROI(c.average_roi)}</td>
        <td>${formatROI(c.median_roi)}</td>
        <td>${formatCompactNumber(c.total_conversions)}</td>
        <td>${formatCurrency(c.average_acquisition_cost, { compact: false })}</td>
      </tr>`)
      .join("");
    el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Recorded Channel Combination</th><th>Campaign Count</th><th>Revenue</th><th>Avg ROI</th><th>Median ROI</th><th>Conversions</th><th>Avg Acquisition Cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (err) {
    renderError(el, err, loadChannelAnalysis);
  }
}

/* ============================================================
   CUSTOMER SEGMENT ANALYSIS
   ============================================================ */

async function loadSegmentAnalysis() {
  const tableEl = document.getElementById("segment-table");
  try {
    const data = await apiFetch("/api/campaign-analytics/customer-segments?" + buildFilterQuery(), { useCache: false });
    const segments = data.customer_segments || [];
    if (!segments.length) {
      renderEmpty(tableEl, "No campaigns match the selected filters.");
      return;
    }
    renderGroupTable(tableEl, segments, "Customer Segment");

    const revenueSeries = toSafeChartSeries(segments, (s) => s.name, (s) => s.total_revenue);
    renderChartSafely("chart-segment-revenue", () => new Chart(document.getElementById("chart-segment-revenue"), {
      type: "bar", data: { labels: revenueSeries.labels, datasets: [{ data: revenueSeries.values, backgroundColor: CHART_COLORS.blue, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatCurrency(v)),
    }));

    const roiSeries = toSafeChartSeries(segments, (s) => s.name, (s) => s.average_roi);
    renderChartSafely("chart-segment-roi", () => new Chart(document.getElementById("chart-segment-roi"), {
      type: "bar", data: { labels: roiSeries.labels, datasets: [{ data: roiSeries.values, backgroundColor: CHART_COLORS.teal, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatROI(v)),
    }));

    const conversionsSeries = toSafeChartSeries(segments, (s) => s.name, (s) => s.total_conversions);
    renderChartSafely("chart-segment-conversions", () => new Chart(document.getElementById("chart-segment-conversions"), {
      type: "bar", data: { labels: conversionsSeries.labels, datasets: [{ data: conversionsSeries.values, backgroundColor: CHART_COLORS.amber, borderRadius: 4 }] },
      options: baseChartOptions((v) => formatCompactNumber(v)),
    }));
  } catch (err) {
    renderError(tableEl, err, loadSegmentAnalysis);
  }
}

/* ============================================================
   TARGET AUDIENCE ANALYSIS
   ============================================================ */

async function loadAudienceAnalysis() {
  const highlightsEl = document.getElementById("audience-highlights");
  const tableEl = document.getElementById("audience-table");
  try {
    const data = await apiFetch("/api/campaign-analytics/audiences?" + buildFilterQuery(), { useCache: false });
    const audiences = data.audiences || [];
    if (!audiences.length) {
      renderEmpty(highlightsEl, "");
      renderEmpty(tableEl, "No campaigns match the selected filters.");
      return;
    }
    highlightsEl.innerHTML = `
      <div class="highlight-card"><div class="highlight-card__label">Highest Average ROI</div><div class="highlight-card__value">${data.highest_average_roi_audience || "—"}</div></div>
      <div class="highlight-card"><div class="highlight-card__label">Highest Revenue</div><div class="highlight-card__value">${data.highest_revenue_audience || "—"}</div></div>
      <div class="highlight-card"><div class="highlight-card__label">Highest Conversions</div><div class="highlight-card__value">${data.highest_conversions_audience || "—"}</div></div>
    `;
    const rows = audiences
      .map((a) => `<tr><td>${a.name}</td><td>${formatCompactNumber(a.campaign_count)}</td><td>${formatCurrency(a.total_revenue)}</td><td>${formatROI(a.average_roi)}</td><td>${formatCompactNumber(a.total_conversions)}</td><td>${formatCurrency(a.average_acquisition_cost, { compact: false })}</td></tr>`)
      .join("");
    tableEl.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Target Audience</th><th>Campaign Count</th><th>Revenue</th><th>Avg ROI</th><th>Conversions</th><th>Avg Acquisition Cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (err) {
    renderError(tableEl, err, loadAudienceAnalysis);
  }
}

/* ============================================================
   LANGUAGE ANALYSIS
   ============================================================ */

async function loadLanguageAnalysis() {
  const highlightEl = document.getElementById("language-highlights");
  const tableEl = document.getElementById("language-table");
  try {
    const data = await apiFetch("/api/campaign-analytics/languages?" + buildFilterQuery(), { useCache: false });
    const languages = data.languages || [];
    if (!languages.length) {
      renderEmpty(tableEl, "No campaigns match the selected filters.");
      return;
    }
    highlightEl.innerHTML = `<div class="highlight-card" style="max-width:280px;"><div class="highlight-card__label">Highest Average ROI Language</div><div class="highlight-card__value">${data.highest_average_roi_language || "—"}</div></div>`;
    const rows = languages
      .map((l) => `<tr><td>${l.name}</td><td>${formatCompactNumber(l.campaign_count)}</td><td>${formatROI(l.average_roi)}</td><td>${formatCurrency(l.total_revenue)}</td><td>${formatCompactNumber(l.total_conversions)}</td><td>${formatCurrency(l.average_acquisition_cost, { compact: false })}</td></tr>`)
      .join("");
    tableEl.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Language</th><th>Campaign Count</th><th>Avg ROI</th><th>Revenue</th><th>Conversions</th><th>Avg Acquisition Cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  } catch (err) {
    renderError(tableEl, err, loadLanguageAnalysis);
  }
}

/* ============================================================
   ROI DISTRIBUTION
   ============================================================ */

async function loadRoiDistribution() {
  const statsEl = document.getElementById("roi-distribution-stats");
  try {
    const data = await apiFetch("/api/campaign-analytics/roi-distribution?" + buildFilterQuery(), { useCache: false });
    const s = data.stats || {};
    if (!data.histogram || !data.histogram.length) {
      renderEmpty(statsEl, "No campaigns match the selected filters.");
      return;
    }
    statsEl.innerHTML = `
      <div class="card"><div class="card__label">Median ROI</div><div class="card__value">${formatROI(s.median_roi)}</div></div>
      <div class="card"><div class="card__label">Average ROI</div><div class="card__value">${formatROI(s.average_roi)}</div></div>
      <div class="card"><div class="card__label">Min / Max ROI</div><div class="card__value" style="font-size:16px;">${formatROI(s.min_roi)} / ${formatROI(s.max_roi)}</div></div>
      <div class="card"><div class="card__label">ROI &gt; 1 / &gt; 2 / &lt; 0</div><div class="card__value" style="font-size:14px;">${s.pct_roi_gt_1}% / ${s.pct_roi_gt_2}% / ${s.pct_roi_lt_0}%</div></div>
    `;
    renderChartSafely("chart-roi-histogram", () => {
      const safeBins = (data.histogram || []).filter(
        (b) => typeof b.bin_start === "number" && Number.isFinite(b.bin_start) && Number.isFinite(Number(b.count))
      );
      return new Chart(document.getElementById("chart-roi-histogram"), {
        type: "bar",
        data: {
          labels: safeBins.map((b) => b.bin_start.toFixed(1)),
          datasets: [{ data: safeBins.map((b) => Number(b.count) || 0), backgroundColor: CHART_COLORS.blue, borderRadius: 2 }],
        },
        options: { ...baseChartOptions((v) => formatCompactNumber(v)), plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => formatCompactNumber(ctx.parsed.y) + " campaigns" } } } },
      });
    });
  } catch (err) {
    renderError(statsEl, err, loadRoiDistribution);
  }
}

/* ============================================================
   PERFORMANCE TIERS
   ============================================================ */

const TIER_COLORS = { Negative: "#FF6B6B", "Low Return": "#F0B429", "Moderate Return": "#4C8DFF", "Strong Return": "#9C7CFF", "High Return": "#2FD9C0" };

async function loadPerformanceTiers() {
  const el = document.getElementById("performance-tiers-content");
  try {
    const data = await apiFetch("/api/campaign-analytics/performance-tiers?" + buildFilterQuery(), { useCache: false });
    document.getElementById("performance-tiers-title").textContent = data.label || "Illustrative ROI Performance Bands";
    const tiers = data.tiers || [];
    if (!tiers.length) {
      renderEmpty(el, "No campaigns match the selected filters.");
      return;
    }
    el.innerHTML = tiers
      .map((t) => `
      <div class="tier-bar-row">
        <div>${t.tier} <span style="color:var(--text-faint); font-size:11px;">(${t.range})</span></div>
        <div class="tier-bar-track"><div class="tier-bar-fill" style="width:${t.percentage || 0}%; background:${TIER_COLORS[t.tier] || CHART_COLORS.blue};"></div></div>
        <div>${formatCompactNumber(t.count)}</div>
        <div>${t.percentage}%</div>
      </div>`)
      .join("");
  } catch (err) {
    renderError(el, err, loadPerformanceTiers);
  }
}

/* ============================================================
   TOP / UNDERPERFORMING CAMPAIGNS
   ============================================================ */

async function loadTopCampaigns() {
  const el = document.getElementById("top-campaigns-table");
  renderLoading(el, "Loading…");
  try {
    const data = await apiFetch(
      `/api/campaign-analytics/top-campaigns?metric=${state.topMetric}&limit=${state.topLimit}&${buildFilterQuery()}`,
      { useCache: false }
    );
    renderRankedTable(el, data.results, "No campaigns match the selected filters.");
  } catch (err) {
    renderError(el, err, loadTopCampaigns);
  }
}

async function loadUnderperforming() {
  const el = document.getElementById("underperforming-table");
  renderLoading(el, "Loading…");
  try {
    const data = await apiFetch(
      `/api/campaign-analytics/underperforming?metric=${state.underMetric}&limit=${state.underLimit}&${buildFilterQuery()}`,
      { useCache: false }
    );
    renderRankedTable(el, data.results, "No campaigns match the selected filters.");
  } catch (err) {
    renderError(el, err, loadUnderperforming);
  }
}

function renderRankedTable(el, results, emptyMsg) {
  if (!results || !results.length) {
    renderEmpty(el, emptyMsg);
    return;
  }
  const rows = results
    .map((r) => {
      const roiClass = r.ROI > 1 ? "roi-badge--positive" : r.ROI >= 0 ? "roi-badge--neutral" : "roi-badge--negative";
      return `
      <tr>
        <td>${r.Campaign_ID ?? "—"}</td>
        <td>${r.Campaign_Type ?? "—"}</td>
        <td>${r.Channel_Used ?? "—"}</td>
        <td>${r.Target_Audience ?? "—"}</td>
        <td>${r.Customer_Segment ?? "—"}</td>
        <td><span class="roi-badge ${roiClass}">${formatROI(r.ROI)}</span></td>
        <td>${formatCurrency(r.Revenue, { compact: false })}</td>
        <td>${formatCompactNumber(r.Conversions)}</td>
        <td>${formatCurrency(r.Acquisition_Cost, { compact: false })}</td>
      </tr>`;
    })
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>Campaign ID</th><th>Campaign Type</th><th>Channel</th><th>Target Audience</th><th>Customer Segment</th><th>ROI</th><th>Revenue</th><th>Conversions</th><th>Acquisition Cost</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

/* ============================================================
   SHARED HELPERS
   ============================================================ */

function renderGroupTable(el, rows, labelHeader) {
  const tableRows = rows
    .map((r) => `
    <tr>
      <td>${r.name}</td>
      <td>${formatCompactNumber(r.campaign_count)}</td>
      <td>${formatCurrency(r.total_revenue)}</td>
      <td>${formatROI(r.average_roi)}</td>
      <td>${formatROI(r.median_roi)}</td>
      <td>${formatCompactNumber(r.total_conversions)}</td>
      <td>${formatCurrency(r.average_acquisition_cost, { compact: false })}</td>
    </tr>`)
    .join("");
  el.innerHTML = `<div class="table-wrap"><table class="data-table"><thead><tr><th>${labelHeader}</th><th>Campaign Count</th><th>Revenue</th><th>Avg ROI</th><th>Median ROI</th><th>Conversions</th><th>Avg Acquisition Cost</th></tr></thead><tbody>${tableRows}</tbody></table></div>`;
}

function baseChartOptions(tickFormatter) {
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

function renderChartSafely(canvasId, createChartFn) {
  try {
    if (typeof Chart === "undefined") throw new Error("chart_library_unavailable");

    const canvas = document.getElementById(canvasId);
    if (!canvas) throw new Error(`canvas_not_found:${canvasId}`);

    // BUGFIX: destroy any Chart.js instance already attached to this
    // canvas before creating a new one. Without this, a second render
    // pass on the same canvas (e.g. from an overlapping refresh, or a
    // future re-filter) throws Chart.js's "Canvas is already in use"
    // error, which this function's try/catch then reported as
    // "Chart could not be rendered."
    const existing = Chart.getChart ? Chart.getChart(canvas) : null;
    if (existing) existing.destroy();

    createChartFn();
  } catch (err) {
    const canvas = document.getElementById(canvasId);
    if (canvas && canvas.parentElement) {
      canvas.parentElement.innerHTML = '<div class="state state--empty">Chart could not be rendered.</div>';
    }
  }
}

/**
 * Coerce a raw array of {label, value} style chart inputs into valid,
 * finite JavaScript numbers, dropping any entry whose value is
 * null/undefined/NaN/non-numeric rather than passing it to Chart.js.
 * Used by the chart-building code below so a single bad/missing value
 * in an API response can't blank out an entire chart.
 */
function toSafeChartSeries(items, labelFn, valueFn) {
  const labels = [];
  const values = [];
  (items || []).forEach((item) => {
    const rawValue = valueFn(item);
    const numericValue = typeof rawValue === "number" ? rawValue : Number(rawValue);
    if (rawValue === null || rawValue === undefined || Number.isNaN(numericValue) || !Number.isFinite(numericValue)) {
      return; // skip invalid entries rather than feeding NaN/undefined to Chart.js
    }
    labels.push(labelFn(item));
    values.push(numericValue);
  });
  return { labels, values };
}
