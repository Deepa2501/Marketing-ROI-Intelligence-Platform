"""
Phase 13 tests — Budget Allocation Optimizer.

Same conventions as the Phase 10/11/12 suites. Run with:

    pytest backend/tests/test_budget_optimizer.py -v

Run from the repository root so relative paths resolve correctly.
"""

import pandas as pd
import pytest

from backend.app import create_app
from backend.services import budget_optimizer_service as bos
from backend.services.budget_optimizer_service import InvalidOptimizerInput

DIMENSIONS = ["Campaign Type", "Customer Segment", "Target Audience", "Channel Group"]
STRATEGY_KEYS = ["equal", "performance", "risk_adjusted"]


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


def test_budget_optimizer_page_loads(client):
    resp = client.get("/budget-optimizer")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["optimize-btn", "allocation-table", "chart-allocation", "comparison-table", "guardrails-list"]:
        assert needle in body


# ============================================================
# 1. DEFAULT OPTIMIZATION
# ============================================================


def test_default_optimization(full_df):
    result = bos.get_budget_optimization(full_df)
    assert result["status"] == "success"
    assert result["dimension"] == "Campaign Type"
    assert result["total_budget"] == 1_000_000
    assert result["constraints"]["min_allocation_percentage"] == 5
    assert result["constraints"]["max_allocation_percentage"] == 40
    assert result["constraints"]["risk_mode"] == "Balanced"
    for key in ("groups", "strategies", "comparison", "assumptions", "limitations"):
        assert key in result


# ============================================================
# 2-5. ALL FOUR DIMENSIONS
# ============================================================


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_each_dimension_produces_valid_allocation(full_df, dimension):
    result = bos.get_budget_optimization(full_df, dimension=dimension)
    assert result["dimension"] == dimension
    assert result["constraints"]["group_count"] > 0
    assert len(result["groups"]) == result["constraints"]["group_count"]
    for key in STRATEGY_KEYS:
        assert key in result["strategies"]
        assert len(result["strategies"][key]["allocations"]) == result["constraints"]["group_count"]


def test_channel_group_does_not_split_multichannel_records(full_df):
    """Channel Group must use recorded Channel_Used values as-is — a
    combination like "WhatsApp, Google" stays one group and is never
    split into separate per-channel attribution.
    """
    result = bos.get_budget_optimization(full_df, dimension="Channel Group")
    group_names = {g["group"] for g in result["groups"]}
    # Every returned group name must exist verbatim in the source column.
    source_values = set(full_df["Channel_Used"].astype(str).unique())
    assert group_names.issubset(source_values)
    # The assumptions must document the no-splitting behaviour.
    assert any("never split into individual channel attribution" in a for a in result["assumptions"])


# ============================================================
# 6. ALLOCATION SUMS TO 100%
# ============================================================


@pytest.mark.parametrize("dimension", DIMENSIONS)
def test_allocations_sum_to_100(full_df, dimension):
    result = bos.get_budget_optimization(full_df, dimension=dimension)
    for key in STRATEGY_KEYS:
        total = sum(a["allocation_percentage"] for a in result["strategies"][key]["allocations"])
        assert abs(total - 100) < 0.011, f"{dimension}/{key} sums to {total}"


def test_allocated_budget_sums_to_total_budget(full_df):
    budget = 2_500_000
    result = bos.get_budget_optimization(full_df, total_budget=budget)
    for key in STRATEGY_KEYS:
        total = sum(a["allocated_budget"] for a in result["strategies"][key]["allocations"])
        assert abs(total - budget) < budget * 0.0002


# ============================================================
# 7-8. MIN / MAX CONSTRAINTS
# ============================================================


def test_minimum_constraint_respected(full_df):
    result = bos.get_budget_optimization(full_df, min_allocation=15, max_allocation=40)
    for key in STRATEGY_KEYS:
        for a in result["strategies"][key]["allocations"]:
            assert a["allocation_percentage"] >= 15 - 0.011


def test_maximum_constraint_respected(full_df):
    result = bos.get_budget_optimization(full_df, min_allocation=5, max_allocation=25)
    for key in STRATEGY_KEYS:
        for a in result["strategies"][key]["allocations"]:
            assert a["allocation_percentage"] <= 25 + 0.011


def test_both_constraints_respected_simultaneously(full_df):
    result = bos.get_budget_optimization(full_df, min_allocation=10, max_allocation=25)
    for a in result["strategies"]["risk_adjusted"]["allocations"]:
        assert 10 - 0.011 <= a["allocation_percentage"] <= 25 + 0.011


# ============================================================
# 9. INFEASIBLE CONSTRAINTS
# ============================================================


def test_infeasible_minimum_raises(full_df):
    # 5 groups x 30% minimum = 150% > 100%
    with pytest.raises(InvalidOptimizerInput) as exc:
        bos.get_budget_optimization(full_df, min_allocation=30, max_allocation=40)
    assert "infeasible" in str(exc.value).lower()


def test_infeasible_maximum_raises(full_df):
    # 5 groups x 15% maximum = 75% < 100%
    with pytest.raises(InvalidOptimizerInput) as exc:
        bos.get_budget_optimization(full_df, min_allocation=5, max_allocation=15)
    assert "infeasible" in str(exc.value).lower()


# ============================================================
# 10-12. INVALID INPUTS
# ============================================================


@pytest.mark.parametrize("budget", [0, -100, "lots", None])
def test_invalid_budget_raises(full_df, budget):
    with pytest.raises(InvalidOptimizerInput):
        bos.get_budget_optimization(full_df, total_budget=budget)


def test_invalid_dimension_raises(full_df):
    with pytest.raises(InvalidOptimizerInput) as exc:
        bos.get_budget_optimization(full_df, dimension="Zodiac Sign")
    assert "dimension" in str(exc.value)


def test_invalid_risk_mode_raises(full_df):
    with pytest.raises(InvalidOptimizerInput) as exc:
        bos.get_budget_optimization(full_df, risk_mode="YOLO")
    assert "risk_mode" in str(exc.value)


def test_min_greater_than_max_raises(full_df):
    with pytest.raises(InvalidOptimizerInput):
        bos.get_budget_optimization(full_df, min_allocation=50, max_allocation=20)


def test_negative_min_and_over_100_max_raise(full_df):
    with pytest.raises(InvalidOptimizerInput):
        bos.get_budget_optimization(full_df, min_allocation=-5)
    with pytest.raises(InvalidOptimizerInput):
        bos.get_budget_optimization(full_df, max_allocation=150)


# ============================================================
# 13-15. THE THREE STRATEGIES
# ============================================================


def test_equal_strategy_allocates_evenly(full_df):
    result = bos.get_budget_optimization(full_df)
    allocations = result["strategies"]["equal"]["allocations"]
    expected = 100 / len(allocations)
    for a in allocations:
        assert abs(a["allocation_percentage"] - expected) < 0.011


def test_performance_strategy_favours_higher_scores(full_df):
    result = bos.get_budget_optimization(full_df)
    allocations = result["strategies"]["performance"]["allocations"]
    best = max(allocations, key=lambda a: a["allocation_score"])
    worst = min(allocations, key=lambda a: a["allocation_score"])
    assert best["allocation_percentage"] > worst["allocation_percentage"]


def test_risk_adjusted_strategy_differs_by_risk_mode(full_df):
    conservative = bos.get_budget_optimization(full_df, risk_mode="Conservative")
    performance_focused = bos.get_budget_optimization(full_df, risk_mode="Performance-focused")

    def top_share(res):
        return max(a["allocation_percentage"] for a in res["strategies"]["risk_adjusted"]["allocations"])

    # Performance-focused amplifies score differences, so its largest
    # allocation should be at least as concentrated as Conservative's.
    assert top_share(performance_focused) >= top_share(conservative)


def test_all_strategies_present_with_required_fields(full_df):
    result = bos.get_budget_optimization(full_df)
    for key in STRATEGY_KEYS:
        for a in result["strategies"][key]["allocations"]:
            for field in ("group", "allocation_percentage", "allocated_budget", "allocation_score", "risk_level"):
                assert field in a
            assert a["risk_level"] in ("LOW", "MEDIUM", "HIGH")


# ============================================================
# SCORING / RISK LOGIC
# ============================================================


def test_allocation_score_bounded_and_weighted(full_df):
    result = bos.get_budget_optimization(full_df)
    weights = result["scoring_methodology"]["allocation_score_weights"]
    assert abs(sum(weights.values()) - 1.0) < 0.001
    for g in result["groups"]:
        assert 0 <= g["allocation_score"] <= 100
        assert set(g["allocation_score_components"]) == {"roi_performance", "roi_consistency", "cost_efficiency", "evidence_volume"}


def test_risk_score_uses_three_signals_not_volatility_alone(full_df):
    result = bos.get_budget_optimization(full_df)
    for g in result["groups"]:
        assert 0 <= g["risk_score"] <= 100
        assert set(g["risk_score_components"]) == {"roi_volatility", "negative_roi_share", "evidence_scarcity"}


def test_scoring_methodology_disclaims_industry_standard(full_df):
    result = bos.get_budget_optimization(full_df)
    note = result["scoring_methodology"]["allocation_score_note"].lower()
    assert "not a standard industry metric" in note


# ============================================================
# 16-18. API
# ============================================================


def test_api_get_returns_default_optimization(client):
    resp = client.get("/api/budget-optimizer")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["dimension"] == "Campaign Type"
    assert data["total_budget"] == 1_000_000


def test_api_post_accepts_custom_parameters(client):
    payload = {"dimension": "Customer Segment", "total_budget": 500000, "min_allocation": 10, "max_allocation": 30, "risk_mode": "Conservative"}
    resp = client.post("/api/budget-optimizer", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dimension"] == "Customer Segment"
    assert data["total_budget"] == 500000
    assert data["constraints"]["risk_mode"] == "Conservative"
    for a in data["strategies"]["risk_adjusted"]["allocations"]:
        assert 10 - 0.011 <= a["allocation_percentage"] <= 30 + 0.011


@pytest.mark.parametrize(
    "payload",
    [
        {"min_allocation": 30, "max_allocation": 40},   # infeasible min
        {"min_allocation": 5, "max_allocation": 15},    # infeasible max
        {"total_budget": 0},
        {"total_budget": -1000},
        {"total_budget": "lots"},
        {"dimension": "Not A Dimension"},
        {"risk_mode": "Reckless"},
        {"min_allocation": -1},
        {"max_allocation": 101},
        {"min_allocation": 60, "max_allocation": 10},
    ],
)
def test_api_post_validation_errors_return_400(client, payload):
    resp = client.post("/api/budget-optimizer", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "invalid_input"
    assert data["message"]
    assert "Traceback" not in str(data)


def test_api_post_with_empty_body_uses_defaults(client):
    resp = client.post("/api/budget-optimizer", json={})
    assert resp.status_code == 200
    assert resp.get_json()["dimension"] == "Campaign Type"


# ============================================================
# 19. DATASET UNAVAILABLE
# ============================================================


def test_dataset_unavailable_returns_503_not_stack_trace():
    from backend.services import data_service

    data_service.reset_cache()
    try:
        app = create_app("testing")
        app.config["DATA_PATH"] = "/tmp/definitely_does_not_exist.csv"
        with app.test_client() as c:
            for resp in (c.get("/api/budget-optimizer"), c.post("/api/budget-optimizer", json={})):
                assert resp.status_code == 503
                data = resp.get_json()
                assert data["error"] == "dataset_unavailable"
                assert "Traceback" not in str(data)
    finally:
        data_service.reset_cache()


# ============================================================
# 20. NO DATASET MUTATION
# ============================================================


def test_optimizer_does_not_mutate_dataset(full_df):
    before_shape = full_df.shape
    before_columns = list(full_df.columns)
    before_hash = pd.util.hash_pandas_object(full_df).sum()

    for dimension in DIMENSIONS:
        bos.get_budget_optimization(full_df, dimension=dimension)

    assert full_df.shape == before_shape
    assert list(full_df.columns) == before_columns
    assert pd.util.hash_pandas_object(full_df).sum() == before_hash


# ============================================================
# ANALYTICAL SAFETY / WORDING
# ============================================================


def test_no_causal_or_guarantee_language_in_response(full_df):
    import json

    result = bos.get_budget_optimization(full_df)
    text = json.dumps(result).lower()
    assert "optimal allocation" not in text
    assert "guaranteed profit" not in text
    assert "will generate" not in text
    # "causes" may only ever appear inside an explicit negation.
    if "causes" in text:
        assert "does not establish that" in text


def test_explanations_use_non_causal_wording(full_df):
    result = bos.get_budget_optimization(full_df)
    assert len(result["explanations"]) > 0
    for e in result["explanations"]:
        assert "allocation score" in e["reason"].lower()
        assert "does not establish" in e["caution"]
        assert e["evidence_strength"].startswith("OBSERVED")


def test_limitations_present_and_complete(full_df):
    result = bos.get_budget_optimization(full_df)
    joined = " ".join(result["limitations"]).lower()
    assert "causality" in joined
    assert "not an industry-standard metric" in joined
    assert "illustrative" in joined
    assert "experimentally" in joined


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/marketing-intelligence", "/forecasting", "/statistics",
        "/ab-testing", "/roi-prediction", "/scenario-simulator", "/model-intelligence",
        "/business-insights", "/recommendations", "/executive-center", "/data-quality",
    ],
)
def test_existing_pages_still_load(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary", "/api/campaign-types", "/api/customer-segments", "/api/statistics",
        "/api/ab-test", "/api/model-info", "/api/model-comparison", "/api/model-intelligence",
        "/api/campaign-analytics/summary", "/api/recommendations", "/api/executive-summary",
        "/api/marketing-intelligence", "/api/forecasting", "/api/data-quality",
    ],
)
def test_existing_apis_still_work(client, path):
    assert client.get(path).status_code == 200


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
