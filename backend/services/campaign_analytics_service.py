"""
Campaign Analytics service layer (Phase 7).

Everything here operates on the SAME cached dataframe from
backend.services.data_service (via require_dataframe) that every other
service already uses — this module never re-reads the CSV. Where an
aggregation already exists (campaign-type and customer-segment
breakdowns), this module reuses backend.services.analytics_service
directly instead of recomputing it.

Channel handling: Channel_Used contains recorded multi-channel
combinations (e.g. "WhatsApp, YouTube") rather than one channel per
row. This module never splits/re-attributes revenue across the
individual channels in a combination — doing so would fabricate
per-channel numbers the data doesn't actually support. Channel
filtering uses substring matching ("contains Instagram"); channel
*analysis* groups by the exact recorded combination and labels it
as such.
"""

import io
import math
from typing import Optional

import numpy as np
import pandas as pd

from backend.services import analytics_service

TABLE_DISPLAY_COLUMNS = [
    "Campaign_ID",
    "Campaign_Type",
    "Target_Audience",
    "Channel_Used",
    "Language",
    "Customer_Segment",
    "Duration",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Conversions",
    "Engagement_Score",
]

RANGE_FILTER_COLUMNS = {
    "duration": "Duration",
    "acquisition_cost": "Acquisition_Cost",
    "roi": "ROI",
    "revenue": "Revenue",
    "conversions": "Conversions",
}

PERFORMANCE_TIERS = [
    ("Negative", None, 0),
    ("Low Return", 0, 1),
    ("Moderate Return", 1, 2),
    ("Strong Return", 2, 3),
    ("High Return", 3, None),
]


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), ndigits)


class InvalidFilterError(ValueError):
    """Raised for malformed filter query params (e.g. non-numeric range bound)."""


def _parse_float(value, field_name):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InvalidFilterError(f"'{field_name}' must be a number.")


def apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply every recognized filter param that was actually supplied.
    Equality filters reuse analytics_service's FILTERABLE_COLUMNS logic
    for everything except Channel (substring match, since a row can
    legitimately belong to several channels at once). Range filters
    apply min/max bounds on numeric columns. Unrecognized/empty params
    are ignored rather than raising.
    """
    filtered = df

    equality_filters = {k: v for k, v in filters.items() if k in analytics_service.FILTERABLE_COLUMNS and k != "channel"}
    filtered = analytics_service.apply_filters(filtered, equality_filters)

    channel = filters.get("channel")
    if channel:
        filtered = filtered[filtered["Channel_Used"].astype(str).str.contains(channel, case=False, na=False)]

    search = filters.get("search")
    if search and "Campaign_ID" in filtered.columns:
        filtered = filtered[filtered["Campaign_ID"].astype(str).str.contains(search, case=False, na=False)]

    for param_prefix, column in RANGE_FILTER_COLUMNS.items():
        if column not in filtered.columns:
            continue
        min_val = _parse_float(filters.get(f"{param_prefix}_min"), f"{param_prefix}_min")
        max_val = _parse_float(filters.get(f"{param_prefix}_max"), f"{param_prefix}_max")
        if min_val is not None:
            filtered = filtered[filtered[column] >= min_val]
        if max_val is not None:
            filtered = filtered[filtered[column] <= max_val]

    return filtered


def get_active_filters_summary(filters: dict) -> dict:
    """Echo back only the filters that were actually applied, for the
    frontend's 'Active Filters' display. Purely descriptive.
    """
    return {k: v for k, v in filters.items() if v not in (None, "")}


def get_filtered_summary(df: pd.DataFrame) -> dict:
    """KPIs for the CURRENT (already-filtered) dataframe — never the
    global dataset once filters are applied.
    """
    if df.empty:
        return {
            "filtered_campaigns": 0,
            "total_revenue": None,
            "average_roi": None,
            "median_roi": None,
            "total_conversions": 0,
            "average_acquisition_cost": None,
            "average_engagement_score": None,
        }
    return {
        "filtered_campaigns": int(len(df)),
        "total_revenue": _safe_round(df["Revenue"].sum(), 2),
        "average_roi": _safe_round(df["ROI"].mean(), 4),
        "median_roi": _safe_round(df["ROI"].median(), 4),
        "total_conversions": int(df["Conversions"].sum()),
        "average_acquisition_cost": _safe_round(df["Acquisition_Cost"].mean(), 2),
        "average_engagement_score": _safe_round(df["Engagement_Score"].mean(), 4)
        if "Engagement_Score" in df.columns
        else None,
    }


def get_table_page(df: pd.DataFrame, page: int, page_size: int, sort_by: Optional[str], sort_dir: str) -> dict:
    """Paginated campaign rows from the already-filtered dataframe."""
    valid_sort_cols = [c for c in TABLE_DISPLAY_COLUMNS if c in df.columns]
    if sort_by and sort_by in valid_sort_cols:
        df = df.sort_values(sort_by, ascending=(sort_dir == "asc"))

    total = int(len(df))
    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end]

    display_cols = [c for c in TABLE_DISPLAY_COLUMNS if c in page_df.columns]
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
            "total_pages": max(1, math.ceil(total / page_size)) if total else 1,
        },
    }


def get_channel_performance(df: pd.DataFrame, limit: int = 50) -> dict:
    """Groups by the EXACT recorded Channel_Used combination — never
    splits or re-attributes across individual channels within a
    combination, since the data doesn't support that attribution.
    """
    if df.empty or "Channel_Used" not in df.columns:
        return {"channels": [], "note": _channel_note()}

    grouped = df.groupby("Channel_Used", dropna=False).agg(
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in df.columns else ("Channel_Used", "count"),
        total_revenue=("Revenue", "sum"),
        average_roi=("ROI", "mean"),
        median_roi=("ROI", "median"),
        total_conversions=("Conversions", "sum"),
        average_acquisition_cost=("Acquisition_Cost", "mean"),
    )
    grouped = grouped.sort_values("campaign_count", ascending=False).head(limit)

    results = [
        {
            "recorded_channel_combination": str(name),
            "campaign_count": int(row["campaign_count"]),
            "total_revenue": _safe_round(row["total_revenue"], 2),
            "average_roi": _safe_round(row["average_roi"], 4),
            "median_roi": _safe_round(row["median_roi"], 4),
            "total_conversions": int(row["total_conversions"]),
            "average_acquisition_cost": _safe_round(row["average_acquisition_cost"], 2),
        }
        for name, row in grouped.iterrows()
    ]

    return {"channels": results, "note": _channel_note()}


def _channel_note() -> str:
    return (
        "The Channel field records multi-channel combinations used for a campaign "
        "(e.g. \"WhatsApp, YouTube\") rather than a single channel per row. Each row below "
        "is a recorded channel combination, not an individually-attributed channel — "
        "revenue and ROI are not split across the channels within a combination."
    )


def get_audience_performance(df: pd.DataFrame) -> dict:
    if df.empty or "Target_Audience" not in df.columns:
        return {
            "audiences": [],
            "highest_average_roi_audience": None,
            "highest_revenue_audience": None,
            "highest_conversions_audience": None,
        }

    grouped = df.groupby("Target_Audience", dropna=False).agg(
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in df.columns else ("Target_Audience", "count"),
        total_revenue=("Revenue", "sum"),
        average_roi=("ROI", "mean"),
        total_conversions=("Conversions", "sum"),
        average_acquisition_cost=("Acquisition_Cost", "mean"),
    )

    results = [
        {
            "name": str(name),
            "campaign_count": int(row["campaign_count"]),
            "total_revenue": _safe_round(row["total_revenue"], 2),
            "average_roi": _safe_round(row["average_roi"], 4),
            "total_conversions": int(row["total_conversions"]),
            "average_acquisition_cost": _safe_round(row["average_acquisition_cost"], 2),
        }
        for name, row in grouped.iterrows()
    ]
    results.sort(key=lambda r: r["average_roi"] or 0, reverse=True)

    highest_roi = max(results, key=lambda r: r["average_roi"] if r["average_roi"] is not None else -math.inf) if results else None
    highest_revenue = max(results, key=lambda r: r["total_revenue"] if r["total_revenue"] is not None else -math.inf) if results else None
    highest_conversions = max(results, key=lambda r: r["total_conversions"]) if results else None

    return {
        "audiences": results,
        "highest_average_roi_audience": highest_roi["name"] if highest_roi else None,
        "highest_revenue_audience": highest_revenue["name"] if highest_revenue else None,
        "highest_conversions_audience": highest_conversions["name"] if highest_conversions else None,
    }


def get_language_performance(df: pd.DataFrame) -> dict:
    if df.empty or "Language" not in df.columns:
        return {"languages": [], "highest_average_roi_language": None}

    grouped = df.groupby("Language", dropna=False).agg(
        campaign_count=("Campaign_ID", "count") if "Campaign_ID" in df.columns else ("Language", "count"),
        total_revenue=("Revenue", "sum"),
        average_roi=("ROI", "mean"),
        total_conversions=("Conversions", "sum"),
        average_acquisition_cost=("Acquisition_Cost", "mean"),
    )

    results = [
        {
            "name": str(name),
            "campaign_count": int(row["campaign_count"]),
            "total_revenue": _safe_round(row["total_revenue"], 2),
            "average_roi": _safe_round(row["average_roi"], 4),
            "total_conversions": int(row["total_conversions"]),
            "average_acquisition_cost": _safe_round(row["average_acquisition_cost"], 2),
        }
        for name, row in grouped.iterrows()
    ]
    results.sort(key=lambda r: r["average_roi"] or 0, reverse=True)

    return {"languages": results, "highest_average_roi_language": results[0]["name"] if results else None}


def get_roi_distribution(df: pd.DataFrame, bins: int = 20) -> dict:
    if df.empty or "ROI" not in df.columns:
        return {"histogram": [], "stats": {}}

    roi = df["ROI"].dropna()
    if roi.empty:
        return {"histogram": [], "stats": {}}

    counts, edges = np.histogram(roi, bins=bins)
    histogram = [
        {"bin_start": _safe_round(edges[i], 3), "bin_end": _safe_round(edges[i + 1], 3), "count": int(counts[i])}
        for i in range(len(counts))
    ]

    n = len(roi)
    stats = {
        "median_roi": _safe_round(roi.median(), 4),
        "average_roi": _safe_round(roi.mean(), 4),
        "min_roi": _safe_round(roi.min(), 4),
        "max_roi": _safe_round(roi.max(), 4),
        "pct_roi_gt_1": _safe_round(100 * (roi > 1).sum() / n, 2),
        "pct_roi_gt_2": _safe_round(100 * (roi > 2).sum() / n, 2),
        "pct_roi_lt_0": _safe_round(100 * (roi < 0).sum() / n, 2),
    }

    return {"histogram": histogram, "stats": stats}


def get_performance_tiers(df: pd.DataFrame) -> dict:
    """Illustrative ROI performance bands — display bands only, not
    statistical significance thresholds.
    """
    if df.empty or "ROI" not in df.columns:
        return {"tiers": [], "label": "Illustrative ROI Performance Bands"}

    roi = df["ROI"].dropna()
    n = len(roi)
    tiers = []
    for label, low, high in PERFORMANCE_TIERS:
        if low is None:
            mask = roi < high
            range_label = f"< {high}"
        elif high is None:
            mask = roi >= low
            range_label = f">= {low}"
        else:
            mask = (roi >= low) & (roi < high)
            range_label = f"{low} – {high}"
        count = int(mask.sum())
        tiers.append(
            {
                "tier": label,
                "range": range_label,
                "count": count,
                "percentage": _safe_round(100 * count / n, 2) if n else None,
            }
        )

    return {"tiers": tiers, "label": "Illustrative ROI Performance Bands"}


TOP_CAMPAIGN_COLUMNS = [
    "Campaign_ID",
    "Campaign_Type",
    "Channel_Used",
    "Target_Audience",
    "Customer_Segment",
    "ROI",
    "Revenue",
    "Conversions",
    "Acquisition_Cost",
]

RANK_METRIC_COLUMNS = {"roi": "ROI", "revenue": "Revenue", "conversions": "Conversions"}
UNDERPERFORM_METRIC_COLUMNS = {
    "lowest_roi": ("ROI", True),
    "highest_acquisition_cost": ("Acquisition_Cost", False),
    "lowest_conversions": ("Conversions", True),
}


def get_top_campaigns(df: pd.DataFrame, metric: str, limit: int) -> dict:
    column = RANK_METRIC_COLUMNS.get(metric, "ROI")
    if df.empty:
        return {"results": [], "ranked_by": column}

    top = df.sort_values(column, ascending=False).head(limit)
    cols = [c for c in TOP_CAMPAIGN_COLUMNS if c in top.columns]
    records = top[cols].to_dict(orient="records")
    for row in records:
        for key in ("Revenue", "Acquisition_Cost", "ROI"):
            if key in row and row[key] is not None:
                row[key] = _safe_round(row[key], 4 if key == "ROI" else 2)

    return {"results": records, "ranked_by": column}


def get_underperforming_campaigns(df: pd.DataFrame, metric: str, limit: int) -> dict:
    column, ascending = UNDERPERFORM_METRIC_COLUMNS.get(metric, ("ROI", True))
    if df.empty:
        return {"results": [], "sorted_by": column, "label": "Underperforming relative to selected metric."}

    bottom = df.sort_values(column, ascending=ascending).head(limit)
    cols = [c for c in TOP_CAMPAIGN_COLUMNS if c in bottom.columns]
    records = bottom[cols].to_dict(orient="records")
    for row in records:
        for key in ("Revenue", "Acquisition_Cost", "ROI"):
            if key in row and row[key] is not None:
                row[key] = _safe_round(row[key], 4 if key == "ROI" else 2)

    return {"results": records, "sorted_by": column, "label": "Underperforming relative to selected metric."}


MAX_EXPORT_ROWS = 55555


def export_filtered_csv(df: pd.DataFrame) -> str:
    """Returns CSV text for the CURRENTLY FILTERED dataframe only —
    never the full dataset when filters are active.
    """
    buffer = io.StringIO()
    if df.empty:
        pd.DataFrame(columns=TABLE_DISPLAY_COLUMNS).to_csv(buffer, index=False)
    else:
        cols = [c for c in TABLE_DISPLAY_COLUMNS if c in df.columns]
        df[cols].head(MAX_EXPORT_ROWS).to_csv(buffer, index=False)
    return buffer.getvalue()
