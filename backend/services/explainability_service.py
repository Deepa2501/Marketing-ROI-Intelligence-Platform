"""
Model Intelligence & Explainability service layer (Phase 6).

This module does NOT compute anything ml_service doesn't already
compute. It composes ml_service.get_metadata() / get_feature_importance()
/ predict_roi() into the richer, governance-aware payloads the Phase 6
Model Intelligence page and explain-prediction endpoint need.

Every number here comes from reports/roi_model_metadata.json (written
by python/train_roi_model.py) or from the trained pipeline itself via
ml_service.get_feature_importance(). Nothing is hardcoded or invented.
The only "authored" content in this file is static governance/
explanatory text (what the model can/cannot tell you, limitations,
badge copy) — not a computed metric.
"""

from backend.services import ml_service
from backend.services.ml_service import ModelUnavailableError  # re-exported for routes

GOVERNANCE_BADGE = "Decision Support — Not Causal Inference"

MODEL_CAN_TELL_US = [
    "Estimate expected ROI from planning-stage inputs before a campaign launches.",
    "Compare campaign scenarios against each other on a like-for-like basis.",
    "Support early budget planning and prioritization discussions.",
    "Identify patterns associated with higher or lower predicted ROI in historical data.",
    "Help prioritize which planned campaigns deserve closer manual evaluation.",
]

MODEL_CANNOT_TELL_US = [
    "It does not prove that any input variable causes ROI to change.",
    "It does not guarantee future ROI for any real campaign.",
    "It does not establish that campaign strategy variables independently drive ROI.",
    "Predictions are dependent on patterns in historical data and may not hold for novel situations.",
    "Unusual or out-of-distribution campaigns may produce less reliable predictions.",
]

MODEL_LIMITATIONS = [
    {
        "title": "Historical-data dependence",
        "detail": "The model learned patterns from past campaigns only; it cannot account for conditions it has never seen.",
    },
    {
        "title": "Acquisition Cost dominance",
        "detail": "Acquisition Cost explains most of the model's predictive performance — see the dedicated section below.",
    },
    {
        "title": "Strategy-only signal is weak",
        "detail": "Campaign strategy variables alone (no cost) have almost no predictive power in this dataset.",
    },
    {
        "title": "ROI distribution skew",
        "detail": "The underlying ROI distribution contains outliers and skew, which can widen prediction error for extreme cases.",
    },
    {
        "title": "Predictions are estimates",
        "detail": "Every predicted value is a model estimate, not a guaranteed outcome.",
    },
    {
        "title": "Performance may drift",
        "detail": "Model accuracy on future campaigns may differ from the test-set metrics shown here if market conditions change.",
    },
    {
        "title": "No causal claims",
        "detail": "The model reflects statistical association learned from data, not a causal mechanism.",
    },
]

PERFORMANCE_EXPLANATION = (
    "R² indicates how much variation in observed ROI is explained by the model on the test set. "
    "MAE represents the average absolute prediction error in ROI points."
)

ACQUISITION_COST_EXPLANATION = (
    "Most of the predictive performance is already captured by Acquisition Cost alone. Adding the "
    "remaining early-stage variables provides only a modest improvement. Acquisition Cost explains "
    "most of the predictive performance of the early-stage model. The model should not be interpreted "
    "as evidence that campaign characteristics independently drive ROI."
)

FEATURE_IMPORTANCE_DISCLAIMER = (
    "Feature importance describes the model's predictive behavior and should not be interpreted as "
    "causal influence."
)

ERROR_CONTEXT_LABEL = "Error context — not a statistical confidence interval."


def _humanize_feature_name(raw_name: str) -> str:
    """Turn a raw pipeline feature name like 'numeric__Acquisition_Cost'
    or 'categorical__Language_Hindi' into a readable label like
    'Acquisition Cost'. Purely cosmetic — does not change any value.
    """
    if not raw_name:
        return raw_name
    name = raw_name.split("__", 1)[-1]
    # For one-hot categorical columns, keep just the source field name
    # (e.g. 'Language_Hindi' -> 'Language') since the dominant driver
    # callout should read as a field, not a single category level.
    for base_field in ("Campaign_Type", "Target_Audience", "Channel_Used", "Language", "Customer_Segment"):
        if name.startswith(base_field):
            name = base_field
            break
    return name.replace("_", " ")


def build_model_intelligence(model_path: str, metadata_path: str) -> dict:
    """Aggregated payload for GET /api/model-intelligence. Composes
    existing ml_service reads — does not recompute anything.
    """
    metadata = ml_service.get_metadata(metadata_path)
    metrics = metadata.get("metrics", {})
    comparison = metadata.get("model_comparison", {})
    cost_only = comparison.get("cost_only", {})
    early_stage = comparison.get("early_stage", {})

    try:
        feature_importance = ml_service.get_feature_importance(model_path)[:10]
    except ModelUnavailableError:
        feature_importance = []

    cost_only_r2 = cost_only.get("r2")
    early_stage_r2 = early_stage.get("r2")
    incremental_r2 = (
        early_stage_r2 - cost_only_r2 if cost_only_r2 is not None and early_stage_r2 is not None else None
    )

    return {
        "governance_badge": GOVERNANCE_BADGE,
        "performance_summary": {
            "model_name": metadata.get("model_name"),
            "model_status": "Trained",
            "prediction_type": metadata.get("prediction_type"),
            "train_sample_count": metadata.get("train_sample_count"),
            "test_sample_count": metadata.get("test_sample_count"),
            "r2": metrics.get("r2"),
            "mae": metrics.get("mae"),
            "rmse": metrics.get("rmse"),
            "explanation": PERFORMANCE_EXPLANATION,
        },
        "comparison": {
            "models": comparison,
            "interpretation": (
                "Acquisition_Cost (cost-only model) explains most of the early-stage model's "
                "predictive performance. Strategy-only variables (campaign type, audience, "
                "channel, language, segment) have very limited predictive power on their own."
            ),
        },
        "feature_importance": {
            "top_features": feature_importance,
            "disclaimer": FEATURE_IMPORTANCE_DISCLAIMER,
        },
        "acquisition_cost_dominance": {
            "cost_only_r2": cost_only_r2,
            "full_early_stage_r2": early_stage_r2,
            "incremental_r2": incremental_r2,
            "explanation": ACQUISITION_COST_EXPLANATION,
        },
        "interpretation": {
            "what_the_model_can_tell_us": MODEL_CAN_TELL_US,
            "what_the_model_cannot_tell_us": MODEL_CANNOT_TELL_US,
        },
        "limitations": MODEL_LIMITATIONS,
        "dominant_feature_note": metadata.get("dominant_feature_note"),
    }


def build_prediction_explanation(model_path: str, metadata_path: str, payload: dict) -> dict:
    """Payload for POST /api/explain-prediction. Runs the SAME cached
    pipeline as /api/predict-roi (via ml_service.predict_roi) — this is
    not a second model and not a retrain.
    """
    predicted_roi = ml_service.predict_roi(model_path, payload)
    metadata = ml_service.get_metadata(metadata_path)
    metrics = metadata.get("metrics", {})

    try:
        top_features = ml_service.get_feature_importance(model_path)
        primary_driver = _humanize_feature_name(top_features[0]["feature"]) if top_features else None
    except ModelUnavailableError:
        primary_driver = None

    mae = metrics.get("mae")

    return {
        "status": "success",
        "predicted_roi": round(predicted_roi, 4),
        "model": metadata.get("model_name"),
        "governance_badge": GOVERNANCE_BADGE,
        "prediction_context": {
            "inputs": {
                "Campaign_Type": payload.get("Campaign_Type"),
                "Target_Audience": payload.get("Target_Audience"),
                "Duration": payload.get("Duration"),
                "Channel_Used": payload.get("Channel_Used"),
                "Language": payload.get("Language"),
                "Customer_Segment": payload.get("Customer_Segment"),
                "Acquisition_Cost": payload.get("Acquisition_Cost"),
            },
        },
        "primary_model_driver": primary_driver,
        "primary_model_driver_disclaimer": FEATURE_IMPORTANCE_DISCLAIMER,
        "error_context": {
            "mae": mae,
            "label": ERROR_CONTEXT_LABEL,
            "note": f"Typical test-set error: ±{round(mae, 2)} ROI points." if mae is not None else None,
        },
    }
