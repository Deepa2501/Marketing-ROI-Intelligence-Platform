"""
Marketing Analyst Copilot routes (Phase 14).

Session context for follow-up questions is held in the Flask session
cookie (lightweight, per-browser-session, no database, no personal
data stored). Reuses the existing cached dataframe — no new CSV
loading, no dataset mutation.
"""

from flask import Blueprint, current_app, jsonify, request, session

from backend.services import copilot_service as cps
from backend.services.copilot_service import InvalidQuestion
from backend.services.data_service import DatasetUnavailableError, require_dataframe

copilot_bp = Blueprint("copilot", __name__)

SESSION_KEY = "copilot_context"


@copilot_bp.route("/copilot/ask", methods=["POST"])
def copilot_ask():
    payload = request.get_json(silent=True)
    if payload is not None and not isinstance(payload, dict):
        return jsonify({"error": "invalid_input", "message": "Request body must be a JSON object."}), 400

    question = (payload or {}).get("question")

    try:
        df = require_dataframe(current_app.config["DATA_PATH"])
        context = session.get(SESSION_KEY, {})
        result, updated_context = cps.ask(
            df,
            question,
            session_context=context,
            data_path=current_app.config["DATA_PATH"],
            model_path=current_app.config["MODEL_PATH"],
            metadata_path=current_app.config["MODEL_METADATA_PATH"],
        )
        session[SESSION_KEY] = updated_context
    except InvalidQuestion as exc:
        return jsonify({"error": "invalid_input", "message": str(exc)}), 400
    except DatasetUnavailableError as exc:
        return jsonify({"error": "dataset_unavailable", "message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Copilot failed to answer a question.")
        return jsonify({"error": "server_error", "message": "The Copilot could not process that question."}), 500

    return jsonify(result), 200


@copilot_bp.route("/copilot/capabilities", methods=["GET"])
def copilot_capabilities():
    try:
        return jsonify(cps.get_capabilities()), 200
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Failed to list copilot capabilities.")
        return jsonify({"error": "server_error", "message": "Failed to list capabilities."}), 500


@copilot_bp.route("/copilot/reset", methods=["POST"])
def copilot_reset():
    session.pop(SESSION_KEY, None)
    return jsonify({"status": "success", "message": "Copilot session context cleared."}), 200
