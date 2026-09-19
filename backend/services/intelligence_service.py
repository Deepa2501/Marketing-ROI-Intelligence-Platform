"""
Marketing Intelligence service layer (Phase 10).

This module adds genuinely new analysis (time-series trends, funnel
stage efficiency, cost-bucketed efficiency) but reuses every existing
aggregation it can — analytics_service, campaign_analytics_service,
statistics_service, recommendation_service — rather than duplicating
calculations. No new CSV loading.

Evidence discipline matches Phase 8/9 exactly:
- OBSERVED    = read directly from historical campaign data.
- PREDICTIVE  = read from the trained ROI model.
- EXPERIMENTAL = read from the A/B test result.
Correlation/association is always explicitly distinguished from
causation — see CORRELATION_DISCLAIMER below.
"""

import math

import numpy as np
import pandas as pd

from backend.services import analytics_service
from backend.services import campaign_analytics_service as cas
from backend.services import recommendation_service as rs
from backend.services import statistics_service

CORRELATION_DISCLAIMER = (
    "These are statistical associations observed in historical data, not proof of causation. "
    "A correlation between two variables does not establish that one causes the other."
)

FUNNEL_STAGES = ["Impressions", "Clicks", "Leads", "Conversions"]


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), ndigits)


# ============================================================
# 1. TREND INTELLIGENCE
# ============================================================


def get_trends(df, freq="M"):
    """Monthly (default) time-series trend of the key portfolio
    metrics. Reuses no other service since this is genuinely new
    time-indexed aggregation, but the metrics themselves (revenue,
    ROI, conversions, engagement) mirror the definitions already used
    by analytics_service.get_summary elsewhere in the platform.
    """
    if df.empty or "Date" not in df.columns:
        return {"points": [], "note": "No date-indexed data available."}

    working = df.copy()
    working["_parsed_date"] = pd.to_datetime(working["Date"], errors="coerce")
    working = working.dropna(subset=["_parsed_date"])
    if working.empty:
        return {"points": [], "note": "No valid dates found in the dataset."}

    working["_period"] = working["_parsed_date"].dt.to_period(freq).astype(str)

    grouped = working.groupby("_period").agg(
        total_revenue=("Revenue", "sum"),
        average_roi=("ROI", "mean"),
        total_conversions=("Conversions", "sum"),
        average_engagement_score=("Engagement_Score", "mean"),
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in working.columns else ("ROI", "count"),
    )
    grouped = grouped.sort_index()

    points = [
        {
            "period": period,
            "total_revenue": _safe_round(row["total_revenue"], 2),
            "average_roi": _safe_round(row["average_roi"], 4),
            "total_conversions": int(row["total_conversions"]),
            "average_engagement_score": _safe_round(row["average_engagement_score"], 4),
            "campaign_count": int(row["campaign_count"]),
        }
        for period, row in grouped.iterrows()
    ]

    return {
        "points": points,
        "granularity": "month",
        "evidence_basis": "OBSERVED",
        "note": "Trend values are calendar-month aggregates of the connected dataset.",
    }


# ============================================================
# 2. PERFORMANCE DRIVER ANALYSIS
# ============================================================


def get_performance_drivers(df):
    """ROI correlations (reused from statistics_service) plus group
    comparisons (reused from analytics_service / campaign_analytics_service).
    """
    correlations = statistics_service.get_roi_correlations(df)

    campaign_types = analytics_service.get_campaign_types(df)
    channels = cas.get_channel_performance(df, limit=25).get("channels", [])
    audiences = cas.get_audience_performance(df).get("audiences", [])
    segments = analytics_service.get_customer_segments(df)

    return {
        "roi_correlations": correlations,
        "correlation_disclaimer": CORRELATION_DISCLAIMER,
        "group_comparisons": {
            "campaign_type": campaign_types,
            "channel": channels[:10],
            "target_audience": audiences,
            "customer_segment": segments,
        },
        "evidence_basis": "OBSERVED",
    }


# ============================================================
# 3. MARKETING FUNNEL INTELLIGENCE
# ============================================================


def get_funnel(df):
    """Impressions -> Clicks -> Leads -> Conversions, with stage
    conversion rates and drop-off, computed directly and only once
    (not reused elsewhere in the platform, so no duplication risk).
    """
    if df.empty or not all(c in df.columns for c in FUNNEL_STAGES):
        return {"stages": [], "note": "Funnel columns not available."}

    totals = {stage: int(df[stage].sum()) for stage in FUNNEL_STAGES}

    stages = []
    for i, stage in enumerate(FUNNEL_STAGES):
        prev_total = totals[FUNNEL_STAGES[i - 1]] if i > 0 else None
        stage_rate = _safe_round(100 * totals[stage] / prev_total, 2) if prev_total else None
        drop_off = _safe_round(100 - stage_rate, 2) if stage_rate is not None else None
        overall_rate = _safe_round(100 * totals[stage] / totals["Impressions"], 4) if totals["Impressions"] else None
        stages.append(
            {
                "stage": stage,
                "total": totals[stage],
                "stage_conversion_rate_pct": stage_rate,
                "drop_off_pct": drop_off,
                "pct_of_impressions": overall_rate,
            }
        )

    # Identify the largest stage-to-stage drop-off dynamically (not hardcoded).
    drop_offs = [(s["stage"], s["drop_off_pct"]) for s in stages if s["drop_off_pct"] is not None]
    biggest_drop = max(drop_offs, key=lambda x: x[1]) if drop_offs else None

    return {
        "stages": stages,
        "overall_conversion_rate_pct": stages[-1]["pct_of_impressions"] if stages else None,
        "biggest_drop_off_stage": biggest_drop[0] if biggest_drop else None,
        "biggest_drop_off_pct": biggest_drop[1] if biggest_drop else None,
        "evidence_basis": "OBSERVED",
        "note": (
            "Stage conversion rate is the share of the previous stage's volume that reached this "
            "stage (e.g. Clicks / Impressions). Drop-off is 100% minus that rate."
        ),
    }


# ============================================================
# 4. MARKETING EFFICIENCY ANALYSIS
# ============================================================


def get_efficiency(df, n_buckets=5):
    """Buckets campaigns into Acquisition Cost quintiles (computed from
    the dataset's own distribution, not fixed dollar thresholds) and
    reports average revenue, ROI, and conversion efficiency per
    bucket, plus the highest/lowest performing campaign-type and
    customer-segment groups by conversion efficiency.
    """
    if df.empty or "Acquisition_Cost" not in df.columns:
        return {"cost_buckets": [], "note": "Acquisition Cost data not available."}

    working = df.copy()
    try:
        working["_cost_bucket"] = pd.qcut(working["Acquisition_Cost"], q=n_buckets, duplicates="drop")
    except ValueError:
        return {"cost_buckets": [], "note": "Not enough distinct Acquisition Cost values to bucket."}

    grouped = working.groupby("_cost_bucket", observed=True).agg(
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in working.columns else ("ROI", "count"),
        average_acquisition_cost=("Acquisition_Cost", "mean"),
        average_revenue=("Revenue", "mean"),
        average_roi=("ROI", "mean"),
        total_conversions=("Conversions", "sum"),
    )

    cost_buckets = []
    for interval, row in grouped.iterrows():
        conv_per_cost = (
            _safe_round(row["total_conversions"] / (row["average_acquisition_cost"] * row["campaign_count"]), 6)
            if row["average_acquisition_cost"] and row["campaign_count"]
            else None
        )
        cost_buckets.append(
            {
                "cost_range": f"{_safe_round(interval.left, 2)} – {_safe_round(interval.right, 2)}",
                "campaign_count": int(row["campaign_count"]),
                "average_acquisition_cost": _safe_round(row["average_acquisition_cost"], 2),
                "average_revenue": _safe_round(row["average_revenue"], 2),
                "average_roi": _safe_round(row["average_roi"], 4),
                "conversions_per_unit_cost": conv_per_cost,
            }
        )

    # Conversion efficiency (conversions per unit acquisition cost) by
    # campaign type and customer segment, to flag high/low performers.
    def _efficiency_by(group_col):
        rows = []
        for name, g in df.groupby(group_col, dropna=False):
            total_cost = g["Acquisition_Cost"].sum()
            if total_cost:
                rows.append(
                    {
                        "name": str(name),
                        "conversions_per_unit_cost": _safe_round(g["Conversions"].sum() / total_cost, 6),
                        "campaign_count": int(len(g)),
                    }
                )
        rows.sort(key=lambda r: r["conversions_per_unit_cost"], reverse=True)
        return rows

    type_efficiency = _efficiency_by("Campaign_Type") if "Campaign_Type" in df.columns else []
    segment_efficiency = _efficiency_by("Customer_Segment") if "Customer_Segment" in df.columns else []

    return {
        "cost_buckets": cost_buckets,
        "campaign_type_efficiency": type_efficiency,
        "customer_segment_efficiency": segment_efficiency,
        "most_efficient_campaign_type": type_efficiency[0] if type_efficiency else None,
        "least_efficient_campaign_type": type_efficiency[-1] if type_efficiency else None,
        "evidence_basis": "OBSERVED",
        "note": (
            "Cost buckets are quintiles of the dataset's own observed Acquisition Cost distribution "
            "(20% of campaigns per bucket), not fixed dollar thresholds. Conversion efficiency is "
            "conversions per unit of acquisition cost spent."
        ),
    }


# ============================================================
# 5. ACTIONABLE BUSINESS INSIGHTS
# ============================================================


def get_actionable_insights(df, metadata_path, funnel=None, efficiency=None, drivers=None):
    """Composes funnel/efficiency findings above with the existing
    recommendation_service risk logic — avoids recomputing anything
    already computed in this request.
    """
    insights = []
    if df.empty:
        return insights

    funnel = funnel or get_funnel(df)
    efficiency = efficiency or get_efficiency(df)

    best_type = rs.get_top_campaign_opportunity(df)
    if best_type:
        insights.append(
            {
                "question": "What is performing well?",
                "finding": best_type["recommendation"],
                "evidence_basis": "OBSERVED",
                "supporting_metrics": best_type["supporting_metrics"],
            }
        )

    if efficiency.get("least_efficient_campaign_type"):
        weak = efficiency["least_efficient_campaign_type"]
        insights.append(
            {
                "question": "Where is efficiency weak?",
                "finding": (
                    f"{weak['name']} shows the lowest observed conversions-per-unit-cost among evaluated "
                    f"campaign types ({weak['conversions_per_unit_cost']} conversions per unit of acquisition cost)."
                ),
                "evidence_basis": "OBSERVED",
                "supporting_metrics": weak,
            }
        )

    if funnel.get("biggest_drop_off_stage"):
        insights.append(
            {
                "question": "Which areas deserve investigation?",
                "finding": (
                    f"The largest observed funnel drop-off occurs at the {funnel['biggest_drop_off_stage']} stage "
                    f"({funnel['biggest_drop_off_pct']}% drop-off from the prior stage)."
                ),
                "evidence_basis": "OBSERVED",
                "supporting_metrics": {"stage": funnel["biggest_drop_off_stage"], "drop_off_pct": funnel["biggest_drop_off_pct"]},
            }
        )

    risk_items = rs.get_risk_flags(df, metadata_path)
    if risk_items:
        top_risk = risk_items[0]
        insights.append(
            {
                "question": "Where should management be cautious?",
                "finding": top_risk["recommendation"],
                "evidence_basis": top_risk["evidence_basis"],
                "supporting_metrics": top_risk["supporting_metrics"],
            }
        )

    return insights


def build_marketing_intelligence(df, metadata_path):
    funnel = get_funnel(df)
    efficiency = get_efficiency(df)
    drivers = get_performance_drivers(df)

    return {
        "status": "success",
        "trends": get_trends(df),
        "drivers": drivers,
        "funnel": funnel,
        "efficiency": efficiency,
        "insights": get_actionable_insights(df, metadata_path, funnel=funnel, efficiency=efficiency, drivers=drivers),
    }
