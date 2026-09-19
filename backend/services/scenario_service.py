"""
Scenario simulator service layer (Phase 5).

This module does NOT load or train its own model. It reuses the
existing cached pipeline from backend.services.ml_service (the same
one /api/predict-roi uses) for every scenario prediction — so scenario
comparisons and budget sensitivity runs are just multiple calls into
the already-loaded early-stage Random Forest, never a retrain.
"""

import math
from typing import Optional

from backend.services import ml_service
from backend.services.ml_service import ModelUnavailableError  # re-exported for routes

DEFAULT_SENSITIVITY_BUDGETS = [250, 500, 750, 1000, 1500, 2000]
MAX_SCENARIOS = 8
MIN_SCENARIOS = 1
MAX_ACQUISITION_COST = 1_000_000


def _scenario_to_model_payload(scenario: dict) -> dict:
    """Map the scenario simulator's snake_case field names to the
    Title_Case field names ml_service/the trained pipeline expect.
    """
    return {
        "Campaign_Type": scenario.get("campaign_type"),
        "Target_Audience": scenario.get("target_audience"),
        "Duration": scenario.get("duration"),
        "Channel_Used": scenario.get("channel"),
        "Language": scenario.get("language"),
        "Customer_Segment": scenario.get("customer_segment"),
        "Acquisition_Cost": scenario.get("acquisition_cost"),
    }


def validate_scenarios_payload(payload: Optional[dict]) -> list:
    """Validate the POST /api/scenario/compare request body.
    Returns a list of error strings; empty list means valid.
    """
    errors = []

    if not isinstance(payload, dict):
        return ["Request body must be a JSON object."]

    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        return ["'scenarios' must be a list."]

    if len(scenarios) < MIN_SCENARIOS:
        return ["At least one scenario is required."]
    if len(scenarios) > MAX_SCENARIOS:
        return [f"No more than {MAX_SCENARIOS} scenarios can be compared at once."]

    for i, scenario in enumerate(scenarios):
        label = scenario.get("name", f"Scenario {i + 1}") if isinstance(scenario, dict) else f"Scenario {i + 1}"
        if not isinstance(scenario, dict):
            errors.append(f"{label}: must be an object.")
            continue

        model_payload = _scenario_to_model_payload(scenario)
        field_errors = ml_service.validate_prediction_input(model_payload)
        for fe in field_errors:
            errors.append(f"{label}: {fe}")

        cost = scenario.get("acquisition_cost")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost > MAX_ACQUISITION_COST:
            errors.append(f"{label}: 'acquisition_cost' must be {MAX_ACQUISITION_COST:,} or less.")

    return errors


def compare_scenarios(model_path: str, scenarios: list) -> dict:
    """Run every scenario through the existing cached model and return
    structured comparison results. Raises ModelUnavailableError if the
    model artifact hasn't been trained/loaded (propagated to the route).
    """
    results = []

    for i, scenario in enumerate(scenarios):
        name = scenario.get("name") or f"Scenario {chr(65 + i)}"
        model_payload = _scenario_to_model_payload(scenario)
        predicted_roi = ml_service.predict_roi(model_path, model_payload)
        acquisition_cost = float(scenario["acquisition_cost"])
        illustrative_estimated_profit = acquisition_cost * predicted_roi

        results.append(
            {
                "name": name,
                "predicted_roi": round(predicted_roi, 4),
                "acquisition_cost": round(acquisition_cost, 2),
                "illustrative_estimated_profit": round(illustrative_estimated_profit, 2),
                "inputs": {
                    "campaign_type": scenario.get("campaign_type"),
                    "target_audience": scenario.get("target_audience"),
                    "duration": scenario.get("duration"),
                    "channel": scenario.get("channel"),
                    "language": scenario.get("language"),
                    "customer_segment": scenario.get("customer_segment"),
                },
            }
        )

    best = max(results, key=lambda r: r["predicted_roi"]) if results else None

    return {
        "status": "success",
        "scenarios": results,
        "best_scenario": best["name"] if best else None,
    }


def run_budget_sensitivity(model_path: str, base_scenario: dict, budgets: Optional[list] = None) -> list:
    """Hold every planning variable constant except Acquisition_Cost,
    and run the existing model once per budget level. This is a
    model-based sensitivity sweep, not a claim that raising budget
    causes higher ROI.
    """
    budgets = budgets if budgets else DEFAULT_SENSITIVITY_BUDGETS
    results = []

    for budget in budgets:
        scenario = dict(base_scenario)
        scenario["acquisition_cost"] = budget
        model_payload = _scenario_to_model_payload(scenario)
        predicted_roi = ml_service.predict_roi(model_path, model_payload)
        illustrative_estimated_profit = float(budget) * predicted_roi

        results.append(
            {
                "acquisition_cost": budget,
                "predicted_roi": round(predicted_roi, 4),
                "illustrative_estimated_profit": round(illustrative_estimated_profit, 2),
            }
        )

    return results


def validate_sensitivity_payload(payload: Optional[dict]) -> list:
    errors = []
    if not isinstance(payload, dict):
        return ["Request body must be a JSON object."]

    scenario = payload.get("scenario")
    if not isinstance(scenario, dict):
        return ["'scenario' must be an object."]

    # Acquisition_Cost is swept by this endpoint, so validate the base
    # scenario using a placeholder cost if none was supplied.
    probe = dict(scenario)
    probe.setdefault("acquisition_cost", probe.get("acquisition_cost", 1))
    model_payload = _scenario_to_model_payload(probe)
    errors.extend(ml_service.validate_prediction_input(model_payload))

    budgets = payload.get("acquisition_costs")
    if budgets is not None:
        if not isinstance(budgets, list) or not budgets:
            errors.append("'acquisition_costs' must be a non-empty list of numbers.")
        else:
            for b in budgets:
                if not isinstance(b, (int, float)) or isinstance(b, bool) or b < 0:
                    errors.append("Each value in 'acquisition_costs' must be a non-negative number.")
                    break
                if b > MAX_ACQUISITION_COST:
                    errors.append(f"'acquisition_costs' values must be {MAX_ACQUISITION_COST:,} or less.")
                    break

    return errors
