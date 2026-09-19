"""
Scenario simulator routes (Phase 5).

Both endpoints reuse the already-loaded model via scenario_service ->
ml_service. Neither route trains anything — they only call .predict()
on the existing cached pipeline, once per scenario/budget level.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import scenario_service
from backend.services.ml_service import ModelUnavailableError

scenario_bp = Blueprint("scenario", __name__)


def _model_unavailable_response(exc: ModelUnavailableError):
    return jsonify({"error": "model_unavailable", "message": str(exc)}), 503


def _server_error_response(context: str):
    current_app.logger.exception(context)
    return jsonify({"error": "server_error", "message": context}), 500


@scenario_bp.route("/scenario/compare", methods=["POST"])
def scenario_compare():
    payload = request.get_json(silent=True)

    errors = scenario_service.validate_scenarios_payload(payload)
    if errors:
        return jsonify({"error": "invalid_input", "message": "Scenario validation failed.", "details": errors}), 400

    model_path = current_app.config["MODEL_PATH"]
    try:
        result = scenario_service.compare_scenarios(model_path, payload["scenarios"])
        from backend.services.ml_service import get_metadata

        metadata = get_metadata(current_app.config["MODEL_METADATA_PATH"])
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to run scenario comparison.")

    result["model"] = metadata.get("model_name", "Random Forest (early-stage)")
    result["illustrative_estimated_profit_formula"] = "Illustrative Estimated Profit = Acquisition Cost × Predicted ROI"
    result["note"] = (
        "Predictions are model estimates and should be used for decision support, "
        "not as guaranteed financial outcomes. This is a model-derived estimate for "
        "decision support and is not guaranteed financial profit or revenue."
    )
    return jsonify(result), 200


@scenario_bp.route("/scenario/sensitivity", methods=["POST"])
def scenario_sensitivity():
    payload = request.get_json(silent=True)

    errors = scenario_service.validate_sensitivity_payload(payload)
    if errors:
        return jsonify({"error": "invalid_input", "message": "Sensitivity request validation failed.", "details": errors}), 400

    model_path = current_app.config["MODEL_PATH"]
    try:
        results = scenario_service.run_budget_sensitivity(
            model_path, payload["scenario"], payload.get("acquisition_costs")
        )
    except ModelUnavailableError as exc:
        return _model_unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to run budget sensitivity analysis.")

    return (
        jsonify(
            {
                "status": "success",
                "analysis_type": "model-based sensitivity analysis",
                "results": results,
                "illustrative_estimated_profit_formula": "Illustrative Estimated Profit = Acquisition Cost × Predicted ROI",
                "note": (
                    "This shows how the model's ROI prediction changes as acquisition cost changes, "
                    "with all other planning variables held constant. It does not imply that increasing "
                    "budget causes higher ROI. This is a model-derived estimate for decision support and "
                    "is not guaranteed financial profit or revenue."
                ),
            }
        ),
        200,
    )
