"""
Analytics service layer.

All functions here operate on the cached dataframe from data_service and
compute aggregates directly with pandas. Nothing here is hardcoded —
every figure returned is derived from whatever dataset is actually
loaded, so results reflect the real data, not the example figures
quoted in the project brief.
"""

import math
from typing import Optional

import numpy as np
import pandas as pd

FILTERABLE_COLUMNS = {
    "campaign_type": "Campaign_Type",
    "customer_segment": "Customer_Segment",
    "target_audience": "Target_Audience",
    "channel": "Channel_Used",
    "language": "Language",
}


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), ndigits)


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply equality filters for any recognized query params that were
    actually supplied. Unknown/empty filters are ignored rather than
    raising, so callers can pass through raw query args safely.
    """
    filtered = df
    for param_key, column in FILTERABLE_COLUMNS.items():
        value = filters.get(param_key)
        if value and column in filtered.columns:
            filtered = filtered[filtered[column].astype(str).str.lower() == str(value).lower()]

    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if (date_from or date_to) and "Date" in filtered.columns:
        dates = pd.to_datetime(filtered["Date"], errors="coerce")
        if date_from:
            filtered = filtered[dates >= pd.to_datetime(date_from, errors="coerce")]
            dates = pd.to_datetime(filtered["Date"], errors="coerce")
        if date_to:
            filtered = filtered[dates <= pd.to_datetime(date_to, errors="coerce")]

    return filtered


def get_summary(df: pd.DataFrame) -> dict:
    """Executive KPI cards. Every value is computed from df directly."""
    return {
        "total_campaigns": int(len(df)),
        "total_revenue": _safe_round(df["Revenue"].sum(), 2),
        "average_roi": _safe_round(df["ROI"].mean(), 4),
        "total_conversions": int(df["Conversions"].sum()),
        "average_acquisition_cost": _safe_round(df["Acquisition_Cost"].mean(), 2),
        "average_engagement_score": _safe_round(df["Engagement_Score"].mean(), 4)
        if "Engagement_Score" in df.columns
        else None,
    }


def _group_metrics(df: pd.DataFrame, group_col: str) -> list:
    grouped = df.groupby(group_col, dropna=False).agg(
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in df.columns else (group_col, "count"),
        total_revenue=("Revenue", "sum"),
        average_roi=("ROI", "mean"),
        median_roi=("ROI", "median"),
        total_conversions=("Conversions", "sum"),
        average_acquisition_cost=("Acquisition_Cost", "mean"),
    )
    grouped = grouped.sort_values("average_roi", ascending=False)

    results = []
    for name, row in grouped.iterrows():
        results.append(
            {
                "name": str(name),
                "campaign_count": int(row["campaign_count"]),
                "total_revenue": _safe_round(row["total_revenue"], 2),
                "average_roi": _safe_round(row["average_roi"], 4),
                "median_roi": _safe_round(row["median_roi"], 4),
                "total_conversions": int(row["total_conversions"]),
                "average_acquisition_cost": _safe_round(row["average_acquisition_cost"], 2),
            }
        )
    return results


def get_campaign_types(df: pd.DataFrame) -> list:
    return _group_metrics(df, "Campaign_Type")


def get_customer_segments(df: pd.DataFrame) -> list:
    return _group_metrics(df, "Customer_Segment")


def get_analytics_overview(df: pd.DataFrame) -> dict:
    """Combined EDA-style view: performance by type/segment plus the
    dynamically-derived leaders (not hardcoded — whichever group has
    the highest values in the current dataset wins).
    """
    by_type = get_campaign_types(df)
    by_segment = get_customer_segments(df)

    highest_roi_type = by_type[0] if by_type else None
    highest_revenue_type = max(by_type, key=lambda r: r["total_revenue"]) if by_type else None
    highest_roi_segment = by_segment[0] if by_segment else None
    highest_revenue_segment = max(by_segment, key=lambda r: r["total_revenue"]) if by_segment else None

    top_campaigns_cols = [
        c
        for c in ["Campaign_ID", "Campaign_Type", "Customer_Segment", "Revenue", "ROI", "Conversions"]
        if c in df.columns
    ]
    top_campaigns_df = df.sort_values("ROI", ascending=False).head(10)[top_campaigns_cols]
    top_campaigns = top_campaigns_df.to_dict(orient="records")
    for row in top_campaigns:
        if "Revenue" in row:
            row["Revenue"] = _safe_round(row["Revenue"], 2)
        if "ROI" in row:
            row["ROI"] = _safe_round(row["ROI"], 4)

    return {
        "by_campaign_type": by_type,
        "by_customer_segment": by_segment,
        "highest_avg_roi_campaign_type": highest_roi_type,
        "highest_total_revenue_campaign_type": highest_revenue_type,
        "highest_avg_roi_customer_segment": highest_roi_segment,
        "highest_total_revenue_customer_segment": highest_revenue_segment,
        "top_campaigns_by_roi": top_campaigns,
    }


def get_campaigns_page(
    df: pd.DataFrame,
    filters: dict,
    page: int,
    page_size: int,
    sort_by: Optional[str],
    sort_dir: str,
    search: Optional[str],
) -> dict:
    """Paginated, filtered, sortable campaign-level rows."""
    filtered = apply_filters(df, filters)

    if search and "Campaign_ID" in filtered.columns:
        filtered = filtered[filtered["Campaign_ID"].astype(str).str.contains(search, case=False, na=False)]

    valid_sort_cols = [
        c
        for c in [
            "Revenue",
            "ROI",
            "Acquisition_Cost",
            "Conversions",
            "Engagement_Score",
            "Clicks",
            "Impressions",
            "Leads",
        ]
        if c in filtered.columns
    ]
    if sort_by and sort_by in valid_sort_cols:
        filtered = filtered.sort_values(sort_by, ascending=(sort_dir == "asc"))

    total = int(len(filtered))
    start = (page - 1) * page_size
    end = start + page_size
    page_df = filtered.iloc[start:end]

    display_cols = [
        c
        for c in [
            "Campaign_ID",
            "Campaign_Type",
            "Target_Audience",
            "Duration",
            "Channel_Used",
            "Customer_Segment",
            "Revenue",
            "Acquisition_Cost",
            "ROI",
            "Conversions",
            "Engagement_Score",
            "Language",
            "Date",
        ]
        if c in page_df.columns
    ]
    records = page_df[display_cols].to_dict(orient="records")
    for row in records:
        for key in ("Revenue", "Acquisition_Cost", "ROI", "Engagement_Score"):
            if key in row and row[key] is not None:
                row[key] = _safe_round(row[key], 4 if key in ("ROI", "Engagement_Score") else 2)

    return {
        "results": records,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_results": total,
            "total_pages": max(1, math.ceil(total / page_size)),
        },
    }
