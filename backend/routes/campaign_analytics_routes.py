"""
Campaign Analytics routes (Phase 7).

All routes here read the cached dataframe via data_service.require_dataframe
(never a second CSV load), apply campaign_analytics_service.apply_filters
once, then hand the already-filtered dataframe to the relevant aggregation
function. This blueprint is entirely additive — it does not touch or
replace the existing /api/campaigns, /api/campaign-types,
/api/customer-segments endpoints used by other pages.
"""

from flask import Blueprint, Response, current_app, jsonify, request

from backend.services import campaign_analytics_service as cas
from backend.services.data_service import DatasetUnavailableError, require_dataframe

campaign_analytics_bp = Blueprint("campaign_analytics_api", __name__)

FILTER_PARAM_NAMES = [
    "campaign_type",
    "customer_segment",
    "target_audience",
    "channel",
    "language",
    "search",
    "duration_min",
    "duration_max",
    "acquisition_cost_min",
    "acquisition_cost_max",
    "roi_min",
    "roi_max",
    "revenue_min",
    "revenue_max",
    "conversions_min",
    "conversions_max",
]


def _read_filters() -> dict:
    return {name: request.args.get(name) for name in FILTER_PARAM_NAMES}


def _unavailable_response(exc: DatasetUnavailableError):
    return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503


def _invalid_filter_response(exc: cas.InvalidFilterError):
    return jsonify({"error": "bad_request", "message": str(exc)}), 400


def _server_error_response(context: str):
    current_app.logger.exception(context)
    return jsonify({"error": "server_error", "message": context}), 500


def _get_filtered_df():
    data_path = current_app.config["DATA_PATH"]
    df = require_dataframe(data_path)
    filters = _read_filters()
    filtered = cas.apply_filters(df, filters)
    return filtered, filters


@campaign_analytics_bp.route("/summary", methods=["GET"])
def summary():
    try:
        filtered, filters = _get_filtered_df()
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute filtered summary.")

    return (
        jsonify(
            {
                "summary": cas.get_filtered_summary(filtered),
                "active_filters": cas.get_active_filters_summary(filters),
            }
        ),
        200,
    )


@campaign_analytics_bp.route("/table", methods=["GET"])
def table():
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", 25))
    except ValueError:
        return jsonify({"error": "bad_request", "message": "page and page_size must be integers."}), 400

    if page < 1 or page_size < 1 or page_size > 500:
        return jsonify({"error": "bad_request", "message": "page must be >= 1 and page_size must be 1-500."}), 400

    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "desc")
    if sort_dir not in ("asc", "desc"):
        return jsonify({"error": "bad_request", "message": "sort_dir must be 'asc' or 'desc'."}), 400

    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_table_page(filtered, page, page_size, sort_by, sort_dir)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to fetch campaign table.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/campaign-types", methods=["GET"])
def campaign_types():
    from backend.services import analytics_service

    try:
        filtered, filters = _get_filtered_df()
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute campaign type performance.")

    return (
        jsonify(
            {
                "campaign_types": analytics_service.get_campaign_types(filtered),
                "active_filters": cas.get_active_filters_summary(filters),
            }
        ),
        200,
    )


@campaign_analytics_bp.route("/channels", methods=["GET"])
def channels():
    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_channel_performance(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute channel performance.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/customer-segments", methods=["GET"])
def customer_segments():
    from backend.services import analytics_service

    try:
        filtered, filters = _get_filtered_df()
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute customer segment performance.")

    return (
        jsonify(
            {
                "customer_segments": analytics_service.get_customer_segments(filtered),
                "active_filters": cas.get_active_filters_summary(filters),
            }
        ),
        200,
    )


@campaign_analytics_bp.route("/audiences", methods=["GET"])
def audiences():
    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_audience_performance(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute audience performance.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/languages", methods=["GET"])
def languages():
    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_language_performance(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute language performance.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/roi-distribution", methods=["GET"])
def roi_distribution():
    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_roi_distribution(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute ROI distribution.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/performance-tiers", methods=["GET"])
def performance_tiers():
    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_performance_tiers(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute performance tiers.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/top-campaigns", methods=["GET"])
def top_campaigns():
    metric = request.args.get("metric", "roi")
    if metric not in cas.RANK_METRIC_COLUMNS:
        return jsonify({"error": "bad_request", "message": f"metric must be one of {list(cas.RANK_METRIC_COLUMNS)}."}), 400
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return jsonify({"error": "bad_request", "message": "limit must be an integer."}), 400
    if limit not in (10, 25, 50):
        return jsonify({"error": "bad_request", "message": "limit must be 10, 25, or 50."}), 400

    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_top_campaigns(filtered, metric, limit)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute top campaigns.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/underperforming", methods=["GET"])
def underperforming():
    metric = request.args.get("metric", "lowest_roi")
    if metric not in cas.UNDERPERFORM_METRIC_COLUMNS:
        return (
            jsonify({"error": "bad_request", "message": f"metric must be one of {list(cas.UNDERPERFORM_METRIC_COLUMNS)}."}),
            400,
        )
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        return jsonify({"error": "bad_request", "message": "limit must be an integer."}), 400
    if limit not in (10, 25, 50):
        return jsonify({"error": "bad_request", "message": "limit must be 10, 25, or 50."}), 400

    try:
        filtered, filters = _get_filtered_df()
        result = cas.get_underperforming_campaigns(filtered, metric, limit)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute underperforming campaigns.")

    result["active_filters"] = cas.get_active_filters_summary(filters)
    return jsonify(result), 200


@campaign_analytics_bp.route("/export", methods=["GET"])
def export():
    try:
        filtered, _filters = _get_filtered_df()
        csv_text = cas.export_filtered_csv(filtered)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except cas.InvalidFilterError as exc:
        return _invalid_filter_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to export filtered campaigns.")

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=filtered_campaigns.csv"},
    )
