"""
Statistics service layer.

Correlation, skewness, outlier detection, and the Social Media vs Paid
Ads A/B comparison are all computed live from the cached dataframe with
pandas/scipy/numpy. No statistic in this file is hardcoded; every
number reflects whatever dataset is actually loaded.
"""

import math

import numpy as np
import pandas as pd
from scipy import stats

NUMERIC_COLUMNS = [
    "Impressions",
    "Clicks",
    "Leads",
    "Conversions",
    "Revenue",
    "Acquisition_Cost",
    "ROI",
    "Engagement_Score",
    "Duration",
]


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value), ndigits)


def get_roi_correlations(df: pd.DataFrame) -> list:
    """Pearson correlation of each numeric column against ROI, with the
    p-value so the API can report significance rather than asserting it.
    """
    results = []
    if "ROI" not in df.columns:
        return results

    for col in NUMERIC_COLUMNS:
        if col == "ROI" or col not in df.columns:
            continue
        pair = df[[col, "ROI"]].dropna()
        if len(pair) < 3:
            continue
        r, p_value = stats.pearsonr(pair[col], pair["ROI"])
        results.append(
            {
                "variable": col,
                "correlation_with_roi": _safe_round(r, 4),
                "p_value": _safe_round(p_value, 6),
                "significant_at_0_05": bool(p_value < 0.05),
            }
        )

    results.sort(key=lambda r: abs(r["correlation_with_roi"] or 0), reverse=True)
    return results


def get_distribution_stats(df: pd.DataFrame) -> list:
    """Skewness for the key financial/outcome columns."""
    results = []
    for col in ["Revenue", "ROI", "Acquisition_Cost", "Conversions"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 3:
            continue
        results.append(
            {
                "variable": col,
                "skewness": _safe_round(series.skew(), 4),
                "mean": _safe_round(series.mean(), 4),
                "median": _safe_round(series.median(), 4),
                "std_dev": _safe_round(series.std(), 4),
            }
        )
    return results


def get_outlier_stats(df: pd.DataFrame) -> list:
    """IQR-method outlier share for the key financial/outcome columns.
    Outliers are reported, not removed — per the project's methodology.
    """
    results = []
    for col in ["Revenue", "ROI", "Acquisition_Cost", "Conversions"]:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if len(series) < 4:
            continue
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_count = int(((series < lower) | (series > upper)).sum())
        results.append(
            {
                "variable": col,
                "outlier_count": outlier_count,
                "outlier_percentage": _safe_round(100 * outlier_count / len(series), 2),
                "lower_bound": _safe_round(lower, 4),
                "upper_bound": _safe_round(upper, 4),
            }
        )
    return results


def get_ab_test(df: pd.DataFrame, group_a_label: str = "Social Media", group_b_label: str = "Paid Ads") -> dict:
    """Welch's t-test comparing ROI between two campaign types, plus
    Cohen's d and a rule-based (not free-generated) recommendation.
    Defaults match the project's original comparison (Social Media vs
    Paid Ads) but the two groups are parameterized, not hardcoded logic.
    """
    if "Campaign_Type" not in df.columns or "ROI" not in df.columns:
        return {"error": "Campaign_Type or ROI column not available in dataset."}

    group_a = df.loc[df["Campaign_Type"].astype(str).str.lower() == group_a_label.lower(), "ROI"].dropna()
    group_b = df.loc[df["Campaign_Type"].astype(str).str.lower() == group_b_label.lower(), "ROI"].dropna()

    if len(group_a) < 2 or len(group_b) < 2:
        return {
            "error": (
                f"Not enough data for one or both groups ('{group_a_label}': {len(group_a)}, "
                f"'{group_b_label}': {len(group_b)}) to run a t-test."
            )
        }

    t_stat, p_value = stats.ttest_ind(group_a, group_b, equal_var=False)

    # Pooled standard deviation for Cohen's d
    n1, n2 = len(group_a), len(group_b)
    pooled_std = math.sqrt(
        ((n1 - 1) * group_a.var(ddof=1) + (n2 - 1) * group_b.var(ddof=1)) / (n1 + n2 - 2)
    )
    cohens_d = (group_a.mean() - group_b.mean()) / pooled_std if pooled_std else 0.0

    abs_d = abs(cohens_d)
    if abs_d < 0.2:
        effect_label = "negligible"
    elif abs_d < 0.5:
        effect_label = "small"
    elif abs_d < 0.8:
        effect_label = "medium"
    else:
        effect_label = "large"

    significant = bool(p_value < 0.05)

    if significant:
        recommendation = (
            f"The difference in average ROI between {group_a_label} and {group_b_label} is "
            "statistically significant at the 0.05 level. This provides evidence to consider "
            "in budget allocation decisions, though other factors (conversion rate, engagement, "
            "acquisition cost, and audience fit) should still be evaluated before reallocating spend."
        )
    else:
        recommendation = (
            f"The difference in average ROI between {group_a_label} and {group_b_label} is not "
            "statistically significant at the 0.05 level. Do not shift budget between these channels "
            "based on ROI alone — evaluate conversion rate, engagement, acquisition cost, and "
            "customer segment before reallocating spend."
        )

    return {
        "group_a": {
            "label": group_a_label,
            "campaign_count": int(n1),
            "average_roi": _safe_round(group_a.mean(), 4),
            "median_roi": _safe_round(group_a.median(), 4),
        },
        "group_b": {
            "label": group_b_label,
            "campaign_count": int(n2),
            "average_roi": _safe_round(group_b.mean(), 4),
            "median_roi": _safe_round(group_b.median(), 4),
        },
        "welchs_t_test": {
            "t_statistic": _safe_round(t_stat, 4),
            "p_value": _safe_round(p_value, 6),
            "significant_at_0_05": significant,
        },
        "effect_size": {
            "cohens_d": _safe_round(cohens_d, 4),
            "interpretation": effect_label,
        },
        "business_recommendation": recommendation,
    }
