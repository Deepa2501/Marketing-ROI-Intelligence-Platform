"""
Forecasting & Future Outlook route (Phase 11).

Reuses the existing cached dataframe (data_service.require_dataframe)
— no new CSV loading. All computation lives in forecasting_service.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import forecasting_service as fs
from backend.services.data_service import DatasetUnavailableError, require_dataframe

forecasting_bp = Blueprint("forecasting", __name__)


@forecasting_bp.route("/forecasting", methods=["GET"])
def forecasting():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = fs.get_forecast_summary(df)
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build forecast summary.")
        return jsonify({"error": "server_error", "message": "Failed to build forecast summary."}), 500

    return jsonify(result), 200
