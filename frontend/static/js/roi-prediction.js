/*
 * roi-prediction.js — Page 5: ROI Prediction.
 * Dropdown options and the prediction itself all come from the API —
 * nothing here is a fixed/fake list or a fabricated prediction.
 */

document.addEventListener("DOMContentLoaded", () => {
  populateDropdowns();
  bindForm();
});

async function populateDropdowns() {
  try {
    const [types, segments, sample] = await Promise.all([
      apiFetch("/api/campaign-types"),
      apiFetch("/api/customer-segments"),
      apiFetch("/api/campaigns?page=1&page_size=500"),
    ]);

    fillSelect(document.getElementById("campaign_type"), types.campaign_types.map((t) => t.name));
    fillSelect(document.getElementById("customer_segment"), segments.customer_segments.map((s) => s.name));

    const audiences = [...new Set((sample.results || []).map((r) => r.Target_Audience).filter(Boolean))].sort();
    const languages = [...new Set((sample.results || []).map((r) => r.Language).filter(Boolean))].sort();
    fillSelect(document.getElementById("target_audience"), audiences);
    fillSelect(document.getElementById("language"), languages);
  } catch (err) {
    // Form still works if a user types values manually where inputs exist;
    // selects will just be empty if this fails.
  }
}

function fillSelect(select, values) {
  select.innerHTML = "";
  values.forEach((v) => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  });
}

function bindForm() {
  const form = document.getElementById("predict-form");
  const resultEmpty = document.getElementById("result-empty");
  const resultContent = document.getElementById("result-content");
  const formError = document.getElementById("form-error");
  const predictBtn = document.getElementById("predict-btn");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formError.hidden = true;
    predictBtn.disabled = true;
    predictBtn.textContent = "Predicting…";

    const payload = {
      Campaign_Type: form.Campaign_Type.value,
      Target_Audience: form.Target_Audience.value,
      Duration: Number(form.Duration.value),
      Channel_Used: form.Channel_Used.value,
      Language: form.Language.value,
      Customer_Segment: form.Customer_Segment.value,
      Acquisition_Cost: Number(form.Acquisition_Cost.value),
    };

    try {
      const data = await apiFetch("/api/predict-roi", { method: "POST", body: payload, useCache: false });
      renderResult(data);
      resultEmpty.hidden = true;
      resultContent.hidden = false;

      // Phase 6: fetch prediction context (input echo, primary driver,
      // error-context label) from the new explain-prediction endpoint.
      // This is an ADDITIONAL call — it never replaces or blocks the
      // existing predict-roi result above.
      loadPredictionContext(payload);
    } catch (err) {
      formError.textContent = err.friendlyMessage || "Prediction failed.";
      formError.hidden = false;
      resultEmpty.hidden = false;
      resultContent.hidden = true;
    } finally {
      predictBtn.disabled = false;
      predictBtn.textContent = "Predict ROI";
    }
  });
}

function renderResult(data) {
  document.getElementById("result-roi").textContent = formatROI(data.predicted_roi);
  document.getElementById("result-error-note").textContent = data.estimated_error_note || "";
  document.getElementById("result-model").textContent = data.model || "—";
  document.getElementById("result-type").textContent = data.prediction_type || "—";
  document.getElementById("result-r2").textContent = data.model_r2 != null ? formatPercent(data.model_r2) : "—";
  document.getElementById("result-mae").textContent = data.model_mae != null ? formatNumber(data.model_mae, 4) : "—";
  document.getElementById("result-caveat").textContent = data.caveat || "";

  renderGauge(data.predicted_roi);
}

/**
 * Illustrative decision-support categorization only — explicitly not
 * presented as a statistically optimal threshold.
 */
function renderGauge(roi) {
  const marker = document.getElementById("roi-gauge-marker");
  const label = document.getElementById("roi-gauge-label");

  // Map roi onto 0-100% of the gauge track. Track visually spans roughly -1x to 5x.
  const clamped = Math.max(-1, Math.min(5, roi));
  const pct = ((clamped - -1) / (5 - -1)) * 100;
  marker.style.left = pct + "%";

  let category;
  if (roi < 0) category = "Potentially loss-making (illustrative)";
  else if (roi < 1) category = "Low predicted return (illustrative)";
  else if (roi < 3) category = "Moderate predicted return (illustrative)";
  else category = "High predicted return (illustrative)";

  label.textContent = category;
}

/* ============================================================
 * PHASE 6 — Prediction Context (additive).
 * Calls the new POST /api/explain-prediction endpoint (which reuses
 * the same cached model as /api/predict-roi — not a second model)
 * to show the input values used, the primary model driver, and an
 * explicit "not a confidence interval" error-context label.
 * Failure here never affects the main prediction result above.
 * ============================================================ */

async function loadPredictionContext(payload) {
  const panel = document.getElementById("prediction-context-panel");
  try {
    const data = await apiFetch("/api/explain-prediction", { method: "POST", body: payload, useCache: false });

    const inputs = data.prediction_context.inputs;
    const grid = document.getElementById("prediction-context-grid");
    grid.innerHTML = [
      ["Campaign Type", inputs.Campaign_Type],
      ["Target Audience", inputs.Target_Audience],
      ["Duration", inputs.Duration + " days"],
      ["Channel", inputs.Channel_Used],
      ["Language", inputs.Language],
      ["Customer Segment", inputs.Customer_Segment],
      ["Acquisition Cost", formatCurrency(inputs.Acquisition_Cost, { compact: false })],
    ]
      .map(([label, value]) => `<div class="prediction-context-grid__row"><span>${label}</span><strong>${value}</strong></div>`)
      .join("");

    document.getElementById("primary-model-driver").textContent = data.primary_model_driver || "—";
    document.getElementById("primary-model-driver-disclaimer").textContent = data.primary_model_driver_disclaimer || "";
    document.getElementById("error-context-label").textContent = data.error_context
      ? `${data.error_context.label} ${data.error_context.note || ""}`
      : "";

    panel.hidden = false;
  } catch (err) {
    // Context is a supplementary panel — hide it quietly rather than
    // showing an error banner that would compete with the main result.
    panel.hidden = true;
  }
}
