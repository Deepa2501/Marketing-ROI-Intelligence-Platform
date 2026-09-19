"""
Data Quality & Governance route (Phase 12).

Reuses the existing cached dataframe (data_service.require_dataframe)
— no new CSV loading. All computation lives in data_quality_service.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import data_quality_service as dqs
from backend.services.data_service import DatasetUnavailableError, require_dataframe

data_quality_bp = Blueprint("data_quality", __name__)


@data_quality_bp.route("/data-quality", methods=["GET"])
def data_quality():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = dqs.get_data_quality_summary(df, current_app.config["DATA_PATH"])
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build data quality summary.")
        return jsonify({"error": "server_error", "message": "Failed to build data quality summary."}), 500

    return jsonify(result), 200
