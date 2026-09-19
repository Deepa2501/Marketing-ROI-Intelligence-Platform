"""
ML / ROI prediction routes.

All routes read the model artifact and metadata once via ml_service's
cache — nothing is retrained per-request. Errors are always returned
as clean JSON (400 for bad input, 503 if the model/metadata artifact
hasn't been produced yet, 500 for anything unexpected) — no stack
traces are ever exposed to the client.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import ml_service
from backend.services import explainability_service
from backend.services.ml_service import ModelUnavailableError

ml_bp = Blueprint("ml", __name__)


def _model_unavailable_response(exc: ModelUnavailableError):
    return jsonify({"error": "model_unavailable", "message": str(exc)}), 503


def _server_error_response(context: str):
    current_app.logger.exception(context)
    return jsonify({"error": "server_error", "message": context}), 500


@ml_bp.route("/predict-roi", methods=["POST"])
def predict_roi():
    payload = request.get_json(silent=True)

    errors = ml_service.validate_prediction_input(payload)
    if errors:
        return jsonify({"error": "invalid_input", "message": "Request validation failed.", "details": errors}), 400

    model_path = current_app.config["MODEL_PATH"]
    try:
        predicted_roi = ml_service.predict_roi(model_path, payload)
        metadata = ml_service.get_metadata(current_app.config["MODEL_METADATA_PATH"])
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to generate ROI prediction.")

    metrics = metadata.get("metrics", {})

    return (
        jsonify(
            {
                "status": "success",
                "predicted_roi": round(predicted_roi, 4),
                "model": metadata.get("model_name", "Random Forest"),
                "prediction_type": metadata.get("prediction_type", "early_stage"),
                "model_r2": metrics.get("r2"),
                "model_mae": metrics.get("mae"),
                "estimated_error_note": (
                    f"Estimated prediction error: approximately ±{round(metrics['mae'], 2)} ROI points "
                    "based on test-set MAE."
                    if metrics.get("mae") is not None
                    else None
                ),
                "caveat": metadata.get("dominant_feature_note"),
            }
        ),
        200,
    )


@ml_bp.route("/model-info", methods=["GET"])
def model_info():
    try:
        metadata = ml_service.get_metadata(current_app.config["MODEL_METADATA_PATH"])
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to load model metadata.")

    return (
        jsonify(
            {
                "model_name": metadata.get("model_name"),
                "prediction_type": metadata.get("prediction_type"),
                "features": metadata.get("features"),
                "metrics": metadata.get("metrics"),
                "train_sample_count": metadata.get("train_sample_count"),
                "test_sample_count": metadata.get("test_sample_count"),
                "total_sample_count": metadata.get("total_sample_count"),
                "random_state": metadata.get("random_state"),
                "training_timestamp_utc": metadata.get("training_timestamp_utc"),
                "model_status": "trained",
                "dominant_feature_warning": metadata.get("dominant_feature_note"),
            }
        ),
        200,
    )


@ml_bp.route("/model-feature-importance", methods=["GET"])
def model_feature_importance():
    model_path = current_app.config["MODEL_PATH"]
    try:
        importance = ml_service.get_feature_importance(model_path)
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute feature importance.")

    return jsonify({"feature_importance": importance}), 200


@ml_bp.route("/model-comparison", methods=["GET"])
def model_comparison():
    try:
        metadata = ml_service.get_metadata(current_app.config["MODEL_METADATA_PATH"])
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to load model comparison data.")

    comparison = metadata.get("model_comparison", {})

    return (
        jsonify(
            {
                "comparison": comparison,
                "additional_r2_from_early_stage_features_vs_cost_only": metadata.get(
                    "additional_r2_from_early_stage_features_vs_cost_only"
                ),
                "interpretation": (
                    "Acquisition_Cost (cost-only model) explains most of the early-stage model's "
                    "predictive performance. Strategy-only variables (campaign type, audience, "
                    "channel, language, segment) have very limited predictive power on their own."
                ),
            }
        ),
        200,
    )


# ============================================================
# PHASE 6 — Model Intelligence & Explainability
#
# Both routes below are new. They compose the EXISTING ml_service
# functions above (get_metadata, get_feature_importance, predict_roi)
# via backend.services.explainability_service — no new model logic,
# no duplicated calculations, nothing retrained.
# ============================================================


@ml_bp.route("/model-intelligence", methods=["GET"])
def model_intelligence():
    """Aggregated Model Intelligence & Explainability payload: performance
    summary, model comparison, feature importance, Acquisition Cost
    dominance breakdown, plain-language interpretation, limitations, and
    the governance badge — all sourced from the existing trained model
    artifact and reports/roi_model_metadata.json.
    """
    try:
        payload = explainability_service.build_model_intelligence(
            current_app.config["MODEL_PATH"], current_app.config["MODEL_METADATA_PATH"]
        )
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to build model intelligence payload.")

    return jsonify(payload), 200


@ml_bp.route("/explain-prediction", methods=["POST"])
def explain_prediction():
    """Runs the same cached prediction pipeline as /api/predict-roi and
    additionally returns prediction context: the input values used, the
    primary model driver (from real feature importances), and an error
    context note explicitly labeled as not a statistical confidence
    interval.
    """
    payload = request.get_json(silent=True)

    errors = ml_service.validate_prediction_input(payload)
    if errors:
        return jsonify({"error": "invalid_input", "message": "Request validation failed.", "details": errors}), 400

    try:
        result = explainability_service.build_prediction_explanation(
            current_app.config["MODEL_PATH"], current_app.config["MODEL_METADATA_PATH"], payload
        )
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to explain prediction.")

    return jsonify(result), 200
