"""
Budget Allocation Optimizer routes (Phase 13).

Reuses the existing cached dataframe (data_service.require_dataframe)
— no new CSV loading, no dataset mutation. All computation lives in
budget_optimizer_service.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import budget_optimizer_service as bos
from backend.services.budget_optimizer_service import InvalidOptimizerInput
from backend.services.data_service import DatasetUnavailableError, require_dataframe

budget_optimizer_bp = Blueprint("budget_optimizer", __name__)

DEFAULTS = {
    "dimension": "Campaign Type",
    "total_budget": 1_000_000,
    "min_allocation": 5,
    "max_allocation": 40,
    "risk_mode": "Balanced",
}


def _run(params):
    df = require_dataframe(current_app.config["DATA_PATH"])
    return bos.get_budget_optimization(
        df,
        dimension=params["dimension"],
        total_budget=params["total_budget"],
        min_allocation=params["min_allocation"],
        max_allocation=params["max_allocation"],
        risk_mode=params["risk_mode"],
    )


@budget_optimizer_bp.route("/budget-optimizer", methods=["GET"])
def budget_optimizer_get():
    """Returns the default optimization (Campaign Type, ₹10,00,000,
    5%-40%, Balanced).
    """
    try:
        result = _run(dict(DEFAULTS))
    except InvalidOptimizerInput as exc:
        return jsonify({"error": "invalid_input", "message": str(exc)}), 400
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build default budget optimization.")
        return jsonify({"error": "server_error", "message": "Failed to build budget optimization."}), 500

    return jsonify(result), 200


@budget_optimizer_bp.route("/budget-optimizer", methods=["POST"])
def budget_optimizer_post():
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"error": "invalid_input", "message": "Request body must be a JSON object."}), 400

    params = dict(DEFAULTS)
    if payload:
        for key in DEFAULTS:
            if key in payload and payload[key] is not None:
                params[key] = payload[key]

    try:
        result = _run(params)
    except InvalidOptimizerInput as exc:
        return jsonify({"error": "invalid_input", "message": str(exc)}), 400
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build budget optimization.")
        return jsonify({"error": "server_error", "message": "Failed to build budget optimization."}), 500

    return jsonify(result), 200
