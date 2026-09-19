"""
Phase 11 tests — Forecasting & Future Outlook.

Uses Flask's test client against the real connected dataset, same
convention as backend/tests/test_marketing_intelligence.py (Phase 10).
Run with:

    pytest backend/tests/test_forecasting.py -v

Run from the repository root so relative paths (DATA_PATH,
MODEL_METADATA_PATH) resolve correctly.
"""

import pandas as pd
import pytest

from backend.app import create_app
from backend.services import forecasting_service as fs


@pytest.fixture()
def client():
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def full_df():
    return pd.read_csv("data/cleaned/marketing_campaign_cleaned.csv")


# ============================================================
# PAGE
# ============================================================


def test_forecasting_page_loads(client):
    resp = client.get("/forecasting")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["chart-forecast-revenue", "chart-forecast-roi", "chart-forecast-conversions", "trend-summary-table", "backtest-table", "Directional Outlook"]:
        assert needle in body


# ============================================================
# API — SHAPE AND REAL DATA
# ============================================================


def test_forecasting_endpoint_status_and_shape(client):
    resp = client.get("/api/forecasting")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    for key in ("historical", "forecasts", "trend_summary", "backtest", "outlook_signals", "methodology", "limitations"):
        assert key in data


def test_historical_has_real_monthly_points(client):
    data = client.get("/api/forecasting").get_json()
    assert data["historical"]["months_available"] > 0
    assert len(data["historical"]["points"]) == data["historical"]["months_available"]


def test_forecasts_cover_revenue_roi_conversions(client):
    data = client.get("/api/forecasting").get_json()
    metrics = {f["metric"] for f in data["forecasts"]}
    assert metrics == {"Revenue", "ROI", "Conversions"}


def test_forecast_values_are_estimated_not_exact(client):
    data = client.get("/api/forecasting").get_json()
    for f in data["forecasts"]:
        if f["status"] != "ok":
            continue
        assert len(f["forecast_values"]) == 3  # 3-month horizon
        for fv in f["forecast_values"]:
            assert "estimated_value" in fv
        assert f["trend_direction"] in ("UP", "DOWN", "STABLE")
        assert f["evidence_strength"] in ("HIGH", "MEDIUM", "LOW")
        assert "not a guaranteed forecast" in f["caveat"]


def test_backtest_reports_mae_and_rmse_when_available(client):
    data = client.get("/api/forecasting").get_json()
    for metric, bt in data["backtest"].items():
        if bt["status"] == "ok":
            assert bt["mae"] >= 0
            assert bt["rmse"] >= 0
            assert "does not guarantee future accuracy" in bt["note"]


def test_outlook_signals_are_evidence_tagged(client):
    data = client.get("/api/forecasting").get_json()
    signals = data["outlook_signals"]
    assert 0 < len(signals) <= 5
    for s in signals:
        assert s["evidence_basis"] in ("OBSERVED", "PREDICTIVE")
        assert "caution" in s and s["caution"]


def test_methodology_explains_recent_window_approach(client):
    data = client.get("/api/forecasting").get_json()
    methodology = data["methodology"]
    assert len(methodology["steps"]) >= 5
    assert "STABLE" in methodology["trend_classification"] or "%" in methodology["trend_classification"]
    assert methodology["forecast_horizon"] == "Next 3 months"


def test_limitations_list_present(client):
    data = client.get("/api/forecasting").get_json()
    assert len(data["limitations"]) >= 5
    joined = " ".join(data["limitations"]).lower()
    assert "causality" in joined
    assert "guaranteed" in joined or "estimates" in joined


# ============================================================
# TREND DIRECTION LOGIC — direct service tests
# ============================================================


def test_trend_classification_stable_within_tolerance():
    # A perfectly flat series must classify as STABLE.
    assert fs._classify_direction(0.0, 100.0) == "STABLE"


def test_trend_classification_up_above_tolerance():
    # Slope representing +5% of mean per month is well above the
    # documented 1.5% STABLE tolerance.
    assert fs._classify_direction(5.0, 100.0) == "UP"


def test_trend_classification_down_above_tolerance():
    assert fs._classify_direction(-5.0, 100.0) == "DOWN"


# ============================================================
# EVIDENCE STRENGTH LOGIC — direct service tests
# ============================================================


def test_evidence_strength_high_requires_long_stable_history():
    assert fs._evidence_strength(total_months=12, recent_r2=0.6, recent_cv=0.1) == "HIGH"


def test_evidence_strength_low_for_short_history():
    assert fs._evidence_strength(total_months=3, recent_r2=0.9, recent_cv=0.05) == "LOW"


def test_evidence_strength_low_for_high_volatility_and_poor_fit():
    assert fs._evidence_strength(total_months=24, recent_r2=0.01, recent_cv=0.6) == "LOW"


# ============================================================
# ERROR HANDLING / GRACEFUL DEGRADATION
# ============================================================


def test_dataset_unavailable_returns_503_not_stack_trace():
    """Reset the module-level dataset cache first (see the identical
    pattern/comment in test_marketing_intelligence.py) so this test
    exercises the "not connected" path in isolation regardless of
    test execution order, then restores it for later tests.
    """
    from backend.services import data_service

    data_service.reset_cache()
    try:
        app = create_app("testing")
        app.config["DATA_PATH"] = "/tmp/definitely_does_not_exist.csv"
        with app.test_client() as c:
            resp = c.get("/api/forecasting")
            assert resp.status_code == 503
            data = resp.get_json()
            assert data["error"] == "dataset_unavailable"
            assert "Traceback" not in str(data)
    finally:
        data_service.reset_cache()


def test_empty_dataframe_returns_insufficient_history_without_crashing():
    columns = [
        "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration", "Channel_Used",
        "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost",
        "ROI", "Language", "Engagement_Score", "Customer_Segment", "Date",
    ]
    empty_df = pd.DataFrame(columns=columns)
    result = fs.get_forecast_summary(empty_df)
    assert result["status"] == "insufficient_history"


def test_missing_date_column_handled_gracefully(full_df):
    no_date_df = full_df.drop(columns=["Date"])
    result = fs.get_forecast_summary(no_date_df)
    assert result["status"] == "insufficient_history"
    assert "Date" in result["message"]


def test_short_history_returns_per_metric_insufficient_status(full_df):
    df = full_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    short_df = df[df["Date"] < "2024-03-01"].copy()
    short_df["Date"] = short_df["Date"].dt.strftime("%Y-%m-%d")

    result = fs.get_forecast_summary(short_df)
    assert result["status"] == "success"  # top-level call still succeeds
    for f in result["forecasts"]:
        assert f["status"] == "insufficient_history"
        assert f["forecast_values"] == []


def test_backtest_unavailable_for_short_history(full_df):
    df = full_df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    short_df = df[df["Date"] < "2024-04-01"].copy()  # ~3 months
    short_df["Date"] = short_df["Date"].dt.strftime("%Y-%m-%d")

    points, _ = fs._get_monthly_series(short_df)
    bt = fs.get_backtest(points, "total_revenue")
    assert bt["status"] == "unavailable"


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/marketing-intelligence", "/statistics", "/ab-testing",
        "/roi-prediction", "/scenario-simulator", "/model-intelligence", "/business-insights",
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
        "/api/marketing-intelligence",
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
