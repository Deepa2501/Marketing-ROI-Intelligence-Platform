"""
Marketing Analyst Copilot service layer (Phase 14).

A CONTROLLED natural-language analytical interface — not a generic
chatbot. It routes questions to a fixed set of approved analytical
capabilities, each of which delegates to an EXISTING service
(analytics, statistics, forecasting, model intelligence,
recommendations, data quality, budget optimizer). It never generates
a statistic itself.

Design guarantees:
- NO external LLM / API key required. Intent routing is deterministic
  keyword + regex rules, so the platform runs fully locally.
- NO code execution of any kind. User input is only ever lowercased,
  regex-matched, and compared against fixed keyword lists. It is never
  eval'd, exec'd, interpolated into a query, or used to look up an
  attribute by name. Campaign ID lookup uses a parameterized pandas
  equality comparison against a column, never a constructed expression.
- NO fabricated numbers. Every figure in an answer comes from an
  existing service call against the connected dataset. If a question
  can't be served by an approved capability, the Copilot declines.
- Governance wording is preserved: observed association is never
  described as causation, forecasts are always "directional", and
  budget allocations are always "illustrative".
"""

import re

from backend.services import analytics_service
from backend.services import budget_optimizer_service as bos
from backend.services import campaign_analytics_service as cas
from backend.services import data_quality_service as dqs
from backend.services import forecasting_service as fs
from backend.services import recommendation_service as rs
from backend.services import statistics_service
from backend.services.explainability_service import _humanize_feature_name, build_model_intelligence
from backend.services.ml_service import ModelUnavailableError

# ============================================================
# REFUSAL / GUARDRAIL MESSAGES
# ============================================================

INSUFFICIENT_DATA = "I don't have enough validated data in the current platform to answer that reliably."
CAUSAL_REFUSAL = "The current observational data and model do not establish causality."
GUARANTEE_REFUSAL = "The platform cannot guarantee future campaign outcomes."
EXACT_FORECAST_REFUSAL = "The forecasting module provides directional estimates, not guaranteed exact outcomes."

# ============================================================
# INTENTS
# ============================================================

INTENTS = [
    "OVERALL_SUMMARY",
    "CAMPAIGN_TYPE_ANALYSIS",
    "CUSTOMER_SEGMENT_ANALYSIS",
    "TARGET_AUDIENCE_ANALYSIS",
    "CHANNEL_ANALYSIS",
    "CAMPAIGN_LOOKUP",
    "ROI_STATISTICS",
    "AB_TEST",
    "FORECAST",
    "MODEL_INTELLIGENCE",
    "RECOMMENDATIONS",
    "DATA_QUALITY",
    "BUDGET_OPTIMIZATION",
    "HELP",
]

# Metric vocabulary. Order matters — longer/more specific phrases are
# checked first so "average acquisition cost" doesn't match "cost".
METRIC_KEYWORDS = [
    ("average_acquisition_cost", ["average acquisition cost", "avg acquisition cost", "acquisition cost", "cost per campaign", "cpa"]),
    ("average_engagement_score", ["engagement score", "engagement"]),
    ("median_roi", ["median roi"]),
    ("average_roi", ["average roi", "avg roi", "mean roi", "roi"]),
    ("total_revenue", ["total revenue", "revenue", "sales", "turnover"]),
    ("total_conversions", ["conversions", "conversion volume", "converted"]),
    ("campaign_count", ["campaign count", "how many campaigns", "number of campaigns"]),
]

CAMPAIGN_ID_PATTERN = re.compile(r"\b([a-z]{2}-cmp-\d+)\b", re.IGNORECASE)
CURRENCY_PATTERN = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lakhs|crore|crores|k|thousand|million|m)?", re.IGNORECASE)
PLAIN_NUMBER_PATTERN = re.compile(r"\b([\d,]{4,})\b")


def normalize(question):
    """Lowercase, collapse whitespace, strip most punctuation. Purely
    string manipulation — nothing is executed.
    """
    if not isinstance(question, str):
        return ""
    text = question.lower().strip()
    text = re.sub(r"[^\w\s₹.,:/-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_any(text, keywords):
    return any(k in text for k in keywords)


def detect_metric(text):
    for metric, keywords in METRIC_KEYWORDS:
        if _contains_any(text, keywords):
            return metric
    return None


# ============================================================
# INTENT ROUTER (deterministic)
# ============================================================


def detect_intent(text, session_context=None):
    """Deterministic keyword/rule routing. Returns
    (intent, extracted_entities). No ML, no external API.
    """
    entities = {}

    if not text:
        return "HELP", entities

    # --- Campaign ID lookup takes priority (highly specific) ---
    id_match = CAMPAIGN_ID_PATTERN.search(text)
    if id_match:
        entities["campaign_id"] = id_match.group(1).upper()
        return "CAMPAIGN_LOOKUP", entities

    # --- Explicit help ---
    if _contains_any(text, ["what can you do", "what can i ask", "help", "capabilities", "supported questions", "examples"]):
        return "HELP", entities

    # --- Unsupported / guardrail categories (checked before topical routing) ---
    if _contains_any(text, ["cause", "causes", "caused", "causal", "because of", "why did", "does x cause"]):
        return "UNSUPPORTED_CAUSAL", entities
    if _contains_any(text, ["guarantee", "guaranteed", "definitely", "for sure", "certain to", "will definitely"]):
        return "UNSUPPORTED_GUARANTEE", entities
    if _contains_any(text, ["exact revenue", "exactly how much", "tomorrow's revenue", "tomorrow revenue", "precise revenue"]):
        return "UNSUPPORTED_EXACT_FORECAST", entities

    # --- Budget optimization ---
    if _contains_any(text, ["allocate", "allocation", "budget", "spend", "split"]) and not _contains_any(text, ["acquisition cost"]):
        entities.update(_extract_budget_entities(text))
        return "BUDGET_OPTIMIZATION", entities

    # --- Data quality ---
    if _contains_any(text, ["data quality", "data-quality", "missing values", "duplicate", "ready for analysis", "data ready", "quality score", "governance flag"]):
        return "DATA_QUALITY", entities

    # --- Forecast ---
    if _contains_any(text, ["forecast", "outlook", "trend", "next month", "next 3 months", "future", "projection", "trending"]):
        entities["metric"] = detect_metric(text) or "total_revenue"
        return "FORECAST", entities

    # --- A/B test ---
    if _contains_any(text, ["a/b", "ab test", "a b test", "significan", "p-value", "p value", "t-test", "experiment", "vs paid ads", "versus paid ads"]):
        return "AB_TEST", entities

    # --- Model intelligence ---
    if _contains_any(text, ["model", "r2", "r²", "r-squared", "mae", "rmse", "feature importance", "predict", "prediction accuracy", "machine learning"]):
        return "MODEL_INTELLIGENCE", entities

    # --- Recommendations ---
    if _contains_any(text, ["recommend", "recommendation", "what should", "suggest", "advice", "prioritize", "priority"]):
        return "RECOMMENDATIONS", entities

    # --- Dimension-specific analysis ---
    metric = detect_metric(text)
    if metric:
        entities["metric"] = metric

    if _contains_any(text, ["campaign type", "campaign types", "social media", "paid ads", "influencer", "email campaign", "seo"]):
        return "CAMPAIGN_TYPE_ANALYSIS", entities
    if _contains_any(text, ["customer segment", "segment", "working women", "premium shopper", "college student", "tier 2"]):
        return "CUSTOMER_SEGMENT_ANALYSIS", entities
    if _contains_any(text, ["target audience", "audience"]):
        return "TARGET_AUDIENCE_ANALYSIS", entities
    if _contains_any(text, ["channel", "instagram", "youtube", "whatsapp", "facebook", "google"]):
        return "CHANNEL_ANALYSIS", entities

    # --- Negative ROI / ROI statistics ---
    if _contains_any(text, ["negative roi", "losing money", "loss-making", "below zero", "roi distribution", "roi spread"]):
        return "ROI_STATISTICS", entities

    # --- Plain metric questions ---
    if metric:
        # Follow-up context: "what about revenue?" after a dimension question
        if session_context and session_context.get("last_dimension_intent") and _contains_any(text, ["what about", "and ", "how about"]):
            return session_context["last_dimension_intent"], entities
        return "OVERALL_SUMMARY", entities

    # --- Follow-up with no metric and no topic ---
    if session_context and session_context.get("last_dimension_intent") and _contains_any(text, ["what about", "how about"]):
        return session_context["last_dimension_intent"], entities

    if _contains_any(text, ["summary", "overview", "overall", "how are we doing", "how is performance"]):
        return "OVERALL_SUMMARY", entities

    # --- Ambiguous superlatives with no metric ---
    if _contains_any(text, ["best", "worst", "top", "highest", "lowest", "which one"]):
        return "AMBIGUOUS", entities

    return "UNKNOWN", entities


def _extract_budget_entities(text):
    """Extract a budget amount from the question. Handles ₹ notation,
    lakh/crore/k/million multipliers, and plain large numbers.
    """
    entities = {}

    match = CURRENCY_PATTERN.search(text)
    if match:
        raw = match.group(1).replace(",", "")
        try:
            amount = float(raw)
        except ValueError:
            return entities
        unit = (match.group(2) or "").lower()
        multipliers = {"lakh": 100_000, "lakhs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
                       "k": 1_000, "thousand": 1_000, "million": 1_000_000, "m": 1_000_000}
        amount *= multipliers.get(unit, 1)
        entities["total_budget"] = amount
        return entities

    # "1 lakh" / "50 lakh" without a currency symbol
    lakh_match = re.search(r"\b([\d.]+)\s*(lakh|lakhs|crore|crores)\b", text)
    if lakh_match:
        try:
            amount = float(lakh_match.group(1))
            unit = lakh_match.group(2)
            amount *= 10_000_000 if unit.startswith("crore") else 100_000
            entities["total_budget"] = amount
            return entities
        except ValueError:
            pass

    plain = PLAIN_NUMBER_PATTERN.search(text)
    if plain:
        try:
            entities["total_budget"] = float(plain.group(1).replace(",", ""))
        except ValueError:
            pass

    # Dimension override
    if "customer segment" in text or "segment" in text:
        entities["dimension"] = "Customer Segment"
    elif "audience" in text:
        entities["dimension"] = "Target Audience"
    elif "channel" in text:
        entities["dimension"] = "Channel Group"

    return entities


# ============================================================
# ANSWER BUILDERS — each delegates to an EXISTING service
# ============================================================


def _response(intent, answer, evidence_basis, supporting_metrics, source_area, caveats):
    return {
        "status": "success",
        "intent": intent,
        "answer": answer,
        "evidence_basis": evidence_basis,
        "supporting_metrics": supporting_metrics or {},
        "source_area": source_area,
        "caveats": caveats or [],
    }


METRIC_LABELS = {
    "total_revenue": "total revenue",
    "average_roi": "average ROI",
    "median_roi": "median ROI",
    "total_conversions": "total conversions",
    "average_acquisition_cost": "average acquisition cost",
    "average_engagement_score": "average engagement score",
    "campaign_count": "campaign count",
}

NON_CAUSAL_CAVEAT = "This reflects observed historical association, not causation."


def _format_metric_value(metric, value):
    if value is None:
        return "not available"
    if metric in ("average_roi", "median_roi"):
        return f"{value}x"
    if metric in ("total_revenue", "average_acquisition_cost"):
        return f"₹{value:,.2f}"
    if metric in ("total_conversions", "campaign_count"):
        return f"{int(value):,}"
    return f"{value}"


def answer_overall_summary(df, entities):
    summary = analytics_service.get_summary(df)
    metric = entities.get("metric")

    if metric and metric in summary:
        label = METRIC_LABELS.get(metric, metric)
        answer = f"The observed {label} across the connected dataset is {_format_metric_value(metric, summary[metric])}."
    elif metric == "campaign_count":
        answer = f"The connected dataset contains {summary['total_campaigns']:,} campaigns."
    else:
        answer = (
            f"Across {summary['total_campaigns']:,} campaigns, the connected dataset shows "
            f"₹{summary['total_revenue']:,.2f} total revenue, an average ROI of {summary['average_roi']}x, "
            f"{summary['total_conversions']:,} total conversions, and an average acquisition cost of "
            f"₹{summary['average_acquisition_cost']:,.2f}."
        )

    return _response("OVERALL_SUMMARY", answer, "OBSERVED", summary, "Overview", [NON_CAUSAL_CAVEAT])


def _best_group_answer(intent, rows, name_key, metric, dimension_label, source_area, extra_caveats=None):
    if not rows:
        return _response(intent, INSUFFICIENT_DATA, "OBSERVED", {}, source_area, [])

    metric = metric or "average_roi"
    sort_key = {
        "average_roi": "average_roi",
        "median_roi": "median_roi",
        "total_revenue": "total_revenue",
        "total_conversions": "total_conversions",
        "average_acquisition_cost": "average_acquisition_cost",
        "campaign_count": "campaign_count",
    }.get(metric, "average_roi")

    usable = [r for r in rows if r.get(sort_key) is not None]
    if not usable:
        return _response(intent, INSUFFICIENT_DATA, "OBSERVED", {}, source_area, [])

    best = max(usable, key=lambda r: r[sort_key])
    name = best.get(name_key) or best.get("name") or best.get("recorded_channel_combination")
    label = METRIC_LABELS.get(metric, metric)

    answer = (
        f"{name} has the highest observed {label} among {dimension_label} "
        f"({_format_metric_value(metric, best[sort_key])}, across {best.get('campaign_count', 0):,} campaigns)."
    )

    caveats = [NON_CAUSAL_CAVEAT]
    if extra_caveats:
        caveats.extend(extra_caveats)

    return _response(intent, answer, "OBSERVED", best, source_area, caveats)


def answer_campaign_type(df, entities):
    rows = analytics_service.get_campaign_types(df)
    return _best_group_answer("CAMPAIGN_TYPE_ANALYSIS", rows, "name", entities.get("metric"), "campaign types", "Campaign Analytics")


def answer_customer_segment(df, entities):
    rows = analytics_service.get_customer_segments(df)
    return _best_group_answer("CUSTOMER_SEGMENT_ANALYSIS", rows, "name", entities.get("metric"), "customer segments", "Campaign Analytics")


def answer_target_audience(df, entities):
    rows = cas.get_audience_performance(df).get("audiences", [])
    return _best_group_answer("TARGET_AUDIENCE_ANALYSIS", rows, "name", entities.get("metric"), "target audiences", "Campaign Analytics")


def answer_channel(df, entities):
    data = cas.get_channel_performance(df, limit=100)
    rows = [r for r in data.get("channels", []) if r.get("campaign_count", 0) >= 200]
    return _best_group_answer(
        "CHANNEL_ANALYSIS",
        rows,
        "recorded_channel_combination",
        entities.get("metric"),
        "recorded channel groups",
        "Campaign Analytics",
        extra_caveats=[
            "Channel values are recorded multi-channel combinations and are not split into individual channel attribution.",
            "Only channel groups with at least 200 observed campaigns are compared.",
        ],
    )


def answer_campaign_lookup(df, entities):
    campaign_id = entities.get("campaign_id")
    if not campaign_id or "Campaign_ID" not in df.columns:
        return _response("CAMPAIGN_LOOKUP", "Campaign ID not found in the connected dataset.", "OBSERVED", {}, "Campaign Analytics", [])

    # Parameterized equality comparison — never a constructed expression.
    match = df[df["Campaign_ID"].astype(str).str.upper() == campaign_id.upper()]
    if match.empty:
        return _response("CAMPAIGN_LOOKUP", "Campaign ID not found in the connected dataset.", "OBSERVED", {}, "Campaign Analytics", [])

    row = match.iloc[0]
    fields = [
        "Campaign_ID", "Campaign_Type", "Target_Audience", "Channel_Used", "Duration",
        "Acquisition_Cost", "ROI", "Revenue", "Conversions", "Engagement_Score",
        "Customer_Segment", "Date",
    ]
    metrics = {f: (row[f].item() if hasattr(row[f], "item") else row[f]) for f in fields if f in match.columns}

    answer = (
        f"Campaign {metrics.get('Campaign_ID')} is a {metrics.get('Campaign_Type')} campaign targeting "
        f"{metrics.get('Target_Audience')} via {metrics.get('Channel_Used')}. It recorded an observed ROI of "
        f"{metrics.get('ROI')}x on ₹{metrics.get('Acquisition_Cost'):,.2f} acquisition cost, generating "
        f"₹{metrics.get('Revenue'):,.2f} revenue and {int(metrics.get('Conversions', 0)):,} conversions."
    )

    return _response("CAMPAIGN_LOOKUP", answer, "OBSERVED", metrics, "Campaign Analytics", ["Single-campaign figures are historical records, not predictions."])


def answer_roi_statistics(df, entities):
    dist = cas.get_roi_distribution(df)
    stats = dist.get("stats", {})
    if not stats:
        return _response("ROI_STATISTICS", INSUFFICIENT_DATA, "OBSERVED", {}, "Statistical Intelligence", [])

    total = len(df)
    negative_count = int((df["ROI"] < 0).sum()) if "ROI" in df.columns else 0

    answer = (
        f"{negative_count:,} campaigns ({stats.get('pct_roi_lt_0')}% of {total:,}) have negative observed ROI. "
        f"Across the dataset, average ROI is {stats.get('average_roi')}x and median ROI is {stats.get('median_roi')}x, "
        f"ranging from {stats.get('min_roi')}x to {stats.get('max_roi')}x."
    )

    metrics = dict(stats)
    metrics["negative_roi_campaign_count"] = negative_count

    return _response(
        "ROI_STATISTICS", answer, "OBSERVED", metrics, "Statistical Intelligence",
        ["Negative ROI is a legitimate business outcome, not a data-quality issue.", NON_CAUSAL_CAVEAT],
    )


def answer_ab_test(df, entities):
    result = statistics_service.get_ab_test(df)
    if "error" in result:
        return _response("AB_TEST", INSUFFICIENT_DATA, "EXPERIMENTAL", {}, "A/B Testing", [])

    sig = result["welchs_t_test"]["significant_at_0_05"]
    a, b = result["group_a"], result["group_b"]

    answer = (
        f"Comparing {a['label']} (average ROI {a['average_roi']}x, {a['campaign_count']:,} campaigns) against "
        f"{b['label']} (average ROI {b['average_roi']}x, {b['campaign_count']:,} campaigns), Welch's t-test returns "
        f"p = {result['welchs_t_test']['p_value']} with Cohen's d = {result['effect_size']['cohens_d']} "
        f"({result['effect_size']['interpretation']} effect). "
        + ("This difference is statistically significant at the 0.05 level. " if sig else "This difference is NOT statistically significant at the 0.05 level. ")
        + result["business_recommendation"]
    )

    metrics = {
        "group_a": a, "group_b": b,
        "p_value": result["welchs_t_test"]["p_value"],
        "t_statistic": result["welchs_t_test"]["t_statistic"],
        "cohens_d": result["effect_size"]["cohens_d"],
        "significant_at_0_05": sig,
    }

    return _response(
        "AB_TEST", answer, "EXPERIMENTAL", metrics, "A/B Testing",
        ["A statistical test measures whether a difference is distinguishable from chance; it does not establish that one channel causes higher ROI."],
    )


def answer_forecast(df, entities):
    result = fs.get_forecast_summary(df)
    if result.get("status") != "success":
        return _response("FORECAST", result.get("message", INSUFFICIENT_DATA), "PREDICTIVE", {}, "Forecasting & Future Outlook", [])

    metric_map = {"total_revenue": "Revenue", "average_roi": "ROI", "total_conversions": "Conversions"}
    wanted = metric_map.get(entities.get("metric"), "Revenue")

    forecast = next((f for f in result["forecasts"] if f["metric"] == wanted), None)
    if not forecast or forecast.get("status") != "ok":
        return _response("FORECAST", INSUFFICIENT_DATA, "PREDICTIVE", {}, "Forecasting & Future Outlook", [])

    direction_phrase = {"UP": "trending up", "DOWN": "trending down", "STABLE": "broadly stable"}.get(forecast["trend_direction"], "unclear")

    answer = (
        f"Directional outlook suggests {wanted.lower()} is {direction_phrase}, based on a linear trend fit across the "
        f"most recent {forecast['recent_window_months']} months. Evidence strength for this outlook is "
        f"{forecast['evidence_strength']}. The forecast horizon is the next 3 months."
    )

    metrics = {
        "metric": wanted,
        "trend_direction": forecast["trend_direction"],
        "evidence_strength": forecast["evidence_strength"],
        "method": forecast["method"],
        "forecast_values": forecast["forecast_values"],
    }

    return _response(
        "FORECAST", answer, "PREDICTIVE", metrics, "Forecasting & Future Outlook",
        [forecast["caveat"], "Historical patterns may not continue; this is not a guaranteed forecast."],
    )


def answer_model_intelligence(df, entities, model_path, metadata_path):
    try:
        intel = build_model_intelligence(model_path, metadata_path)
    except ModelUnavailableError as exc:
        return _response("MODEL_INTELLIGENCE", str(exc), "PREDICTIVE", {}, "Model Intelligence", [])

    perf = intel["performance_summary"]
    dominance = intel["acquisition_cost_dominance"]
    top_features = intel["feature_importance"]["top_features"]
    top_feature = _humanize_feature_name(top_features[0]["feature"]) if top_features else "not available"

    answer = (
        f"The current model is a {perf['model_name']} with an R² of {perf['r2']:.4f} "
        f"(MAE {perf['mae']:.4f}, RMSE {perf['rmse']:.4f}) on {perf['test_sample_count']:,} held-out test campaigns. "
        f"Its most influential feature is {top_feature}. Note that a cost-only model reaches R² "
        f"{dominance['cost_only_r2']:.4f} versus {dominance['full_early_stage_r2']:.4f} for the full early-stage model — "
        f"Acquisition Cost explains most of the predictive performance. "
        f"The model provides predictive estimates and does not establish causality."
    )

    metrics = {
        "model_name": perf["model_name"],
        "r2": perf["r2"], "mae": perf["mae"], "rmse": perf["rmse"],
        "train_sample_count": perf["train_sample_count"],
        "test_sample_count": perf["test_sample_count"],
        "top_feature": top_feature,
        "cost_only_r2": dominance["cost_only_r2"],
        "full_early_stage_r2": dominance["full_early_stage_r2"],
    }

    return _response(
        "MODEL_INTELLIGENCE", answer, "PREDICTIVE", metrics, "Model Intelligence",
        intel["interpretation"]["what_the_model_cannot_tell_us"][:3],
    )


def answer_recommendations(df, entities, metadata_path):
    result = rs.build_recommendations(df, metadata_path)
    recs = result.get("recommendations", [])
    if not recs:
        return _response("RECOMMENDATIONS", INSUFFICIENT_DATA, "OBSERVED", {}, "Recommendation Intelligence", [])

    top = [r for r in recs if r.get("recommendation_type") != "Risk"][:3]
    lines = [f"{i + 1}. {r['title']} — {r['recommendation']}" for i, r in enumerate(top)]
    answer = "Current recommendations from the platform:\n" + "\n".join(lines)

    metrics = {
        "total_recommendations": result["summary"]["total"],
        "high_priority": result["summary"]["high_priority"],
        "warnings": result["summary"]["warnings"],
        "top_recommendations": [{"title": r["title"], "evidence_basis": r["evidence_basis"], "confidence": r["confidence"]} for r in top],
    }

    bases = sorted({r["evidence_basis"] for r in top})
    evidence = bases[0] if len(bases) == 1 else "OBSERVED"

    return _response(
        "RECOMMENDATIONS", answer, evidence, metrics, "Recommendation Intelligence",
        ["Each recommendation carries its own evidence basis; see the Recommendation Intelligence page for full detail.", NON_CAUSAL_CAVEAT],
    )


def answer_data_quality(df, entities, data_path):
    result = dqs.get_data_quality_summary(df, data_path)
    score = result["quality_score"]
    readiness = result["analytics_readiness"]
    flags = result["governance_flags"]

    notable = [f for f in flags if f["severity"] in ("WATCH", "RISK")]
    flag_text = (
        f" Notable flags: {', '.join(f['title'] for f in notable[:3])}."
        if notable
        else " No WATCH- or RISK-level governance flags were raised."
    )

    answer = (
        f"The Analytical Data Quality Score is {score['score']}/100 ({score['status']}), and analytics readiness is "
        f"{readiness['status']}. {readiness['explanation']}{flag_text}"
    )

    metrics = {
        "quality_score": score["score"],
        "quality_status": score["status"],
        "analytics_readiness": readiness["status"],
        "governance_flag_count": len(flags),
        "notable_flags": [f["title"] for f in notable],
    }

    return _response(
        "DATA_QUALITY", answer, "OBSERVED", metrics, "Data Quality & Governance",
        [score["note"], "Statistical outliers are not automatically invalid records."],
    )


def answer_budget_optimization(df, entities):
    dimension = entities.get("dimension", "Campaign Type")
    total_budget = entities.get("total_budget", 1_000_000)

    try:
        result = bos.get_budget_optimization(
            df, dimension=dimension, total_budget=total_budget,
            min_allocation=5, max_allocation=40, risk_mode="Balanced",
        )
    except bos.InvalidOptimizerInput as exc:
        return _response("BUDGET_OPTIMIZATION", str(exc), "OBSERVED", {}, "Budget Allocation Optimizer", [])

    allocations = sorted(result["strategies"]["risk_adjusted"]["allocations"], key=lambda a: a["allocation_percentage"], reverse=True)
    lines = [f"{a['group']}: {a['allocation_percentage']}% (₹{a['allocated_budget']:,.2f})" for a in allocations]

    answer = (
        f"This is an illustrative historical-performance-based allocation of ₹{total_budget:,.2f} across "
        f"{dimension.lower()} groups, using the default documented constraints (minimum 5%, maximum 40%, Balanced "
        f"risk mode) under the Risk-Adjusted strategy:\n" + "\n".join(lines)
    )

    metrics = {
        "dimension": dimension,
        "total_budget": total_budget,
        "constraints": result["constraints"],
        "allocations": allocations,
    }

    return _response(
        "BUDGET_OPTIMIZATION", answer, "OBSERVED", metrics, "Budget Allocation Optimizer",
        result["limitations"][:4],
    )


def answer_help():
    answer = (
        "I can answer questions grounded in this platform's validated analytics. Supported areas include: "
        "overall summary metrics, campaign type / customer segment / target audience / channel comparisons, "
        "individual campaign lookup by Campaign ID, ROI statistics, A/B test results, forecast direction, "
        "model performance and limitations, recommendations, data quality, and illustrative budget allocation."
    )
    return _response("HELP", answer, "OBSERVED", {"supported_intents": INTENTS}, "Copilot", [])


# ============================================================
# CAPABILITIES
# ============================================================

CAPABILITIES = [
    {"category": "Overall Summary", "intent": "OVERALL_SUMMARY", "source_area": "Overview",
     "examples": ["What is the average ROI?", "What is the total revenue?", "How many campaigns are there?"]},
    {"category": "Campaign Type Analysis", "intent": "CAMPAIGN_TYPE_ANALYSIS", "source_area": "Campaign Analytics",
     "examples": ["Which campaign type has the highest average ROI?", "Which campaign type has the highest conversion volume?"]},
    {"category": "Customer Segment Analysis", "intent": "CUSTOMER_SEGMENT_ANALYSIS", "source_area": "Campaign Analytics",
     "examples": ["Which customer segment generates the highest revenue?", "Which segment has the best average ROI?"]},
    {"category": "Target Audience Analysis", "intent": "TARGET_AUDIENCE_ANALYSIS", "source_area": "Campaign Analytics",
     "examples": ["Which target audience has the highest average ROI?"]},
    {"category": "Channel Analysis", "intent": "CHANNEL_ANALYSIS", "source_area": "Campaign Analytics",
     "examples": ["Which channel group has the highest observed ROI?"]},
    {"category": "Campaign Lookup", "intent": "CAMPAIGN_LOOKUP", "source_area": "Campaign Analytics",
     "examples": ["Show me campaign NY-CMP-1000"]},
    {"category": "ROI Statistics", "intent": "ROI_STATISTICS", "source_area": "Statistical Intelligence",
     "examples": ["How many campaigns have negative ROI?", "What does the ROI distribution look like?"]},
    {"category": "A/B Testing", "intent": "AB_TEST", "source_area": "A/B Testing",
     "examples": ["What does the Social Media vs Paid Ads A/B test show?", "Is the difference statistically significant?"]},
    {"category": "Forecasting", "intent": "FORECAST", "source_area": "Forecasting & Future Outlook",
     "examples": ["What is the current revenue outlook?", "What is the ROI trend direction?"]},
    {"category": "Model Intelligence", "intent": "MODEL_INTELLIGENCE", "source_area": "Model Intelligence",
     "examples": ["What is the ROI model's R²?", "What is the most important model feature?", "Can the model prove campaign strategy causes ROI?"]},
    {"category": "Recommendations", "intent": "RECOMMENDATIONS", "source_area": "Recommendation Intelligence",
     "examples": ["What are the main recommendations?", "What should we prioritize?"]},
    {"category": "Data Quality", "intent": "DATA_QUALITY", "source_area": "Data Quality & Governance",
     "examples": ["Is the dataset ready for analysis?", "What is the data-quality score?"]},
    {"category": "Budget Optimization", "intent": "BUDGET_OPTIMIZATION", "source_area": "Budget Allocation Optimizer",
     "examples": ["How should ₹1 lakh be allocated across campaign types?"]},
]


def get_capabilities():
    return {
        "status": "success",
        "capabilities": CAPABILITIES,
        "supported_intents": INTENTS,
        "notes": [
            "The Copilot answers only from this platform's validated analytical services.",
            "It does not use an external AI service and never invents statistics.",
            "Questions that require causal claims or guaranteed future outcomes are declined by design.",
        ],
    }


# ============================================================
# MAIN ENTRY POINT
# ============================================================


class InvalidQuestion(ValueError):
    """Raised for a missing/empty/invalid question. Routes turn this
    into a clean HTTP 400.
    """


MAX_QUESTION_LENGTH = 500


def ask(df, question, session_context=None, data_path=None, model_path=None, metadata_path=None):
    """Route a natural-language question to an approved capability.

    session_context is a plain dict carried by the caller (the Flask
    session) for lightweight follow-up support. No personal data is
    stored and no database is used.
    """
    if not isinstance(question, str) or not question.strip():
        raise InvalidQuestion("'question' is required and must be a non-empty string.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise InvalidQuestion(f"'question' must be {MAX_QUESTION_LENGTH} characters or fewer.")

    session_context = session_context if isinstance(session_context, dict) else {}
    text = normalize(question)
    intent, entities = detect_intent(text, session_context)

    # --- Guardrail intents ---
    if intent == "UNSUPPORTED_CAUSAL":
        return _response("UNSUPPORTED", CAUSAL_REFUSAL, "OBSERVED", {}, "Governance",
                         ["Observational data and the current model measure association, not causation."]), session_context
    if intent == "UNSUPPORTED_GUARANTEE":
        return _response("UNSUPPORTED", GUARANTEE_REFUSAL, "PREDICTIVE", {}, "Governance",
                         ["Forecasts and model estimates are directional decision support, not guarantees."]), session_context
    if intent == "UNSUPPORTED_EXACT_FORECAST":
        return _response("UNSUPPORTED", EXACT_FORECAST_REFUSAL, "PREDICTIVE", {}, "Forecasting & Future Outlook",
                         ["The forecasting module produces directional outlooks over a 3-month horizon."]), session_context
    if intent == "AMBIGUOUS":
        return _response("CLARIFICATION_NEEDED",
                         "Do you mean best by average ROI, revenue, conversions, or acquisition cost?",
                         "OBSERVED", {}, "Copilot",
                         ["Please specify a metric so the comparison is unambiguous."]), session_context
    if intent == "UNKNOWN":
        return _response("UNSUPPORTED", INSUFFICIENT_DATA, "OBSERVED", {}, "Copilot",
                         ["Ask about supported areas, or send 'help' to see what I can answer."]), session_context
    if intent == "HELP":
        return answer_help(), session_context

    # --- Dispatch to the approved capability ---
    handlers_needing_df = {
        "OVERALL_SUMMARY": lambda: answer_overall_summary(df, entities),
        "CAMPAIGN_TYPE_ANALYSIS": lambda: answer_campaign_type(df, entities),
        "CUSTOMER_SEGMENT_ANALYSIS": lambda: answer_customer_segment(df, entities),
        "TARGET_AUDIENCE_ANALYSIS": lambda: answer_target_audience(df, entities),
        "CHANNEL_ANALYSIS": lambda: answer_channel(df, entities),
        "CAMPAIGN_LOOKUP": lambda: answer_campaign_lookup(df, entities),
        "ROI_STATISTICS": lambda: answer_roi_statistics(df, entities),
        "AB_TEST": lambda: answer_ab_test(df, entities),
        "FORECAST": lambda: answer_forecast(df, entities),
        "MODEL_INTELLIGENCE": lambda: answer_model_intelligence(df, entities, model_path, metadata_path),
        "RECOMMENDATIONS": lambda: answer_recommendations(df, entities, metadata_path),
        "DATA_QUALITY": lambda: answer_data_quality(df, entities, data_path),
        "BUDGET_OPTIMIZATION": lambda: answer_budget_optimization(df, entities),
    }

    handler = handlers_needing_df.get(intent)
    if handler is None:
        return _response("UNSUPPORTED", INSUFFICIENT_DATA, "OBSERVED", {}, "Copilot", []), session_context

    result = handler()

    # Update lightweight session context for follow-ups.
    if intent in ("CAMPAIGN_TYPE_ANALYSIS", "CUSTOMER_SEGMENT_ANALYSIS", "TARGET_AUDIENCE_ANALYSIS", "CHANNEL_ANALYSIS"):
        session_context["last_dimension_intent"] = intent
    if entities.get("metric"):
        session_context["last_metric"] = entities["metric"]

    return result, session_context
