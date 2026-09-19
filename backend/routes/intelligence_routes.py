"""
Marketing Intelligence routes (Phase 10).

Reuses the existing cached dataframe (data_service.require_dataframe)
and model metadata path — no new CSV loading. All computation lives in
intelligence_service, which composes existing services.
"""

from flask import Blueprint, current_app, jsonify

from backend.services import intelligence_service as ins
from backend.services.data_service import DatasetUnavailableError, require_dataframe

intelligence_bp = Blueprint("intelligence", __name__)


def _unavailable_response(exc: DatasetUnavailableError):
    return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503


def _server_error_response(context: str):
    current_app.logger.exception(context)
    return jsonify({"error": "server_error", "message": context}), 500


@intelligence_bp.route("/marketing-intelligence", methods=["GET"])
def marketing_intelligence():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = ins.build_marketing_intelligence(df, current_app.config["MODEL_METADATA_PATH"])
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to build marketing intelligence summary.")

    return jsonify(result), 200


@intelligence_bp.route("/marketing-intelligence/trends", methods=["GET"])
def trends():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = ins.get_trends(df)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute trends.")
    return jsonify(result), 200


@intelligence_bp.route("/marketing-intelligence/drivers", methods=["GET"])
def drivers():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = ins.get_performance_drivers(df)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute performance drivers.")
    return jsonify(result), 200


@intelligence_bp.route("/marketing-intelligence/funnel", methods=["GET"])
def funnel():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = ins.get_funnel(df)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute funnel.")
    return jsonify(result), 200


@intelligence_bp.route("/marketing-intelligence/efficiency", methods=["GET"])
def efficiency():
    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        result = ins.get_efficiency(df)
    except DatasetUnavailableError as exc:
        return _unavailable_response(exc)
    except Exception:  # noqa: BLE001
        return _server_error_response("Failed to compute efficiency analysis.")
    return jsonify(result), 200
