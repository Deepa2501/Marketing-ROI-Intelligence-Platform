/*
 * api.js — shared fetch helper + formatting utilities.
 * Every page script uses apiFetch() so loading/error handling and
 * response caching behave consistently across the app.
 */

const _responseCache = new Map();

/**
 * Fetch JSON from a Flask API endpoint with basic in-memory caching
 * (per page load) so charts/tables on the same page don't trigger the
 * same request twice. Throws an Error with a friendly `.friendlyMessage`
 * on any failure (network, non-2xx, bad JSON) — callers render that
 * message rather than a raw stack trace.
 */
async function apiFetch(path, { useCache = true, method = "GET", body = null } = {}) {
  const cacheKey = method + " " + path + (body ? JSON.stringify(body) : "");
  if (useCache && method === "GET" && _responseCache.has(cacheKey)) {
    return _responseCache.get(cacheKey);
  }

  let res;
  try {
    res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (networkErr) {
    const err = new Error("network_error");
    err.friendlyMessage = "Could not reach the server. Check your connection and try again.";
    throw err;
  }

  let data = null;
  try {
    data = await res.json();
  } catch (parseErr) {
    const err = new Error("bad_json");
    err.friendlyMessage = "The server returned an unexpected response.";
    throw err;
  }

  if (!res.ok) {
    const err = new Error(data.error || "api_error");
    err.status = res.status;
    err.details = data.details;
    if (res.status === 503) {
      err.friendlyMessage = data.message || "This data source is not connected yet.";
    } else if (res.status === 400) {
      err.friendlyMessage = Array.isArray(data.details) ? data.details.join(" ") : (data.message || "Invalid request.");
    } else {
      err.friendlyMessage = data.message || "Something went wrong loading this data.";
    }
    throw err;
  }

  if (useCache && method === "GET") {
    _responseCache.set(cacheKey, data);
  }
  return data;
}

/* ============================================================
   NUMBER FORMATTING
   ============================================================ */

function formatCurrency(value, { compact = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (compact) {
    if (abs >= 1e9) return "₹" + (value / 1e9).toFixed(2) + "B";
    if (abs >= 1e6) return "₹" + (value / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return "₹" + (value / 1e3).toFixed(2) + "K";
  }
  return "₹" + value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCompactNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e9) return (value / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (value / 1e6).toFixed(2) + "M";
  if (abs >= 1e3) return (value / 1e3).toFixed(2) + "K";
  return value.toLocaleString();
}

function formatROI(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(2) + "x";
}

function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (value * 100).toFixed(digits) + "%";
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/* ============================================================
   SHARED STATE RENDER HELPERS
   ============================================================ */

function renderLoading(el, message = "Loading…") {
  el.innerHTML = `<div class="state state--loading">${message}</div>`;
}

function renderError(el, err, retryFn) {
  const message = err && err.friendlyMessage ? err.friendlyMessage : "Something went wrong.";
  el.innerHTML = `
    <div class="state state--error">
      <div class="state__message">${message}</div>
      ${retryFn ? '<button class="state__retry-btn" type="button">Retry</button>' : ""}
    </div>
  `;
  if (retryFn) {
    el.querySelector(".state__retry-btn").addEventListener("click", retryFn);
  }
}

function renderEmpty(el, message = "No data found.") {
  el.innerHTML = `<div class="state state--empty">${message}</div>`;
}

/* ============================================================
   CHART.JS SHARED THEME
   ============================================================ */

const CHART_COLORS = {
  blue: "#4C8DFF",
  violet: "#9C7CFF",
  teal: "#2FD9C0",
  amber: "#F0B429",
  grid: "#1B1F2B",
  text: "#8A90A3",
};

function applyChartDefaults() {
  if (typeof Chart === "undefined") return;
  Chart.defaults.color = CHART_COLORS.text;
  Chart.defaults.borderColor = CHART_COLORS.grid;
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
}
