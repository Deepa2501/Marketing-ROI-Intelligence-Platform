"""
Analytics + statistics routes.

Every endpoint here reads from the cached dataframe (data_service) and
computes results through analytics_service / statistics_service. No
route recomputes or reloads the CSV — data_service.get_dataframe caches
it once per process.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import analytics_service, statistics_service
from backend.services.data_service import DatasetUnavailableError, require_dataframe

analytics_bp = Blueprint("analytics", __name__)


def _unavailable_response(exc: DatasetUnavailableError):
    return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503


def _server_error_response(context: str):
    current_app.logger.exception(context)
    return jsonify({"error": "server_error", "message": context}), 500


@analytics_bp.route("/campaign-types", methods=["GET"])
def campaign_types():
    data_path = current_app.config["DATA_PATH"]
    try:
        df = require_dataframe(data_path)
        return jsonify({"campaign_types": analytics_service.get_campaign_types(df)}), 200
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute campaign type breakdown.")


@analytics_bp.route("/customer-segments", methods=["GET"])
def customer_segments():
    data_path = current_app.config["DATA_PATH"]
    try:
        df = require_dataframe(data_path)
        return jsonify({"customer_segments": analytics_service.get_customer_segments(df)}), 200
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute customer segment breakdown.")


@analytics_bp.route("/analytics", methods=["GET"])
def analytics_overview():
    data_path = current_app.config["DATA_PATH"]
    try:
        df = require_dataframe(data_path)
        return jsonify(analytics_service.get_analytics_overview(df)), 200
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute analytics overview.")


@analytics_bp.route("/statistics", methods=["GET"])
def statistics():
    data_path = current_app.config["DATA_PATH"]
    try:
        df = require_dataframe(data_path)
        return (
            jsonify(
                {
                    "roi_correlations": statistics_service.get_roi_correlations(df),
                    "distribution": statistics_service.get_distribution_stats(df),
                    "outliers": statistics_service.get_outlier_stats(df),
                }
            ),
            200,
        )
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute statistics.")


@analytics_bp.route("/campaigns", methods=["GET"])
def campaigns():
    data_path = current_app.config["DATA_PATH"]

    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 25))
    except ValueError:
        return jsonify({"error": "bad_request", "message": "page and page_size must be integers."}), 400

    if page < 1 or page_size < 1 or page_size > 500:
        return (
            jsonify(
                {
                    "error": "bad_request",
                    "message": "page must be >= 1 and page_size must be between 1 and 500.",
                }
            ),
            400,
        )

    filters = {
        "campaign_type": request.args.get("campaign_type"),
        "customer_segment": request.args.get("customer_segment"),
        "target_audience": request.args.get("target_audience"),
        "channel": request.args.get("channel"),
        "language": request.args.get("language"),
        "date_from": request.args.get("date_from"),
        "date_to": request.args.get("date_to"),
    }
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "desc")
    if sort_dir not in ("asc", "desc"):
        return jsonify({"error": "bad_request", "message": "sort_dir must be 'asc' or 'desc'."}), 400
    search = request.args.get("search")

    try:
        df = require_dataframe(data_path)
        page_result = analytics_service.get_campaigns_page(
            df, filters, page, page_size, sort_by, sort_dir, search
        )
        return jsonify(page_result), 200
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to fetch campaigns.")
