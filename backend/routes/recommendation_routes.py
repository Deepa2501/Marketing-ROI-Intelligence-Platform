"""
Recommendation Intelligence routes (Phase 8).

Reuses the existing cached dataframe (data_service.require_dataframe)
and the existing model metadata path — no new CSV loading, no new
model training. All computation lives in recommendation_service.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import recommendation_service as rs
from backend.services.data_service import DatasetUnavailableError, require_dataframe

recommendation_bp = Blueprint("recommendations", __name__)


@recommendation_bp.route("/recommendations", methods=["GET"])
def recommendations():
    filter_type = request.args.get("type")
    if filter_type and filter_type not in rs.VALID_TYPES:
        return (
            jsonify(
                {
                    "error": "bad_request",
                    "message": f"'type' must be one of {sorted(rs.VALID_TYPES)}.",
                }
            ),
            400,
        )

    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = rs.build_recommendations(df, current_app.config["MODEL_METADATA_PATH"], filter_type)
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build recommendations.")
        return jsonify({"error": "server_error", "message": "Failed to build recommendations."}), 500

    return jsonify(result), 200
