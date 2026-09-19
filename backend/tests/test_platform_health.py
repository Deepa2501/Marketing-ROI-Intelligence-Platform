"""
Phase 15 tests — Platform Health & Readiness.

Same conventions as the Phase 10-14 suites. Run with:

    pytest backend/tests/test_platform_health.py -v

Run from the repository root so relative paths resolve correctly.
"""

import json
import os

import pytest

from backend.app import create_app
from backend.services import platform_health_service as phs


@pytest.fixture()
def app():
    application = create_app("testing")
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


# ============================================================
# 1. PLATFORM HEALTH
# ============================================================


def test_platform_health_returns_expected_shape(app):
    health = phs.get_platform_health(app)
    for key in ("status", "timestamp", "summary", "checks", "model_governance", "analytical_guardrails", "final_governance_statement"):
        assert key in health
    assert health["status"] in ("HEALTHY", "HEALTHY_WITH_WARNINGS", "DEGRADED")


def test_every_check_has_required_fields(app):
    health = phs.get_platform_health(app)
    assert len(health["checks"]) > 0
    for check in health["checks"]:
        for field in ("name", "status", "message", "severity"):
            assert field in check
        assert check["status"] in ("PASS", "WARN", "FAIL")


def test_summary_counts_match_checks(app):
    health = phs.get_platform_health(app)
    checks = health["checks"]
    s = health["summary"]
    assert s["total_checks"] == len(checks)
    assert s["passed"] == sum(1 for c in checks if c["status"] == "PASS")
    assert s["warnings"] == sum(1 for c in checks if c["status"] == "WARN")
    assert s["failed"] == sum(1 for c in checks if c["status"] == "FAIL")


def test_overall_status_reflects_worst_check(app):
    health = phs.get_platform_health(app)
    statuses = {c["status"] for c in health["checks"]}
    if "FAIL" in statuses:
        assert health["status"] == "DEGRADED"
    elif "WARN" in statuses:
        assert health["status"] == "HEALTHY_WITH_WARNINGS"
    else:
        assert health["status"] == "HEALTHY"


# ============================================================
# 2-3. DATASET & SCHEMA DETECTION
# ============================================================


def test_dataset_detection(app):
    checks, df = phs.check_dataset(app.config["DATA_PATH"])
    names = {c["name"]: c for c in checks}
    assert names["Dataset availability"]["status"] == "PASS"
    assert names["Dataset row count"]["details"]["rows"] > 0
    assert df is not None


def test_schema_detection_finds_all_required_columns(app):
    checks, _ = phs.check_dataset(app.config["DATA_PATH"])
    schema = next(c for c in checks if c["name"] == "Required schema")
    assert schema["status"] == "PASS"
    assert schema["details"]["missing_columns"] == []


def test_required_columns_list_is_complete():
    assert len(phs.REQUIRED_COLUMNS) == 16
    for col in ("Campaign_ID", "ROI", "Revenue", "Acquisition_Cost", "Date"):
        assert col in phs.REQUIRED_COLUMNS


def test_missing_dataset_is_reported_as_fail():
    checks, df = phs.check_dataset("/tmp/definitely_not_a_dataset.csv")
    assert df is None
    assert checks[0]["status"] == "FAIL"
    assert checks[0]["severity"] == "critical"


# ============================================================
# 4-5. MODEL ARTIFACT & METADATA
# ============================================================


def test_model_artifact_detection(app):
    checks, metrics = phs.check_model(app.config["MODEL_PATH"], app.config["MODEL_METADATA_PATH"])
    artifact = next(c for c in checks if c["name"] == "Model artifact")
    assert artifact["status"] == "PASS"


def test_model_metadata_detection_uses_real_values(app):
    checks, metrics = phs.check_model(app.config["MODEL_PATH"], app.config["MODEL_METADATA_PATH"])
    metadata_check = next(c for c in checks if c["name"] == "Model metadata")
    assert metadata_check["status"] == "PASS"

    with open(app.config["MODEL_METADATA_PATH"]) as fh:
        expected = json.load(fh)["metrics"]

    # Metrics must come from the file, never hard-coded.
    assert metadata_check["details"]["r2"] == expected["r2"]
    assert metadata_check["details"]["mae"] == expected["mae"]
    assert metadata_check["details"]["rmse"] == expected["rmse"]


def test_model_metadata_includes_governance_note(app):
    checks, _ = phs.check_model(app.config["MODEL_PATH"], app.config["MODEL_METADATA_PATH"])
    metadata_check = next(c for c in checks if c["name"] == "Model metadata")
    assert "decision support, not causal inference" in metadata_check["details"]["governance_note"]


def test_missing_model_is_reported_as_fail():
    checks, metrics = phs.check_model("/tmp/no_model.joblib", "/tmp/no_metadata.json")
    assert all(c["status"] == "FAIL" for c in checks)
    assert metrics is None


# ============================================================
# 6-7. SERVICES & TEMPLATES
# ============================================================


def test_required_services_all_import():
    check = phs.check_services()
    assert check["status"] == "PASS"
    assert check["details"]["missing"] == []


def test_required_templates_all_present(app):
    template_dir = app.template_folder
    if not os.path.isabs(template_dir):
        template_dir = os.path.join(app.root_path, template_dir)
    check = phs.check_templates(template_dir)
    assert check["status"] == "PASS"
    assert check["details"]["missing"] == []


def test_missing_template_directory_is_reported():
    check = phs.check_templates("/tmp/no_such_template_dir")
    assert check["status"] == "FAIL"


def test_api_endpoints_registered(app):
    check = phs.check_api_endpoints(app)
    assert check["status"] == "PASS"
    assert check["details"]["missing"] == []


def test_page_routes_registered(app):
    check = phs.check_page_routes(app)
    assert check["status"] == "PASS"
    assert check["details"]["missing"] == []


def test_navigation_audit_finds_no_duplicates(app):
    template_dir = app.template_folder
    if not os.path.isabs(template_dir):
        template_dir = os.path.join(app.root_path, template_dir)
    check = phs.check_navigation(template_dir)
    assert check["status"] == "PASS"
    assert check["details"]["duplicates"] == []
    assert check["details"]["link_count"] >= 15


# ============================================================
# 8. HEALTH API
# ============================================================


def test_platform_health_api(client):
    resp = client.get("/api/health/platform")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] in ("HEALTHY", "HEALTHY_WITH_WARNINGS", "DEGRADED")
    assert "timestamp" in data
    assert len(data["checks"]) > 0


def test_platform_health_page_loads(client):
    resp = client.get("/platform-health")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    for needle in ["status-grid", "checks-table", "model-governance-list", "final-governance-list"]:
        assert needle in body


# ============================================================
# 9-10. MISSING ASSET HANDLING
# ============================================================


def test_missing_dataset_degrades_overall_status():
    application = create_app("testing")
    application.config["DATA_PATH"] = "/tmp/definitely_not_a_dataset.csv"
    health = phs.get_platform_health(application)
    assert health["status"] == "DEGRADED"
    assert health["summary"]["failed"] > 0


def test_missing_model_degrades_overall_status():
    application = create_app("testing")
    application.config["MODEL_PATH"] = "/tmp/no_model.joblib"
    application.config["MODEL_METADATA_PATH"] = "/tmp/no_metadata.json"
    health = phs.get_platform_health(application)
    assert health["status"] == "DEGRADED"


# ============================================================
# 11. MALFORMED CONFIGURATION
# ============================================================


def test_missing_configuration_key_is_reported():
    application = create_app("testing")
    application.config["MODEL_PATH"] = None
    check = phs.check_configuration(application)
    assert check["status"] == "FAIL"
    assert "MODEL_PATH" in check["message"]


def test_default_secret_key_produces_warning(app):
    check = phs.check_configuration(app)
    # The testing config ships the development default, so this must warn.
    if check["details"]["secret_key_is_development_default"]:
        assert check["status"] == "WARN"


# ============================================================
# 12. NO SENSITIVE INFORMATION LEAKAGE
# ============================================================


SENSITIVE_MARKERS = ["/home/", "/root/", "C:\\", "password", "secret_key=", "api_key", "token="]


def test_health_response_contains_no_absolute_paths_or_secrets(client):
    raw = json.dumps(client.get("/api/health/platform").get_json()).lower()
    for marker in SENSITIVE_MARKERS:
        assert marker.lower() not in raw, f"health response leaked '{marker}'"


def test_health_response_never_echoes_secret_key_value(app, client):
    secret = app.config.get("SECRET_KEY")
    raw = json.dumps(client.get("/api/health/platform").get_json())
    assert secret not in raw


def test_health_response_has_no_stack_traces(client):
    raw = json.dumps(client.get("/api/health/platform").get_json())
    assert "Traceback" not in raw
    assert 'File "' not in raw


# ============================================================
# 13-14. DATASET INTEGRITY
# ============================================================


def test_dataset_integrity_check(app):
    check = phs.check_dataset_integrity(app.config["DATA_PATH"])
    assert check["status"] == "PASS"
    assert "integrity verified" in check["message"].lower()
    assert len(check["details"]["sha256"]) == 64
    assert check["details"]["rows"] > 0


def test_dataset_integrity_is_non_destructive(app):
    """Running the integrity check must not alter the file in any way."""
    path = app.config["DATA_PATH"]
    before_size = os.path.getsize(path)
    before_mtime = os.path.getmtime(path)

    first = phs.check_dataset_integrity(path)
    second = phs.check_dataset_integrity(path)

    assert os.path.getsize(path) == before_size
    assert os.path.getmtime(path) == before_mtime
    # Hash must be stable across runs.
    assert first["details"]["sha256"] == second["details"]["sha256"]


def test_dataset_integrity_missing_file():
    check = phs.check_dataset_integrity("/tmp/definitely_not_a_dataset.csv")
    assert check["status"] == "FAIL"


# ============================================================
# 15. EXISTING HEALTH ENDPOINT UNCHANGED
# ============================================================


def test_existing_health_endpoint_still_available(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "marketing-roi-intelligence-platform"


# ============================================================
# GOVERNANCE CONTENT
# ============================================================


def test_model_governance_statements_present(app):
    health = phs.get_platform_health(app)
    joined = " ".join(health["model_governance"]).lower()
    assert "does not establish causality" in joined
    assert "acquisition cost is a dominant predictive signal" in joined
    assert "estimates, not guaranteed outcomes" in joined


def test_analytical_guardrails_cover_all_evidence_types(app):
    health = phs.get_platform_health(app)
    joined = " ".join(health["analytical_guardrails"])
    for evidence in ("OBSERVED", "PREDICTIVE", "EXPERIMENTAL"):
        assert evidence in joined
    assert "never blended" in joined.lower()


def test_final_governance_statement_present(app):
    health = phs.get_platform_health(app)
    final = health["final_governance_statement"]
    assert final["title"] == "Decision-Support Platform"
    joined = " ".join(final["statements"]).lower()
    assert "does not establish causality" in joined
    assert "illustrative" in joined
    assert "support human decision-making" in joined


def test_health_never_claims_production_ready(client):
    raw = json.dumps(client.get("/api/health/platform").get_json()).lower()
    assert "100% production ready" not in raw
    assert "production ready" not in raw


# ============================================================
# REGRESSION — existing pages/APIs must still work
# ============================================================


@pytest.mark.parametrize(
    "path",
    [
        "/", "/campaign-analytics", "/marketing-intelligence", "/forecasting", "/statistics",
        "/ab-testing", "/roi-prediction", "/scenario-simulator", "/model-intelligence",
        "/business-insights", "/recommendations", "/executive-center", "/data-quality",
        "/budget-optimizer", "/copilot", "/platform-health",
    ],
)
def test_existing_pages_still_load(client, path):
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/health", "/api/summary", "/api/campaign-types", "/api/customer-segments",
        "/api/statistics", "/api/ab-test", "/api/model-info", "/api/model-comparison",
        "/api/model-intelligence", "/api/campaign-analytics/summary", "/api/recommendations",
        "/api/executive-summary", "/api/marketing-intelligence", "/api/forecasting",
        "/api/data-quality", "/api/budget-optimizer", "/api/copilot/capabilities",
        "/api/health/platform",
    ],
)
def test_existing_apis_still_work(client, path):
    assert client.get(path).status_code == 200
