/*
 * ab-testing.js — Page 4: A/B Testing.
 * The statistical conclusion (significant / not significant) and the
 * business recommendation text both come directly from GET /api/ab-test —
 * this page never generates its own conclusion.
 */

document.addEventListener("DOMContentLoaded", loadAbTest);

async function loadAbTest() {
  const el = document.getElementById("ab-test-content");
  renderLoading(el, "Loading experiment results…");

  try {
    const data = await apiFetch("/api/ab-test");
    render(el, data);
  } catch (err) {
    renderError(el, err, loadAbTest);
  }
}

function render(el, data) {
  const significant = data.welchs_t_test.significant_at_0_05;
  const bannerClass = significant ? "experiment-banner--significant" : "experiment-banner--not-significant";
  const bannerTitle = significant
    ? "Statistically significant difference detected."
    : "No statistically significant difference detected.";

  el.innerHTML = `
    <div class="experiment-banner ${bannerClass}">
      <div class="experiment-banner__title">${bannerTitle}</div>
      <div class="experiment-banner__sub">
        Welch's t-test comparing average ROI between ${data.group_a.label} and ${data.group_b.label}.
      </div>
    </div>

    <div class="group-compare">
      <div class="group-card">
        <div class="group-card__name">${data.group_a.label}</div>
        <div class="group-card__stat"><span>Average ROI</span><strong>${formatROI(data.group_a.average_roi)}</strong></div>
        <div class="group-card__stat"><span>Median ROI</span><strong>${formatROI(data.group_a.median_roi)}</strong></div>
        <div class="group-card__stat"><span>Campaign Count</span><strong>${formatCompactNumber(data.group_a.campaign_count)}</strong></div>
      </div>
      <div class="group-compare__vs">VS</div>
      <div class="group-card">
        <div class="group-card__name">${data.group_b.label}</div>
        <div class="group-card__stat"><span>Average ROI</span><strong>${formatROI(data.group_b.average_roi)}</strong></div>
        <div class="group-card__stat"><span>Median ROI</span><strong>${formatROI(data.group_b.median_roi)}</strong></div>
        <div class="group-card__stat"><span>Campaign Count</span><strong>${formatCompactNumber(data.group_b.campaign_count)}</strong></div>
      </div>
    </div>

    <div class="grid grid--2">
      <section class="panel" style="margin-bottom: 0;">
        <h2 class="panel__title">Welch's t-test</h2>
        <div class="group-card__stat"><span>t-statistic</span><strong>${formatNumber(data.welchs_t_test.t_statistic, 4)}</strong></div>
        <div class="group-card__stat"><span>p-value</span><strong>${formatNumber(data.welchs_t_test.p_value, 6)}</strong></div>
        <div class="group-card__stat"><span>Significant at 0.05</span><strong><span class="sig-badge ${significant ? "sig-badge--yes" : "sig-badge--no"}">${significant ? "Yes" : "No"}</span></strong></div>
      </section>

      <section class="panel" style="margin-bottom: 0;">
        <h2 class="panel__title">Effect Size</h2>
        <div class="group-card__stat"><span>Cohen's d</span><strong>${formatNumber(data.effect_size.cohens_d, 4)}</strong></div>
        <div class="group-card__stat"><span>Interpretation</span><strong style="text-transform: capitalize;">${data.effect_size.interpretation}</strong></div>
      </section>
    </div>

    <section class="panel">
      <h2 class="panel__title">Business Recommendation</h2>
      <p class="panel__text">${data.business_recommendation}</p>
    </section>
  `;
}
