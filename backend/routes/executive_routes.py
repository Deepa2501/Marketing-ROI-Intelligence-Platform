"""
Executive Decision Center route (Phase 9).

Reuses the existing cached dataframe (data_service.require_dataframe)
and model metadata path — no new CSV loading, no model retraining. All
computation lives in executive_service, which itself composes existing
services.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import executive_service as es
from backend.services.data_service import DatasetUnavailableError, require_dataframe

executive_bp = Blueprint("executive", __name__)


@executive_bp.route("/executive-summary", methods=["GET"])
def executive_summary():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = es.get_executive_summary(df, current_app.config["MODEL_METADATA_PATH"])
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build executive summary.")
        return jsonify({"error": "server_error", "message": "Failed to build executive summary."}), 500

    return jsonify(result), 200
