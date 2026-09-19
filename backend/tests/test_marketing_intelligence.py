"""
Phase 10 tests — Marketing Intelligence Upgrade.

Uses Flask's test client against the real connected dataset (no mocking
of data_service), so these tests exercise the actual aggregation code
paths. Run with:

    pytest backend/tests/test_marketing_intelligence.py -v

Run from the repository root so relative paths (DATA_PATH, MODEL_PATH)
resolve correctly, same as the existing app.
"""

import pandas as pd
import pytest

from backend.app import create_app
from backend.services import intelligence_service as ins


@pytest.fixture()
def client():
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def empty_df():
    columns = [
        "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration", "Channel_Used",
        "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost",
        "ROI", "Language", "Engagement_Score", "Customer_Segment", "Date",
    ]
    return pd.DataFrame(columns=columns)


# ============================================================
# PAGE
# ============================================================


def test_marketing_intelligence_page_loads(client):
    resp = client.get("/marketing-intelligence")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["chart-trend-revenue", "chart-driver-correlations", "chart-funnel", "chart-efficiency-buckets", "insights-grid"]:
        assert needle in body


# ============================================================
# AGGREGATED ENDPOINT
# ============================================================


def test_marketing_intelligence_endpoint_status_and_shape(client):
    resp = client.get("/api/marketing-intelligence")
    assert resp.status_code == 200
    data = resp.get_json()
    for key in ("trends", "drivers", "funnel", "efficiency", "insights"):
        assert key in data


def test_trends_have_real_monthly_points(client):
    data = client.get("/api/marketing-intelligence").get_json()
    points = data["trends"]["points"]
    assert len(points) > 0
    for p in points:
        assert p["total_revenue"] is not None
        assert p["average_roi"] is not None


def test_funnel_stage_order_and_drop_off(client):
    data = client.get("/api/marketing-intelligence").get_json()
    stages = data["funnel"]["stages"]
    stage_names = [s["stage"] for s in stages]
    assert stage_names == ["Impressions", "Clicks", "Leads", "Conversions"]
    # Impressions is the funnel entry point and has no prior-stage rate.
    assert stages[0]["stage_conversion_rate_pct"] is None
    # Every later stage must report a rate between 0 and 100.
    for s in stages[1:]:
        assert 0 <= s["stage_conversion_rate_pct"] <= 100
    assert data["funnel"]["biggest_drop_off_stage"] in stage_names


def test_efficiency_buckets_and_ranking(client):
    data = client.get("/api/marketing-intelligence").get_json()
    efficiency = data["efficiency"]
    assert len(efficiency["cost_buckets"]) > 0
    assert efficiency["most_efficient_campaign_type"] is not None
    assert efficiency["least_efficient_campaign_type"] is not None
    # Most efficient must be >= least efficient by definition of the ranking.
    assert (
        efficiency["most_efficient_campaign_type"]["conversions_per_unit_cost"]
        >= efficiency["least_efficient_campaign_type"]["conversions_per_unit_cost"]
    )


def test_drivers_include_correlation_disclaimer_and_no_causal_claims(client):
    data = client.get("/api/marketing-intelligence").get_json()
    drivers = data["drivers"]
    assert "not proof of causation" in drivers["correlation_disclaimer"]
    assert len(drivers["roi_correlations"]) > 0
    for corr in drivers["roi_correlations"]:
        assert -1 <= corr["correlation_with_roi"] <= 1


def test_insights_are_evidence_tagged(client):
    data = client.get("/api/marketing-intelligence").get_json()
    insights = data["insights"]
    assert len(insights) > 0
    for item in insights:
        assert item["evidence_basis"] in ("OBSERVED", "PREDICTIVE", "EXPERIMENTAL", "OBSERVED + PREDICTIVE")
        assert "causes" not in item["finding"].lower() or "does not" in item["finding"].lower()


# ============================================================
# GRANULAR ENDPOINTS
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/api/marketing-intelligence/trends",
        "/api/marketing-intelligence/drivers",
        "/api/marketing-intelligence/funnel",
        "/api/marketing-intelligence/efficiency",
    ],
)
def test_granular_endpoints_return_200(client, path):
    resp = client.get(path)
    assert resp.status_code == 200


# ============================================================
# ERROR HANDLING
# ============================================================


def test_dataset_unavailable_returns_503_not_stack_trace():
    """The dataset cache in data_service is a module-level singleton
    (by design, so the CSV is loaded once per process — see Phase 1).
    Since other tests in this session load the real dataset, we must
    explicitly reset that cache here to test the "not connected" path
    in isolation, then restore it so later tests still see real data.
    """
    from backend.services import data_service

    data_service.reset_cache()
    try:
        app = create_app("testing")
        app.config["DATA_PATH"] = "/tmp/definitely_does_not_exist.csv"
        with app.test_client() as c:
            resp = c.get("/api/marketing-intelligence")
            assert resp.status_code == 503
            data = resp.get_json()
            assert data["error"] == "dataset_unavailable"
            assert "Traceback" not in str(data)
    finally:
        data_service.reset_cache()


# ============================================================
# EMPTY / MISSING DATA HANDLING (direct service tests)
# ============================================================


def test_service_handles_empty_dataframe_without_crashing(empty_df):
    result = ins.build_marketing_intelligence(empty_df, "reports/roi_model_metadata.json")
    assert result["trends"]["points"] == []
    assert result["funnel"]["stages"] == []
    assert result["efficiency"]["cost_buckets"] == []
    assert result["insights"] == []


def test_trends_handles_missing_date_column():
    df = pd.read_csv("data/cleaned/marketing_campaign_cleaned.csv").drop(columns=["Date"])
    result = ins.get_trends(df)
    assert result["points"] == []
    assert "note" in result


def test_funnel_handles_missing_funnel_columns():
    df = pd.read_csv("data/cleaned/marketing_campaign_cleaned.csv").drop(columns=["Leads"])
    result = ins.get_funnel(df)
    assert result["stages"] == []
    assert "note" in result


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/statistics", "/ab-testing", "/roi-prediction",
        "/scenario-simulator", "/model-intelligence", "/business-insights",
        "/recommendations", "/executive-center",
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
