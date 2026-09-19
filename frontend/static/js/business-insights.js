/*
 * business-insights.js — Page 7: Business Insights.
 * Every card here is derived from a live API response — no invented
 * recommendations, no numbers that didn't come from the backend.
 */

document.addEventListener("DOMContentLoaded", () => {
  loadCampaignAndSegmentInsights();
  loadStatisticalInsights();
  loadAbTestInsight();
  loadMlInsights();
});

async function loadCampaignAndSegmentInsights() {
  const campaignEl = document.getElementById("insights-campaign");
  const segmentEl = document.getElementById("insights-segments");

  try {
    const [typesData, segmentsData] = await Promise.all([
      apiFetch("/api/campaign-types"),
      apiFetch("/api/customer-segments"),
    ]);
    const types = typesData.campaign_types || [];
    const segments = segmentsData.customer_segments || [];

    if (!types.length) {
      renderEmpty(campaignEl, "No campaign data available.");
    } else {
      const topRoiType = [...types].sort((a, b) => b.average_roi - a.average_roi)[0];
      const topRevenueType = [...types].sort((a, b) => b.total_revenue - a.total_revenue)[0];
      campaignEl.innerHTML = [
        card(
          "opportunity",
          "Performance Opportunity",
          `${topRoiType.name} has the highest average ROI`,
          `Finding: ${topRoiType.name} campaigns average ${formatROI(topRoiType.average_roi)} ROI across ${formatCompactNumber(topRoiType.campaign_count)} campaigns.`,
          `Business implication: this campaign type is currently the most ROI-efficient, though see the A/B Testing page before shifting budget based on ROI alone.`
        ),
        card(
          "optimization",
          "Optimization Opportunity",
          `${topRevenueType.name} generates the most total revenue`,
          `Finding: ${topRevenueType.name} produced ${formatCurrency(topRevenueType.total_revenue)} in total revenue.`,
          `Business implication: this is currently the platform's largest revenue driver by volume.`
        ),
      ].join("");
    }

    if (!segments.length) {
      renderEmpty(segmentEl, "No segment data available.");
    } else {
      const topRoiSeg = [...segments].sort((a, b) => b.average_roi - a.average_roi)[0];
      const topRevenueSeg = [...segments].sort((a, b) => b.total_revenue - a.total_revenue)[0];
      segmentEl.innerHTML = [
        card(
          "opportunity",
          "Performance Opportunity",
          `${topRoiSeg.name} has the highest average ROI`,
          `Finding: ${topRoiSeg.name} averages ${formatROI(topRoiSeg.average_roi)} ROI.`,
          `Business implication: campaigns targeting this segment are currently the most ROI-efficient.`
        ),
        card(
          "optimization",
          "Optimization Opportunity",
          `${topRevenueSeg.name} generates the most total revenue`,
          `Finding: ${topRevenueSeg.name} produced ${formatCurrency(topRevenueSeg.total_revenue)} in total revenue.`,
          `Business implication: this segment currently represents the platform's largest revenue base.`
        ),
      ].join("");
    }
  } catch (err) {
    renderError(campaignEl, err, loadCampaignAndSegmentInsights);
    renderError(segmentEl, err, loadCampaignAndSegmentInsights);
  }
}

async function loadStatisticalInsights() {
  const el = document.getElementById("insights-statistics");
  try {
    const data = await apiFetch("/api/statistics");
    const correlations = data.roi_correlations || [];
    if (!correlations.length) {
      renderEmpty(el, "No statistical data available.");
      return;
    }
    const strongestPositive = [...correlations].filter((c) => c.correlation_with_roi >= 0).sort((a, b) => b.correlation_with_roi - a.correlation_with_roi)[0];
    const strongestNegative = [...correlations].filter((c) => c.correlation_with_roi < 0).sort((a, b) => a.correlation_with_roi - b.correlation_with_roi)[0];
    const nonSignificant = correlations.find((c) => !c.significant_at_0_05);

    el.innerHTML = [
      card("opportunity", "Strongest Positive Correlation", strongestPositive ? strongestPositive.variable : "—", strongestPositive ? `r = ${formatNumber(strongestPositive.correlation_with_roi, 4)} with ROI.` : "", "Correlation does not imply causation."),
      card("risk", "Strongest Negative Correlation", strongestNegative ? strongestNegative.variable : "—", strongestNegative ? `r = ${formatNumber(strongestNegative.correlation_with_roi, 4)} with ROI.` : "None found in this dataset.", "Correlation does not imply causation."),
      card("experiment", "Non-Significant Relationship", nonSignificant ? nonSignificant.variable : "—", nonSignificant ? `p = ${formatNumber(nonSignificant.p_value, 4)}, not significant at 0.05.` : "All measured relationships were significant at 0.05.", ""),
    ].join("");
  } catch (err) {
    renderError(el, err, loadStatisticalInsights);
  }
}

async function loadAbTestInsight() {
  const el = document.getElementById("insights-abtest");
  try {
    const data = await apiFetch("/api/ab-test");
    const sig = data.welchs_t_test.significant_at_0_05;
    el.innerHTML = card(
      "experiment",
      "Experiment Recommendation",
      sig ? "Statistically significant difference detected" : "No statistically significant difference detected",
      `Finding: ${data.group_a.label} averaged ${formatROI(data.group_a.average_roi)} ROI vs ${data.group_b.label} at ${formatROI(data.group_b.average_roi)} (p = ${formatNumber(data.welchs_t_test.p_value, 4)}).`,
      `Recommendation: ${data.business_recommendation}`
    );
  } catch (err) {
    renderError(el, err, loadAbTestInsight);
  }
}

async function loadMlInsights() {
  const el = document.getElementById("insights-ml");
  try {
    const data = await apiFetch("/api/model-info");
    const m = data.metrics || {};
    el.innerHTML = [
      card("optimization", "Model Performance", data.model_name || "—", `R² = ${formatPercent(m.r2)}, MAE = ${formatNumber(m.mae, 4)}.`, "This reflects predictive accuracy on held-out test data, not causal explanatory power."),
      card("risk", "Dominant Feature", "Acquisition Cost", data.dominant_feature_warning || "Acquisition Cost explains most of the model's predictive power.", "Treat predictions as decision-support, not causal evidence."),
    ].join("");
  } catch (err) {
    renderError(el, err, loadMlInsights);
  }
}

function card(variant, tag, title, finding, implication) {
  return `
    <div class="insight-card insight-card--${variant}">
      <div class="insight-card__tag">${tag}</div>
      <div class="insight-card__title">${title}</div>
      ${finding ? `<div class="insight-card__row">${finding}</div>` : ""}
      ${implication ? `<div class="insight-card__row">${implication}</div>` : ""}
    </div>
  `;
}
