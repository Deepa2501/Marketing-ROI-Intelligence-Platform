"""
Executive Decision Center service layer (Phase 9).

This module computes NOTHING that another service doesn't already
compute — it composes analytics_service, campaign_analytics_service,
statistics_service, recommendation_service, and ml_service into one
management-level summary. No new CSV loading, no new statistical
calculations duplicated, no invented numbers.

Evidence discipline matches Phase 8 exactly:
- OBSERVED    = read directly from historical campaign data.
- PREDICTIVE  = read from the trained ROI model.
- EXPERIMENTAL = read from the A/B test result.
No recommendation, priority, or risk item here asserts causation.
"""

import math

from backend.services import analytics_service
from backend.services import campaign_analytics_service as cas
from backend.services import recommendation_service as rs
from backend.services import statistics_service
from backend.services.ml_service import ModelUnavailableError, get_metadata

# ============================================================
# DOCUMENTED THRESHOLDS
# ============================================================
# Negative ROI:  ROI < 0
# Positive ROI:  ROI >= 0
# High ROI:      ROI >= 2  — reuses the SAME boundary already
#                established by campaign_analytics_service's
#                "Illustrative ROI Performance Bands" ("Strong Return"
#                starts at 2), so this isn't a new arbitrary number —
#                it's the threshold this project already documents and
#                displays elsewhere.
HIGH_ROI_THRESHOLD = 2.0


def _pick_best(rows, name_key):
    """Return the row with the highest average_roi, or None."""
    if not rows:
        return None
    return max(rows, key=lambda r: r.get("average_roi") if r.get("average_roi") is not None else -math.inf)


def get_portfolio_kpis(df):
    """Reuses analytics_service.get_summary directly — no duplicate
    aggregation logic.
    """
    return analytics_service.get_summary(df)


def get_portfolio_interpretation(df):
    """Positive/negative/high-ROI campaign shares, reusing the existing
    ROI-distribution and performance-tier calculations rather than
    recomputing them.
    """
    if df.empty:
        return {
            "positive_roi_campaign_percentage": None,
            "negative_roi_campaign_percentage": None,
            "high_roi_campaign_percentage": None,
            "thresholds": {
                "negative_roi": "ROI < 0",
                "positive_roi": "ROI >= 0",
                "high_roi": f"ROI >= {HIGH_ROI_THRESHOLD} (matches this project's existing 'Strong Return' band)",
            },
        }

    dist = cas.get_roi_distribution(df)
    negative_pct = dist.get("stats", {}).get("pct_roi_lt_0")
    positive_pct = round(100 - negative_pct, 2) if negative_pct is not None else None

    high_roi_count = int((df["ROI"] >= HIGH_ROI_THRESHOLD).sum())
    high_roi_pct = round(100 * high_roi_count / len(df), 2)

    return {
        "positive_roi_campaign_percentage": positive_pct,
        "negative_roi_campaign_percentage": negative_pct,
        "high_roi_campaign_percentage": high_roi_pct,
        "thresholds": {
            "negative_roi": "ROI < 0",
            "positive_roi": "ROI >= 0",
            "high_roi": f"ROI >= {HIGH_ROI_THRESHOLD} (matches this project's existing 'Strong Return' band)",
        },
    }


def get_top_observed_performers(df):
    """Best campaign type / customer segment / target audience /
    channel group by observed average ROI. Every figure comes from the
    existing group-aggregation functions.
    """
    best_type = _pick_best(analytics_service.get_campaign_types(df), "name")
    best_segment = _pick_best(analytics_service.get_customer_segments(df), "name")
    best_audience = _pick_best(cas.get_audience_performance(df).get("audiences", []), "name")
    best_channel = _pick_best(cas.get_channel_performance(df, limit=100).get("channels", []), "recorded_channel_combination")

    def _shape(row, name_key):
        if not row:
            return None
        return {
            "group_name": row.get(name_key) or row.get("name") or row.get("recorded_channel_combination"),
            "average_roi": row.get("average_roi"),
            "campaign_count": row.get("campaign_count"),
            "total_revenue": row.get("total_revenue"),
            "total_conversions": row.get("total_conversions"),
            "note": "Highest observed average ROI among evaluated groups.",
        }

    return {
        "best_campaign_type": _shape(best_type, "name"),
        "best_customer_segment": _shape(best_segment, "name"),
        "best_target_audience": _shape(best_audience, "name"),
        "best_channel_group": _shape(best_channel, "recorded_channel_combination"),
    }


# ============================================================
# STRATEGIC PRIORITIES — reuses recommendation_service builders
# ============================================================


def get_strategic_priorities(df, metadata_path):
    priorities = []

    best_type = rs.get_top_campaign_opportunity(df)
    if best_type:
        priorities.append(
            {
                "priority": len(priorities) + 1,
                "title": best_type["title"],
                "category": "Performance",
                "importance": "HIGH" if best_type["confidence"] in ("High", "Medium") else "MEDIUM",
                "recommendation": best_type["recommendation"],
                "evidence": best_type["why"]["evidence"],
                "caution": best_type["why"]["caution"],
            }
        )

    best_segment = rs.get_segment_opportunity(df)
    if best_segment:
        priorities.append(
            {
                "priority": len(priorities) + 1,
                "title": best_segment["title"],
                "category": "Performance",
                "importance": "HIGH" if best_segment["confidence"] in ("High", "Medium") else "MEDIUM",
                "recommendation": best_segment["recommendation"],
                "evidence": best_segment["why"]["evidence"],
                "caution": best_segment["why"]["caution"],
            }
        )

    risk_items = rs.get_risk_flags(df, metadata_path)
    negative_roi_risk = next((r for r in risk_items if any(f["flag"] == "NEGATIVE ROI" for f in r.get("risk_flags", []))), None)
    if negative_roi_risk:
        priorities.append(
            {
                "priority": len(priorities) + 1,
                "title": negative_roi_risk["title"],
                "category": "Risk",
                "importance": negative_roi_risk["risk_level"].upper(),
                "recommendation": "Review campaigns with negative observed ROI before scaling budget in affected areas.",
                "evidence": negative_roi_risk["why"]["evidence"],
                "caution": negative_roi_risk["why"]["caution"],
            }
        )

    budget_signal = rs.get_budget_cost_signal(df, metadata_path)
    if budget_signal:
        priorities.append(
            {
                "priority": len(priorities) + 1,
                "title": budget_signal["title"],
                "category": "Cost",
                "importance": "MEDIUM",
                "recommendation": budget_signal["recommendation"],
                "evidence": budget_signal["why"]["evidence"],
                "caution": budget_signal["why"]["caution"],
            }
        )

    ab_signal = rs.get_ab_test_signal(df)
    if ab_signal:
        significant = ab_signal["confidence"] == "High"
        priorities.append(
            {
                "priority": len(priorities) + 1,
                "title": ab_signal["title"] + (" — Statistically Significant" if significant else " — Statistically Inconclusive"),
                "category": "Experiment",
                "importance": "MEDIUM" if significant else "LOW",
                "recommendation": ab_signal["recommendation"],
                "evidence": ab_signal["why"]["evidence"],
                "caution": ab_signal["why"]["caution"],
            }
        )

    return priorities[:5]


# ============================================================
# OPPORTUNITY SCORECARD — reuses recommendation_service builders
# ============================================================


def get_opportunity_scorecard(df):
    opportunities = []
    overall_avg_roi = df["ROI"].mean() if not df.empty else None

    builders = [
        ("Campaign Type", rs.get_top_campaign_opportunity(df)),
        ("Customer Segment", rs.get_segment_opportunity(df)),
        ("Target Audience", rs.get_audience_opportunity(df)),
        ("Channel Group", rs.get_channel_opportunity(df)),
    ]

    for dimension, rec in builders:
        if not rec:
            continue
        avg_roi = rec["supporting_metrics"]["average_roi"]
        comparison = (
            f"{round(((avg_roi - overall_avg_roi) / overall_avg_roi) * 100, 1)}% above portfolio average ROI"
            if overall_avg_roi
            else None
        )
        opportunities.append(
            {
                "opportunity_name": rec["title"].split(": ", 1)[-1],
                "dimension": dimension,
                "observed_average_roi": avg_roi,
                "comparison_to_portfolio_average": comparison,
                "campaign_count": rec["supporting_metrics"]["campaign_count"],
                "evidence_basis": rec["evidence_basis"],
                "confidence": rec["confidence"],
                "caution": rec["why"]["caution"],
            }
        )

    return opportunities[:5]


# ============================================================
# EXECUTIVE RISK MONITOR
# ============================================================


def get_executive_risks(df, metadata_path):
    risks = []
    for item in rs.get_risk_flags(df, metadata_path):
        risks.append(
            {
                "risk_title": item["title"],
                "severity": item["risk_level"],
                "metric": item["supporting_metrics"],
                "interpretation": item["recommendation"],
                "management_action": item["why"]["interpretation"],
                "evidence_basis": item["evidence_basis"],
            }
        )

    ab_signal = rs.get_ab_test_signal(df)
    if ab_signal and ab_signal["confidence"] != "High":
        risks.append(
            {
                "risk_title": "Statistical Uncertainty: " + ab_signal["title"],
                "severity": "Low",
                "metric": ab_signal["supporting_metrics"],
                "interpretation": ab_signal["recommendation"],
                "management_action": "Do not reallocate budget based on this comparison alone; treat as statistically inconclusive.",
                "evidence_basis": "EXPERIMENTAL",
            }
        )

    return risks


# ============================================================
# DECISION GUARDRAILS
# ============================================================


def get_decision_guardrails(metadata_path):
    model_note = None
    try:
        metadata = get_metadata(metadata_path)
        model_note = metadata.get("dominant_feature_note")
    except ModelUnavailableError:
        pass

    return [
        "Observed performance describes historical association, not proven causation.",
        "Model predictions (PREDICTIVE evidence) are decision-support estimates, not guarantees of future ROI.",
        "Experimental evidence (A/B testing) should be reviewed before major budget reallocation — observed or predictive signals alone are not sufficient.",
        model_note or "Acquisition Cost is a dominant signal in the current early-stage ROI model.",
        "Groups with a small number of observed campaigns should be treated with additional caution regardless of their apparent performance.",
    ]


# ============================================================
# PORTFOLIO HEALTH SCORE
# ============================================================
#
# Documented, transparent formula — every component is itself already
# a 0-100 percentage (or normalized to one using the DATASET'S OWN
# observed range, never an arbitrary constant):
#
#   1. Positive ROI Rate      (weight 30%) = % of campaigns with ROI >= 0
#   2. Low Negative Exposure  (weight 25%) = 100 - (% of campaigns with ROI < 0)
#   3. High-ROI Campaign Rate (weight 20%) = % of campaigns with ROI >= 2
#      (same "Strong Return" boundary used elsewhere in this project)
#   4. Conversion Rate        (weight 15%) = (total conversions / total leads) * 100, capped at 100
#   5. Engagement Normalized  (weight 10%) = (average engagement score / the
#      DATASET'S OWN observed maximum engagement score) * 100
#
# Weights sum to 100% and were chosen to weight realized ROI outcomes
# (components 1-3, 75% combined) above secondary funnel/engagement
# signals (components 4-5, 25% combined). This is an analytical
# summary score, not a validated financial health metric.
HEALTH_SCORE_WEIGHTS = {
    "positive_roi_rate": 0.30,
    "low_negative_exposure": 0.25,
    "high_roi_rate": 0.20,
    "conversion_rate": 0.15,
    "engagement_normalized": 0.10,
}

HEALTH_SCORE_BANDS = [
    (80, "Strong"),
    (60, "Stable"),
    (40, "Watch"),
    (0, "At Risk"),
]


def _health_label(score):
    for threshold, label in HEALTH_SCORE_BANDS:
        if score >= threshold:
            return label
    return "At Risk"


def get_portfolio_health_score(df):
    if df.empty:
        return {"score": None, "label": "Unavailable", "components": [], "note": "No data available to compute a score."}

    interpretation = get_portfolio_interpretation(df)
    positive_roi_rate = interpretation["positive_roi_campaign_percentage"] or 0
    negative_roi_rate = interpretation["negative_roi_campaign_percentage"] or 0
    high_roi_rate = interpretation["high_roi_campaign_percentage"] or 0

    low_negative_exposure = round(100 - negative_roi_rate, 2)

    leads_total = df["Leads"].sum() if "Leads" in df.columns else 0
    conversion_rate = min(100.0, round(100 * df["Conversions"].sum() / leads_total, 2)) if leads_total else 0

    if "Engagement_Score" in df.columns and df["Engagement_Score"].max() > 0:
        engagement_normalized = min(100.0, round(100 * df["Engagement_Score"].mean() / df["Engagement_Score"].max(), 2))
    else:
        engagement_normalized = 0

    components = [
        {"component": "Positive ROI Rate", "value": positive_roi_rate, "weight": HEALTH_SCORE_WEIGHTS["positive_roi_rate"]},
        {"component": "Low Negative ROI Exposure", "value": low_negative_exposure, "weight": HEALTH_SCORE_WEIGHTS["low_negative_exposure"]},
        {"component": "High-ROI Campaign Rate (ROI >= 2)", "value": high_roi_rate, "weight": HEALTH_SCORE_WEIGHTS["high_roi_rate"]},
        {"component": "Conversion Rate", "value": conversion_rate, "weight": HEALTH_SCORE_WEIGHTS["conversion_rate"]},
        {"component": "Engagement (normalized to dataset max)", "value": engagement_normalized, "weight": HEALTH_SCORE_WEIGHTS["engagement_normalized"]},
    ]

    score = sum(c["value"] * c["weight"] for c in components)
    score = round(score, 1)

    return {
        "score": score,
        "label": "Analytical Portfolio Health Score",
        "status": _health_label(score),
        "status_bands": {"Strong": ">= 80", "Stable": ">= 60", "Watch": ">= 40", "At Risk": "< 40"},
        "components": components,
        "note": "This is an analytical summary score derived from observed portfolio data — not a statistically validated financial or business health metric.",
    }


# ============================================================
# CHARTS DATA (lightweight — for the 2-3 charts specified)
# ============================================================


def get_executive_charts(df):
    types = analytics_service.get_campaign_types(df)
    segments = analytics_service.get_customer_segments(df)
    dist = cas.get_roi_distribution(df)
    interpretation = get_portfolio_interpretation(df)

    return {
        "roi_by_campaign_type": [{"name": t["name"], "average_roi": t["average_roi"]} for t in types],
        "roi_by_customer_segment": [{"name": s["name"], "average_roi": s["average_roi"]} for s in segments],
        "roi_exposure": {
            "positive_roi_campaign_percentage": interpretation["positive_roi_campaign_percentage"],
            "negative_roi_campaign_percentage": interpretation["negative_roi_campaign_percentage"],
        },
    }


# ============================================================
# SNAPSHOT (4 concise cards)
# ============================================================


def get_executive_snapshot(df, metadata_path):
    performers = get_top_observed_performers(df)
    strongest = performers.get("best_customer_segment") or performers.get("best_campaign_type")

    risks = rs.get_risk_flags(df, metadata_path)
    biggest_risk = max(risks, key=lambda r: {"High": 3, "Medium": 2, "Low": 1}.get(r["risk_level"], 0)) if risks else None

    budget_signal = rs.get_budget_cost_signal(df, metadata_path)
    ab_signal = rs.get_ab_test_signal(df)

    return {
        "strongest_observed_performance": {
            "title": "Strongest Observed Performance",
            "metric": f"{strongest['group_name']}: {strongest['average_roi']}x avg ROI" if strongest else "Not available",
            "evidence_basis": "OBSERVED",
            "interpretation": "Highest observed average ROI among evaluated groups in the current dataset.",
        }
        if strongest
        else None,
        "biggest_risk": {
            "title": "Biggest Risk",
            "metric": biggest_risk["title"] if biggest_risk else "None flagged",
            "evidence_basis": biggest_risk.get("evidence_basis", "OBSERVED") if biggest_risk else "OBSERVED",
            "interpretation": biggest_risk["recommendation"] if biggest_risk else "No significant risk flags detected.",
        },
        "key_cost_signal": {
            "title": "Key Cost Signal",
            "metric": f"r={budget_signal['supporting_metrics']['acquisition_cost_roi_correlation']}" if budget_signal else "Not available",
            "evidence_basis": budget_signal["evidence_basis"] if budget_signal else "OBSERVED",
            "interpretation": budget_signal["reason"] if budget_signal else "Not available.",
        },
        "most_important_experiment": {
            "title": "Most Important Experiment",
            "metric": ab_signal["title"] if ab_signal else "Not available",
            "evidence_basis": "EXPERIMENTAL",
            "interpretation": ab_signal["reason"] if ab_signal else "No experiment data available.",
        },
    }


def get_executive_summary(df, metadata_path):
    return {
        "status": "success",
        "portfolio_health": get_portfolio_health_score(df),
        "kpis": get_portfolio_kpis(df),
        "portfolio_interpretation": get_portfolio_interpretation(df),
        "top_observed_performers": get_top_observed_performers(df),
        "snapshot": get_executive_snapshot(df, metadata_path),
        "strategic_priorities": get_strategic_priorities(df, metadata_path),
        "opportunities": get_opportunity_scorecard(df),
        "risks": get_executive_risks(df, metadata_path),
        "charts": get_executive_charts(df),
        "decision_guardrails": get_decision_guardrails(metadata_path),
    }
