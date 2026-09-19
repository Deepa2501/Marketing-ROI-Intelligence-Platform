"""
Data Quality & Governance service layer (Phase 12).

This module INSPECTS the connected dataset exactly as it currently
exists. It never modifies, cleans, deduplicates, or removes any row or
value — every function here is read-only analysis. Reuses
data_service (dataframe loading/caching) and statistics_service's
existing IQR outlier logic where the columns overlap, rather than
recomputing them from scratch.

Analytical-safety rules enforced throughout (see PHASE 12 spec):
- An outlier is reported as "a statistical outlier was detected",
  never as "incorrect" or "invalid" data.
- Negative ROI is never treated as a data-quality problem — it is a
  legitimate business outcome.
- A duplicate Campaign_ID is reported distinctly from an exact
  duplicate row; neither is assumed to mean "bad data" without
  evidence.
- Governance flags never recommend automatic deletion of outliers or
  any other data.
"""

import math
import os

import numpy as np
import pandas as pd

from backend.services import statistics_service

IMPORTANT_FIELDS = [
    "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration", "Channel_Used",
    "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost",
    "ROI", "Language", "Engagement_Score", "Customer_Segment", "Date",
]

NUMERIC_FIELDS = [
    "Duration", "Impressions", "Clicks", "Leads", "Conversions",
    "Revenue", "Acquisition_Cost", "ROI", "Engagement_Score",
]
CATEGORICAL_FIELDS = ["Campaign_Type", "Target_Audience", "Channel_Used", "Language", "Customer_Segment"]
IDENTIFIER_FIELDS = ["Campaign_ID"]
DATE_FIELDS = ["Date"]

# ============================================================
# DOCUMENTED THRESHOLDS
# ============================================================
# Missing-data health classification, applied per column:
#   GOOD:  < 1% missing
#   WATCH: 1% - 5% missing
#   RISK:  > 5% missing
MISSING_GOOD_MAX_PCT = 1.0
MISSING_WATCH_MAX_PCT = 5.0

OUTLIER_FIELDS = ["Revenue", "Acquisition_Cost", "ROI", "Conversions", "Engagement_Score"]


def _safe_round(value, ndigits=4):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    return round(float(value), ndigits)


def _pct(count, total):
    return _safe_round(100 * count / total, 2) if total else None


# ============================================================
# 1. DATASET PROFILE
# ============================================================


def get_dataset_profile(df, data_path):
    duplicate_rows = int(df.duplicated().sum())

    numeric_cols = [c for c in NUMERIC_FIELDS if c in df.columns]
    categorical_cols = [c for c in CATEGORICAL_FIELDS if c in df.columns]
    date_cols = [c for c in DATE_FIELDS if c in df.columns]

    size_mb = None
    try:
        if os.path.exists(data_path):
            size_mb = _safe_round(os.path.getsize(data_path) / (1024 * 1024), 2)
    except OSError:
        size_mb = None

    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "dataset_size_mb": size_mb,
        "column_names": list(df.columns),
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "duplicate_rows": duplicate_rows,
        "duplicate_percentage": _pct(duplicate_rows, len(df)),
    }


# ============================================================
# 2. MISSING VALUE ANALYSIS
# ============================================================


def _missing_status(pct):
    if pct < MISSING_GOOD_MAX_PCT:
        return "GOOD"
    if pct <= MISSING_WATCH_MAX_PCT:
        return "WATCH"
    return "RISK"


def get_missing_value_analysis(df):
    total = len(df)
    results = []
    for col in df.columns:
        missing = int(df[col].isnull().sum())
        pct = _pct(missing, total) or 0.0
        results.append(
            {
                "column": col,
                "missing_count": missing,
                "missing_percentage": pct,
                "non_missing_count": int(total - missing),
                "status": _missing_status(pct),
            }
        )
    # Columns with issues first, as required by the frontend table ordering.
    results.sort(key=lambda r: r["missing_percentage"], reverse=True)

    total_missing = sum(r["missing_count"] for r in results)
    return {
        "columns": results,
        "thresholds": {
            "GOOD": f"< {MISSING_GOOD_MAX_PCT}% missing",
            "WATCH": f"{MISSING_GOOD_MAX_PCT}% - {MISSING_WATCH_MAX_PCT}% missing",
            "RISK": f"> {MISSING_WATCH_MAX_PCT}% missing",
        },
        "summary": "No missing values detected." if total_missing == 0 else f"{total_missing:,} missing values detected across {sum(1 for r in results if r['missing_count'] > 0)} column(s).",
    }


# ============================================================
# 3. DATA TYPE VALIDATION
# ============================================================


def get_type_validation(df):
    checks = []

    for col in NUMERIC_FIELDS:
        if col not in df.columns:
            checks.append({"field": col, "check": "Numeric type", "result": "FAIL", "explanation": "Column not found in dataset."})
            continue
        is_numeric = pd.api.types.is_numeric_dtype(df[col])
        non_numeric_count = 0
        if not is_numeric:
            non_numeric_count = int(pd.to_numeric(df[col], errors="coerce").isnull().sum() - df[col].isnull().sum())
        result = "PASS" if is_numeric else ("WARNING" if non_numeric_count < len(df) * 0.05 else "FAIL")
        checks.append(
            {
                "field": col,
                "check": "Numeric type",
                "result": result,
                "explanation": "Column is numeric." if is_numeric else f"Column is not a numeric dtype; {non_numeric_count} value(s) could not convert to numeric.",
            }
        )

    for col in CATEGORICAL_FIELDS:
        if col not in df.columns:
            checks.append({"field": col, "check": "Populated categorical field", "result": "FAIL", "explanation": "Column not found in dataset."})
            continue
        empty_count = int((df[col].isnull() | (df[col].astype(str).str.strip() == "")).sum())
        pct_empty = _pct(empty_count, len(df)) or 0.0
        result = "PASS" if empty_count == 0 else ("WARNING" if pct_empty <= 5 else "FAIL")
        checks.append(
            {
                "field": col,
                "check": "Populated categorical field",
                "result": result,
                "explanation": "All values populated." if empty_count == 0 else f"{empty_count:,} empty/missing value(s) ({pct_empty}%).",
            }
        )

    for col in IDENTIFIER_FIELDS:
        if col not in df.columns:
            checks.append({"field": col, "check": "Identifier populated", "result": "FAIL", "explanation": "Column not found in dataset."})
            continue
        empty_count = int((df[col].isnull() | (df[col].astype(str).str.strip() == "")).sum())
        result = "PASS" if empty_count == 0 else "FAIL"
        checks.append(
            {
                "field": col,
                "check": "Identifier populated",
                "result": result,
                "explanation": "All rows have a populated Campaign_ID." if empty_count == 0 else f"{empty_count:,} row(s) missing Campaign_ID.",
            }
        )

    for col in DATE_FIELDS:
        if col not in df.columns:
            checks.append({"field": col, "check": "Date parseable", "result": "FAIL", "explanation": "Column not found in dataset."})
            continue
        parsed = pd.to_datetime(df[col], errors="coerce")
        invalid = int(parsed.isnull().sum() - df[col].isnull().sum())
        pct_invalid = _pct(invalid, len(df)) or 0.0
        result = "PASS" if invalid == 0 else ("WARNING" if pct_invalid <= 1 else "FAIL")
        checks.append(
            {
                "field": col,
                "check": "Date parseable",
                "result": result,
                "explanation": "All date values parsed successfully." if invalid == 0 else f"{invalid:,} value(s) ({pct_invalid}%) could not be parsed as dates.",
            }
        )

    return checks


# ============================================================
# 4. RANGE / VALIDITY CHECKS
# ============================================================


def get_range_validation(df):
    """Non-negativity and positivity checks only. ROI is deliberately
    excluded — negative ROI is a legitimate business outcome, not a
    data-quality issue.
    """
    checks = []
    non_negative_fields = ["Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost"]

    for col in non_negative_fields:
        if col not in df.columns:
            continue
        violation_count = int((df[col] < 0).sum())
        pct = _pct(violation_count, len(df)) or 0.0
        result = "PASS" if violation_count == 0 else ("WARNING" if pct <= 1 else "FAIL")
        checks.append(
            {
                "rule": f"{col} >= 0",
                "violation_count": violation_count,
                "violation_percentage": pct,
                "result": result,
                "explanation": f"No negative values found in {col}." if violation_count == 0 else f"{violation_count:,} row(s) ({pct}%) have a negative {col} value.",
            }
        )

    if "Duration" in df.columns:
        violation_count = int((df["Duration"] <= 0).sum())
        pct = _pct(violation_count, len(df)) or 0.0
        result = "PASS" if violation_count == 0 else ("WARNING" if pct <= 1 else "FAIL")
        checks.append(
            {
                "rule": "Duration > 0",
                "violation_count": violation_count,
                "violation_percentage": pct,
                "result": result,
                "explanation": "All campaigns have a positive duration." if violation_count == 0 else f"{violation_count:,} row(s) ({pct}%) have a non-positive Duration.",
            }
        )

    return checks


# ============================================================
# 5. OUTLIER MONITORING (reuses statistics_service's IQR logic)
# ============================================================


def get_outlier_monitor(df):
    """Reuses statistics_service.get_outlier_stats() for the overlapping
    fields (Revenue, ROI, Acquisition_Cost, Conversions) and adds
    Engagement_Score with the identical IQR method, since Phase 12
    requires it but the existing function doesn't compute it.
    """
    existing = {r["variable"]: r for r in statistics_service.get_outlier_stats(df)}

    results = []
    for field in OUTLIER_FIELDS:
        if field in existing:
            row = existing[field]
            results.append(
                {
                    "field": field,
                    "outlier_count": row["outlier_count"],
                    "outlier_percentage": row["outlier_percentage"],
                    "method": "IQR (1.5x interquartile range)",
                    "interpretation": f"Statistical outlier detected in {row['outlier_count']:,} campaign(s) ({row['outlier_percentage']}%). These are not automatically invalid records.",
                }
            )
        elif field in df.columns:
            series = df[field].dropna()
            if len(series) < 4:
                continue
            q1, q3 = series.quantile(0.25), series.quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            count = int(((series < lower) | (series > upper)).sum())
            pct = _pct(count, len(series))
            results.append(
                {
                    "field": field,
                    "outlier_count": count,
                    "outlier_percentage": pct,
                    "method": "IQR (1.5x interquartile range)",
                    "interpretation": f"Statistical outlier detected in {count:,} campaign(s) ({pct}%). These are not automatically invalid records." if count else "No statistical outliers detected using the IQR method.",
                }
            )

    return results


# ============================================================
# 6. DUPLICATE ANALYSIS
# ============================================================


def get_duplicate_analysis(df):
    exact_duplicates = int(df.duplicated().sum())
    exact_pct = _pct(exact_duplicates, len(df))

    duplicate_campaign_id_count = None
    duplicate_campaign_id_pct = None
    if "Campaign_ID" in df.columns:
        duplicate_campaign_id_count = int(df["Campaign_ID"].duplicated().sum())
        duplicate_campaign_id_pct = _pct(duplicate_campaign_id_count, len(df))

    return {
        "exact_duplicate_rows": exact_duplicates,
        "exact_duplicate_percentage": exact_pct,
        "duplicate_campaign_id_count": duplicate_campaign_id_count,
        "duplicate_campaign_id_percentage": duplicate_campaign_id_pct,
        "note": (
            "Exact duplicate rows and repeated Campaign_ID values are tracked separately — a repeated "
            "Campaign_ID does not necessarily mean the underlying campaign record is duplicated, and "
            "an exact duplicate row does not necessarily indicate an error without further investigation."
        ),
    }


# ============================================================
# 7. DATE QUALITY
# ============================================================


def get_date_quality(df):
    if "Date" not in df.columns:
        return {"status": "unavailable", "message": "Date column not found."}

    missing_count = int(df["Date"].isnull().sum())
    parsed = pd.to_datetime(df["Date"], errors="coerce")
    invalid_count = int(parsed.isnull().sum() - missing_count)
    valid = parsed.dropna()

    now = pd.Timestamp.now()
    future_count = int((valid > now).sum()) if not valid.empty else 0

    return {
        "min_date": valid.min().strftime("%Y-%m-%d") if not valid.empty else None,
        "max_date": valid.max().strftime("%Y-%m-%d") if not valid.empty else None,
        "invalid_count": invalid_count,
        "missing_count": missing_count,
        "future_date_count": future_count,
        "valid_count": int(len(valid)),
    }


# ============================================================
# 8. BUSINESS LOGIC / FUNNEL CHECKS
# ============================================================


def get_business_logic_checks(df):
    checks = []
    funnel_rules = [
        ("Impressions >= Clicks", "Impressions", "Clicks"),
        ("Clicks >= Leads", "Clicks", "Leads"),
        ("Leads >= Conversions", "Leads", "Conversions"),
    ]

    for rule_label, higher_col, lower_col in funnel_rules:
        if higher_col not in df.columns or lower_col not in df.columns:
            continue
        violations = int((df[lower_col] > df[higher_col]).sum())
        pct = _pct(violations, len(df)) or 0.0
        if violations == 0:
            severity = "INFO"
        elif pct <= 1:
            severity = "WATCH"
        else:
            severity = "RISK"
        checks.append(
            {
                "rule": rule_label,
                "violation_count": violations,
                "violation_percentage": pct,
                "severity": severity,
                "explanation": f"No rows violate {rule_label}." if violations == 0 else f"{violations:,} row(s) ({pct}%) violate {rule_label}.",
            }
        )

    valid_rows = len(df) - sum(c["violation_count"] for c in checks) if checks else len(df)
    return {
        "checks": checks,
        "valid_row_count": max(valid_rows, 0),
        "violation_row_count": len(df) - max(valid_rows, 0),
    }


# ============================================================
# 9. DATA QUALITY SCORE
# ============================================================
#
# "Analytical Data Quality Score" — documented, transparent formula.
# NOT a universal/industry-standard data quality benchmark.
#
#   1. Completeness  (weight 30%) = 100 - average missing % across all columns
#   2. Validity      (weight 25%) = 100 - average violation % across range checks
#   3. Duplicate Rate(weight 20%) = 100 - exact duplicate row percentage
#   4. Funnel Consistency (15%)   = 100 - average funnel violation % across the 3 funnel rules
#   5. Date Quality   (weight 10%) = 100 * (valid, non-future dates / total rows)
#
# Weights sum to 100%.
QUALITY_SCORE_WEIGHTS = {
    "completeness": 0.30,
    "validity": 0.25,
    "duplicate_rate": 0.20,
    "funnel_consistency": 0.15,
    "date_quality": 0.10,
}

QUALITY_SCORE_BANDS = [(90, "Excellent"), (75, "Good"), (55, "Watch"), (0, "Risk")]


def _quality_label(score):
    for threshold, label in QUALITY_SCORE_BANDS:
        if score >= threshold:
            return label
    return "Risk"


def get_quality_score(df, missing_analysis, range_checks, duplicates, funnel, date_quality):
    total_rows = len(df)

    avg_missing_pct = (
        sum(c["missing_percentage"] for c in missing_analysis["columns"]) / len(missing_analysis["columns"])
        if missing_analysis["columns"]
        else 0
    )
    completeness = max(0.0, 100 - avg_missing_pct)

    avg_violation_pct = sum(c["violation_percentage"] for c in range_checks) / len(range_checks) if range_checks else 0
    validity = max(0.0, 100 - avg_violation_pct)

    duplicate_rate = max(0.0, 100 - (duplicates["exact_duplicate_percentage"] or 0))

    funnel_checks = funnel.get("checks", [])
    avg_funnel_violation = sum(c["violation_percentage"] for c in funnel_checks) / len(funnel_checks) if funnel_checks else 0
    funnel_consistency = max(0.0, 100 - avg_funnel_violation)

    if date_quality.get("status") == "unavailable" or not total_rows:
        date_score = 0.0
    else:
        bad_dates = (date_quality.get("invalid_count") or 0) + (date_quality.get("missing_count") or 0) + (date_quality.get("future_date_count") or 0)
        date_score = max(0.0, 100 * (1 - bad_dates / total_rows))

    components = [
        {"component": "Completeness", "value": _safe_round(completeness, 2), "weight": QUALITY_SCORE_WEIGHTS["completeness"]},
        {"component": "Validity (range checks)", "value": _safe_round(validity, 2), "weight": QUALITY_SCORE_WEIGHTS["validity"]},
        {"component": "Duplicate Rate", "value": _safe_round(duplicate_rate, 2), "weight": QUALITY_SCORE_WEIGHTS["duplicate_rate"]},
        {"component": "Funnel Consistency", "value": _safe_round(funnel_consistency, 2), "weight": QUALITY_SCORE_WEIGHTS["funnel_consistency"]},
        {"component": "Date Quality", "value": _safe_round(date_score, 2), "weight": QUALITY_SCORE_WEIGHTS["date_quality"]},
    ]

    score = sum(c["value"] * c["weight"] for c in components)
    score = round(score, 1)

    return {
        "score": score,
        "label": "Analytical Data Quality Score",
        "status": _quality_label(score),
        "status_bands": {"Excellent": ">= 90", "Good": ">= 75", "Watch": ">= 55", "Risk": "< 55"},
        "components": components,
        "note": "This is an analytical summary score derived from the connected dataset's observed structure — not a universal or industry-standard data-quality benchmark.",
    }


# ============================================================
# 10. ANALYTICS READINESS
# ============================================================


def get_analytics_readiness(type_validation, missing_analysis, business_logic, outliers):
    has_type_fail = any(c["result"] == "FAIL" for c in type_validation)
    has_missing_risk = any(c["status"] == "RISK" for c in missing_analysis["columns"])
    has_funnel_risk = any(c["severity"] == "RISK" for c in business_logic.get("checks", []))

    if has_type_fail or has_missing_risk or has_funnel_risk:
        return {
            "status": "NOT READY",
            "explanation": "NOT READY — one or more required analytical fields failed validation, or a material completeness/consistency issue was detected. Review the Data Validation section before relying on downstream analytics.",
        }

    has_outliers = any(o["outlier_count"] > 0 for o in outliers)
    has_watch = any(c["status"] == "WATCH" for c in missing_analysis["columns"]) or any(
        c["severity"] == "WATCH" for c in business_logic.get("checks", [])
    )

    if has_outliers or has_watch:
        return {
            "status": "READY WITH CAUTION",
            "explanation": "READY WITH CAUTION — statistical outliers are present but do not necessarily indicate invalid data; required analytical fields are otherwise populated and consistent.",
        }

    return {
        "status": "READY",
        "explanation": "READY — required analytical fields are populated and no material validation failures were detected.",
    }


# ============================================================
# 11. GOVERNANCE FLAGS
# ============================================================


def get_governance_flags(df, missing_analysis, duplicates, business_logic, outliers, date_quality):
    flags = []

    total_missing = sum(c["missing_count"] for c in missing_analysis["columns"])
    if total_missing == 0:
        flags.append(
            {
                "title": "No Missing Values Detected",
                "severity": "INFO",
                "metric": "0 missing values across all columns",
                "explanation": "Every column in the connected dataset is fully populated.",
                "recommended_action": "No action required.",
            }
        )
    else:
        risk_cols = [c["column"] for c in missing_analysis["columns"] if c["status"] == "RISK"]
        flags.append(
            {
                "title": "Missing Data Present",
                "severity": "RISK" if risk_cols else "WATCH",
                "metric": f"{total_missing:,} missing values",
                "explanation": f"Missing values were found, including in: {', '.join(risk_cols) if risk_cols else 'columns below the RISK threshold'}.",
                "recommended_action": "Review the source extract for these columns before excluding or imputing any records.",
            }
        )

    if duplicates["exact_duplicate_rows"] == 0:
        flags.append(
            {
                "title": "No Exact Duplicate Rows Detected",
                "severity": "INFO",
                "metric": "0 exact duplicate rows",
                "explanation": "No row in the dataset is an exact duplicate of another.",
                "recommended_action": "No action required.",
            }
        )
    else:
        flags.append(
            {
                "title": "Exact Duplicate Rows Present",
                "severity": "WATCH",
                "metric": f"{duplicates['exact_duplicate_rows']:,} duplicate rows ({duplicates['exact_duplicate_percentage']}%)",
                "explanation": "Some rows are exact duplicates of one another.",
                "recommended_action": "Review source-system extraction logic before excluding these records; do not remove them automatically.",
            }
        )

    for check in business_logic.get("checks", []):
        if check["violation_count"] > 0:
            flags.append(
                {
                    "title": f"Funnel Inconsistency: {check['rule']}",
                    "severity": check["severity"],
                    "metric": f"{check['violation_count']:,} rows ({check['violation_percentage']}%)",
                    "explanation": check["explanation"],
                    "recommended_action": "Review source-system definitions before excluding or reinterpreting these records.",
                }
            )

    for o in outliers:
        if o["outlier_count"] > 0 and o["outlier_percentage"] and o["outlier_percentage"] > 5:
            flags.append(
                {
                    "title": f"Elevated Statistical Outliers: {o['field']}",
                    "severity": "WATCH",
                    "metric": f"{o['outlier_count']:,} outliers ({o['outlier_percentage']}%) via {o['method']}",
                    "explanation": f"A statistical outlier share above 5% was detected in {o['field']} using the IQR method. This does not automatically indicate invalid data.",
                    "recommended_action": "Consider reviewing these observations qualitatively before drawing strong conclusions from aggregate statistics; do not remove them automatically.",
                }
            )

    if "ROI" in df.columns:
        negative_roi_count = int((df["ROI"] < 0).sum())
        if negative_roi_count:
            pct = _pct(negative_roi_count, len(df))
            flags.append(
                {
                    "title": "Negative ROI Observed",
                    "severity": "INFO",
                    "metric": f"{negative_roi_count:,} campaigns ({pct}%) with negative ROI",
                    "explanation": "Negative ROI is a legitimate business outcome and is not treated as a data-quality issue.",
                    "recommended_action": "Review these campaigns through business analysis (e.g. Business Insights or Recommendations), not as a data-correction task.",
                }
            )

    if date_quality.get("invalid_count") or date_quality.get("future_date_count"):
        flags.append(
            {
                "title": "Date Quality Issue Detected",
                "severity": "WATCH",
                "metric": f"{date_quality.get('invalid_count', 0):,} unparseable, {date_quality.get('future_date_count', 0):,} future-dated",
                "explanation": "Some Date values could not be parsed or fall after the current date.",
                "recommended_action": "Review these records' source dates before including them in time-series analysis.",
            }
        )

    return flags


# ============================================================
# 12. DATA DICTIONARY
# ============================================================

ROLE_MAP = {
    "Campaign_ID": "IDENTIFIER",
    "Date": "DATE",
    "Campaign_Type": "DIMENSION",
    "Target_Audience": "DIMENSION",
    "Channel_Used": "DIMENSION",
    "Language": "DIMENSION",
    "Customer_Segment": "DIMENSION",
    "Duration": "MEASURE",
    "Impressions": "PERFORMANCE METRIC",
    "Clicks": "PERFORMANCE METRIC",
    "Leads": "PERFORMANCE METRIC",
    "Conversions": "PERFORMANCE METRIC",
    "Engagement_Score": "PERFORMANCE METRIC",
    "Revenue": "TARGET / OUTCOME",
    "Acquisition_Cost": "COST",
    "ROI": "TARGET / OUTCOME",
}


def get_data_dictionary(df):
    total = len(df)
    entries = []
    for col in df.columns:
        non_null_pct = _pct(int(df[col].notnull().sum()), total)
        entries.append(
            {
                "field": col,
                "detected_type": str(df[col].dtype),
                "non_missing_percentage": non_null_pct,
                "unique_values": int(df[col].nunique(dropna=True)),
                "analytical_role": ROLE_MAP.get(col, "UNSPECIFIED"),
            }
        )
    return entries


# ============================================================
# TOP-LEVEL ENTRY POINT
# ============================================================


def get_data_quality_summary(df, data_path):
    if df.empty:
        return {
            "status": "success",
            "dataset_profile": get_dataset_profile(df, data_path),
            "missing_values": {"columns": [], "thresholds": {}, "summary": "No rows available to assess."},
            "type_validation": [],
            "range_validation": [],
            "outliers": [],
            "duplicates": {"exact_duplicate_rows": 0, "exact_duplicate_percentage": None},
            "date_quality": {"status": "unavailable"},
            "business_logic": {"checks": [], "valid_row_count": 0, "violation_row_count": 0},
            "quality_score": {"score": None, "label": "Analytical Data Quality Score", "status": "Unavailable", "components": []},
            "analytics_readiness": {"status": "NOT READY", "explanation": "NOT READY — no campaign data is available to assess."},
            "governance_flags": [],
            "data_dictionary": [],
        }

    dataset_profile = get_dataset_profile(df, data_path)
    missing_values = get_missing_value_analysis(df)
    type_validation = get_type_validation(df)
    range_validation = get_range_validation(df)
    outliers = get_outlier_monitor(df)
    duplicates = get_duplicate_analysis(df)
    date_quality = get_date_quality(df)
    business_logic = get_business_logic_checks(df)
    quality_score = get_quality_score(df, missing_values, range_validation, duplicates, business_logic, date_quality)
    analytics_readiness = get_analytics_readiness(type_validation, missing_values, business_logic, outliers)
    governance_flags = get_governance_flags(df, missing_values, duplicates, business_logic, outliers, date_quality)
    data_dictionary = get_data_dictionary(df)

    return {
        "status": "success",
        "dataset_profile": dataset_profile,
        "missing_values": missing_values,
        "type_validation": type_validation,
        "range_validation": range_validation,
        "outliers": outliers,
        "duplicates": duplicates,
        "date_quality": date_quality,
        "business_logic": business_logic,
        "quality_score": quality_score,
        "analytics_readiness": analytics_readiness,
        "governance_flags": governance_flags,
        "data_dictionary": data_dictionary,
    }
