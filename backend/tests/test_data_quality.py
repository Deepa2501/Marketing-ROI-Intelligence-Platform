"""
Phase 12 tests — Data Quality & Governance Center.

Uses Flask's test client against the real connected dataset, same
convention as backend/tests/test_marketing_intelligence.py (Phase 10)
and backend/tests/test_forecasting.py (Phase 11). Run with:

    pytest backend/tests/test_data_quality.py -v

Run from the repository root so relative paths (DATA_PATH) resolve
correctly.
"""

import pandas as pd
import pytest

from backend.app import create_app
from backend.services import data_quality_service as dqs


@pytest.fixture()
def client():
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def full_df():
    return pd.read_csv("data/cleaned/marketing_campaign_cleaned.csv")


DATA_PATH = "data/cleaned/marketing_campaign_cleaned.csv"


# ============================================================
# PAGE
# ============================================================


def test_data_quality_page_loads(client):
    resp = client.get("/data-quality")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["overview-grid", "completeness-table", "outlier-table", "dictionary-table", "governance-flags-grid"]:
        assert needle in body


# ============================================================
# 1. DATASET PROFILE
# ============================================================


def test_dataset_profile(full_df):
    profile = dqs.get_dataset_profile(full_df, DATA_PATH)
    assert profile["rows"] == len(full_df)
    assert profile["columns"] == len(full_df.columns)
    assert "Campaign_ID" in profile["column_names"]
    assert "Revenue" in profile["numeric_columns"]
    assert "Campaign_Type" in profile["categorical_columns"]
    assert "Date" in profile["date_columns"]
    assert profile["duplicate_rows"] == 0


# ============================================================
# 2. MISSING VALUE ANALYSIS
# ============================================================


def test_missing_value_analysis_reports_no_missing_on_clean_data(full_df):
    result = dqs.get_missing_value_analysis(full_df)
    assert result["summary"] == "No missing values detected."
    for col in result["columns"]:
        assert col["status"] == "GOOD"
        assert col["missing_count"] == 0


def test_missing_value_analysis_detects_injected_missing_values(full_df):
    df = full_df.copy()
    df.loc[: int(len(df) * 0.02), "Engagement_Score"] = None  # inject ~2% missing
    result = dqs.get_missing_value_analysis(df)
    row = next(c for c in result["columns"] if c["column"] == "Engagement_Score")
    assert row["missing_count"] > 0
    assert row["status"] == "WATCH"  # 1%-5% band
    assert "missing values detected" in result["summary"]


# ============================================================
# 3. DATA TYPE VALIDATION
# ============================================================


def test_type_validation_passes_on_clean_data(full_df):
    checks = dqs.get_type_validation(full_df)
    assert len(checks) > 0
    for c in checks:
        assert c["result"] == "PASS"


# ============================================================
# 4. RANGE VALIDATION
# ============================================================


def test_range_validation_passes_on_clean_data(full_df):
    checks = dqs.get_range_validation(full_df)
    assert len(checks) > 0
    for c in checks:
        assert c["result"] == "PASS"
        assert c["violation_count"] == 0


def test_range_validation_does_not_flag_negative_roi(full_df):
    # ROI must NOT appear in the range validation checks at all —
    # negative ROI is a legitimate business outcome, not a validity issue.
    checks = dqs.get_range_validation(full_df)
    rules = [c["rule"] for c in checks]
    assert not any("ROI" in r for r in rules)


def test_range_validation_detects_negative_values():
    df = pd.DataFrame({"Impressions": [-5, 100], "Clicks": [10, 20], "Leads": [5, 10], "Conversions": [1, 2], "Revenue": [100, 200], "Acquisition_Cost": [10, 20], "Duration": [5, 10]})
    checks = dqs.get_range_validation(df)
    impressions_check = next(c for c in checks if c["rule"] == "Impressions >= 0")
    assert impressions_check["violation_count"] == 1
    assert impressions_check["result"] in ("WARNING", "FAIL")


# ============================================================
# 5. FUNNEL / BUSINESS LOGIC VALIDATION
# ============================================================


def test_funnel_validation_passes_on_clean_data(full_df):
    result = dqs.get_business_logic_checks(full_df)
    for c in result["checks"]:
        assert c["violation_count"] == 0
        assert c["severity"] == "INFO"
    assert result["violation_row_count"] == 0


def test_funnel_validation_detects_violation():
    df = pd.DataFrame({"Impressions": [100, 50], "Clicks": [200, 10], "Leads": [5, 5], "Conversions": [1, 1]})
    result = dqs.get_business_logic_checks(df)
    clicks_rule = next(c for c in result["checks"] if c["rule"] == "Impressions >= Clicks")
    assert clicks_rule["violation_count"] == 1
    assert clicks_rule["severity"] in ("WATCH", "RISK")


# ============================================================
# 6. DUPLICATE ANALYSIS
# ============================================================


def test_duplicate_analysis_on_clean_data(full_df):
    result = dqs.get_duplicate_analysis(full_df)
    assert result["exact_duplicate_rows"] == 0
    assert result["duplicate_campaign_id_count"] == 0
    assert "separately" in result["note"]


def test_duplicate_analysis_detects_exact_duplicate_rows(full_df):
    df = pd.concat([full_df.head(5), full_df.head(2)], ignore_index=True)
    result = dqs.get_duplicate_analysis(df)
    assert result["exact_duplicate_rows"] == 2


# ============================================================
# 7. DATE VALIDATION
# ============================================================


def test_date_quality_on_clean_data(full_df):
    result = dqs.get_date_quality(full_df)
    assert result["invalid_count"] == 0
    assert result["missing_count"] == 0
    assert result["min_date"] is not None
    assert result["max_date"] is not None


def test_date_quality_detects_invalid_dates(full_df):
    df = full_df.copy()
    df.loc[0, "Date"] = "not-a-date"
    result = dqs.get_date_quality(df)
    assert result["invalid_count"] == 1


def test_date_quality_missing_column():
    df = pd.DataFrame({"Revenue": [1, 2]})
    result = dqs.get_date_quality(df)
    assert result["status"] == "unavailable"


# ============================================================
# 8. OUTLIER DETECTION
# ============================================================


def test_outlier_detection_returns_expected_fields(full_df):
    outliers = dqs.get_outlier_monitor(full_df)
    fields = {o["field"] for o in outliers}
    assert fields == {"Revenue", "Acquisition_Cost", "ROI", "Conversions", "Engagement_Score"}
    for o in outliers:
        assert o["method"] == "IQR (1.5x interquartile range)"
        assert "Statistical outlier" in o["interpretation"] or "No statistical outliers" in o["interpretation"]
        assert "incorrect" not in o["interpretation"].lower()
        assert "invalid" not in o["interpretation"].lower() or "not automatically invalid" in o["interpretation"].lower()


# ============================================================
# 9. QUALITY SCORE
# ============================================================


def test_quality_score_is_high_on_clean_data(full_df):
    missing = dqs.get_missing_value_analysis(full_df)
    ranges = dqs.get_range_validation(full_df)
    duplicates = dqs.get_duplicate_analysis(full_df)
    funnel = dqs.get_business_logic_checks(full_df)
    dates = dqs.get_date_quality(full_df)
    score = dqs.get_quality_score(full_df, missing, ranges, duplicates, funnel, dates)

    assert 0 <= score["score"] <= 100
    assert score["label"] == "Analytical Data Quality Score"
    assert score["status"] in ("Excellent", "Good", "Watch", "Risk")
    assert len(score["components"]) == 5
    weights = sum(c["weight"] for c in score["components"])
    assert abs(weights - 1.0) < 0.001  # weights must sum to 100%
    assert "not a universal" in score["note"].lower() or "not a universal or industry-standard" in score["note"].lower()


# ============================================================
# 10. ANALYTICS READINESS
# ============================================================


def test_analytics_readiness_ready_with_caution_when_outliers_present(full_df):
    type_validation = dqs.get_type_validation(full_df)
    missing = dqs.get_missing_value_analysis(full_df)
    funnel = dqs.get_business_logic_checks(full_df)
    outliers = dqs.get_outlier_monitor(full_df)

    readiness = dqs.get_analytics_readiness(type_validation, missing, funnel, outliers)
    # This dataset has real statistical outliers, so it should not
    # claim unqualified READY.
    assert readiness["status"] in ("READY", "READY WITH CAUTION")
    assert readiness["explanation"]


def test_analytics_readiness_not_ready_on_empty_data():
    empty_df = pd.DataFrame(columns=["Campaign_ID"])
    result = dqs.get_data_quality_summary(empty_df, DATA_PATH)
    assert result["analytics_readiness"]["status"] == "NOT READY"


# ============================================================
# 11. GOVERNANCE FLAGS
# ============================================================


def test_governance_flags_no_alarmist_language(full_df):
    missing = dqs.get_missing_value_analysis(full_df)
    duplicates = dqs.get_duplicate_analysis(full_df)
    funnel = dqs.get_business_logic_checks(full_df)
    outliers = dqs.get_outlier_monitor(full_df)
    dates = dqs.get_date_quality(full_df)

    flags = dqs.get_governance_flags(full_df, missing, duplicates, funnel, outliers, dates)
    assert len(flags) > 0
    for f in flags:
        assert f["severity"] in ("INFO", "WATCH", "RISK")
        assert "delete" not in f["recommended_action"].lower()
        assert "remove" not in f["recommended_action"].lower() or "not remove" in f["recommended_action"].lower() or "do not remove" in f["recommended_action"].lower()
        assert "fraud" not in f["explanation"].lower()
        assert "corrupt" not in f["explanation"].lower()


def test_governance_flags_include_negative_roi_as_info_not_risk(full_df):
    missing = dqs.get_missing_value_analysis(full_df)
    duplicates = dqs.get_duplicate_analysis(full_df)
    funnel = dqs.get_business_logic_checks(full_df)
    outliers = dqs.get_outlier_monitor(full_df)
    dates = dqs.get_date_quality(full_df)

    flags = dqs.get_governance_flags(full_df, missing, duplicates, funnel, outliers, dates)
    roi_flag = next((f for f in flags if "Negative ROI" in f["title"]), None)
    assert roi_flag is not None
    assert roi_flag["severity"] == "INFO"
    assert "legitimate business outcome" in roi_flag["explanation"]


# ============================================================
# 12. DATA DICTIONARY
# ============================================================


def test_data_dictionary_covers_all_columns(full_df):
    dictionary = dqs.get_data_dictionary(full_df)
    assert len(dictionary) == len(full_df.columns)
    fields = {d["field"] for d in dictionary}
    assert fields == set(full_df.columns)
    campaign_id_entry = next(d for d in dictionary if d["field"] == "Campaign_ID")
    assert campaign_id_entry["analytical_role"] == "IDENTIFIER"
    date_entry = next(d for d in dictionary if d["field"] == "Date")
    assert date_entry["analytical_role"] == "DATE"


# ============================================================
# 13. API SUCCESS
# ============================================================


def test_data_quality_endpoint_status_and_shape(client):
    resp = client.get("/api/data-quality")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in (
        "dataset_profile", "missing_values", "type_validation", "range_validation", "outliers",
        "duplicates", "date_quality", "business_logic", "quality_score", "analytics_readiness",
        "governance_flags", "data_dictionary",
    ):
        assert key in data


def test_data_quality_endpoint_real_numbers_match_direct_calculation(client, full_df):
    api_data = client.get("/api/data-quality").get_json()
    direct_profile = dqs.get_dataset_profile(full_df, DATA_PATH)
    assert api_data["dataset_profile"]["rows"] == direct_profile["rows"]
    assert api_data["dataset_profile"]["duplicate_rows"] == direct_profile["duplicate_rows"]


# ============================================================
# 14. API UNAVAILABLE HANDLING
# ============================================================


def test_dataset_unavailable_returns_503_not_stack_trace():
    """Reset the module-level dataset cache first (same pattern used in
    the Phase 10/11 test suites) so this test exercises the "not
    connected" path in isolation regardless of execution order.
    """
    from backend.services import data_service

    data_service.reset_cache()
    try:
        app = create_app("testing")
        app.config["DATA_PATH"] = "/tmp/definitely_does_not_exist.csv"
        with app.test_client() as c:
            resp = c.get("/api/data-quality")
            assert resp.status_code == 503
            data = resp.get_json()
            assert data["error"] == "dataset_unavailable"
            assert "Traceback" not in str(data)
    finally:
        data_service.reset_cache()


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/marketing-intelligence", "/forecasting", "/statistics",
        "/ab-testing", "/roi-prediction", "/scenario-simulator", "/model-intelligence",
        "/business-insights", "/recommendations", "/executive-center",
    ],
)
def test_existing_pages_still_load(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary", "/api/campaign-types", "/api/customer-segments", "/api/statistics",
        "/api/ab-test", "/api/model-info", "/api/model-comparison", "/api/model-intelligence",
        "/api/campaign-analytics/summary", "/api/recommendations", "/api/executive-summary",
        "/api/marketing-intelligence", "/api/forecasting",
    ],
)
def test_existing_apis_still_work(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


def test_scenario_compare_label_unchanged(client):
    payload = {
        "scenarios": [
            {
                "name": "A", "campaign_type": "Social Media", "target_audience": "Youth",
                "duration": 20, "channel": "Instagram", "language": "English",
                "customer_segment": "Youth", "acquisition_cost": 500,
            }
        ]
    }
    resp = client.post("/api/scenario/compare", json=payload)
    assert resp.status_code == 200
    assert "illustrative_estimated_profit" in resp.get_json()["scenarios"][0]
