"""
Platform health route (Phase 15).

Adds GET /api/health/platform. The pre-existing /health endpoint is
left completely unchanged.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import platform_health_service as phs

platform_health_bp = Blueprint("platform_health", __name__)


@platform_health_bp.route("/health/platform", methods=["GET"])
def platform_health():
    try:
        result = phs.get_platform_health(current_app)
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to build platform health report.")
        return jsonify({"error": "server_error", "message": "Failed to build platform health report."}), 500

    return jsonify(result), 200
