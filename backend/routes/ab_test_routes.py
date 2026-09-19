"""
A/B testing route.

Computes a real Welch's t-test (unequal variance) comparing ROI between
two campaign types, defaulting to Social Media vs Paid Ads as in the
original analysis, but accepting group_a / group_b query params so any
two Campaign_Type values in the dataset can be compared.
"""

from flask import Blueprint, current_app, jsonify, request

from backend.services import statistics_service
from backend.services.data_service import DatasetUnavailableError, require_dataframe

ab_test_bp = Blueprint("ab_test", __name__)


@ab_test_bp.route("/ab-test", methods=["GET"])
def ab_test():
    data_path = current_app.config["DATA_PATH"]
    group_a = request.args.get("group_a", "Social Media")
    group_b = request.args.get("group_b", "Paid Ads")

    try:
        df = require_dataframe(data_path)
        result = statistics_service.get_ab_test(df, group_a_label=group_a, group_b_label=group_b)
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to compute A/B test.")
        return jsonify({"error": "server_error", "message": "Failed to compute A/B test."}), 500

    if "error" in result:
        return jsonify({"error": "bad_request", "message": result["error"]}), 400

    return jsonify(result), 200
