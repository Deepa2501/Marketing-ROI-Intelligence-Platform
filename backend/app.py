"""
Marketing ROI Intelligence Platform — Flask application factory.

Phase 1 scope:
- App factory + blueprint registration
- Global error handlers (no raw tracebacks exposed)
- Home page route

Later phases will register additional blueprints (analytics, prediction,
ab_test, insight, statistics) under backend/routes/.
"""

import logging
import os

from flask import Flask, jsonify, render_template

from backend.config import get_config


def create_app(config_name: str | None = None) -> Flask:
    """Application factory. Builds and configures the Flask app."""

    app = Flask(
        __name__,
        template_folder=os.path.join("..", "frontend", "templates"),
        static_folder=os.path.join("..", "frontend", "static"),
    )

    app.config.from_object(get_config(config_name))

    _configure_logging(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_core_routes(app)

    return app


def _configure_logging(app: Flask) -> None:
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _register_blueprints(app: Flask) -> None:
    """Register API blueprints.

    Phase 3 adds the ML/prediction blueprint alongside the Phase 1
    dashboard and Phase 2 analytics/A-B-test blueprints. The insight
    blueprint is still added in a later phase.
    """
    from backend.routes.ab_test_routes import ab_test_bp
    from backend.routes.analytics_routes import analytics_bp
    from backend.routes.budget_optimizer_routes import budget_optimizer_bp
    from backend.routes.campaign_analytics_routes import campaign_analytics_bp
    from backend.routes.copilot_routes import copilot_bp
    from backend.routes.dashboard_routes import dashboard_bp
    from backend.routes.data_quality_routes import data_quality_bp
    from backend.routes.executive_routes import executive_bp
    from backend.routes.forecasting_routes import forecasting_bp
    from backend.routes.intelligence_routes import intelligence_bp
    from backend.routes.ml_routes import ml_bp
    from backend.routes.platform_health_routes import platform_health_bp
    from backend.routes.recommendation_routes import recommendation_bp
    from backend.routes.scenario_routes import scenario_bp

    app.register_blueprint(dashboard_bp, url_prefix="/api")
    app.register_blueprint(analytics_bp, url_prefix="/api")
    app.register_blueprint(ab_test_bp, url_prefix="/api")
    app.register_blueprint(ml_bp, url_prefix="/api")
    app.register_blueprint(scenario_bp, url_prefix="/api")
    app.register_blueprint(campaign_analytics_bp, url_prefix="/api/campaign-analytics")
    app.register_blueprint(recommendation_bp, url_prefix="/api")
    app.register_blueprint(executive_bp, url_prefix="/api")
    app.register_blueprint(intelligence_bp, url_prefix="/api")
    app.register_blueprint(forecasting_bp, url_prefix="/api")
    app.register_blueprint(data_quality_bp, url_prefix="/api")
    app.register_blueprint(budget_optimizer_bp, url_prefix="/api")
    app.register_blueprint(copilot_bp, url_prefix="/api")
    app.register_blueprint(platform_health_bp, url_prefix="/api")


def _register_core_routes(app: Flask) -> None:
    """Page routes. Each renders a template only — no API/business logic
    lives here; pages fetch their data client-side from the /api/*
    blueprints registered in _register_blueprints.
    """

    @app.route("/")
    def index():
        return render_template("index.html", active_page="overview")

    @app.route("/campaign-analytics")
    def campaign_analytics():
        return render_template("campaign_analytics.html", active_page="campaign-analytics")

    @app.route("/statistics")
    def statistics_page():
        return render_template("statistics.html", active_page="statistics")

    @app.route("/ab-testing")
    def ab_testing_page():
        return render_template("ab_testing.html", active_page="ab-testing")

    @app.route("/roi-prediction")
    def roi_prediction_page():
        return render_template("roi_prediction.html", active_page="roi-prediction")

    @app.route("/scenario-simulator")
    def scenario_simulator_page():
        return render_template("scenario_simulator.html", active_page="scenario-simulator")

    @app.route("/model-intelligence")
    def model_intelligence_page():
        return render_template("model_intelligence.html", active_page="model-intelligence")

    @app.route("/business-insights")
    def business_insights_page():
        return render_template("business_insights.html", active_page="business-insights")

    @app.route("/recommendations")
    def recommendations_page():
        return render_template("recommendations.html", active_page="recommendations")

    @app.route("/executive-center")
    def executive_center_page():
        return render_template("executive-center.html", active_page="executive-center")

    @app.route("/marketing-intelligence")
    def marketing_intelligence_page():
        return render_template("marketing-intelligence.html", active_page="marketing-intelligence")

    @app.route("/forecasting")
    def forecasting_page():
        return render_template("forecasting.html", active_page="forecasting")

    @app.route("/data-quality")
    def data_quality_page():
        return render_template("data-quality.html", active_page="data-quality")

    @app.route("/budget-optimizer")
    def budget_optimizer_page():
        return render_template("budget-optimizer.html", active_page="budget-optimizer")

    @app.route("/copilot")
    def copilot_page():
        return render_template("copilot.html", active_page="copilot")

    @app.route("/platform-health")
    def platform_health_page():
        return render_template("platform-health.html", active_page="platform-health")

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "service": "marketing-roi-intelligence-platform"})


def _register_error_handlers(app: Flask) -> None:
    """Professional error responses. Never leak stack traces to the client."""

    @app.errorhandler(404)
    def not_found(_error):
        if _wants_json():
            return jsonify({"error": "not_found", "message": "The requested resource was not found."}), 404
        return render_template("index.html"), 404

    @app.errorhandler(400)
    def bad_request(_error):
        return jsonify({"error": "bad_request", "message": "The request could not be processed."}), 400

    @app.errorhandler(500)
    def server_error(_error):
        app.logger.exception("Unhandled server error")
        return jsonify({"error": "server_error", "message": "An unexpected error occurred."}), 500


def _wants_json() -> bool:
    from flask import request

    return request.path.startswith("/api/")
