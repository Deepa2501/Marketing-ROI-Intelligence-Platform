"""
Platform health service (Phase 15).

Read-only integrity checks across the dataset, model artifacts,
backend services, frontend templates, and application configuration.

Safety properties:
- READ-ONLY. Nothing here writes, moves, or modifies any file. The
  dataset integrity check opens the CSV for hashing only.
- NO ABSOLUTE PATHS OR SECRETS in any returned message. Paths are
  reported as basenames or repo-relative fragments only, so the
  response can be shown in a browser without leaking filesystem
  layout. Config values are reported as booleans/derived facts, never
  as raw values (e.g. SECRET_KEY is reported as "set"/"not set",
  never echoed).
- NO EXTERNAL NETWORK CALLS. API checks introspect the Flask URL map
  in-process rather than issuing HTTP requests.
"""

import hashlib
import importlib
import json
import os
from datetime import datetime, timezone

REQUIRED_COLUMNS = [
    "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration", "Channel_Used",
    "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost",
    "ROI", "Language", "Engagement_Score", "Customer_Segment", "Date",
]

REQUIRED_SERVICES = [
    "analytics_service", "budget_optimizer_service", "campaign_analytics_service",
    "copilot_service", "data_quality_service", "data_service", "executive_service",
    "explainability_service", "forecasting_service", "intelligence_service",
    "ml_service", "recommendation_service", "scenario_service", "statistics_service",
]

# Actual template filenames in this repository. Naming is intentionally
# mixed (snake_case from earlier phases, kebab-case from later ones);
# these are the real files on disk, verified rather than assumed.
REQUIRED_TEMPLATES = [
    "base.html", "index.html", "campaign_analytics.html", "marketing-intelligence.html",
    "forecasting.html", "statistics.html", "ab_testing.html", "roi_prediction.html",
    "scenario_simulator.html", "model_intelligence.html", "business_insights.html",
    "recommendations.html", "data-quality.html", "budget-optimizer.html",
    "copilot.html", "executive-center.html", "platform-health.html",
]

REQUIRED_API_ENDPOINTS = [
    "/api/health/platform", "/api/summary", "/api/campaign-types", "/api/customer-segments",
    "/api/statistics", "/api/ab-test", "/api/recommendations", "/api/budget-optimizer",
    "/api/copilot/capabilities", "/api/data-quality",
]

REQUIRED_PAGE_ROUTES = [
    "/", "/campaign-analytics", "/marketing-intelligence", "/forecasting", "/statistics",
    "/ab-testing", "/roi-prediction", "/scenario-simulator", "/model-intelligence",
    "/business-insights", "/recommendations", "/data-quality", "/budget-optimizer",
    "/copilot", "/executive-center", "/platform-health",
]

MODEL_GOVERNANCE_STATEMENTS = [
    "The ROI model is an early-stage Random Forest intended for pre-launch decision support.",
    "Acquisition Cost is a dominant predictive signal in the current model.",
    "A strategy-only model (campaign characteristics without cost) has weak predictive power.",
    "The model does not establish causality — it measures statistical association.",
    "Predictions are estimates, not guaranteed outcomes.",
    "Historical relationships may not continue into future periods.",
    "The model should support, not replace, business judgment.",
]

ANALYTICAL_GUARDRAILS = [
    "OBSERVED — descriptive findings read directly from historical campaign records.",
    "PREDICTIVE — model- or forecast-derived estimates, never presented as guarantees.",
    "EXPERIMENTAL — A/B testing and statistical comparison results.",
    "Evidence types are labelled on every recommendation, insight, and Copilot answer, and are never blended within a single claim.",
    "Recommendations describe observed association, never causation.",
    "Forecasts are described as directional outlooks over a limited horizon.",
    "Budget allocations are described as illustrative, historical-performance-based scenarios.",
    "A/B test results report statistical significance without asserting that one channel causes higher ROI.",
]

FINAL_GOVERNANCE_STATEMENT = {
    "title": "Decision-Support Platform",
    "statements": [
        "This platform combines historical analytics, statistical evidence, predictive modeling, forecasting, recommendations, and illustrative budget scenarios.",
        "Outputs are intended to support human decision-making.",
        "Historical association does not establish causality.",
        "Predictions and forecasts are estimates.",
        "Budget allocations are illustrative and should be validated before real-world deployment.",
    ],
}


def _check(name, status, message, severity, details=None):
    result = {"name": name, "status": status, "message": message, "severity": severity}
    if details:
        result["details"] = details
    return result


def _safe_name(path):
    """Return only the basename so absolute filesystem layout is never
    exposed in an API response.
    """
    return os.path.basename(path) if path else "not configured"


# ============================================================
# DATASET CHECKS
# ============================================================


def check_dataset(data_path):
    checks = []

    if not data_path or not os.path.exists(data_path):
        checks.append(_check(
            "Dataset availability", "FAIL",
            f"Dataset file '{_safe_name(data_path)}' was not found at the configured location.",
            "critical",
        ))
        return checks, None

    checks.append(_check(
        "Dataset availability", "PASS",
        f"Dataset '{_safe_name(data_path)}' is present and readable.", "info",
    ))

    try:
        import pandas as pd

        df = pd.read_csv(data_path)
    except Exception:  # noqa: BLE001
        checks.append(_check(
            "Dataset readability", "FAIL",
            "The dataset file exists but could not be parsed as CSV.", "critical",
        ))
        return checks, None

    checks.append(_check(
        "Dataset row count", "PASS" if len(df) > 0 else "FAIL",
        f"{len(df):,} rows loaded." if len(df) else "Dataset contains no rows.",
        "info" if len(df) else "critical",
        {"rows": int(len(df))},
    ))

    checks.append(_check(
        "Dataset column count", "PASS" if len(df.columns) else "FAIL",
        f"{len(df.columns)} columns detected.", "info",
        {"columns": int(len(df.columns))},
    ))

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    checks.append(_check(
        "Required schema", "PASS" if not missing else "FAIL",
        "All 16 required analytical columns are present."
        if not missing else f"{len(missing)} required column(s) missing: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"required_columns": REQUIRED_COLUMNS, "missing_columns": missing},
    ))

    return checks, df


def check_dataset_integrity(data_path):
    """Non-destructive integrity check: row/column count plus a SHA-256
    of the file contents. Informational only — the hash is reported,
    never enforced against a hard-coded value.
    """
    if not data_path or not os.path.exists(data_path):
        return _check(
            "Dataset integrity", "FAIL",
            "Integrity check skipped — dataset file not found.", "critical",
        )

    try:
        sha = hashlib.sha256()
        with open(data_path, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                sha.update(block)
        digest = sha.hexdigest()

        import pandas as pd

        df = pd.read_csv(data_path)
        schema_valid = all(c in df.columns for c in REQUIRED_COLUMNS)

        return _check(
            "Dataset integrity",
            "PASS" if schema_valid else "WARN",
            "Dataset integrity verified — file is readable and the schema is valid."
            if schema_valid else "Dataset is readable but the expected schema is incomplete.",
            "info" if schema_valid else "moderate",
            {
                "rows": int(len(df)),
                "columns": int(len(df.columns)),
                "sha256": digest,
                "note": "Hash is informational; it is not enforced against a stored value.",
            },
        )
    except Exception:  # noqa: BLE001
        return _check("Dataset integrity", "FAIL", "Integrity check could not be completed.", "critical")


# ============================================================
# MODEL CHECKS
# ============================================================


def check_model(model_path, metadata_path):
    checks = []
    metrics = None

    if model_path and os.path.exists(model_path):
        try:
            size_mb = round(os.path.getsize(model_path) / (1024 * 1024), 2)
        except OSError:
            size_mb = None
        checks.append(_check(
            "Model artifact", "PASS",
            f"Model artifact '{_safe_name(model_path)}' is present.", "info",
            {"size_mb": size_mb},
        ))
    else:
        checks.append(_check(
            "Model artifact", "FAIL",
            f"Model artifact '{_safe_name(model_path)}' was not found. "
            "Run python/train_roi_model.py to produce it.", "critical",
        ))

    if metadata_path and os.path.exists(metadata_path):
        try:
            with open(metadata_path) as fh:
                metadata = json.load(fh)
            metrics = metadata.get("metrics", {})
            checks.append(_check(
                "Model metadata", "PASS",
                f"Metadata present for '{metadata.get('model_name', 'unknown model')}'.", "info",
                {
                    "model_name": metadata.get("model_name"),
                    "prediction_type": metadata.get("prediction_type"),
                    "r2": metrics.get("r2"),
                    "mae": metrics.get("mae"),
                    "rmse": metrics.get("rmse"),
                    "train_sample_count": metadata.get("train_sample_count"),
                    "test_sample_count": metadata.get("test_sample_count"),
                    "governance_note": "Model is decision support, not causal inference.",
                },
            ))
        except Exception:  # noqa: BLE001
            checks.append(_check("Model metadata", "FAIL", "Model metadata exists but could not be parsed as JSON.", "critical"))
    else:
        checks.append(_check(
            "Model metadata", "FAIL",
            f"Model metadata '{_safe_name(metadata_path)}' was not found.", "critical",
        ))

    return checks, metrics


def check_reports(metadata_path):
    reports_dir = os.path.dirname(metadata_path) if metadata_path else "reports"
    if os.path.isdir(reports_dir):
        try:
            files = sorted(f for f in os.listdir(reports_dir) if not f.startswith("."))
        except OSError:
            files = []
        return _check(
            "Reports directory", "PASS" if files else "WARN",
            f"{len(files)} report file(s) present." if files else "Reports directory exists but is empty.",
            "info" if files else "low",
            {"files": files},
        )
    return _check("Reports directory", "WARN", "Reports directory was not found.", "low")


# ============================================================
# SERVICE / TEMPLATE / ROUTE CHECKS
# ============================================================


def check_services():
    missing = []
    for name in REQUIRED_SERVICES:
        try:
            importlib.import_module(f"backend.services.{name}")
        except Exception:  # noqa: BLE001
            missing.append(name)

    return _check(
        "Backend services",
        "PASS" if not missing else "FAIL",
        f"All {len(REQUIRED_SERVICES)} required backend services import successfully."
        if not missing else f"{len(missing)} service(s) failed to import: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"required": len(REQUIRED_SERVICES), "missing": missing},
    )


def check_templates(template_dir):
    if not template_dir or not os.path.isdir(template_dir):
        return _check("Frontend templates", "FAIL", "Template directory was not found.", "critical")

    try:
        present = set(os.listdir(template_dir))
    except OSError:
        return _check("Frontend templates", "FAIL", "Template directory could not be read.", "critical")

    missing = [t for t in REQUIRED_TEMPLATES if t not in present]
    return _check(
        "Frontend templates",
        "PASS" if not missing else "FAIL",
        f"All {len(REQUIRED_TEMPLATES)} required templates are present."
        if not missing else f"{len(missing)} template(s) missing: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"required": len(REQUIRED_TEMPLATES), "missing": missing},
    )


def check_api_endpoints(app):
    """Introspects the Flask URL map in-process. Makes no HTTP requests
    and contacts no external service.
    """
    registered = {str(rule.rule) for rule in app.url_map.iter_rules()}
    missing = [e for e in REQUIRED_API_ENDPOINTS if e not in registered]
    # /api/health is registered as the plain /health route in this app.
    return _check(
        "API endpoints",
        "PASS" if not missing else "FAIL",
        f"All {len(REQUIRED_API_ENDPOINTS)} checked API endpoints are registered."
        if not missing else f"{len(missing)} endpoint(s) not registered: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"checked": len(REQUIRED_API_ENDPOINTS), "missing": missing},
    )


def check_page_routes(app):
    registered = {str(rule.rule) for rule in app.url_map.iter_rules()}
    missing = [r for r in REQUIRED_PAGE_ROUTES if r not in registered]
    return _check(
        "Page routes",
        "PASS" if not missing else "FAIL",
        f"All {len(REQUIRED_PAGE_ROUTES)} page routes are registered."
        if not missing else f"{len(missing)} page route(s) not registered: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"checked": len(REQUIRED_PAGE_ROUTES), "missing": missing},
    )


def check_navigation(template_dir):
    """Audits the sidebar for broken/duplicate entries. Reads base.html
    as text — nothing is rendered or executed.
    """
    base_path = os.path.join(template_dir, "base.html") if template_dir else None
    if not base_path or not os.path.exists(base_path):
        return _check("Navigation audit", "FAIL", "base.html was not found.", "critical")

    try:
        with open(base_path, encoding="utf-8") as fh:
            content = fh.read()
    except OSError:
        return _check("Navigation audit", "FAIL", "base.html could not be read.", "critical")

    import re

    labels = re.findall(r'sidebar__link-label">(.*?)</span>', content, re.DOTALL)
    labels = [re.sub(r"\s+", " ", l).strip() for l in labels]
    endpoints = re.findall(r"url_for\('([a-z_]+)'\)", content)

    duplicates = sorted({l for l in labels if labels.count(l) > 1})
    has_active_logic = "is-active" in content

    issues = []
    if duplicates:
        issues.append(f"duplicate labels: {', '.join(duplicates)}")
    if not has_active_logic:
        issues.append("active-page highlighting not detected")
    if not labels:
        issues.append("no sidebar labels detected")

    return _check(
        "Navigation audit",
        "PASS" if not issues else "WARN",
        f"{len(labels)} sidebar links detected with no duplicates and active-page highlighting in place."
        if not issues else "; ".join(issues),
        "info" if not issues else "moderate",
        {"link_count": len(labels), "labels": labels, "endpoints": sorted(set(endpoints)), "duplicates": duplicates},
    )


# ============================================================
# CONFIGURATION / ENVIRONMENT
# ============================================================


def check_configuration(app):
    """Reports derived facts about configuration — never raw values.
    SECRET_KEY is reported only as set/not-set and is never echoed.
    """
    secret = app.config.get("SECRET_KEY")
    secret_set = bool(secret)
    secret_is_default = secret == "dev-secret-key-change-in-production"

    required_keys = ["DATA_PATH", "MODEL_PATH", "MODEL_METADATA_PATH", "SECRET_KEY"]
    missing_keys = [k for k in required_keys if not app.config.get(k)]

    if missing_keys:
        status, severity = "FAIL", "critical"
        message = f"Missing configuration key(s): {', '.join(missing_keys)}."
    elif secret_is_default:
        status, severity = "WARN", "moderate"
        message = "Configuration present, but SECRET_KEY is still the development default. Set a unique value before any shared deployment."
    else:
        status, severity = "PASS", "info"
        message = "All required configuration keys are set."

    return _check(
        "Application configuration", status, message, severity,
        {
            "required_keys_present": [k for k in required_keys if app.config.get(k)],
            "secret_key_set": secret_set,
            "secret_key_is_development_default": secret_is_default,
            "debug_enabled": bool(app.config.get("DEBUG")),
            "note": "Configuration values are never echoed in this response.",
        },
    )


def check_environment():
    import sys
    from importlib import metadata as importlib_metadata

    # Distribution names differ from import names for scikit-learn.
    packages = {
        "flask": "flask", "pandas": "pandas", "numpy": "numpy",
        "scipy": "scipy", "sklearn": "scikit-learn", "joblib": "joblib",
    }
    versions = {}
    missing = []
    for import_name, dist_name in packages.items():
        try:
            importlib.import_module(import_name)
        except Exception:  # noqa: BLE001
            missing.append(import_name)
            continue
        try:
            # importlib.metadata avoids the deprecated __version__ attribute.
            versions[import_name] = importlib_metadata.version(dist_name)
        except Exception:  # noqa: BLE001
            versions[import_name] = "unknown"

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    return _check(
        "Python environment",
        "PASS" if not missing else "FAIL",
        f"Python {python_version} with all {len(packages)} required packages importable."
        if not missing else f"{len(missing)} package(s) not importable: {', '.join(missing)}.",
        "info" if not missing else "critical",
        {"python_version": python_version, "packages": versions, "missing": missing},
    )


def check_test_summary(reports_dir):
    """Reads reports/platform_test_summary.json if it exists. Never
    fabricates results — reports only what a real test run wrote.
    """
    path = os.path.join(reports_dir, "platform_test_summary.json") if reports_dir else None
    if not path or not os.path.exists(path):
        return _check(
            "Test suite summary", "WARN",
            "No recorded test summary found. Run the test suite to generate one.", "low",
        )

    try:
        with open(path) as fh:
            summary = json.load(fh)
    except Exception:  # noqa: BLE001
        return _check("Test suite summary", "WARN", "Test summary file exists but could not be parsed.", "low")

    failed = summary.get("failed", 0)
    return _check(
        "Test suite summary",
        "PASS" if failed == 0 else "FAIL",
        f"{summary.get('passed', 0)} passed, {failed} failed as of the last recorded run."
        if failed == 0 else f"{failed} test(s) failed in the last recorded run.",
        "info" if failed == 0 else "critical",
        summary,
    )


# ============================================================
# TOP-LEVEL ENTRY POINT
# ============================================================


def get_platform_health(app):
    data_path = app.config.get("DATA_PATH")
    model_path = app.config.get("MODEL_PATH")
    metadata_path = app.config.get("MODEL_METADATA_PATH")
    template_dir = app.template_folder
    if template_dir and not os.path.isabs(template_dir):
        template_dir = os.path.join(app.root_path, template_dir)
    reports_dir = os.path.dirname(metadata_path) if metadata_path else "reports"

    checks = []

    dataset_checks, df = check_dataset(data_path)
    checks.extend(dataset_checks)
    checks.append(check_dataset_integrity(data_path))

    model_checks, metrics = check_model(model_path, metadata_path)
    checks.extend(model_checks)
    checks.append(check_reports(metadata_path))

    checks.append(check_services())
    checks.append(check_templates(template_dir))
    checks.append(check_api_endpoints(app))
    checks.append(check_page_routes(app))
    checks.append(check_navigation(template_dir))
    checks.append(check_configuration(app))
    checks.append(check_environment())
    checks.append(check_test_summary(reports_dir))

    has_fail = any(c["status"] == "FAIL" for c in checks)
    has_warn = any(c["status"] == "WARN" for c in checks)
    overall = "DEGRADED" if has_fail else ("HEALTHY_WITH_WARNINGS" if has_warn else "HEALTHY")

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_checks": len(checks),
            "passed": sum(1 for c in checks if c["status"] == "PASS"),
            "warnings": sum(1 for c in checks if c["status"] == "WARN"),
            "failed": sum(1 for c in checks if c["status"] == "FAIL"),
        },
        "checks": checks,
        "model_governance": MODEL_GOVERNANCE_STATEMENTS,
        "analytical_guardrails": ANALYTICAL_GUARDRAILS,
        "final_governance_statement": FINAL_GOVERNANCE_STATEMENT,
    }
