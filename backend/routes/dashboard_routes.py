"""
Dashboard routes.

Phase 2 update: /api/summary now returns real KPI aggregates computed
from the cached dataset (total campaigns, total revenue, average ROI,
total conversions, average acquisition cost) when the dataset is
connected. When it isn't, it falls back to the Phase 1 "pending"
response — no figures are ever invented.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import analytics_service
from backend.services.data_service import DatasetUnavailableError, get_connection_status, require_dataframe

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/summary", methods=["GET"])
def summary():
    data_path = current_app.config["DATA_PATH"]
    status = get_connection_status(data_path)

    if not status["connected"]:
        return (
            jsonify(
                {
                    "status": "pending",
                    "data_connection": status,
                    "note": "Dataset not connected yet. No figures below are invented or estimated.",
                }
            ),
            200,
        )

    try:
        df = require_dataframe(data_path)
        kpis = analytics_service.get_summary(df)
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to compute summary KPIs")
        return jsonify({"error": "server_error", "message": "Failed to compute summary KPIs."}), 500

    return (
        jsonify(
            {
                "status": "connected",
                "data_connection": status,
                "kpis": kpis,
            }
        ),
        200,
    )
