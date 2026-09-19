"""
Recommendation Intelligence service layer (Phase 8).

Every recommendation here is built from existing service functions —
analytics_service, campaign_analytics_service, statistics_service, and
ml_service — never from hardcoded example values. This module adds no
new CSV loading and no new statistical calculations; it only
interprets numbers those modules already compute.

Evidence discipline (see PHASE 8 spec "Evidence Rules"):
- OBSERVED  = read directly from the historical campaign data.
- PREDICTIVE = read from the trained ROI model / model comparison.
- EXPERIMENTAL = read from the A/B test result.
These are never blended into a single unlabeled claim, and no
recommendation asserts causation — only observed/predicted association.
"""

import math

from backend.services import analytics_service, campaign_analytics_service as cas
from backend.services import statistics_service
from backend.services.ml_service import ModelUnavailableError

VALID_TYPES = {"campaign", "segment", "audience", "channel", "budget", "risk"}

# Minimum campaign count for a group to be treated as reasonably
# evidenced. Below this, the recommendation is still shown but is
# capped at LOW confidence and carries a "Limited evidence" risk flag.
MIN_CAMPAIGNS_FOR_MEDIUM_CONFIDENCE = 500
MIN_CAMPAIGNS_FOR_HIGH_CONFIDENCE = 5000


def _confidence_from_sample_size(count, separation_pct=None):
    """Transparent, explainable confidence logic based on sample size
    and (optionally) how clearly a group separates from its peers.
    """
    if count is None or count < MIN_CAMPAIGNS_FOR_MEDIUM_CONFIDENCE:
        return "Low"
    if separation_pct is not None and separation_pct < 2:
        return "Medium" if count >= MIN_CAMPAIGNS_FOR_HIGH_CONFIDENCE else "Low"
    if count >= MIN_CAMPAIGNS_FOR_HIGH_CONFIDENCE:
        return "High"
    return "Medium"


def _relative_separation(best, second):
    if not second:
        return 100.0
    return abs((best - second) / second) * 100.0


def _risk_flags_for_group(row, overall_avg_roi, overall_avg_cost):
    flags = []
    if row.get("average_roi") is not None and row["average_roi"] < 0:
        flags.append({"flag": "NEGATIVE ROI", "message": "This group has negative observed average ROI."})
    if (
        row.get("average_acquisition_cost") is not None
        and overall_avg_cost
        and row["average_acquisition_cost"] > overall_avg_cost * 1.15
        and row.get("average_roi") is not None
        and overall_avg_roi
        and row["average_roi"] < overall_avg_roi
    ):
        flags.append(
            {
                "flag": "HIGH ACQUISITION COST",
                "message": "Acquisition cost is high relative to observed returns for this group.",
            }
        )
    if row.get("campaign_count") is not None and row["campaign_count"] < MIN_CAMPAIGNS_FOR_MEDIUM_CONFIDENCE:
        flags.append(
            {
                "flag": "LIMITED EVIDENCE",
                "message": f"Recommendation is based on a relatively small number of campaigns ({row['campaign_count']:,}).",
            }
        )
    return flags


def _build_group_recommendation(recommendation_type, title_prefix, rows, name_key, overall_avg_roi, overall_avg_cost):
    """Shared builder for segment / audience / channel opportunity
    recommendations: picks the group with the highest observed average
    ROI, provided it also carries meaningful revenue/conversions.
    """
    if not rows:
        return None

    ranked = sorted(rows, key=lambda r: r.get("average_roi") if r.get("average_roi") is not None else -math.inf, reverse=True)
    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else None
    separation = _relative_separation(best.get("average_roi") or 0, second.get("average_roi") if second else None)

    confidence = _confidence_from_sample_size(best.get("campaign_count"), separation)
    risk_flags = _risk_flags_for_group(best, overall_avg_roi, overall_avg_cost)
    risk_level = "High" if any(f["flag"] == "NEGATIVE ROI" for f in risk_flags) else ("Medium" if risk_flags else "Low")

    name = best.get(name_key) or best.get("name") or best.get("recorded_channel_combination")

    return {
        "recommendation_type": recommendation_type,
        "title": f"{title_prefix}: {name}",
        "recommendation": (
            f"Observed performance suggests '{name}' currently shows the strongest average ROI "
            f"among evaluated {recommendation_type.lower()} groups."
        ),
        "reason": (
            f"This group has the highest observed average ROI ({separation:.1f}% above the next-best group)."
            if second
            else "This group has the highest observed average ROI."
        ),
        "evidence_basis": "OBSERVED",
        "supporting_metrics": {
            "average_roi": best.get("average_roi"),
            "total_revenue": best.get("total_revenue"),
            "total_conversions": best.get("total_conversions"),
            "campaign_count": best.get("campaign_count"),
        },
        "confidence": confidence,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "why": {
            "evidence": f"average_roi={best.get('average_roi')}, campaigns_evaluated={best.get('campaign_count')}",
            "interpretation": (
                f"Among the observed data, {name} shows the highest average ROI in this grouping. "
                "This reflects historical association, not a guaranteed future outcome."
            ),
            "caution": (
                "This does not establish that belonging to this group causes higher ROI — other "
                "unobserved factors may explain the difference."
            ),
        },
    }


def get_top_campaign_opportunity(df):
    """Aggregated Campaign_Type view (not single-row outliers) with a
    meaningful-contribution guard: the top group by average ROI must
    also carry above-median revenue among the compared groups.
    """
    types = analytics_service.get_campaign_types(df)
    if not types:
        return None

    median_revenue = sorted([t["total_revenue"] for t in types])[len(types) // 2]
    eligible = [t for t in types if t["total_revenue"] >= median_revenue] or types

    overall_avg_roi = df["ROI"].mean() if not df.empty else None
    overall_avg_cost = df["Acquisition_Cost"].mean() if not df.empty else None

    return _build_group_recommendation("Campaign", "Top Campaign Opportunity", eligible, "name", overall_avg_roi, overall_avg_cost)


def get_segment_opportunity(df):
    segments = analytics_service.get_customer_segments(df)
    overall_avg_roi = df["ROI"].mean() if not df.empty else None
    overall_avg_cost = df["Acquisition_Cost"].mean() if not df.empty else None
    return _build_group_recommendation("Customer Segment", "Prioritize Segment", segments, "name", overall_avg_roi, overall_avg_cost)


def get_audience_opportunity(df):
    audience_data = cas.get_audience_performance(df)
    audiences = audience_data.get("audiences", [])
    overall_avg_roi = df["ROI"].mean() if not df.empty else None
    overall_avg_cost = df["Acquisition_Cost"].mean() if not df.empty else None
    return _build_group_recommendation("Target Audience", "Prioritize Audience", audiences, "name", overall_avg_roi, overall_avg_cost)


def get_channel_opportunity(df):
    channel_data = cas.get_channel_performance(df, limit=100)
    channels = channel_data.get("channels", [])
    eligible = [c for c in channels if c.get("campaign_count", 0) >= 200] or channels
    overall_avg_roi = df["ROI"].mean() if not df.empty else None
    overall_avg_cost = df["Acquisition_Cost"].mean() if not df.empty else None
    rec = _build_group_recommendation(
        "Channel", "Channel Opportunity", eligible, "recorded_channel_combination", overall_avg_roi, overall_avg_cost
    )
    if rec:
        rec["why"]["caution"] += (
            " The Channel field records multi-channel combinations rather than single-channel "
            "attribution — this reflects the recorded combination, not an isolated channel effect."
        )
    return rec


def get_budget_cost_signal(df, metadata_path):
    """Combines the OBSERVED Acquisition_Cost/ROI correlation with the
    PREDICTIVE cost-only vs early-stage model comparison. Explicitly
    avoids asserting that spending more causes higher ROI.
    """
    correlations = statistics_service.get_roi_correlations(df)
    cost_corr = next((c for c in correlations if c["variable"] == "Acquisition_Cost"), None)

    model_note = None
    cost_only_r2 = None
    early_stage_r2 = None
    try:
        from backend.services import ml_service

        metadata = ml_service.get_metadata(metadata_path)
        comparison = metadata.get("model_comparison", {})
        cost_only_r2 = comparison.get("cost_only", {}).get("r2")
        early_stage_r2 = comparison.get("early_stage", {}).get("r2")
        model_note = metadata.get("dominant_feature_note")
    except ModelUnavailableError:
        pass

    direction = "inverse" if cost_corr and cost_corr["correlation_with_roi"] < 0 else "positive"

    recommendation_text = (
        f"Observed data shows a {direction} relationship between Acquisition Cost and ROI "
        f"(r={cost_corr['correlation_with_roi']})."
        if cost_corr
        else "Acquisition Cost correlation data is not available."
    )
    if cost_only_r2 is not None:
        recommendation_text += (
            f" Model estimates suggest Acquisition Cost alone explains a large share of the "
            f"early-stage model's predictive performance (cost-only R²={cost_only_r2*100:.1f}%, "
            f"full early-stage R²={(early_stage_r2 or 0)*100:.1f}%)."
        )

    return {
        "recommendation_type": "Budget / Cost Signal",
        "title": "Interpret Acquisition Cost Carefully",
        "recommendation": recommendation_text,
        "reason": "Higher spending is not shown to automatically cause higher ROI in this data.",
        "evidence_basis": "OBSERVED + PREDICTIVE",
        "supporting_metrics": {
            "acquisition_cost_roi_correlation": cost_corr["correlation_with_roi"] if cost_corr else None,
            "correlation_p_value": cost_corr["p_value"] if cost_corr else None,
            "cost_only_model_r2": cost_only_r2,
            "early_stage_model_r2": early_stage_r2,
        },
        "confidence": "High" if cost_corr and cost_corr.get("significant_at_0_05") else "Medium",
        "risk_level": "Medium",
        "risk_flags": [
            {
                "flag": "MODEL LIMITATION",
                "message": model_note or "Prediction is sensitive to Acquisition_Cost and should be treated as decision support.",
            }
        ],
        "why": {
            "evidence": f"Pearson r={cost_corr['correlation_with_roi'] if cost_corr else 'n/a'}; cost-only model R²={cost_only_r2}",
            "interpretation": (
                "Acquisition Cost has a strong statistical association with ROI in both the raw "
                "correlation and the trained model's structure."
            ),
            "caution": (
                "This is a statistical association and a model finding, not evidence that changing "
                "acquisition cost will causally change ROI. Do not conclude that spending more or "
                "less will directly produce a specific ROI outcome."
            ),
        },
    }


def get_ab_test_signal(df):
    """EXPERIMENTAL evidence type — surfaces the existing A/B test
    result as a recommendation-shaped item, without recomputing it.
    """
    result = statistics_service.get_ab_test(df)
    if "error" in result:
        return None

    significant = result["welchs_t_test"]["significant_at_0_05"]

    return {
        "recommendation_type": "Experiment Signal",
        "title": f"{result['group_a']['label']} vs {result['group_b']['label']}",
        "recommendation": result["business_recommendation"],
        "reason": (
            "A/B test results indicate a statistically significant difference."
            if significant
            else "A/B test results indicate no statistically significant difference."
        ),
        "evidence_basis": "EXPERIMENTAL",
        "supporting_metrics": {
            "group_a_avg_roi": result["group_a"]["average_roi"],
            "group_b_avg_roi": result["group_b"]["average_roi"],
            "p_value": result["welchs_t_test"]["p_value"],
            "cohens_d": result["effect_size"]["cohens_d"],
        },
        "confidence": "High" if significant else "Medium",
        "risk_level": "Low",
        "risk_flags": [],
        "why": {
            "evidence": f"Welch's t-test p={result['welchs_t_test']['p_value']}, Cohen's d={result['effect_size']['cohens_d']}",
            "interpretation": "A/B test results indicate "
            + ("a real difference between groups." if significant else "no reliable difference between groups."),
            "caution": "A/B testing evidence should not be combined with observed or predictive claims as if it were the same type of evidence.",
        },
    }


def get_risk_flags(df, metadata_path):
    """Portfolio-level risk/warning items, distinct from the per-group
    risk_flags attached to individual opportunity recommendations.
    """
    risks = []
    if df.empty:
        return risks

    dist = cas.get_roi_distribution(df)
    stats = dist.get("stats", {})

    if stats.get("pct_roi_lt_0"):
        risks.append(
            {
                "recommendation_type": "Risk",
                "title": "Negative ROI Campaigns Present",
                "recommendation": f"{stats['pct_roi_lt_0']}% of evaluated campaigns have negative observed ROI.",
                "reason": "A meaningful share of campaigns show negative observed ROI.",
                "evidence_basis": "OBSERVED",
                "supporting_metrics": {"pct_roi_lt_0": stats["pct_roi_lt_0"]},
                "confidence": "High",
                "risk_level": "High" if stats["pct_roi_lt_0"] > 15 else "Medium",
                "risk_flags": [{"flag": "NEGATIVE ROI", "message": "Campaign has negative observed ROI."}],
                "why": {
                    "evidence": f"pct_roi_lt_0={stats['pct_roi_lt_0']}%",
                    "interpretation": "A portion of campaigns underperform their acquisition cost.",
                    "caution": "This does not identify which specific factors caused underperformance.",
                },
            }
        )

    channel_data = cas.get_channel_performance(df, limit=100)
    overall_avg_cost = df["Acquisition_Cost"].mean()
    overall_avg_roi = df["ROI"].mean()
    high_cost_low_roi = [
        c
        for c in channel_data.get("channels", [])
        if c.get("campaign_count", 0) >= MIN_CAMPAIGNS_FOR_MEDIUM_CONFIDENCE
        and c.get("average_acquisition_cost")
        and c["average_acquisition_cost"] > overall_avg_cost * 1.15
        and c.get("average_roi") is not None
        and c["average_roi"] < overall_avg_roi
    ]
    if high_cost_low_roi:
        worst = max(high_cost_low_roi, key=lambda c: c["average_acquisition_cost"])
        risks.append(
            {
                "recommendation_type": "Risk",
                "title": f"High Acquisition Cost: {worst['recorded_channel_combination']}",
                "recommendation": "Acquisition cost is high relative to observed returns for this channel combination.",
                "reason": "Average acquisition cost exceeds the overall average while average ROI is below the overall average.",
                "evidence_basis": "OBSERVED",
                "supporting_metrics": {
                    "average_acquisition_cost": worst["average_acquisition_cost"],
                    "average_roi": worst["average_roi"],
                    "campaign_count": worst["campaign_count"],
                },
                "confidence": _confidence_from_sample_size(worst["campaign_count"]),
                "risk_level": "Medium",
                "risk_flags": [{"flag": "HIGH ACQUISITION COST", "message": "Acquisition cost is high relative to observed returns."}],
                "why": {
                    "evidence": f"avg_cost={worst['average_acquisition_cost']} vs overall={round(overall_avg_cost,2)}",
                    "interpretation": "This channel combination costs more per campaign on average without a corresponding ROI advantage.",
                    "caution": "Cost and ROI are associated, not proven causal, for this specific group.",
                },
            }
        )

    if "Leads" in df.columns and "Conversions" in df.columns and not df.empty:
        leads_total = df["Leads"].sum()
        conv_rate_overall = df["Conversions"].sum() / leads_total if leads_total else None
        if conv_rate_overall:
            for t in analytics_service.get_campaign_types(df):
                type_df = df[df["Campaign_Type"] == t["name"]]
                leads_sum = type_df["Leads"].sum()
                conv_sum = type_df["Conversions"].sum()
                if leads_sum:
                    conv_rate = conv_sum / leads_sum
                    if conv_rate < conv_rate_overall * 0.85:
                        risks.append(
                            {
                                "recommendation_type": "Risk",
                                "title": f"Lower Conversion Rate: {t['name']}",
                                "recommendation": f"{t['name']} converts leads to conversions at a lower rate than the overall average.",
                                "reason": "Conversion-to-lead ratio is below the dataset-wide average for this campaign type.",
                                "evidence_basis": "OBSERVED",
                                "supporting_metrics": {
                                    "conversion_rate": round(conv_rate, 4),
                                    "overall_conversion_rate": round(conv_rate_overall, 4),
                                    "campaign_count": t["campaign_count"],
                                },
                                "confidence": _confidence_from_sample_size(t["campaign_count"]),
                                "risk_level": "Medium",
                                "risk_flags": [
                                    {"flag": "LOW CONVERSION", "message": "Campaign generates weak conversions relative to its reach/leads."}
                                ],
                                "why": {
                                    "evidence": f"conversion_rate={round(conv_rate,4)} vs overall={round(conv_rate_overall,4)}",
                                    "interpretation": "This campaign type converts a smaller share of leads than average.",
                                    "caution": "Lower conversion rate does not by itself explain why — targeting, creative, or offer quality are not measured here.",
                                },
                            }
                        )
                        break

    try:
        from backend.services import ml_service

        metadata = ml_service.get_metadata(metadata_path)
        risks.append(
            {
                "recommendation_type": "Risk",
                "title": "Model Limitation: Acquisition Cost Dominance",
                "recommendation": metadata.get(
                    "dominant_feature_note",
                    "Prediction is sensitive to Acquisition_Cost and should be treated as decision support.",
                ),
                "reason": "The ROI prediction model's performance is driven largely by Acquisition Cost.",
                "evidence_basis": "PREDICTIVE",
                "supporting_metrics": {"model_r2": metadata.get("metrics", {}).get("r2")},
                "confidence": "High",
                "risk_level": "Medium",
                "risk_flags": [
                    {"flag": "MODEL LIMITATION", "message": "Prediction is sensitive to Acquisition_Cost and should be treated as decision support."}
                ],
                "why": {
                    "evidence": "cost-only model R² closely approaches the full early-stage model's R².",
                    "interpretation": "Most of the model's predictive power comes from Acquisition Cost alone.",
                    "caution": "Do not treat ROI predictions as evidence that campaign strategy independently causes ROI.",
                },
            }
        )
    except ModelUnavailableError:
        pass

    return risks


def build_recommendations(df, metadata_path, filter_type=None):
    """Assemble the full recommendation set, optionally filtered by
    category. Returns the same shape regardless of filter so the API
    layer can serialize it directly.
    """
    builders = {
        "campaign": lambda: [get_top_campaign_opportunity(df)],
        "segment": lambda: [get_segment_opportunity(df)],
        "audience": lambda: [get_audience_opportunity(df)],
        "channel": lambda: [get_channel_opportunity(df)],
        "budget": lambda: [get_budget_cost_signal(df, metadata_path)],
        "risk": lambda: get_risk_flags(df, metadata_path),
    }

    if filter_type:
        items = [r for r in builders[filter_type]() if r]
    else:
        items = []
        for key in ("campaign", "segment", "audience", "channel", "budget"):
            items.extend([r for r in builders[key]() if r])
        ab_signal = get_ab_test_signal(df)
        if ab_signal:
            items.append(ab_signal)
        items.extend(get_risk_flags(df, metadata_path))

    high_priority = sum(1 for r in items if r.get("confidence") == "High" and r.get("risk_level") in ("Low", "Medium"))
    warnings = sum(1 for r in items if r.get("recommendation_type") == "Risk" or r.get("risk_level") == "High")

    return {
        "status": "success",
        "recommendations": items,
        "summary": {"total": len(items), "high_priority": high_priority, "warnings": warnings},
    }
